# AgentOps EvalBench MCP

> MCP-powered LLM evaluation and observability platform for testing RAG and agentic AI systems across groundedness, hallucination risk, retrieval quality, latency, and cost.

**AgentOps EvalBench MCP** is a quality-control platform for LLM applications. It helps developers test whether a RAG or agentic AI system is reliable by running evaluation test cases, scoring generated answers, highlighting failed cases, comparing prompt/model versions, and exporting reports.

This project focuses on the production layer of AI systems: **evaluation, debugging, observability, and quality gates**.

---

## Highlights

- RAG evaluation workflow with document loading, retrieval, generation, and scoring
- Metrics for groundedness, hallucination risk, relevance, retrieval quality, latency, token usage, and estimated cost
- Premium Streamlit dashboard for results, failed cases, comparisons, and reports
- FastAPI backend for projects, test cases, evaluation runs, results, and exports
- Typer CLI for local developer workflows and CI usage
- MCP server exposing evaluation tools through a standard tool interface
- PostgreSQL persistence with Supabase used only as hosted PostgreSQL through `DATABASE_URL`
- SQLite and offline fallback mode for local demos without keys
- GitHub Actions quality gate for automated checks

---

## Demo Screenshots

### Dashboard Home

<img width="900" height="890" alt="Dashboard Home" src="https://github.com/user-attachments/assets/aaed705b-a30f-42a1-a90a-72768de21772" />

### Results Dashboard

<img width="1747" height="872" alt="Results Dashboard" src="https://github.com/user-attachments/assets/3698461e-270f-4d54-8394-56a98989654b" />

### Failed Cases

<img width="1675" height="892" alt="Failed Cases" src="https://github.com/user-attachments/assets/65362519-f38e-48d0-ae5e-dd8931687737" />

### Compare Runs

<img width="865" height="875" alt="Compare Runs" src="https://github.com/user-attachments/assets/efbcb741-f2d9-49d3-a805-b5bc2febcda3" />

### Export Report

<img width="606" height="873" alt="Export Report" src="https://github.com/user-attachments/assets/7fe77ae2-aa93-44b5-a2ca-f79d079ccccf" />

---

## How It Works

```text
1. Create a project
2. Load documents or use the included sample documents
3. Create or import evaluation test cases
4. Run the RAG pipeline
5. Retrieve context and generate answers
6. Score each answer with evaluation metrics
7. Review failed cases and metric breakdowns
8. Compare prompt/model versions
9. Export Markdown or JSON reports
10. Run the workflow through the dashboard, API, CLI, or MCP tools
```

Each evaluation run stores the question, retrieved context, generated answer, expected answer, metric scores, latency, token usage, estimated cost, prompt version, model configuration, pass/fail status, and failure reason.

---

## Architecture

```text
                         ┌────────────────────────────────────┐
                         │             Interfaces              │
                         │                                    │
                         │  Streamlit UI   FastAPI   CLI   MCP │
                         └────────┬──────────┬───────┬───────┘
                                  │          │       │
                                  ▼          ▼       ▼
                         ┌────────────────────────────────────┐
                         │        Shared Service Layer          │
                         │ projects / docs / tests / runs /     │
                         │ reports / traces                     │
                         └─────────────────┬──────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
    ┌──────────────────┐        ┌────────────────────┐        ┌───────────────────┐
    │   RAG Pipeline   │        │ Evaluation Engine  │        │   Persistence     │
    │ docs → chunks →  │        │ groundedness /     │        │ SQLAlchemy →      │
    │ retrieval → LLM  │───────►│ hallucination /    │───────►│ PostgreSQL        │
    │ answer           │        │ relevance / cost   │        │ SQLite fallback   │
    └──────────────────┘        └────────────────────┘        └───────────────────┘
                                           │
                                           ▼
                                ┌────────────────────┐
                                │ Reports + CI Gate  │
                                │ Markdown / JSON    │
                                └────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Dashboard | Streamlit, Plotly, Pandas |
| Backend API | FastAPI, Pydantic, SQLAlchemy, Uvicorn |
| Database | PostgreSQL, Supabase as hosted PostgreSQL, SQLite fallback |
| RAG Pipeline | OpenAI, LangChain, LangGraph, ChromaDB, PyPDF |
| Evaluation | Custom Python evaluators, RAGAS/DeepEval-compatible design |
| CLI | Typer, Rich |
| MCP Server | Python MCP SDK |
| Reports | Markdown, JSON |
| Testing | Pytest, HTTPX |
| Code Quality | Ruff, Black |
| DevOps | Docker, Docker Compose, GitHub Actions |

---

## Project Structure

```text
Agentops-Evalbench-MCP/
├── src/
│   └── agentops_evalbench/
│       ├── api/                 # FastAPI app and routes
│       ├── cli/                 # Typer CLI
│       ├── dashboard/           # Streamlit dashboard
│       ├── evaluation/          # metrics, evaluator, cost tracking
│       ├── mcp_server/          # MCP tools
│       ├── rag/                 # document loading, vector store, RAG pipeline
│       ├── reports/             # Markdown / JSON exporters
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── schemas.py
│       └── services.py
├── data/
│   ├── sample_docs/
│   ├── sample_evals/
│   └── reports/
├── docs/screenshots/
├── tests/
├── .github/workflows/
├── .streamlit/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

