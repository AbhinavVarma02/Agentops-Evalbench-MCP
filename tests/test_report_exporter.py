"""Tests for the report exporter (Markdown / JSON rendering + saving)."""

import json

import pytest

from agentops_evalbench.reports import exporter


@pytest.fixture
def sample_report() -> dict:
    return {
        "project": {"id": 1, "name": "Demo", "description": None},
        "run": {
            "id": 7,
            "run_name": "baseline",
            "model_name": "gpt-4o-mini",
            "prompt_version": "v1",
            "status": "completed",
            "created_at": "2026-07-04T00:00:00",
            "avg_groundedness": 0.9,
            "avg_hallucination_risk": 0.1,
            "avg_answer_relevance": 0.8,
            "avg_retrieval_score": 0.85,
            "avg_latency_seconds": 1.2,
            "total_estimated_cost": 0.0012,
        },
        "summary": {"total_cases": 4, "passed_cases": 3, "failed_cases": 1, "pass_rate": 0.75},
        "thresholds": {
            "min_groundedness": 0.8,
            "max_hallucination_risk": 0.2,
            "min_retrieval_score": 0.75,
            "min_answer_relevance": 0.7,
            "max_latency_seconds": 5.0,
        },
        "results": [],
        "failed_cases": [
            {
                "question": "Why did it fail?",
                "generated_answer": "some answer",
                "groundedness": 0.5,
                "hallucination_risk": 0.5,
                "answer_relevance": 0.4,
                "retrieval_score": 0.6,
                "latency_seconds": 0.3,
                "estimated_cost": 0.0001,
                "passed": False,
                "failure_reason": "groundedness 0.50 < 0.80",
            }
        ],
        "recommendations": ["Review the failed case."],
    }


def test_render_markdown_has_all_sections(sample_report):
    md = exporter.render_markdown(sample_report)
    for section in (
        "# Evaluation Report",
        "## Run",
        "## Summary",
        "## Metrics vs Thresholds",
        "## Failed Cases",
        "## Recommendations",
    ):
        assert section in md
    # Threshold marks are present.
    assert "✅" in md
    assert "Why did it fail?" in md


def test_render_json_round_trips(sample_report):
    data = json.loads(exporter.render_json(sample_report))
    assert data["run"]["id"] == 7
    assert data["summary"]["failed_cases"] == 1


def test_render_rejects_unknown_format(sample_report):
    with pytest.raises(ValueError):
        exporter.render(sample_report, "pdf")


def test_save_report_writes_file(sample_report, tmp_path):
    path = exporter.save_report(sample_report, "markdown", out_dir=tmp_path)
    assert path.exists()
    assert path.suffix == ".md"
    assert "Evaluation Report" in path.read_text(encoding="utf-8")

    json_path = exporter.save_report(sample_report, "json", out_dir=tmp_path)
    assert json_path.suffix == ".json"
    assert json.loads(json_path.read_text(encoding="utf-8"))["run"]["id"] == 7
