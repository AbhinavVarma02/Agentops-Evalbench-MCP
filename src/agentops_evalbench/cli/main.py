"""AgentOps EvalBench MCP — command-line runner (Typer + Rich).

The CLI calls the shared ``services`` core **directly** against its own database
session, so it works with no API server running (ideal for local demos and CI).

Commands::

    agentops-eval init
    agentops-eval run --project-id 1 --run-name baseline
    agentops-eval results --run-id 1
    agentops-eval failed --run-id 1
    agentops-eval compare --baseline 1 --candidate 2
    agentops-eval export --run-id 1 --format markdown
    agentops-eval gate --run-id 1 --min-score 0.80
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .. import services
from ..config import get_settings
from ..database import session_scope
from ..reports import exporter

app = typer.Typer(
    add_completion=False,
    help="LLM evaluation & observability for RAG systems (groundedness, hallucination, retrieval, latency, cost).",
)
console = Console()

DEMO_PROJECT_NAME = "AgentOps Demo"


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _averages_table(run) -> Table:
    table = Table(
        title=f"Run #{run.id} — {run.run_name} ({run.model_name}, prompt {run.prompt_version})"
    )
    table.add_column("Metric", style="cyan")
    table.add_column("Average", justify="right")
    table.add_row("Groundedness", _fmt(run.avg_groundedness))
    table.add_row("Hallucination risk", _fmt(run.avg_hallucination_risk))
    table.add_row("Answer relevance", _fmt(run.avg_answer_relevance))
    table.add_row("Retrieval quality", _fmt(run.avg_retrieval_score))
    table.add_row("Latency (s)", _fmt(run.avg_latency_seconds))
    table.add_row("Est. cost (USD)", f"{run.total_estimated_cost or 0:.6f}")
    return table


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def init() -> None:
    """Initialize the database and create a demo project (sample docs + test set)."""
    with session_scope() as db:
        projects = services.list_projects(db)
        demo = next((p for p in projects if p.name == DEMO_PROJECT_NAME), None)
        if demo is None:
            demo = services.create_project(
                db, DEMO_PROJECT_NAME, "Demo project with bundled sample docs and test set."
            )
        if not services.list_documents(db, demo.id):
            services.load_sample_documents(db, demo.id)
        if not services.list_test_cases(db, demo.id):
            services.import_sample_test_cases(db, demo.id)

        docs = len(services.list_documents(db, demo.id))
        tcs = len(services.list_test_cases(db, demo.id))
        cfg = get_settings().safe_summary()

    console.print(
        Panel.fit(
            f"[bold green]Ready.[/]\nProject id: [bold]{demo.id}[/] ({DEMO_PROJECT_NAME})\n"
            f"Documents: {docs} • Test cases: {tcs}\n"
            f"Database: {cfg['database']} • OpenAI: {'on' if cfg['openai_configured'] else 'offline mode'}\n\n"
            f"Next: [cyan]agentops-eval run --project-id {demo.id} --run-name baseline[/]",
            title="agentops-eval init",
        )
    )


@app.command()
def run(
    project_id: int = typer.Option(..., "--project-id", "-p", help="Project to evaluate."),
    run_name: str = typer.Option("baseline", "--run-name", "-n", help="Name for this run."),
    prompt_version: str = typer.Option("v1", "--prompt-version", help="Prompt version (v1/v2)."),
    model: str = typer.Option("", "--model", help="Model name (blank = default)."),
    judge: bool = typer.Option(False, "--judge/--no-judge", help="Use the OpenAI LLM judge."),
) -> None:
    """Run an evaluation over a project's test cases and store the results."""
    with session_scope() as db:
        if services.get_project(db, project_id) is None:
            console.print(
                f"[red]Project {project_id} not found.[/] Run [cyan]agentops-eval init[/] first."
            )
            raise typer.Exit(code=1)
        with console.status("Running RAG + evaluation…"):
            run_obj = services.create_and_run_eval(
                db,
                project_id=project_id,
                run_name=run_name,
                model_name=model or None,
                prompt_version=prompt_version,
                use_llm_judge=judge,
            )
        total, passed, failed = services.run_counts(db, run_obj.id)
        console.print(_averages_table(run_obj))
        style = "green" if failed == 0 else "yellow"
        console.print(
            f"[{style}]{passed}/{total} passed, {failed} failed.[/] Run id: [bold]{run_obj.id}[/]"
        )


@app.command()
def results(run_id: int = typer.Option(..., "--run-id", "-r")) -> None:
    """Show per-case results for a run."""
    with session_scope() as db:
        if services.get_eval_run(db, run_id) is None:
            console.print(f"[red]Run {run_id} not found.[/]")
            raise typer.Exit(code=1)
        rows = services.list_results(db, run_id)
        table = Table(title=f"Results — run #{run_id}")
        table.add_column("#", justify="right")
        table.add_column("Question", max_width=44)
        table.add_column("Pass")
        table.add_column("Ground", justify="right")
        table.add_column("Halluc", justify="right")
        table.add_column("Relev", justify="right")
        table.add_column("Retr", justify="right")
        table.add_column("Lat(s)", justify="right")
        for r in rows:
            table.add_row(
                str(r.id),
                r.question,
                "[green]PASS[/]" if r.passed else "[red]FAIL[/]",
                _fmt(r.groundedness),
                _fmt(r.hallucination_risk),
                _fmt(r.answer_relevance),
                _fmt(r.retrieval_score),
                _fmt(r.latency_seconds),
            )
        console.print(table)


