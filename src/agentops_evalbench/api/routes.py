"""FastAPI routes.

Thin HTTP layer over ``services`` (which owns persistence + evaluation) and
``reports.exporter`` (formatting). Every handler validates input with Pydantic
schemas and maps "not found" errors to 404s.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import __version__, schemas, services
from ..config import get_settings
from ..database import db_health, get_db
from ..evaluation import metrics
from ..reports import exporter

router = APIRouter()


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@router.get("/health", response_model=schemas.HealthResponse, tags=["system"])
def health() -> schemas.HealthResponse:
    """Liveness + a non-secret config snapshot for quick diagnostics."""
    settings = get_settings()
    return schemas.HealthResponse(
        status="ok",
        version=__version__,
        database_connected=db_health(),
        config=settings.safe_summary(),
    )


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
@router.post("/projects", response_model=schemas.ProjectRead, tags=["projects"], status_code=201)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    return services.create_project(db, name=payload.name, description=payload.description)


@router.get("/projects", response_model=list[schemas.ProjectRead], tags=["projects"])
def list_projects(db: Session = Depends(get_db)):
    return services.list_projects(db)


def _require_project(db: Session, project_id: int):
    project = services.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #
@router.post(
    "/projects/{project_id}/documents/load-sample",
    response_model=schemas.LoadSampleResponse,
    tags=["documents"],
)
def load_sample_documents(project_id: int, db: Session = Depends(get_db)):
    """Register the bundled sample documents for a project (great for demos)."""
    _require_project(db, project_id)
    docs, chunks = services.load_sample_documents(db, project_id)
    return schemas.LoadSampleResponse(
        project_id=project_id,
        documents_loaded=len(docs),
        chunks_indexed=chunks,
        documents=[schemas.DocumentRead.model_validate(d) for d in docs],
    )


# --------------------------------------------------------------------------- #
# Test cases
# --------------------------------------------------------------------------- #
@router.post(
    "/projects/{project_id}/test-cases",
    response_model=schemas.TestCaseRead,
    tags=["test-cases"],
    status_code=201,
)
def create_test_case(
    project_id: int, payload: schemas.TestCaseCreate, db: Session = Depends(get_db)
):
    _require_project(db, project_id)
    return services.add_test_case(
        db,
        project_id=project_id,
        question=payload.question,
        expected_answer=payload.expected_answer,
        ground_truth_context=payload.ground_truth_context,
    )


@router.post(
    "/projects/{project_id}/test-cases/import-sample",
    response_model=list[schemas.TestCaseRead],
    tags=["test-cases"],
)
def import_sample_test_cases(project_id: int, db: Session = Depends(get_db)):
    """Bulk-import the bundled sample test set (convenience for demos)."""
    _require_project(db, project_id)
    return services.import_sample_test_cases(db, project_id)


@router.get(
    "/projects/{project_id}/test-cases",
    response_model=list[schemas.TestCaseRead],
    tags=["test-cases"],
)
def list_test_cases(project_id: int, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    return services.list_test_cases(db, project_id)


# --------------------------------------------------------------------------- #
# Evaluation runs
# --------------------------------------------------------------------------- #
@router.post(
    "/projects/{project_id}/eval-runs",
    response_model=schemas.EvalRunRead,
    tags=["eval-runs"],
    status_code=201,
)
def create_eval_run(project_id: int, payload: schemas.EvalRunCreate, db: Session = Depends(get_db)):
    """Run an evaluation over the project's test cases and persist the results."""
    _require_project(db, project_id)
    run = services.create_and_run_eval(
        db,
        project_id=project_id,
        run_name=payload.run_name,
        model_name=payload.model_name,
        prompt_version=payload.prompt_version,
        test_case_ids=payload.test_case_ids,
    )
    return run


