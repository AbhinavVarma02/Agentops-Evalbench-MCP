"""Tests for evaluator validation metrics and report export."""

import json

import pytest

from agentops_evalbench.evaluation.validation import (
    REQUIRED_FIELDS,
    calculate_validation_metrics,
    load_validation_examples,
    run_validation,
)


def test_validation_set_has_40_required_examples():
    examples = load_validation_examples()
    assert len(examples) == 40
    for example in examples:
        assert REQUIRED_FIELDS <= example.keys()


def test_calculate_validation_metrics_confusion_counts():
    records = [
        {
            "human_label_pass": True,
            "predicted_pass": True,
            "human_label_grounded": True,
            "predicted_grounded": True,
            "human_label_hallucinated": True,
            "predicted_hallucinated": True,
        },
        {
            "human_label_pass": True,
            "predicted_pass": False,
            "human_label_grounded": True,
            "predicted_grounded": False,
            "human_label_hallucinated": True,
            "predicted_hallucinated": False,
        },
        {
            "human_label_pass": False,
            "predicted_pass": False,
            "human_label_grounded": False,
            "predicted_grounded": False,
            "human_label_hallucinated": False,
            "predicted_hallucinated": True,
        },
        {
            "human_label_pass": False,
            "predicted_pass": True,
            "human_label_grounded": False,
            "predicted_grounded": True,
            "human_label_hallucinated": False,
            "predicted_hallucinated": False,
        },
    ]

    summary = calculate_validation_metrics(records)

    assert summary["pass_fail_agreement_pct"] == 50.0
    assert summary["groundedness_agreement_pct"] == 50.0
    assert summary["hallucination_precision"] == 0.5
    assert summary["hallucination_recall"] == 0.5
    assert summary["hallucination_f1"] == 0.5
    assert summary["hallucination_true_positives"] == 1
    assert summary["hallucination_false_positives"] == 1
    assert summary["hallucination_false_negatives"] == 1
    assert summary["hallucination_true_negatives"] == 1


def test_calculate_validation_metrics_handles_no_predicted_hallucinations():
    records = [
        {
            "human_label_pass": False,
            "predicted_pass": False,
            "human_label_grounded": False,
            "predicted_grounded": False,
            "human_label_hallucinated": True,
            "predicted_hallucinated": False,
        }
    ]

    summary = calculate_validation_metrics(records)

    assert summary["hallucination_precision"] == 0.0
    assert summary["hallucination_recall"] == 0.0
    assert summary["hallucination_f1"] == 0.0


def test_calculate_validation_metrics_rejects_empty_records():
    with pytest.raises(ValueError, match="At least one"):
        calculate_validation_metrics([])


def test_run_validation_exports_markdown_and_json(tmp_path):
    report, paths = run_validation(output_dir=tmp_path)

    assert report["summary"]["total_examples"] == 40
    assert paths["markdown"].exists()
    assert paths["json"].exists()
    assert "Evaluator Validation Report" in paths["markdown"].read_text(encoding="utf-8")
    exported = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert exported["summary"] == report["summary"]
