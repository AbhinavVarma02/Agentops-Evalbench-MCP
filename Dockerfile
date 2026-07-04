# AgentOps EvalBench MCP — application image (serves the API and/or dashboard).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tooling + curl (curl is used by the compose healthcheck).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata + source, then install.
# An *editable* install keeps the package under /app/src so PROJECT_ROOT resolves
# to /app and the bundled data/ (sample docs + test set) is found at runtime.
COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data

RUN python -m pip install --upgrade pip \
    && pip install -e ".[db,rag,dashboard,mcp]"

# API: 8000, Streamlit dashboard: 8501
EXPOSE 8000 8501

# Default command runs the API; docker-compose overrides it for the dashboard.
CMD ["uvicorn", "agentops_evalbench.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