Requires **Python 3.10+**.

```bash
git clone https://github.com/AbhinavVarma02/Agentops-Evalbench-MCP.git
cd Agentops-Evalbench-MCP

python -m venv .venv
```

Activate the environment:

```bash
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

Install dependencies:

```bash
# Full install
pip install -r requirements.txt

# Or editable install for development
pip install -e ".[db,dev]"
```

Create a local environment file:

```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```

Add your values to `.env`:

```env
OPENAI_API_KEY=
DATABASE_URL=
```

`DATABASE_URL` is optional for local testing. If it is missing, the app uses SQLite fallback.

---

## Environment Variables

| Variable | Required | Purpose |
|---|---:|---|
| `OPENAI_API_KEY` | For live LLM runs | OpenAI chat and embeddings |
| `DATABASE_URL` | Recommended | PostgreSQL connection string |
| `DEFAULT_MODEL` | Optional | Defaults to `gpt-4o-mini` |
| `DEFAULT_EMBEDDING_MODEL` | Optional | Defaults to `text-embedding-3-small` |
| `CHROMA_PERSIST_DIR` | Optional | Local vector store path |
| `EVAL_MIN_GROUNDEDNESS` | Optional | Groundedness pass threshold |
| `EVAL_MAX_HALLUCINATION_RISK` | Optional | Hallucination risk threshold |
| `EVAL_MIN_RETRIEVAL_SCORE` | Optional | Retrieval quality threshold |
| `EVAL_MAX_LATENCY_SECONDS` | Optional | Latency threshold |
| `LANGSMITH_API_KEY` | Optional | Tracing support |
| `LANGSMITH_TRACING` | Optional | Enable or disable tracing |

Supabase is used only as hosted PostgreSQL through `DATABASE_URL`. Supabase Auth, Storage, anon keys, and service role keys are not required.

---

## Running the Backend

```bash
python -m uvicorn agentops_evalbench.api.main:app --reload --port 8000
```

Open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/health
http://127.0.0.1:8000/meta
```

---

## Running the Dashboard

```bash
streamlit run src/agentops_evalbench/dashboard/streamlit_app.py
```

Open:

```text
http://localhost:8501
```

If the backend is offline, the dashboard shows a friendly offline message with the command to start the API.

---

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

---

## Running the MCP Server

```bash
python -m agentops_evalbench.mcp_server.server
```

Available MCP tools:

```text
run_eval
score_answer
compare_runs
export_report
list_eval_runs
get_failed_cases
```

Example MCP server config:

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

---

## API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | HTML landing page |
| `GET /docs` | Swagger API docs |
| `GET /health` | JSON health check |
| `GET /meta` | API metadata |
| `POST /projects` | Create project |
| `GET /projects` | List projects |
| `POST /projects/{project_id}/documents/load-sample` | Load sample documents |
| `POST /projects/{project_id}/test-cases` | Create test case |
| `GET /projects/{project_id}/test-cases` | List test cases |
| `POST /projects/{project_id}/eval-runs` | Run evaluation |
| `GET /eval-runs/{run_id}` | Get run summary |
| `GET /eval-runs/{run_id}/results` | Get detailed results |
| `GET /eval-runs/{run_id}/failed-cases` | Get failed cases |
| `GET /eval-runs/{run_id}/export` | Export report |
| `POST /eval-runs/compare` | Compare runs |

---

## Running Tests

```bash
pytest
ruff check .
black --check .
```

Current validation:

```text
31 passed
ruff clean
black clean
```

---

## GitHub Actions Quality Gate

The repository includes a lightweight CI workflow that installs dependencies, runs tests, and runs a sample evaluation gate.

```text
.github/workflows/eval-gate.yml
```

---

## What This Project Demonstrates

- LLM evaluation and reliability engineering
- RAG pipeline design
- AI observability and quality gates
- MCP tool integration
- FastAPI backend development
- Streamlit dashboarding
- CLI tooling for developer workflows
- PostgreSQL persistence with SQLAlchemy
- Secure environment variable handling
- Testable and offline-friendly AI system design

---

## Future Improvements

- Add async/batched evaluation for larger test sets
- Add more provider adapters through a pluggable model interface
- Add richer agent trace visualization
- Add user accounts for hosted multi-user usage
- Add a lightweight VS Code extension as a separate phase
- Add deployed demo links after cloud deployment is complete

---

## License

This project is licensed under the MIT License.
