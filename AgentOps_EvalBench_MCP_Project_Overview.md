# AgentOps EvalBench MCP

## Project Overview

**AgentOps EvalBench MCP** is an MCP-powered LLM evaluation and observability platform designed to help developers test, debug, compare, and productionize RAG and agentic AI systems before deployment. Instead of being another chatbot or simple RAG demo, this project acts like a **quality-control layer for LLM applications**. A developer can upload documents, create evaluation test sets, run RAG or agent responses, and automatically score each output for **groundedness, hallucination risk, retrieval quality, answer relevance, latency, token usage, and estimated cost**. The platform stores each run, highlights failed cases, compares prompt/model versions, and generates exportable reports so teams can understand exactly where an AI system is reliable and where it breaks.

The project includes a **FastAPI backend**, **Streamlit dashboard**, **MCP server**, **CLI runner**, **Supabase PostgreSQL database**, **OpenAI-powered RAG/evaluation pipeline**, **ChromaDB vector store**, and optional tracing through **LangSmith/OpenTelemetry**. The MCP server exposes tools such as `run_eval`, `score_answer`, `compare_runs`, `export_report`, `list_eval_runs`, and `get_failed_cases`, allowing MCP-compatible clients like VS Code, Cursor, or Claude Desktop to trigger evaluations directly from a developer workspace. The CLI makes the same evaluation workflow available from the terminal, while the dashboard provides a visual view of scores, traces, failed answers, retrieved context, prompt versions, and run comparisons.

The main workflow is simple: a user creates a project, uploads source documents, builds or imports a test set, runs the RAG/agent pipeline, evaluates the generated answers, stores the results in Supabase PostgreSQL, and reviews everything in the dashboard. Each evaluation run captures the original question, retrieved context, generated answer, expected answer if available, scoring metrics, latency, cost, model configuration, prompt version, and pass/fail decision. A GitHub Actions quality gate can later run the CLI on a fixed test set and fail a pull request if groundedness drops, hallucination risk increases, retrieval quality falls below threshold, or latency becomes too high.

The goal is to show production-level AI engineering skill: not only building LLM apps, but also **testing, monitoring, evaluating, and controlling them**. This makes the project strong for AI Engineer, LLM Engineer, Applied AI Engineer, MLOps/LLMOps Engineer, AI Infrastructure Engineer, and Developer Tools Engineer roles. On a resume, the project demonstrates practical experience with RAG evaluation, MCP integration, observability, backend engineering, database design, CLI tooling, dashboarding, CI/CD quality gates, and production-minded AI reliability.

## Final Project Name

**AgentOps EvalBench MCP**

## GitHub Repository Name

```text
agentops-evalbench-mcp
```

## Resume Project Title

```text
AgentOps EvalBench MCP | FastAPI, Streamlit, MCP, LangGraph, RAGAS, DeepEval, OpenAI, PostgreSQL, Docker
```

Shorter version:

```text
AgentOps EvalBench MCP | LLM Evaluation, MCP, RAGAS, FastAPI, PostgreSQL, Docker
```

## GitHub One-Line Description

```text
MCP-powered LLM evaluation and observability platform for testing RAG and agentic AI systems across groundedness, hallucination risk, retrieval quality, latency, and cost.
```

## Resume Summary

Built **AgentOps EvalBench MCP**, an MCP-powered LLM evaluation and observability platform for testing production RAG and agentic AI systems, with FastAPI, Streamlit, MCP tools, CLI execution, Supabase PostgreSQL storage, RAGAS/DeepEval metrics, dashboard reporting, trace logs, prompt/model comparison, and CI/CD quality gates for groundedness, hallucination risk, retrieval quality, latency, and cost.

## Recommended Tech Stack

| Layer | Tech Stack |
|---|---|
| Frontend Dashboard | Streamlit, Plotly, Pandas |
| Backend API | FastAPI, Pydantic, SQLAlchemy |
| MCP Server | Python MCP SDK |
| CLI Runner | Typer, Rich |
| LLM/RAG Orchestration | LangGraph, LangChain |
| LLM Provider | OpenAI |
| Evaluation | RAGAS, DeepEval, custom Python evaluators |
| Vector Database | ChromaDB |
| Database | Supabase used only as PostgreSQL |
| Tracing | LangSmith optional, OpenTelemetry optional |
| CI/CD | GitHub Actions |
| Testing | Pytest |
| Containerization | Docker, Docker Compose |
| Deployment | Render/Railway/Fly.io for API, Streamlit Cloud/Render for dashboard, Supabase PostgreSQL for database |

## Required API Keys / Environment Variables

For the MVP, keep it simple:

```env
OPENAI_API_KEY=
DATABASE_URL=
```

Optional:

```env
LANGSMITH_API_KEY=
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=agentops-evalbench
```

## Core Features

| Feature | Description |
|---|---|
| Document Upload | Upload PDFs, text files, markdown files, or small datasets for RAG testing |
| Test Set Manager | Create questions, expected answers, and ground-truth context |
| RAG Runner | Generate answers using selected documents, retriever, prompt, and model |
| Evaluation Engine | Score groundedness, hallucination risk, answer relevance, retrieval quality, latency, token usage, and cost |
| MCP Server | Expose evaluation tools to MCP-compatible clients like VS Code, Cursor, or Claude Desktop |
| CLI Runner | Run evaluations directly from terminal |
| Dashboard | Visualize scores, failed cases, traces, retrieved context, prompt versions, and run comparisons |
| Export Reports | Export results as Markdown/JSON reports |
| CI/CD Gate | Fail a GitHub Actions workflow if evaluation quality drops below threshold |

## MCP Tools

```text
run_eval(project_path, testset_path)
score_answer(question, answer, context)
compare_runs(baseline_run_id, new_run_id)
export_report(run_id)
list_eval_runs(project_id)
get_failed_cases(run_id)
```

## Main Evaluation Metrics

| Metric | Purpose |
|---|---|
| Groundedness | Checks whether the answer is supported by retrieved context |
| Hallucination Risk | Flags unsupported or fabricated claims |
| Answer Relevance | Measures how directly the answer responds to the question |
| Retrieval Quality | Measures whether the retrieved chunks contain the needed information |
| Faithfulness | Checks whether the generated answer stays faithful to context |
| Latency | Tracks response speed |
| Token Usage | Tracks input/output tokens |
| Estimated Cost | Estimates cost per run or per answer |
| Pass/Fail Status | Applies thresholds for deployment readiness |

## Example User Flow

```text
1. Create a new project
2. Upload documents
3. Generate or import evaluation questions
4. Run the RAG/agent pipeline
5. Evaluate answers automatically
6. Review failed cases in the dashboard
7. Compare against a previous prompt/model version
8. Export a report
9. Run the same eval from CLI or MCP
10. Use GitHub Actions to block low-quality deployments
```

## Resume Impact

This project is strong for:

- AI Engineer
- LLM Engineer
- Applied AI Engineer
- MLOps / LLMOps Engineer
- AI Infrastructure Engineer
- Developer Tools Engineer

The strongest positioning is that the project does not just build an AI app. It builds the infrastructure to **test, evaluate, monitor, and productionize AI apps**.
