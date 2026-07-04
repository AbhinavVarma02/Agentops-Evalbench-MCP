"""Smoke tests for the FastAPI backend using an in-process TestClient."""

import pytest
from fastapi.testclient import TestClient

from agentops_evalbench.api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_root_serves_html_landing_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "AgentOps EvalBench MCP" in body
    assert "/docs" in body
    assert "/status" in body
    assert "/meta" in body


def test_meta_returns_json_metadata(client):
    resp = client.get("/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "AgentOps EvalBench MCP"
    assert "version" in body
    assert body["docs"] == "/docs"
    assert body["health"] == "/health"


def test_favicon_returns_no_content(client):
    resp = client.get("/favicon.ico")
    assert resp.status_code == 204


def test_status_returns_html(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "AgentOps EvalBench MCP" in body
    assert "Online" in body
    assert "Database" in body
    assert "OpenAI" in body


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database_connected"] is True
    assert "openai_api_key" not in body["config"]
    assert "thresholds" in body["config"]


def test_health_does_not_expose_secrets(client):
    resp = client.get("/health")
    raw = resp.text
    for secret_key in ("OPENAI_API_KEY", "DATABASE_URL", "sk-", "secret"):
        assert secret_key not in raw


def test_full_eval_flow(client):
    # Create a project.
    pid = client.post("/projects", json={"name": "Test Project"}).json()["id"]

    # Load sample docs and import the sample test set.
    docs = client.post(f"/projects/{pid}/documents/load-sample").json()
    assert docs["documents_loaded"] >= 1
    imported = client.post(f"/projects/{pid}/test-cases/import-sample").json()
    assert len(imported) >= 1

    # Run an evaluation.
    run = client.post(
        f"/projects/{pid}/eval-runs", json={"run_name": "test", "prompt_version": "v1"}
    ).json()
    assert run["status"] == "completed"

    # Detail + results.
    detail = client.get(f"/eval-runs/{run['id']}").json()
    assert detail["total_cases"] == detail["passed_cases"] + detail["failed_cases"]
    results = client.get(f"/eval-runs/{run['id']}/results").json()
    assert len(results) == detail["total_cases"]

    # Export both formats.
    md = client.get(f"/eval-runs/{run['id']}/export", params={"format": "markdown"}).json()
    assert "Evaluation Report" in md["content"]
    js = client.get(f"/eval-runs/{run['id']}/export", params={"format": "json"}).json()
    assert js["format"] == "json"


def test_missing_run_returns_404(client):
    assert client.get("/eval-runs/999999").status_code == 404


def test_score_endpoint():
    with TestClient(app) as c:
        resp = c.post(
            "/score",
            json={
                "question": "min groundedness?",
                "answer": "at least 0.80",
                "context": "Groundedness must be at least 0.80.",
            },
        )
        assert resp.status_code == 200
        assert 0.0 <= resp.json()["groundedness"] <= 1.0
