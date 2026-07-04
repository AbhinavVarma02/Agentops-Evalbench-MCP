# AgentOps EvalBench MCP

> MCP-powered LLM evaluation and observability platform for testing RAG and agentic AI systems across groundedness, hallucination risk, retrieval quality, latency, and cost.

AgentOps EvalBench MCP is a **quality-control layer for LLM applications**. Instead of being another chatbot or RAG demo, it lets you upload documents, build evaluation test sets, run a RAG pipeline, and automatically score every answer for **groundedness, hallucination risk, retrieval quality, answer relevance, latency, token usage, and estimated cost**. Runs are stored in PostgreSQL, failed cases are highlighted, prompt/model versions are compared, and reports are exported — so teams know exactly where an AI system is reliable and where it breaks.

The same evaluation workflow is available four ways: a **FastAPI backend**, a **Streamlit dashboard**, a **Typer CLI**, and an **MCP server** that exposes tools to MCP-compatible clients (VS Code, Cursor, Claude Desktop). A **GitHub Actions quality gate** can block a pull request when quality drops below threshold.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Features](#features)
5. [Project Structure](#project-structure)
6. [Setup](#setup)
7. [Environment Variables](#environment-variables)
8. [Running the Backend](#running-the-backend)
9. [Running the Dashboard](#running-the-dashboard)
10. [Running the CLI](#running-the-cli)
11. [Running the MCP Server](#running-the-mcp-server)
12. [Running Tests](#running-tests)
13. [GitHub Actions Quality Gate](#github-actions-quality-gate)
14. [Screenshots](#screenshots)
15. [Resume Bullet](#resume-bullet)
16. [Future Improvements](#future-improvements)

---

## Project Overview

The main workflow is simple:

```text
1. Create a project
2. Load documents (sample docs included)
3. Create or import evaluation test cases
4. Run the RAG pipeline (OpenAI)
5. Evaluate answers automatically
6. Review failed cases in the dashboard
7. Compare against a previous prompt/model version
8. Export a Markdown / JSON report
9. Run the same eval from CLI or MCP
10. Use GitHub Actions to block low-quality deployments
```

Every run captures the question, retrieved context, generated answer, expected answer (if any), scoring metrics, latency, cost, model configuration, prompt version, and a pass/fail decision.

**Design principle:** the core (config, DB, evaluation metrics, cost tracking, reports, API, CLI) runs with a small dependency set and **degrades gracefully**. Heavy RAG/eval libraries are lazy-imported; when they are missing or a key is absent, lightweight custom evaluators still produce every metric so the platform is always demoable.

## Architecture

```text
                         ┌─────────────────────────────────────────────┐
                         │            Interfaces (4 ways in)            │
                         │                                              │
   Cursor / Claude ◄────►│  MCP Server   Streamlit UI   Typer CLI   ─┐  │
   Desktop / VS Code     │      │             │             │        │  │
                         └──────┼─────────────┼─────────────┼────────┼──┘
                                │             │             │        │
                                ▼             ▼             ▼        ▼
                         ┌─────────────────────────────────────────────┐
                         │              FastAPI backend                 │
                         │        (projects / test cases / runs)        │
                         └───────────────────────┬─────────────────────┘
                                                 │
              ┌──────────────────────────────────┼──────────────────────────────┐
              ▼                                  ▼                               ▼
    ┌──────────────────┐              ┌────────────────────┐          ┌───────────────────┐
    │   RAG pipeline   │              │  Evaluation engine │          │   Persistence     │
    │ loader → Chroma  │─ context ───►│ groundedness /     │          │  SQLAlchemy →     │
    │ → OpenAI answer  │  + answer    │ hallucination /    │─ scores ─►│  PostgreSQL       │
    │                  │              │ relevance / retriev│          │  (Supabase) or    │
    └──────────────────┘              │ latency/token/cost │          │  SQLite fallback  │
                                      └────────────────────┘          └───────────────────┘
                                                 │
                                                 ▼
                                      ┌────────────────────┐
                                      │  Reports (MD/JSON) │
                                      │  + CI quality gate │
                                      └────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend Dashboard | Streamlit, Plotly, Pandas |
| Backend API | FastAPI, Pydantic, SQLAlchemy, Alembic, Uvicorn |
| Database | PostgreSQL (Supabase as hosted Postgres via `DATABASE_URL`), SQLite fallback |
| MCP Server | Python MCP SDK |
| CLI | Typer, Rich |
| LLM / RAG | OpenAI, LangChain, LangGraph, ChromaDB, PyPDF, tiktoken |
| Evaluation | RAGAS, DeepEval, custom Python evaluators (fallback) |
| Observability | LangSmith (optional), OpenTelemetry (optional) |
| Testing | Pytest, HTTPX |
| Code Quality | Ruff, Black |
| DevOps | Docker, Docker Compose, GitHub Actions |

## Features

- **Document loading** — text/markdown/PDF loaders; sample docs included so it works immediately.
- **Test set manager** — questions, expected answers, ground-truth context.
- **RAG runner** — OpenAI embeddings + ChromaDB retrieval + OpenAI generation.
- **Evaluation engine** — groundedness, hallucination risk, answer relevance, retrieval quality, latency, token usage, estimated cost.
- **Thresholds & pass/fail** — configurable via environment variables.
- **Persistence** — projects, documents, test cases, runs, results, and trace logs in PostgreSQL.
- **Four interfaces** — FastAPI, Streamlit, CLI, and MCP tools sharing one core.
- **Reports** — Markdown and JSON exports with a pass/fail summary and recommendations.
- **CI quality gate** — GitHub Actions fails the build when quality drops.

## Project Structure

```text
agentops-evalbench-mcp/
├── src/agentops_evalbench/
│   ├── config.py            # settings (secrets masked, DB URL normalization, thresholds)
│   ├── database.py          # SQLAlchemy engine/session, Postgres→SQLite fallback
│   ├── models.py            # Project, Document, TestCase, EvalRun, EvalResult, TraceLog
│   ├── schemas.py           # Pydantic v2 request/response models
│   ├── services.py          # shared DB orchestration reused by API/CLI/MCP
│   ├── rag/                 # document_loader, vector_store (Chroma + TF-IDF), rag_pipeline
│   ├── evaluation/          # metrics, cost_tracker, evaluator (thresholds + run orchestration)
│   ├── api/                 # FastAPI app + routes
│   ├── dashboard/           # Streamlit app
│   ├── cli/                 # Typer + Rich CLI
│   ├── mcp_server/          # MCP tools (FastMCP)
│   └── reports/             # Markdown / JSON exporters
├── data/
│   ├── sample_docs/         # bundled RAG documents
│   ├── sample_evals/        # bundled test set (JSON)
│   ├── chroma/              # local vector store (git-ignored)
│   └── reports/             # generated reports (git-ignored)
├── tests/                   # pytest suite
├── .github/workflows/       # eval-gate CI
├── Dockerfile / docker-compose.yml
├── pyproject.toml / requirements.txt
└── PROGRESS.md              # build log & handoff notes
```

**One core, four interfaces.** The API, dashboard, CLI, and MCP server all call the same
`services` + `evaluation` core, so evaluation logic is never duplicated. Heavy libraries
(OpenAI, ChromaDB, LangChain, tiktoken) are lazy-imported with lightweight fallbacks, so the
platform runs — and is fully testable — with no API key and no database.

## Setup

Requires **Python 3.10+** (developed on 3.13).

```bash
# 1. Clone and enter the repo
git clone https://github.com/AbhinavVarma02/Agentops-Evalbench-MCP.git
cd agentops-evalbench-mcp

# 2. Create a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3a. Full install (RAG + eval + dashboard + MCP)
pip install -r requirements.txt

# 3b. OR minimal core (API, DB, evaluation, CLI, tests)
pip install -e ".[db,dev]"

# 4. Configure environment
cp .env.example .env        # Windows: copy .env.example .env
# then edit .env and add your OPENAI_API_KEY (and DATABASE_URL if using Postgres)
```

> **No database or API key?** You can still run the whole thing. With no `DATABASE_URL` the app uses a local SQLite file, and evaluators fall back to custom logic when OpenAI is unavailable.

## Environment Variables

Only two are required; everything else has sensible defaults. See [.env.example](.env.example).

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ (for live runs) | — | Embeddings + chat completions |
| `DATABASE_URL` | ✅ (recommended) | SQLite file | Postgres/Supabase connection string |
| `DEFAULT_MODEL` | | `gpt-4o-mini` | Chat model |
| `DEFAULT_EMBEDDING_MODEL` | | `text-embedding-3-small` | Embedding model |
| `CHROMA_PERSIST_DIR` | | `./data/chroma` | Vector store directory |
| `EVAL_MIN_GROUNDEDNESS` | | `0.80` | Pass threshold |
| `EVAL_MAX_HALLUCINATION_RISK` | | `0.20` | Pass threshold |
| `EVAL_MIN_RETRIEVAL_SCORE` | | `0.75` | Pass threshold |
| `EVAL_MAX_LATENCY_SECONDS` | | `5` | Pass threshold |
| `LANGSMITH_API_KEY` / `LANGSMITH_TRACING` | | off | Optional tracing |

> **Deployment note:** Add `OPENAI_API_KEY` and `DATABASE_URL` later through your hosting platform environment variables. Supabase is used only as hosted PostgreSQL through `DATABASE_URL`; no Supabase auth or storage configuration is required for this project.

## Running the Backend

```bash
uvicorn agentops_evalbench.api.main:app --reload --port 8000
# landing page:
open http://127.0.0.1:8000/          # friendly HTML landing page
open http://127.0.0.1:8000/docs      # Swagger API docs
# health check:
curl http://localhost:8000/health
# machine-readable metadata:
curl http://localhost:8000/meta
```

## Running the Dashboard

```bash
streamlit run src/agentops_evalbench/dashboard/streamlit_app.py
# opens http://localhost:8501
```

If the API is offline the dashboard shows a clear message instead of crashing.

## Running the CLI

```bash
agentops-eval --help
agentops-eval init
agentops-eval run --project-id 1 --run-name baseline
agentops-eval results --run-id 1
agentops-eval failed --run-id 1
agentops-eval compare --baseline 1 --candidate 2
agentops-eval export --run-id 1 --format markdown
agentops-eval gate --run-id 1 --min-score 0.80
```

## Running the MCP Server

```bash
python -m agentops_evalbench.mcp_server.server
```

Register it with an MCP client (e.g. Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agentops-evalbench": {
      "command": "python",
      "args": ["-m", "agentops_evalbench.mcp_server.server"]
    }
  }
}
```

Exposed tools: `run_eval`, `score_answer`, `compare_runs`, `export_report`, `list_eval_runs`, `get_failed_cases`.

## Running Tests

```bash
pytest
# or with coverage of the core modules
pytest -q
```

## GitHub Actions Quality Gate

[.github/workflows/eval-gate.yml](.github/workflows/eval-gate.yml) installs deps, runs the test suite, and runs a lightweight evaluation gate on sample data. It fails the build when quality thresholds are not met. Secrets are referenced as placeholders only:

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

## Screenshots

_Add screenshots here once you run the dashboard locally._

- `docs/screenshots/dashboard-home.png`
- `docs/screenshots/results.png`
- `docs/screenshots/failed-cases.png`
- `docs/screenshots/compare-runs.png`

## Resume Bullet

```text
Built AgentOps EvalBench MCP, an MCP-powered LLM evaluation and observability platform for testing production RAG and agentic AI systems, with FastAPI, Streamlit, MCP tools, CLI execution, Supabase PostgreSQL storage, RAGAS/DeepEval metrics, dashboard reporting, trace logs, prompt/model comparison, and CI/CD quality gates for groundedness, hallucination risk, retrieval quality, latency, and cost.
```

## Future Improvements

- Async / batched evaluation runs for large test sets.
- Additional providers behind a pluggable LLM interface.
- Alembic migrations wired into CI for schema versioning.
- Richer agentic (multi-step tool) traces beyond single-hop RAG.
- Auth + multi-user projects for a hosted deployment.
- Native RAGAS/DeepEval scoring surfaced alongside the custom metrics.

---

Built as a portfolio project for AI Engineer, LLM Engineer, Applied AI, MLOps/LLMOps, AI Infrastructure, and Developer Tools roles. See [AgentOps_EvalBench_MCP_Project_Overview.md](AgentOps_EvalBench_MCP_Project_Overview.md) for the full project brief and [PROGRESS.md](PROGRESS.md) for the build log.
