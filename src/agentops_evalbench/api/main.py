"""FastAPI application entry point.

Run with:  ``uvicorn agentops_evalbench.api.main:app --reload``

Tables are created on startup (via the lifespan handler) so the app is usable
immediately against either Postgres/Supabase or the local SQLite fallback.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .. import __version__
from ..config import get_settings
from ..database import db_health, init_db
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (idempotent). Nothing to tear down on shutdown.
    init_db()
    yield


app = FastAPI(
    title="AgentOps EvalBench MCP",
    version=__version__,
    description=(
        "MCP-powered LLM evaluation and observability platform for testing RAG and "
        "agentic AI systems across groundedness, hallucination risk, retrieval "
        "quality, latency, and cost."
    ),
    lifespan=lifespan,
)

# Allow the Streamlit dashboard (and other local tools) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# --------------------------------------------------------------------------- #
# Root landing page + machine-readable metadata
# --------------------------------------------------------------------------- #
def _landing_html() -> str:
    """A small, dependency-free HTML landing page (inline CSS, no JS/CDN)."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentOps EvalBench MCP</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55;
    color: #1f2933;
    background: #f5f7fa;
  }}
  .wrap {{ max-width: 720px; margin: 0 auto; padding: 48px 24px; }}
  .card {{
    background: #ffffff;
    border: 1px solid #e4e7eb;
    border-radius: 14px;
    padding: 32px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
  }}
  h1 {{ margin: 0 0 4px; font-size: 1.7rem; }}
  .version {{
    display: inline-block; font-size: 0.75rem; font-weight: 600;
    color: #3e5c76; background: #eaf1f8; border-radius: 999px;
    padding: 2px 10px; margin-bottom: 14px;
  }}
  p.lead {{ margin: 0 0 24px; color: #52606d; }}
  h2 {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em;
        color: #7b8794; margin: 28px 0 12px; }}
  .links {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  .links a {{
    text-decoration: none; font-weight: 600; font-size: 0.95rem;
    color: #ffffff; background: #2f6feb; padding: 9px 16px; border-radius: 8px;
  }}
  .links a.secondary {{ background: #52606d; }}
  ul.interfaces {{ margin: 0; padding-left: 20px; color: #3e4c59; }}
  ul.interfaces li {{ margin-bottom: 4px; }}
  .note {{
    margin-top: 24px; font-size: 0.9rem; color: #52606d;
    background: #f5f7fa; border: 1px dashed #cbd2d9; border-radius: 10px; padding: 14px 16px;
  }}
  code {{ background: #eef1f5; padding: 1px 6px; border-radius: 5px; font-size: 0.85em; }}
  footer {{ margin-top: 22px; font-size: 0.78rem; color: #9aa5b1; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>AgentOps EvalBench MCP</h1>
      <span class="version">v{__version__}</span>
      <p class="lead">
        MCP-powered LLM evaluation and observability platform for RAG and
        agentic AI systems.
      </p>

      <h2>Explore the API</h2>
      <div class="links">
        <a href="/docs">Swagger docs</a>
        <a class="secondary" href="/status">System Status</a>
        <a class="secondary" href="/meta">Metadata</a>
      </div>

      <h2>Available interfaces</h2>
      <ul class="interfaces">
        <li>FastAPI backend (this service)</li>
        <li>Streamlit dashboard</li>
        <li>CLI runner</li>
        <li>MCP server</li>
      </ul>

      <div class="note">
        The Streamlit dashboard usually runs separately at
        <code>http://localhost:8501</code>.
      </div>

      <footer>Local demo &middot; running offline-first with sensible fallbacks.</footer>
    </div>
  </div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse, tags=["system"])
def root() -> HTMLResponse:
    """Human-friendly HTML landing page for the local demo."""
    return HTMLResponse(content=_landing_html())


@app.get("/meta", tags=["system"])
def meta() -> dict:
    """Machine-readable API metadata (previously served at ``/``)."""
    return {
        "name": "AgentOps EvalBench MCP",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


def _status_html() -> str:
    """Build a human-friendly system status page (inline CSS only)."""
    settings = get_settings()
    summary = settings.safe_summary()
    db_ok = db_health()
    openai_mode = "OpenAI configured" if summary["openai_configured"] else "Offline fallback mode"
    langsmith = "Enabled" if summary["langsmith_tracing"] else "Disabled"
    thresholds: dict = summary.get("thresholds", {})

    threshold_rows = ""
    labels = {
        "min_groundedness": "Min Groundedness",
        "max_hallucination_risk": "Max Hallucination Risk",
        "min_retrieval_score": "Min Retrieval Score",
        "min_answer_relevance": "Min Answer Relevance",
        "max_latency_seconds": "Max Latency (s)",
    }
    for key, label in labels.items():
        val = thresholds.get(key, "—")
        threshold_rows += f"<tr><td>{label}</td><td>{val}</td></tr>\n"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>System Status — AgentOps EvalBench MCP</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55; color: #1f2933; background: #f5f7fa;
  }}
  .wrap {{ max-width: 720px; margin: 0 auto; padding: 48px 24px; }}
  .card {{
    background: #fff; border: 1px solid #e4e7eb; border-radius: 14px;
    padding: 32px; box-shadow: 0 1px 3px rgba(15,23,42,.06); margin-bottom: 20px;
  }}
  h1 {{ font-size: 1.7rem; margin-bottom: 4px; }}
  .badge {{
    display: inline-block; font-size: 0.8rem; font-weight: 700;
    border-radius: 999px; padding: 3px 12px; margin-bottom: 16px;
  }}
  .badge.online {{ background: #d1fae5; color: #065f46; }}
  .badge.offline {{ background: #fee2e2; color: #991b1b; }}
  h2 {{
    font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: #7b8794; margin: 24px 0 10px;
  }}
  .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  .info-item {{ background: #f5f7fa; border-radius: 10px; padding: 14px 16px; }}
  .info-label {{ font-size: 0.78rem; color: #7b8794; text-transform: uppercase; letter-spacing: .03em; }}
  .info-value {{ font-size: 1rem; font-weight: 600; color: #1f2933; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 8px 12px; font-size: 0.92rem; }}
  th {{ background: #f0f2f5; color: #52606d; font-weight: 600; border-radius: 6px 6px 0 0; }}
  tr:nth-child(even) td {{ background: #f9fafb; }}
  td {{ border-bottom: 1px solid #e4e7eb; }}
  .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }}
  .links a {{
    text-decoration: none; font-weight: 600; font-size: 0.9rem;
    color: #fff; background: #2f6feb; padding: 8px 14px; border-radius: 8px;
  }}
  .links a.secondary {{ background: #52606d; }}
  .links a.small {{ font-size: 0.8rem; padding: 6px 12px; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>AgentOps EvalBench MCP</h1>
      <span class="badge {"online" if db_ok else "offline"}">{"Online" if db_ok else "Offline"}</span>

      <div class="info-grid">
        <div class="info-item">
          <div class="info-label">Version</div>
          <div class="info-value">{__version__}</div>
        </div>
        <div class="info-item">
          <div class="info-label">Database</div>
          <div class="info-value">{summary["database"]}</div>
        </div>
        <div class="info-item">
          <div class="info-label">OpenAI</div>
          <div class="info-value">{openai_mode}</div>
        </div>
        <div class="info-item">
          <div class="info-label">LangSmith Tracing</div>
          <div class="info-value">{langsmith}</div>
        </div>
      </div>

      <h2>Evaluation Thresholds</h2>
      <table>
        <thead><tr><th>Metric</th><th>Value</th></tr></thead>
        <tbody>
{threshold_rows}        </tbody>
      </table>

      <h2>Quick Links</h2>
      <div class="links">
        <a href="/">Home</a>
        <a href="/docs">API Docs</a>
        <a class="secondary small" href="/health">Health JSON</a>
        <a class="secondary small" href="/meta">Metadata</a>
      </div>
    </div>
  </div>
</body>
</html>"""


@app.get("/status", response_class=HTMLResponse, tags=["system"])
def status() -> HTMLResponse:
    """Human-friendly system status page."""
    return HTMLResponse(content=_status_html())


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Return an empty 204 so browsers stop logging a noisy 404."""
    return Response(status_code=204)
