"""MCP server exposing AgentOps EvalBench evaluation tools.

Run it directly::

    python -m agentops_evalbench.mcp_server.server

Register it with an MCP client (e.g. Claude Desktop / Cursor / VS Code)::

    {
      "mcpServers": {
        "agentops-evalbench": {
          "command": "python",
          "args": ["-m", "agentops_evalbench.mcp_server.server"]
        }
      }
    }

Safety boundaries (by design):
* Tools call the shared ``services`` / ``metrics`` core — no duplicated logic.
* No shell execution, no file deletion, no arbitrary file writes.
* Reports are written ONLY under ``data/reports/`` (via ``exporter.save_report``).
* No access to secrets or ``.env`` — configuration is read through the normal
  ``Settings`` object, and no tool ever returns API keys.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .. import services
from ..database import session_scope
from ..evaluation.evaluator import EvalThresholds, check_pass
from ..evaluation.metrics import score_answer as _score_answer
from ..reports import exporter

mcp = FastMCP("agentops-evalbench")


# --------------------------------------------------------------------------- #
# Serialization helpers (plain JSON-friendly dicts)
# --------------------------------------------------------------------------- #
def _run_summary(run) -> dict:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "run_name": run.run_name,
        "model_name": run.model_name,
        "prompt_version": run.prompt_version,
        "status": run.status,
        "avg_groundedness": run.avg_groundedness,
        "avg_hallucination_risk": run.avg_hallucination_risk,
        "avg_answer_relevance": run.avg_answer_relevance,
        "avg_retrieval_score": run.avg_retrieval_score,
        "avg_latency_seconds": run.avg_latency_seconds,
        "total_estimated_cost": run.total_estimated_cost,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _result_summary(r) -> dict:
    return {
        "id": r.id,
        "question": r.question,
        "generated_answer": r.generated_answer,
        "groundedness": r.groundedness,
        "hallucination_risk": r.hallucination_risk,
        "answer_relevance": r.answer_relevance,
        "retrieval_score": r.retrieval_score,
        "latency_seconds": r.latency_seconds,
        "passed": r.passed,
        "failure_reason": r.failure_reason,
    }


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def run_eval(project_id: int, run_name: str = "mcp-run", prompt_version: str = "v1") -> dict:
    """Run an evaluation over a project's test cases and store the results.

    Returns the run summary (id, averaged metrics, pass/fail counts). Requires a
    project that already has test cases (use the dashboard/CLI to create them, or
    the CLI ``init`` command to seed the demo project).
    """
    with session_scope() as db:
        if services.get_project(db, project_id) is None:
            return {"error": f"Project {project_id} not found"}
        run = services.create_and_run_eval(
            db, project_id=project_id, run_name=run_name, prompt_version=prompt_version
        )
        total, passed, failed = services.run_counts(db, run.id)
        summary = _run_summary(run)
        summary.update({"total_cases": total, "passed_cases": passed, "failed_cases": failed})
        return summary


@mcp.tool()
def score_answer(
    question: str, answer: str, context: str, expected_answer: str | None = None
) -> dict:
    """Score a single (question, answer, context) triple without persisting it.

    Returns groundedness, hallucination risk, answer relevance, retrieval quality,
    and a pass/fail decision against the configured thresholds (latency is not
    applicable to ad-hoc scoring).
    """
    scores = _score_answer(question, answer, context, expected_answer)
    thresholds = EvalThresholds.from_settings()
    passed, reason = check_pass(
        groundedness=scores.groundedness,
        hallucination_risk=scores.hallucination_risk,
        retrieval_score=scores.retrieval_score,
        answer_relevance=scores.answer_relevance,
        latency_seconds=0.0,
        thresholds=thresholds,
    )
    return {**scores.as_dict(), "passed": passed, "failure_reason": reason}


@mcp.tool()
def compare_runs(baseline_run_id: int, candidate_run_id: int) -> dict:
    """Compare two evaluation runs metric-by-metric (improvements vs regressions)."""
    with session_scope() as db:
        try:
            return services.compare_runs(db, baseline_run_id, candidate_run_id)
        except ValueError as exc:
            return {"error": str(exc)}


@mcp.tool()
def export_report(run_id: int, format: str = "markdown") -> dict:
    """Export a run's report to ``data/reports/`` and return its path + content.

    ``format`` is 'markdown' or 'json'. Files are written only under the project's
    reports directory — no arbitrary paths.
    """
    fmt = format.lower()
    if fmt not in ("markdown", "md", "json"):
        return {"error": "format must be 'markdown' or 'json'"}
    with session_scope() as db:
        try:
            report = services.build_run_report(db, run_id)
        except ValueError as exc:
            return {"error": str(exc)}
    path = exporter.save_report(report, fmt)
    return {
        "run_id": run_id,
        "format": fmt,
        "saved_path": str(path),
        "content": exporter.render(report, fmt),
    }


@mcp.tool()
def list_eval_runs(project_id: int) -> list[dict]:
    """List all evaluation runs for a project (newest first)."""
    with session_scope() as db:
        return [_run_summary(r) for r in services.list_eval_runs(db, project_id)]


@mcp.tool()
def get_failed_cases(run_id: int) -> list[dict]:
    """Return the failed cases for a run, each with its failure reason."""
    with session_scope() as db:
        if services.get_eval_run(db, run_id) is None:
            return [{"error": f"Run {run_id} not found"}]
        return [_result_summary(r) for r in services.get_failed_cases(db, run_id)]


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
