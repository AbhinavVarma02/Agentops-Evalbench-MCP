"""Report exporters.

Turn the report dict produced by ``services.build_run_report`` into Markdown or
JSON, and optionally save it under ``data/reports/``. Kept as pure formatting so
the API, CLI, and MCP server can all reuse it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import PROJECT_ROOT

REPORTS_DIR = PROJECT_ROOT / "data" / "reports"


def render_json(report: dict) -> str:
    """Serialize a report dict to pretty JSON."""
    return json.dumps(report, indent=2, default=str)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _metric_rows(report: dict) -> list[str]:
    """Build the averages-vs-thresholds table rows with pass/fail marks."""
    run = report["run"]
    th = report["thresholds"]
    # (label, average value, threshold text, passed?)
    checks = [
        (
            "Groundedness",
            run["avg_groundedness"],
            f">= {th['min_groundedness']}",
            run["avg_groundedness"] is not None
            and run["avg_groundedness"] >= th["min_groundedness"],
        ),
        (
            "Hallucination risk",
            run["avg_hallucination_risk"],
            f"<= {th['max_hallucination_risk']}",
            run["avg_hallucination_risk"] is not None
            and run["avg_hallucination_risk"] <= th["max_hallucination_risk"],
        ),
        (
            "Answer relevance",
            run["avg_answer_relevance"],
            f">= {th['min_answer_relevance']}",
            run["avg_answer_relevance"] is not None
            and run["avg_answer_relevance"] >= th["min_answer_relevance"],
        ),
        (
            "Retrieval quality",
            run["avg_retrieval_score"],
            f">= {th['min_retrieval_score']}",
            run["avg_retrieval_score"] is not None
            and run["avg_retrieval_score"] >= th["min_retrieval_score"],
        ),
        (
            "Latency (s)",
            run["avg_latency_seconds"],
            f"<= {th['max_latency_seconds']}",
            run["avg_latency_seconds"] is not None
            and run["avg_latency_seconds"] <= th["max_latency_seconds"],
        ),
    ]
    rows = []
    for label, value, threshold, ok in checks:
        mark = "✅" if ok else "❌"
        rows.append(f"| {label} | {_fmt(value)} | {threshold} | {mark} |")
    return rows


def render_markdown(report: dict) -> str:
    """Render a human-readable Markdown report."""
    project = report["project"]
    run = report["run"]
    summary = report["summary"]

    lines: list[str] = []
    lines.append(f"# Evaluation Report — {project['name']}")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_")
    lines.append("")

    # Run configuration
    lines.append("## Run")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Run ID | {run['id']} |")
    lines.append(f"| Run name | {run['run_name']} |")
    lines.append(f"| Model | {run['model_name']} |")
    lines.append(f"| Prompt version | {run['prompt_version']} |")
    lines.append(f"| Status | {run['status']} |")
    lines.append(f"| Created | {run['created_at']} |")
    lines.append(f"| Estimated cost (USD) | {run['total_estimated_cost']} |")
    lines.append("")

    # Pass/fail summary
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"- **{summary['passed_cases']}/{summary['total_cases']} passed** "
        f"(pass rate {summary['pass_rate'] * 100:.1f}%)"
    )
    lines.append(f"- Failed cases: **{summary['failed_cases']}**")
    lines.append("")

    # Averages vs thresholds
    lines.append("## Metrics vs Thresholds")
    lines.append("")
    lines.append("| Metric | Average | Threshold | Status |")
    lines.append("|---|---|---|---|")
    lines.extend(_metric_rows(report))
    lines.append("")

    # Failed cases
    failed = report.get("failed_cases", [])
    lines.append(f"## Failed Cases ({len(failed)})")
    lines.append("")
    if not failed:
        lines.append("_None — every case passed._")
    else:
        for i, r in enumerate(failed, 1):
            lines.append(f"### {i}. {r['question']}")
            lines.append("")
            lines.append(f"- **Answer:** {r['generated_answer']}")
            lines.append(
                f"- **Scores:** grounded {_fmt(r['groundedness'])}, "
                f"halluc {_fmt(r['hallucination_risk'])}, "
                f"relevance {_fmt(r['answer_relevance'])}, "
                f"retrieval {_fmt(r['retrieval_score'])}, "
                f"latency {_fmt(r['latency_seconds'])}s"
            )
            lines.append(f"- **Why it failed:** {r['failure_reason']}")
            lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    for rec in report.get("recommendations", []):
        lines.append(f"- {rec}")
    lines.append("")

    return "\n".join(lines)


def render(report: dict, fmt: str = "markdown") -> str:
    """Render a report to the requested format string ('markdown' or 'json')."""
    fmt = (fmt or "markdown").lower()
    if fmt == "json":
        return render_json(report)
    if fmt in ("markdown", "md"):
        return render_markdown(report)
    raise ValueError(f"Unsupported report format: {fmt!r} (use 'markdown' or 'json')")


def save_report(report: dict, fmt: str = "markdown", out_dir: Path | None = None) -> Path:
    """Render and write a report file; returns the written path.

    Files are written under ``data/reports/`` by default. This is the only place
    reports are written — no arbitrary paths — which keeps the MCP export tool safe.
    """
    out_dir = out_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "json" if fmt.lower() == "json" else "md"
    run_id = report.get("run", {}).get("id", "unknown")
    filename = f"eval_report_run_{run_id}.{ext}"
    path = out_dir / filename
    path.write_text(render(report, fmt), encoding="utf-8")
    return path
