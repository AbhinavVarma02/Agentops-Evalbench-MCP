"""Service layer: the single source of truth for persistence + orchestration.

Every interface (FastAPI, CLI, MCP) calls these functions instead of re-writing
database or evaluation logic. Functions take an open SQLAlchemy ``Session`` so the
caller owns the transaction boundary (FastAPI via ``get_db``; CLI/MCP via
``SessionLocal``).

This module ties together:
* ``models``      — persistence,
* ``evaluator``   — scoring + thresholds,
* ``document_loader`` — sample content,
so a run goes: create EvalRun -> evaluate test cases -> store results/traces ->
update rolled-up averages.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import PROJECT_ROOT, get_settings
from .evaluation.evaluator import EvalThresholds, run_evaluation
from .models import Document, EvalResult, EvalRun, Project, TestCase, TraceLog
from .rag import document_loader

SAMPLE_TESTSET_PATH = PROJECT_ROOT / "data" / "sample_evals" / "sample_testset.json"

# Metrics used by run comparison, with the direction that counts as "better".
# True  -> higher is better (groundedness, relevance, retrieval)
# False -> lower is better  (hallucination risk, latency, cost)
_COMPARE_METRICS: list[tuple[str, bool]] = [
    ("avg_groundedness", True),
    ("avg_answer_relevance", True),
    ("avg_retrieval_score", True),
    ("avg_hallucination_risk", False),
    ("avg_latency_seconds", False),
    ("total_estimated_cost", False),
]


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
def create_project(db: Session, name: str, description: str | None = None) -> Project:
    project = Project(name=name, description=description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.id)))


def get_project(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #
def load_sample_documents(db: Session, project_id: int) -> tuple[list[Document], int]:
    """Register the bundled sample docs as ``Document`` rows for a project.

    Returns the created documents and the number of chunks they produce (the
    same chunks the RAG pipeline indexes at run time).
    """
    docs = document_loader.load_documents()
    created: list[Document] = []
    for d in docs:
        row = Document(
            project_id=project_id,
            filename=d.filename,
            source_type=d.source_type,
            content_preview=document_loader.preview(d.text),
        )
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    chunk_count = len(document_loader.load_and_chunk())
    return created, chunk_count


def list_documents(db: Session, project_id: int) -> list[Document]:
    return list(
        db.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.id))
    )


# --------------------------------------------------------------------------- #
# Test cases
# --------------------------------------------------------------------------- #
def add_test_case(
    db: Session,
    project_id: int,
    question: str,
    expected_answer: str | None = None,
    ground_truth_context: str | None = None,
) -> TestCase:
    tc = TestCase(
        project_id=project_id,
        question=question,
        expected_answer=expected_answer,
        ground_truth_context=ground_truth_context,
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return tc


def import_sample_test_cases(db: Session, project_id: int) -> list[TestCase]:
    """Load ``sample_testset.json`` into ``TestCase`` rows for quick demos."""
    import json

    if not SAMPLE_TESTSET_PATH.exists():
        return []
    data = json.loads(SAMPLE_TESTSET_PATH.read_text(encoding="utf-8"))
    created: list[TestCase] = []
    for tc in data.get("test_cases", []):
        created.append(
            add_test_case(
                db,
                project_id=project_id,
                question=tc["question"],
                expected_answer=tc.get("expected_answer"),
                ground_truth_context=tc.get("ground_truth_context"),
            )
        )
    return created


def list_test_cases(db: Session, project_id: int) -> list[TestCase]:
    return list(
        db.scalars(select(TestCase).where(TestCase.project_id == project_id).order_by(TestCase.id))
    )


# --------------------------------------------------------------------------- #
# Evaluation runs
# --------------------------------------------------------------------------- #
def create_and_run_eval(
    db: Session,
    project_id: int,
    run_name: str,
    model_name: str | None = None,
    prompt_version: str = "v1",
    test_case_ids: list[int] | None = None,
    use_llm_judge: bool = False,
    docs_directory: str | None = None,
) -> EvalRun:
    """Create an ``EvalRun``, evaluate the project's test cases, and persist all.

    Steps: create run (status running) -> run the RAG+evaluation pipeline over the
    selected test cases -> store each ``EvalResult`` + ``TraceLog`` -> write the
    rolled-up averages back onto the run (status completed).
    """
    settings = get_settings()
    model = model_name or settings.default_model

    # Select test cases (a subset by id, or all for the project).
    test_cases = list_test_cases(db, project_id)
    if test_case_ids:
        wanted = set(test_case_ids)
        test_cases = [tc for tc in test_cases if tc.id in wanted]

    run = EvalRun(
        project_id=project_id,
        run_name=run_name,
        model_name=model,
        prompt_version=prompt_version,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if not test_cases:
        run.status = "completed"
        db.commit()
        db.refresh(run)
        return run

    # Evaluate (persistence-agnostic core logic).
    evaluation = run_evaluation(
        test_cases=test_cases,
        prompt_version=prompt_version,
        model_name=model,
        use_llm_judge=use_llm_judge,
        docs_directory=docs_directory,
    )

    # Persist per-case results.
    for r in evaluation.results:
        db.add(
            EvalResult(
                eval_run_id=run.id,
                test_case_id=r.test_case_id,
                question=r.question,
                generated_answer=r.generated_answer,
                retrieved_context=r.retrieved_context,
                groundedness=r.groundedness,
                hallucination_risk=r.hallucination_risk,
                answer_relevance=r.answer_relevance,
                retrieval_score=r.retrieval_score,
                latency_seconds=r.latency_seconds,
                token_usage=r.token_usage,
                estimated_cost=r.estimated_cost,
                passed=r.passed,
                failure_reason=r.failure_reason,
            )
        )

    # Persist trace logs.
    for t in evaluation.traces:
        db.add(
            TraceLog(
                eval_run_id=run.id,
                step_name=t.step_name,
                input_summary=t.input_summary,
                output_summary=t.output_summary,
                metadata_json=t.metadata_json,
            )
        )

    # Roll up averages onto the run.
    agg = evaluation.aggregate
    run.avg_groundedness = agg["avg_groundedness"]
    run.avg_hallucination_risk = agg["avg_hallucination_risk"]
    run.avg_answer_relevance = agg["avg_answer_relevance"]
    run.avg_retrieval_score = agg["avg_retrieval_score"]
    run.avg_latency_seconds = agg["avg_latency_seconds"]
    run.total_estimated_cost = agg["total_estimated_cost"]
    run.status = "completed"

    db.commit()
    db.refresh(run)
    return run


def get_eval_run(db: Session, run_id: int) -> EvalRun | None:
    return db.get(EvalRun, run_id)


def list_eval_runs(db: Session, project_id: int | None = None) -> list[EvalRun]:
    stmt = select(EvalRun).order_by(EvalRun.id.desc())
    if project_id is not None:
        stmt = stmt.where(EvalRun.project_id == project_id)
    return list(db.scalars(stmt))


def list_results(db: Session, run_id: int) -> list[EvalResult]:
    return list(
        db.scalars(
            select(EvalResult).where(EvalResult.eval_run_id == run_id).order_by(EvalResult.id)
        )
    )


def get_failed_cases(db: Session, run_id: int) -> list[EvalResult]:
    return list(
        db.scalars(
            select(EvalResult)
            .where(EvalResult.eval_run_id == run_id, EvalResult.passed.is_(False))
            .order_by(EvalResult.id)
        )
    )


def list_traces(db: Session, run_id: int) -> list[TraceLog]:
    return list(
        db.scalars(select(TraceLog).where(TraceLog.eval_run_id == run_id).order_by(TraceLog.id))
    )


def run_counts(db: Session, run_id: int) -> tuple[int, int, int]:
    """Return ``(total, passed, failed)`` result counts for a run."""
    results = list_results(db, run_id)
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return total, passed, total - passed


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
def compare_runs(db: Session, baseline_run_id: int, candidate_run_id: int) -> dict:
    """Compare two runs metric-by-metric and summarize improvements/regressions."""
    baseline = get_eval_run(db, baseline_run_id)
    candidate = get_eval_run(db, candidate_run_id)
    if baseline is None or candidate is None:
        missing = baseline_run_id if baseline is None else candidate_run_id
        raise ValueError(f"Run {missing} not found")

    deltas = []
    improved_count = 0
    comparable = 0
    for metric, higher_better in _COMPARE_METRICS:
        b = getattr(baseline, metric)
        c = getattr(candidate, metric)
        if b is None or c is None:
            deltas.append(
                {"metric": metric, "baseline": b, "candidate": c, "delta": None, "improved": None}
            )
            continue
        delta = round(c - b, 6)
        improved = (delta > 0) if higher_better else (delta < 0)
        if delta != 0:
            comparable += 1
            improved_count += int(improved)
        deltas.append(
            {"metric": metric, "baseline": b, "candidate": c, "delta": delta, "improved": improved}
        )

    summary = (
        f"Candidate run #{candidate_run_id} improved on {improved_count}/{comparable} "
        f"changed metrics vs baseline run #{baseline_run_id}."
        if comparable
        else "Runs are identical on all comparable metrics."
    )
    return {
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        "summary": summary,
        "deltas": deltas,
    }


# --------------------------------------------------------------------------- #
# Report data assembly (formatting lives in reports/exporter.py)
# --------------------------------------------------------------------------- #
def _recommendations(
    run: EvalRun, thresholds: EvalThresholds, failed: int, total: int
) -> list[str]:
    """Generate simple, actionable recommendations from the run's averages."""
    recs: list[str] = []
    if run.avg_groundedness is not None and run.avg_groundedness < thresholds.min_groundedness:
        recs.append(
            "Groundedness is below threshold — tighten the prompt to answer only from context "
            "and improve retrieval coverage."
        )
    if (
        run.avg_hallucination_risk is not None
        and run.avg_hallucination_risk > thresholds.max_hallucination_risk
    ):
        recs.append(
            "Hallucination risk is above threshold — instruct the model to refuse when context "
            "is insufficient."
        )
    if (
        run.avg_retrieval_score is not None
        and run.avg_retrieval_score < thresholds.min_retrieval_score
    ):
        recs.append(
            "Retrieval quality is low — revisit chunk size/overlap or increase the number of "
            "retrieved chunks (top_k)."
        )
    if (
        run.avg_answer_relevance is not None
        and run.avg_answer_relevance < thresholds.min_answer_relevance
    ):
        recs.append("Answer relevance is low — ensure answers directly address the question asked.")
    if (
        run.avg_latency_seconds is not None
        and run.avg_latency_seconds > thresholds.max_latency_seconds
    ):
        recs.append("Latency exceeds the threshold — consider a smaller/faster model or caching.")
    if not recs:
        # No average-level threshold was violated.
        if total and failed:
            recs.append(
                f"Averages meet thresholds, but {failed} case(s) failed individually — "
                "review them before promoting."
            )
        else:
            recs.append("All averages meet thresholds. Safe to promote this configuration.")
    elif total and failed:
        recs.append(f"Also review the {failed} failed case(s) individually before deploying.")
    return recs


