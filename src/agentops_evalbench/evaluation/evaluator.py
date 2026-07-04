"""Evaluation orchestration and the deployment-readiness threshold logic.

This module is intentionally **persistence-agnostic**: it turns test cases into
scored results and aggregates, and returns plain dataclasses. The API, CLI, and
MCP server call it and handle their own database writes. That keeps the core
evaluation logic in one place and avoids duplication across interfaces.

Pass/fail rule (thresholds come from the environment via ``Settings``)::

    passed = groundedness       >= EVAL_MIN_GROUNDEDNESS
             and hallucination_risk <= EVAL_MAX_HALLUCINATION_RISK
             and retrieval_score    >= EVAL_MIN_RETRIEVAL_SCORE
             and answer_relevance   >= EVAL_MIN_ANSWER_RELEVANCE
             and latency_seconds    <= EVAL_MAX_LATENCY_SECONDS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings
from ..rag.document_loader import preview
from ..rag.rag_pipeline import RAGPipeline
from . import metrics
from .cost_tracker import estimate_cost


@dataclass
class EvalThresholds:
    """Deployment-readiness thresholds (loaded from settings by default)."""

    min_groundedness: float = 0.80
    max_hallucination_risk: float = 0.20
    min_retrieval_score: float = 0.75
    min_answer_relevance: float = 0.70
    max_latency_seconds: float = 5.0

    @classmethod
    def from_settings(cls) -> EvalThresholds:
        s = get_settings()
        return cls(
            min_groundedness=s.eval_min_groundedness,
            max_hallucination_risk=s.eval_max_hallucination_risk,
            min_retrieval_score=s.eval_min_retrieval_score,
            min_answer_relevance=s.eval_min_answer_relevance,
            max_latency_seconds=s.eval_max_latency_seconds,
        )


@dataclass
class EvaluatedResult:
    """One fully scored test case, ready to persist as an ``EvalResult`` row."""

    question: str
    generated_answer: str
    retrieved_context: str
    groundedness: float
    hallucination_risk: float
    answer_relevance: float
    retrieval_score: float
    latency_seconds: float
    token_usage: dict
    estimated_cost: float
    passed: bool
    failure_reason: str | None = None
    test_case_id: int | None = None


@dataclass
class TraceEntry:
    """A single observable pipeline step, ready to persist as a ``TraceLog`` row."""

    step_name: str
    input_summary: str
    output_summary: str
    metadata_json: dict


@dataclass
class RunEvaluation:
    """The full result of evaluating a test set."""

    results: list[EvaluatedResult]
    traces: list[TraceEntry]
    aggregate: dict
    model_name: str
    backend: str
    method: str = "custom"
    extras: dict = field(default_factory=dict)


def check_pass(
    groundedness: float,
    hallucination_risk: float,
    retrieval_score: float,
    answer_relevance: float,
    latency_seconds: float,
    thresholds: EvalThresholds,
) -> tuple[bool, str | None]:
    """Apply thresholds and return ``(passed, failure_reason)``.

    ``failure_reason`` is ``None`` on pass, or a human-readable list of every
    threshold that was violated (useful in the dashboard and reports).
    """
    reasons: list[str] = []
    if groundedness < thresholds.min_groundedness:
        reasons.append(f"groundedness {groundedness:.2f} < {thresholds.min_groundedness:.2f}")
    if hallucination_risk > thresholds.max_hallucination_risk:
        reasons.append(
            f"hallucination_risk {hallucination_risk:.2f} > {thresholds.max_hallucination_risk:.2f}"
        )
    if retrieval_score < thresholds.min_retrieval_score:
        reasons.append(
            f"retrieval_score {retrieval_score:.2f} < {thresholds.min_retrieval_score:.2f}"
        )
    if answer_relevance < thresholds.min_answer_relevance:
        reasons.append(
            f"answer_relevance {answer_relevance:.2f} < {thresholds.min_answer_relevance:.2f}"
        )
    if latency_seconds > thresholds.max_latency_seconds:
        reasons.append(f"latency {latency_seconds:.2f}s > {thresholds.max_latency_seconds:.2f}s")

    passed = not reasons
    return passed, None if passed else "; ".join(reasons)


def _tc_field(test_case: Any, name: str) -> Any:
    """Read ``name`` from a test case that may be a dict or an ORM object."""
    if isinstance(test_case, dict):
        return test_case.get(name)
    return getattr(test_case, name, None)


def evaluate_single(
    question: str,
    generated_answer: str,
    retrieved_context: str,
    latency_seconds: float,
    token_usage: dict,
    model_name: str,
    expected_answer: str | None = None,
    thresholds: EvalThresholds | None = None,
    use_llm_judge: bool = False,
    test_case_id: int | None = None,
) -> EvaluatedResult:
    """Score one answer and apply the pass/fail thresholds."""
    thresholds = thresholds or EvalThresholds.from_settings()
    scores = metrics.score_answer(
        question=question,
        answer=generated_answer,
        context=retrieved_context,
        expected_answer=expected_answer,
        use_llm_judge=use_llm_judge,
        model=model_name,
    )
    cost = estimate_cost(token_usage, model_name)
    passed, reason = check_pass(
        groundedness=scores.groundedness,
        hallucination_risk=scores.hallucination_risk,
        retrieval_score=scores.retrieval_score,
        answer_relevance=scores.answer_relevance,
        latency_seconds=latency_seconds,
        thresholds=thresholds,
    )
    return EvaluatedResult(
        question=question,
        generated_answer=generated_answer,
        retrieved_context=retrieved_context,
        groundedness=scores.groundedness,
        hallucination_risk=scores.hallucination_risk,
        answer_relevance=scores.answer_relevance,
        retrieval_score=scores.retrieval_score,
        latency_seconds=round(latency_seconds, 4),
        token_usage=token_usage,
        estimated_cost=cost,
        passed=passed,
        failure_reason=reason,
        test_case_id=test_case_id,
    )


def aggregate_results(results: list[EvaluatedResult]) -> dict:
    """Roll up per-case results into run-level averages and pass/fail counts."""
    n = len(results)
    if n == 0:
        return {
            "total_cases": 0,
            "passed_cases": 0,
            "failed_cases": 0,
            "avg_groundedness": None,
            "avg_hallucination_risk": None,
            "avg_answer_relevance": None,
            "avg_retrieval_score": None,
            "avg_latency_seconds": None,
            "total_estimated_cost": 0.0,
        }

    def _avg(attr: str) -> float:
        return round(sum(getattr(r, attr) for r in results) / n, 4)

    passed = sum(1 for r in results if r.passed)
    return {
        "total_cases": n,
        "passed_cases": passed,
        "failed_cases": n - passed,
        "avg_groundedness": _avg("groundedness"),
        "avg_hallucination_risk": _avg("hallucination_risk"),
        "avg_answer_relevance": _avg("answer_relevance"),
        "avg_retrieval_score": _avg("retrieval_score"),
        "avg_latency_seconds": _avg("latency_seconds"),
        "total_estimated_cost": round(sum(r.estimated_cost for r in results), 8),
    }


def run_evaluation(
    test_cases: list[Any],
    pipeline: RAGPipeline | None = None,
    prompt_version: str = "v1",
    model_name: str | None = None,
    use_llm_judge: bool = False,
    thresholds: EvalThresholds | None = None,
    docs_directory: str | None = None,
) -> RunEvaluation:
    """Run the RAG pipeline over ``test_cases`` and score every answer.

    ``test_cases`` may be dicts or ORM ``TestCase`` objects (each needs a
    ``question`` and optionally ``expected_answer``). A pipeline is built from
    the sample docs when one is not supplied.
    """
    thresholds = thresholds or EvalThresholds.from_settings()
    if pipeline is None:
        if docs_directory:
            pipeline = RAGPipeline.from_directory(docs_directory, model_name=model_name)
        else:
            pipeline = RAGPipeline.from_sample_docs(model_name=model_name)

    results: list[EvaluatedResult] = []
    traces: list[TraceEntry] = []
    method = "llm" if use_llm_judge and get_settings().has_openai_key else "custom"

    for tc in test_cases:
        question = _tc_field(tc, "question")
        expected = _tc_field(tc, "expected_answer")
        tc_id = _tc_field(tc, "id")

        rag = pipeline.answer(question, prompt_version=prompt_version)
        result = evaluate_single(
            question=question,
            generated_answer=rag.generated_answer,
            retrieved_context=rag.context_text,
            latency_seconds=rag.latency_seconds,
            token_usage=rag.token_usage,
            model_name=rag.model_name,
            expected_answer=expected,
            thresholds=thresholds,
            use_llm_judge=use_llm_judge,
            test_case_id=tc_id,
        )
        results.append(result)

        # One compact trace per case for observability in the dashboard.
        traces.append(
            TraceEntry(
                step_name="rag_answer",
                input_summary=preview(question, 200),
                output_summary=preview(rag.generated_answer, 200),
                metadata_json={
                    "retrieved_chunks": len(rag.retrieved_context),
                    "latency_seconds": round(rag.latency_seconds, 4),
                    "tokens": rag.token_usage.get("total", 0),
                    "used_openai": rag.used_openai,
                    "backend": pipeline.vector_store.backend,
                    "passed": result.passed,
                },
            )
        )

    aggregate = aggregate_results(results)
    traces.append(
        TraceEntry(
            step_name="evaluation_summary",
            input_summary=f"{aggregate['total_cases']} test cases",
            output_summary=f"{aggregate['passed_cases']} passed / {aggregate['failed_cases']} failed",
            metadata_json=aggregate,
        )
    )

    return RunEvaluation(
        results=results,
        traces=traces,
        aggregate=aggregate,
        model_name=pipeline.model_name,
        backend=pipeline.vector_store.backend,
        method=method,
    )
