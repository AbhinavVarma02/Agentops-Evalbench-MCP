"""Pydantic v2 schemas for API requests and responses.

Read models set ``from_attributes=True`` so they can be built directly from
SQLAlchemy ORM instances (``Model.model_validate(orm_obj)``).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _ORMModel(BaseModel):
    """Base for response models built from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Project
# --------------------------------------------------------------------------- #
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class ProjectRead(_ORMModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Document
# --------------------------------------------------------------------------- #
class DocumentRead(_ORMModel):
    id: int
    project_id: int
    filename: str
    source_type: str
    content_preview: str | None = None
    created_at: datetime


class LoadSampleResponse(BaseModel):
    project_id: int
    documents_loaded: int
    chunks_indexed: int
    documents: list[DocumentRead] = []


# --------------------------------------------------------------------------- #
# Test cases
# --------------------------------------------------------------------------- #
class TestCaseCreate(BaseModel):
    question: str = Field(..., min_length=1)
    expected_answer: str | None = None
    ground_truth_context: str | None = None


class TestCaseRead(_ORMModel):
    id: int
    project_id: int
    question: str
    expected_answer: str | None = None
    ground_truth_context: str | None = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Evaluation runs & results
# --------------------------------------------------------------------------- #
class EvalRunCreate(BaseModel):
    run_name: str = Field(..., min_length=1, max_length=255)
    model_name: str | None = None
    prompt_version: str = "v1"
    # Optional subset of test-case ids; empty/None means "all test cases".
    test_case_ids: list[int] | None = None


class EvalResultRead(_ORMModel):
    id: int
    eval_run_id: int
    test_case_id: int | None = None
    question: str
    generated_answer: str | None = None
    retrieved_context: str | None = None
    groundedness: float | None = None
    hallucination_risk: float | None = None
    answer_relevance: float | None = None
    retrieval_score: float | None = None
    latency_seconds: float | None = None
    token_usage: dict | None = None
    estimated_cost: float | None = None
    passed: bool
    failure_reason: str | None = None
    created_at: datetime


class EvalRunRead(_ORMModel):
    id: int
    project_id: int
    run_name: str
    model_name: str
    prompt_version: str
    status: str
    avg_groundedness: float | None = None
    avg_hallucination_risk: float | None = None
    avg_answer_relevance: float | None = None
    avg_retrieval_score: float | None = None
    avg_latency_seconds: float | None = None
    total_estimated_cost: float | None = None
    created_at: datetime


class EvalRunDetail(EvalRunRead):
    """Run summary plus the number of results and pass/fail counts."""

    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0


# --------------------------------------------------------------------------- #
# Trace logs
# --------------------------------------------------------------------------- #
class TraceLogRead(_ORMModel):
    id: int
    eval_run_id: int
    step_name: str
    input_summary: str | None = None
    output_summary: str | None = None
    metadata_json: dict | None = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Ad-hoc scoring (reused by the API and the MCP score_answer tool)
# --------------------------------------------------------------------------- #
class ScoreAnswerRequest(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    context: str = Field(..., min_length=1)
    expected_answer: str | None = None


class ScoreAnswerResponse(BaseModel):
    groundedness: float
    hallucination_risk: float
    answer_relevance: float
    retrieval_score: float
    passed: bool
    failure_reason: str | None = None


# --------------------------------------------------------------------------- #
# Run comparison
# --------------------------------------------------------------------------- #
class CompareRequest(BaseModel):
    baseline_run_id: int
    candidate_run_id: int


class MetricDelta(BaseModel):
    metric: str
    baseline: float | None = None
    candidate: float | None = None
    delta: float | None = None
    improved: bool | None = None


class CompareResponse(BaseModel):
    baseline_run_id: int
    candidate_run_id: int
    summary: str
    deltas: list[MetricDelta] = []


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    database_connected: bool
    config: dict
