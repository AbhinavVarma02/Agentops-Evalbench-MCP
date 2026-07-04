"""Tests for the threshold gate and the offline run orchestration."""

from agentops_evalbench.evaluation.evaluator import (
    EvalThresholds,
    aggregate_results,
    check_pass,
    evaluate_single,
    run_evaluation,
)

THRESHOLDS = EvalThresholds()  # defaults: 0.80 / 0.20 / 0.75 / 0.70 / 5.0s


def test_check_pass_all_good():
    passed, reason = check_pass(0.9, 0.1, 0.9, 0.9, 1.0, THRESHOLDS)
    assert passed
    assert reason is None


def test_check_pass_reports_every_violation():
    passed, reason = check_pass(0.5, 0.5, 0.5, 0.5, 9.0, THRESHOLDS)
    assert not passed
    for token in (
        "groundedness",
        "hallucination_risk",
        "retrieval_score",
        "answer_relevance",
        "latency",
    ):
        assert token in reason


def test_latency_alone_can_fail_a_result():
    result = evaluate_single(
        question="q",
        generated_answer="Groundedness must be at least 0.80.",
        retrieved_context="Groundedness must be at least 0.80.",
        latency_seconds=99.0,  # exceeds the 5s threshold
        token_usage={"prompt": 10, "completion": 5, "total": 15},
        model_name="gpt-4o-mini",
        thresholds=THRESHOLDS,
    )
    assert not result.passed
    assert "latency" in result.failure_reason


def test_run_evaluation_offline_over_sample_cases():
    test_cases = [
        {"question": "What is the minimum groundedness?", "expected_answer": "0.80"},
        {"question": "What is the default production model?", "expected_answer": "gpt-4o-mini"},
    ]
    run = run_evaluation(test_cases)  # builds a pipeline from the sample docs
    assert run.method == "custom"  # no OpenAI key in tests
    assert run.aggregate["total_cases"] == 2
    assert len(run.results) == 2
    # A per-case trace plus the run-level summary trace.
    assert run.traces[-1].step_name == "evaluation_summary"


def test_aggregate_of_empty_results():
    agg = aggregate_results([])
    assert agg["total_cases"] == 0
    assert agg["total_estimated_cost"] == 0.0