@app.command()
def failed(run_id: int = typer.Option(..., "--run-id", "-r")) -> None:
    """Show only the failed cases for a run, with reasons."""
    with session_scope() as db:
        if services.get_eval_run(db, run_id) is None:
            console.print(f"[red]Run {run_id} not found.[/]")
            raise typer.Exit(code=1)
        rows = services.get_failed_cases(db, run_id)
        if not rows:
            console.print(f"[green]No failed cases in run #{run_id}.[/]")
            return
        for r in rows:
            console.print(
                Panel(
                    f"[bold]Q:[/] {r.question}\n[bold]A:[/] {r.generated_answer}\n"
                    f"[bold red]Why:[/] {r.failure_reason}",
                    title=f"failed result #{r.id}",
                    border_style="red",
                )
            )


@app.command()
def compare(
    baseline: int = typer.Option(..., "--baseline", "-b"),
    candidate: int = typer.Option(..., "--candidate", "-c"),
) -> None:
    """Compare two runs metric-by-metric."""
    with session_scope() as db:
        try:
            data = services.compare_runs(db, baseline, candidate)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(code=1) from exc
    table = Table(title="Run comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Baseline", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Better?")
    for d in data["deltas"]:
        improved = d["improved"]
        mark = "n/a" if improved is None else ("[green]yes[/]" if improved else "[red]no[/]")
        table.add_row(
            d["metric"].replace("avg_", "").replace("_", " "),
            _fmt(d["baseline"]),
            _fmt(d["candidate"]),
            _fmt(d["delta"]),
            mark,
        )
    console.print(table)
    console.print(f"[bold]{data['summary']}[/]")


@app.command()
def export(
    run_id: int = typer.Option(..., "--run-id", "-r"),
    format: str = typer.Option("markdown", "--format", "-f", help="markdown or json."),
    output: str = typer.Option("", "--output", "-o", help="Output path (default data/reports/)."),
) -> None:
    """Export a run report to a file (Markdown or JSON)."""
    fmt = format.lower()
    if fmt not in ("markdown", "md", "json"):
        console.print("[red]--format must be 'markdown' or 'json'.[/]")
        raise typer.Exit(code=1)
    with session_scope() as db:
        try:
            report = services.build_run_report(db, run_id)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(code=1) from exc
    out_dir = None
    if output:
        from pathlib import Path

        out_dir = Path(output)
    path = exporter.save_report(report, fmt, out_dir)
    console.print(f"[green]Report written:[/] {path}")


@app.command()
def gate(
    run_id: int = typer.Option(
        0, "--run-id", "-r", help="Run to gate (0 = latest of --project-id)."
    ),
    project_id: int = typer.Option(
        0, "--project-id", "-p", help="Gate the latest run of this project."
    ),
    min_score: float = typer.Option(
        None, "--min-score", help="Minimum average groundedness (default = EVAL_MIN_GROUNDEDNESS)."
    ),
    min_pass_rate: float = typer.Option(
        None, "--min-pass-rate", help="Optional: minimum fraction of cases that must pass."
    ),
) -> None:
    """CI quality gate: exit non-zero if the run's averages miss the thresholds.

    Checks average groundedness (>= --min-score), hallucination risk, retrieval
    quality, and latency (against the EVAL_* environment thresholds), plus an
    optional minimum pass-rate. Designed to be called from GitHub Actions.
    """
    settings = get_settings()
    min_score = settings.eval_min_groundedness if min_score is None else min_score

    with session_scope() as db:
        run_obj = None
        if run_id:
            run_obj = services.get_eval_run(db, run_id)
        elif project_id:
            runs = services.list_eval_runs(db, project_id)
            run_obj = runs[0] if runs else None  # list_eval_runs is newest-first
        if run_obj is None:
            console.print("[red]No run found to gate.[/] Provide --run-id or --project-id.")
            raise typer.Exit(code=1)

        total, passed, _failed = services.run_counts(db, run_obj.id)
        pass_rate = (passed / total) if total else 0.0

        # (label, value, ok?) — each check contributes to the gate decision.
        checks = [
            (
                f"Groundedness >= {min_score:.2f}",
                run_obj.avg_groundedness,
                run_obj.avg_groundedness is not None and run_obj.avg_groundedness >= min_score,
            ),
            (
                f"Hallucination <= {settings.eval_max_hallucination_risk:.2f}",
                run_obj.avg_hallucination_risk,
                run_obj.avg_hallucination_risk is not None
                and run_obj.avg_hallucination_risk <= settings.eval_max_hallucination_risk,
            ),
            (
                f"Retrieval >= {settings.eval_min_retrieval_score:.2f}",
                run_obj.avg_retrieval_score,
                run_obj.avg_retrieval_score is not None
                and run_obj.avg_retrieval_score >= settings.eval_min_retrieval_score,
            ),
            (
                f"Latency <= {settings.eval_max_latency_seconds:.2f}s",
                run_obj.avg_latency_seconds,
                run_obj.avg_latency_seconds is not None
                and run_obj.avg_latency_seconds <= settings.eval_max_latency_seconds,
            ),
        ]
        if min_pass_rate is not None:
            checks.append(
                (f"Pass rate >= {min_pass_rate:.0%}", pass_rate, pass_rate >= min_pass_rate)
            )

    table = Table(title=f"Quality gate — run #{run_obj.id}")
    table.add_column("Check", style="cyan")
    table.add_column("Value", justify="right")
    table.add_column("Result")
    all_ok = True
    for label, value, ok in checks:
        all_ok = all_ok and ok
        table.add_row(
            label,
            _fmt(value) if isinstance(value, float) or value is None else str(value),
            "[green]PASS[/]" if ok else "[red]FAIL[/]",
        )
    console.print(table)

    if all_ok:
        console.print("[bold green]Quality gate PASSED.[/]")
    else:
        console.print("[bold red]Quality gate FAILED.[/]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