def build_run_report(db: Session, run_id: int) -> dict:
    """Assemble a serializable report dict for a run (used by every exporter)."""
    run = get_eval_run(db, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")
    project = get_project(db, run.project_id)
    results = list_results(db, run_id)
    thresholds = EvalThresholds.from_settings()
    total, passed, failed = len(results), sum(1 for r in results if r.passed), 0
    failed = total - passed
    pass_rate = round(passed / total, 4) if total else 0.0

    def _result_dict(r: EvalResult) -> dict:
        return {
            "test_case_id": r.test_case_id,
            "question": r.question,
            "generated_answer": r.generated_answer,
            "groundedness": r.groundedness,
            "hallucination_risk": r.hallucination_risk,
            "answer_relevance": r.answer_relevance,
            "retrieval_score": r.retrieval_score,
            "latency_seconds": r.latency_seconds,
            "estimated_cost": r.estimated_cost,
            "passed": r.passed,
            "failure_reason": r.failure_reason,
        }

    return {
        "project": {
            "id": project.id if project else run.project_id,
            "name": project.name if project else "(unknown)",
            "description": project.description if project else None,
        },
        "run": {
            "id": run.id,
            "run_name": run.run_name,
            "model_name": run.model_name,
            "prompt_version": run.prompt_version,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "avg_groundedness": run.avg_groundedness,
            "avg_hallucination_risk": run.avg_hallucination_risk,
            "avg_answer_relevance": run.avg_answer_relevance,
            "avg_retrieval_score": run.avg_retrieval_score,
            "avg_latency_seconds": run.avg_latency_seconds,
            "total_estimated_cost": run.total_estimated_cost,
        },
        "summary": {
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": failed,
            "pass_rate": pass_rate,
        },
        "thresholds": {
            "min_groundedness": thresholds.min_groundedness,
            "max_hallucination_risk": thresholds.max_hallucination_risk,
            "min_retrieval_score": thresholds.min_retrieval_score,
            "min_answer_relevance": thresholds.min_answer_relevance,
            "max_latency_seconds": thresholds.max_latency_seconds,
        },
        "results": [_result_dict(r) for r in results],
        "failed_cases": [_result_dict(r) for r in results if not r.passed],
        "recommendations": _recommendations(run, thresholds, failed, total),
    }