@router.get(
    "/projects/{project_id}/eval-runs", response_model=list[schemas.EvalRunRead], tags=["eval-runs"]
)
def list_project_eval_runs(project_id: int, db: Session = Depends(get_db)):
    _require_project(db, project_id)
    return services.list_eval_runs(db, project_id)


def _require_run(db: Session, run_id: int):
    run = services.get_eval_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.get("/eval-runs/{run_id}", response_model=schemas.EvalRunDetail, tags=["eval-runs"])
def get_eval_run(run_id: int, db: Session = Depends(get_db)):
    run = _require_run(db, run_id)
    total, passed, failed = services.run_counts(db, run_id)
    base = schemas.EvalRunRead.model_validate(run).model_dump()
    return schemas.EvalRunDetail(
        **base, total_cases=total, passed_cases=passed, failed_cases=failed
    )


@router.get(
    "/eval-runs/{run_id}/results", response_model=list[schemas.EvalResultRead], tags=["eval-runs"]
)
def get_run_results(run_id: int, db: Session = Depends(get_db)):
    _require_run(db, run_id)
    return services.list_results(db, run_id)


@router.get(
    "/eval-runs/{run_id}/failed-cases",
    response_model=list[schemas.EvalResultRead],
    tags=["eval-runs"],
)
def get_failed_cases(run_id: int, db: Session = Depends(get_db)):
    _require_run(db, run_id)
    return services.get_failed_cases(db, run_id)


@router.get(
    "/eval-runs/{run_id}/traces", response_model=list[schemas.TraceLogRead], tags=["eval-runs"]
)
def get_run_traces(run_id: int, db: Session = Depends(get_db)):
    _require_run(db, run_id)
    return services.list_traces(db, run_id)


@router.get("/eval-runs/{run_id}/export", tags=["reports"])
def export_run(
    run_id: int,
    format: str = Query("markdown", pattern="^(markdown|md|json)$"),
    save: bool = False,
    db: Session = Depends(get_db),
):
    """Export a run report as Markdown or JSON. Optionally save it to data/reports/."""
    _require_run(db, run_id)
    try:
        report = services.build_run_report(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    saved_path = str(exporter.save_report(report, format)) if save else None
    return {
        "run_id": run_id,
        "format": "json" if format == "json" else "markdown",
        "saved_path": saved_path,
        "content": exporter.render(report, format),
    }


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
@router.post("/eval-runs/compare", response_model=schemas.CompareResponse, tags=["eval-runs"])
def compare_runs(payload: schemas.CompareRequest, db: Session = Depends(get_db)):
    try:
        result = services.compare_runs(db, payload.baseline_run_id, payload.candidate_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


# --------------------------------------------------------------------------- #
# Ad-hoc scoring (shared with the MCP score_answer tool)
# --------------------------------------------------------------------------- #
@router.post("/score", response_model=schemas.ScoreAnswerResponse, tags=["evaluation"])
def score_answer(payload: schemas.ScoreAnswerRequest):
    """Score a single (question, answer, context) triple without persisting it."""
    from ..evaluation.evaluator import EvalThresholds, check_pass

    scores = metrics.score_answer(
        question=payload.question,
        answer=payload.answer,
        context=payload.context,
        expected_answer=payload.expected_answer,
    )
    thresholds = EvalThresholds.from_settings()
    # Latency is not applicable to ad-hoc scoring; pass 0 so it never trips the gate.
    passed, reason = check_pass(
        groundedness=scores.groundedness,
        hallucination_risk=scores.hallucination_risk,
        retrieval_score=scores.retrieval_score,
        answer_relevance=scores.answer_relevance,
        latency_seconds=0.0,
        thresholds=thresholds,
    )
    return schemas.ScoreAnswerResponse(
        groundedness=scores.groundedness,
        hallucination_risk=scores.hallucination_risk,
        answer_relevance=scores.answer_relevance,
        retrieval_score=scores.retrieval_score,
        passed=passed,
        failure_reason=reason,
    )
