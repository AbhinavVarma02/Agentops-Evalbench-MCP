# AgentOps EvalBench MCP — common commands.
# On Windows without `make`, just run the commands under each target manually.

.PHONY: help install install-all api dashboard cli mcp test lint fmt gate docker-build docker-up clean

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:         ## Install core + dev (minimal, runs everything offline)
	pip install -e ".[db,dev]"

install-all:     ## Install the full stack (RAG, eval, dashboard, MCP)
	pip install -r requirements.txt

api:             ## Run the FastAPI backend
	uvicorn agentops_evalbench.api.main:app --reload --port 8000

dashboard:       ## Run the Streamlit dashboard
	streamlit run src/agentops_evalbench/dashboard/streamlit_app.py

cli:             ## Seed the demo project (sample docs + test set)
	agentops-eval init

mcp:             ## Run the MCP server (stdio)
	python -m agentops_evalbench.mcp_server.server

test:            ## Run the test suite
	pytest -q

lint:            ## Lint with ruff
	ruff check src tests

fmt:             ## Format with black
	black src tests

gate:            ## Run the sample-data quality gate (demo project)
	agentops-eval init && agentops-eval run --project-id 1 --run-name local && agentops-eval gate --project-id 1 --min-score 0.80

docker-build:    ## Build the Docker image
	docker build -t agentops-evalbench:latest .

docker-up:       ## Start API + dashboard via docker compose
	docker compose up --build

clean:           ## Remove caches and local SQLite/reports
	rm -rf .pytest_cache .ruff_cache **/__pycache__ data/chroma
	rm -f data/agentops.db
