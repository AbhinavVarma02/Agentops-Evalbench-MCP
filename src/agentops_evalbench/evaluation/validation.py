"""Human-labeled validation for the automated evaluator.

The validation set is intentionally small and local: it measures whether the
offline custom evaluator agrees with manual labels for pass/fail,
groundedness, and hallucination detection.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import metrics

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VALIDATION_SET = PROJECT_ROOT / "data" / "sample_evals" / "evaluator_validation_set.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "reports"

REQUIRED_FIELDS = {
    "question",
    "context",
    "answer",
    "human_label_pass",
    "human_label_grounded",
    "human_label_hallucinated",
    "notes",
}


@dataclass(frozen=True)
class ValidationThresholds:
    """Thresholds mirroring the default evaluator gate, minus latency."""

    min_groundedness: float = 0.80
    max_hallucination_risk: float = 0.20
    min_retrieval_score: float = 0.75
    min_answer_relevance: float = 0.70

    def as_dict(self) -> dict[str, float]:
        return {
            "min_groundedness": self.min_groundedness,
            "max_hallucination_risk": self.max_hallucination_risk,
            "min_retrieval_score": self.min_retrieval_score,
            "min_answer_relevance": self.min_answer_relevance,
        }


def load_validation_examples(path: Path | str = DEFAULT_VALIDATION_SET) -> list[dict[str, Any]]:
    """Load and validate the human-labeled examples."""
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    examples = data.get("examples", data) if isinstance(data, dict) else data
    if not isinstance(examples, list):
        raise ValueError("Validation data must be a list or an object with an 'examples' list.")

    validated: list[dict[str, Any]] = []
    for index, example in enumerate(examples, 1):
        if not isinstance(example, dict):
            raise ValueError(f"Example {index} must be an object.")
        missing = sorted(REQUIRED_FIELDS - example.keys())
        if missing:
            raise ValueError(f"Example {index} is missing required field(s): {', '.join(missing)}")
        for field in (
            "human_label_pass",
            "human_label_grounded",
            "human_label_hallucinated",
        ):
            if not isinstance(example[field], bool):
                raise ValueError(f"Example {index} field {field!r} must be a boolean.")
        validated.append(dict(example))
    return validated


def _passes_thresholds(
    scores: metrics.MetricScores,
    thresholds: ValidationThresholds,
) -> bool:
    return (
        scores.groundedness >= thresholds.min_groundedness
        and scores.hallucination_risk <= thresholds.max_hallucination_risk
        and scores.retrieval_score >= thresholds.min_retrieval_score
        and scores.answer_relevance >= thresholds.min_answer_relevance
    )


def score_validation_example(
    example: dict[str, Any],
    index: int,
    thresholds: ValidationThresholds,
) -> dict[str, Any]:
    """Score one human-labeled example and attach automated labels."""
    scores = metrics.custom_scores(
        question=example["question"],
        answer=example["answer"],
        context=example["context"],
    )
    predicted_pass = _passes_thresholds(scores, thresholds)
    predicted_grounded = scores.groundedness >= thresholds.min_groundedness
    predicted_hallucinated = scores.hallucination_risk > thresholds.max_hallucination_risk

    return {
        "index": index,
        "id": example.get("id", f"case_{index:02d}"),
        "category": example.get("category", ""),
        "question": example["question"],
        "context": example["context"],
        "answer": example["answer"],
        "notes": example["notes"],
        "human_label_pass": example["human_label_pass"],
        "human_label_grounded": example["human_label_grounded"],
        "human_label_hallucinated": example["human_label_hallucinated"],
        "predicted_pass": predicted_pass,
        "predicted_grounded": predicted_grounded,
        "predicted_hallucinated": predicted_hallucinated,
        "scores": scores.as_dict(),
    }


def score_validation_examples(
    examples: list[dict[str, Any]],
    thresholds: ValidationThresholds | None = None,
) -> list[dict[str, Any]]:
    """Score all examples with the automated evaluator."""
    thresholds = thresholds or ValidationThresholds()
    return [
        score_validation_example(example, index, thresholds)
        for index, example in enumerate(examples, 1)
    ]


def _percentage(matches: int, total: int) -> float:
    return round((matches / total) * 100, 2) if total else 0.0


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def calculate_validation_metrics(records: list[dict[str, Any]]) -> dict[str, float | int]:
    """Calculate agreement and hallucination precision/recall/F1."""
    total = len(records)
    if total == 0:
        raise ValueError("At least one validation record is required.")

    pass_matches = sum(r["human_label_pass"] == r["predicted_pass"] for r in records)
    grounded_matches = sum(r["human_label_grounded"] == r["predicted_grounded"] for r in records)

    true_positive = sum(
        r["human_label_hallucinated"] and r["predicted_hallucinated"] for r in records
    )
    false_positive = sum(
        (not r["human_label_hallucinated"]) and r["predicted_hallucinated"] for r in records
    )
    false_negative = sum(
        r["human_label_hallucinated"] and (not r["predicted_hallucinated"]) for r in records
    )
    true_negative = sum(
        (not r["human_label_hallucinated"]) and (not r["predicted_hallucinated"]) for r in records
    )

    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = _ratio(2 * precision * recall, precision + recall)

    return {
        "total_examples": total,
        "pass_fail_agreement_pct": _percentage(pass_matches, total),
        "groundedness_agreement_pct": _percentage(grounded_matches, total),
        "hallucination_precision": precision,
        "hallucination_recall": recall,
        "hallucination_f1": f1,
        "hallucination_true_positives": true_positive,
        "hallucination_false_positives": false_positive,
        "hallucination_false_negatives": false_negative,
        "hallucination_true_negatives": true_negative,
    }


def build_validation_report(
    examples: list[dict[str, Any]],
    source_path: Path | str = DEFAULT_VALIDATION_SET,
    thresholds: ValidationThresholds | None = None,
) -> dict[str, Any]:
    """Build a serializable validation report."""
    thresholds = thresholds or ValidationThresholds()
    results = score_validation_examples(examples, thresholds)
    return {
        "name": "Evaluator Validation",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_path": str(Path(source_path)),
        "thresholds": thresholds.as_dict(),
        "summary": calculate_validation_metrics(results),
        "results": results,
    }


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def render_validation_markdown(report: dict[str, Any]) -> str:
    """Render the validation report as Markdown."""
    summary = report["summary"]
    thresholds = report["thresholds"]
    lines = [
        "# Evaluator Validation Report",
        "",
        f"_Generated {report['generated_at']}_",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Validation set size | {summary['total_examples']} |",
        f"| Pass/fail agreement | {summary['pass_fail_agreement_pct']:.2f}% |",
        f"| Groundedness agreement | {summary['groundedness_agreement_pct']:.2f}% |",
        f"| Hallucination precision | {summary['hallucination_precision']:.4f} |",
        f"| Hallucination recall | {summary['hallucination_recall']:.4f} |",
        f"| Hallucination F1 | {summary['hallucination_f1']:.4f} |",
        "",
        "## Hallucination Confusion Matrix",
        "",
        "| Count | Value |",
        "|---|---:|",
        f"| True positives | {summary['hallucination_true_positives']} |",
        f"| False positives | {summary['hallucination_false_positives']} |",
        f"| False negatives | {summary['hallucination_false_negatives']} |",
        f"| True negatives | {summary['hallucination_true_negatives']} |",
        "",
        "## Thresholds",
        "",
        "| Threshold | Value |",
        "|---|---:|",
    ]
    for name, value in thresholds.items():
        lines.append(f"| {name} | {value:.2f} |")

    lines.extend(
        [
            "",
            "## Per-Example Results",
            "",
            "| # | Category | Human pass | Pred pass | Human halluc | Pred halluc | Grounded | Halluc risk | Notes |",
            "|---:|---|---|---|---|---|---:|---:|---|",
        ]
    )
    for result in report["results"]:
        scores = result["scores"]
        lines.append(
            "| {index} | {category} | {human_pass} | {pred_pass} | {human_halluc} | "
            "{pred_halluc} | {grounded:.3f} | {halluc:.3f} | {notes} |".format(
                index=result["index"],
                category=result["category"],
                human_pass=_yes_no(result["human_label_pass"]),
                pred_pass=_yes_no(result["predicted_pass"]),
                human_halluc=_yes_no(result["human_label_hallucinated"]),
                pred_halluc=_yes_no(result["predicted_hallucinated"]),
                grounded=scores["groundedness"],
                halluc=scores["hallucination_risk"],
                notes=str(result["notes"]).replace("|", "/"),
            )
        )

    lines.append("")
    return "\n".join(lines)


def save_validation_report(report: dict[str, Any], output_dir: Path | str) -> dict[str, Path]:
    """Write Markdown and JSON validation reports."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = out_dir / "evaluator_validation_results.md"
    json_path = out_dir / "evaluator_validation_results.json"
    markdown_path.write_text(render_validation_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"markdown": markdown_path, "json": json_path}


def run_validation(
    input_path: Path | str = DEFAULT_VALIDATION_SET,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    thresholds: ValidationThresholds | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Load, score, summarize, and export the validation study."""
    examples = load_validation_examples(input_path)
    report = build_validation_report(examples, input_path, thresholds)
    paths = save_validation_report(report, output_dir)
    return report, paths


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for direct module execution."""
    parser = argparse.ArgumentParser(description="Run evaluator validation.")
    parser.add_argument("--input", type=Path, default=DEFAULT_VALIDATION_SET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report, paths = run_validation(input_path=args.input, output_dir=args.output_dir)
    summary = report["summary"]
    print(f"Validation set size: {summary['total_examples']}")
    print(f"Pass/fail agreement: {summary['pass_fail_agreement_pct']:.2f}%")
    print(f"Groundedness agreement: {summary['groundedness_agreement_pct']:.2f}%")
    print(f"Hallucination precision: {summary['hallucination_precision']:.4f}")
    print(f"Hallucination recall: {summary['hallucination_recall']:.4f}")
    print(f"Hallucination F1: {summary['hallucination_f1']:.4f}")
    print(f"Markdown report: {paths['markdown']}")
    print(f"JSON report: {paths['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
