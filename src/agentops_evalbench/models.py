"""SQLAlchemy ORM models.

Schema overview (kept intentionally practical):

    Project 1─┬─* Document
              ├─* TestCase
              └─* EvalRun 1─┬─* EvalResult ─? TestCase
                            └─* TraceLog

Every ``EvalRun`` stores rolled-up averages (for fast dashboard/list views) while
each ``EvalResult`` keeps the per-question detail (answer, context, metrics,
pass/fail). ``TraceLog`` captures pipeline steps for observability.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    """Timezone-aware UTC timestamp used as the default for ``created_at``."""
    return datetime.now(timezone.utc)


class Project(Base):
    """A unit of work: one document set + test cases + evaluation runs."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    documents: Mapped[list[Document]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    test_cases: Mapped[list[TestCase]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    eval_runs: Mapped[list[EvalRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Document(Base):
    """A source document loaded into the RAG pipeline for a project."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="text")  # text|markdown|pdf
    content_preview: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="documents")


class TestCase(Base):
    """A single evaluation question with optional expected answer / context."""

    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text, default=None)
    ground_truth_context: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="test_cases")


class EvalRun(Base):
    """One evaluation run over a project's test set with a given model/prompt.

    Averages are denormalized onto the run so list/compare views don't have to
    re-aggregate every result row.
    """

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    prompt_version: Mapped[str] = mapped_column(String(50), default="v1")
    status: Mapped[str] = mapped_column(
        String(30), default="pending"
    )  # pending|running|completed|failed

    # Rolled-up averages across all results (0..1 metrics, plus latency/cost).
    avg_groundedness: Mapped[float | None] = mapped_column(Float, default=None)
    avg_hallucination_risk: Mapped[float | None] = mapped_column(Float, default=None)
    avg_answer_relevance: Mapped[float | None] = mapped_column(Float, default=None)
    avg_retrieval_score: Mapped[float | None] = mapped_column(Float, default=None)
    avg_latency_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    total_estimated_cost: Mapped[float | None] = mapped_column(Float, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="eval_runs")
    results: Mapped[list[EvalResult]] = relationship(
        back_populates="eval_run", cascade="all, delete-orphan"
    )
    traces: Mapped[list[TraceLog]] = relationship(
        back_populates="eval_run", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    """Per-question evaluation detail: the answer, its context, and all metrics."""

    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    eval_run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True
    )
    # Nullable so ad-hoc scoring (e.g. the MCP score_answer tool) can be stored too.
    test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), default=None
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_answer: Mapped[str | None] = mapped_column(Text, default=None)
    retrieved_context: Mapped[str | None] = mapped_column(Text, default=None)

    # Metrics in the 0..1 range unless noted otherwise.
    groundedness: Mapped[float | None] = mapped_column(Float, default=None)
    hallucination_risk: Mapped[float | None] = mapped_column(Float, default=None)
    answer_relevance: Mapped[float | None] = mapped_column(Float, default=None)
    retrieval_score: Mapped[float | None] = mapped_column(Float, default=None)
    latency_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    # token_usage stored as JSON: {"prompt": int, "completion": int, "total": int}
    token_usage: Mapped[dict | None] = mapped_column(JSON, default=None)
    estimated_cost: Mapped[float | None] = mapped_column(Float, default=None)

    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    eval_run: Mapped[EvalRun] = relationship(back_populates="results")
    test_case: Mapped[TestCase | None] = relationship()


class TraceLog(Base):
    """A single observable step in the pipeline (retrieval, generation, scoring)."""

    __tablename__ = "trace_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    eval_run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True
    )
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text, default=None)
    output_summary: Mapped[str | None] = mapped_column(Text, default=None)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    eval_run: Mapped[EvalRun] = relationship(back_populates="traces")
