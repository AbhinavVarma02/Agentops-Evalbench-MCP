"""AgentOps EvalBench MCP — Streamlit dashboard.

Run with:  ``streamlit run src/agentops_evalbench/dashboard/streamlit_app.py``

The dashboard talks to the FastAPI backend over HTTP only (it is intentionally
decoupled from the package internals — even thresholds are read from ``/health``).
If the API is offline every page shows a clear, actionable message with the exact
command to start the backend, instead of crashing.

Design + speed notes:
* One inline ``<style>`` block builds the whole "premium" look — a small set of
  CSS design tokens (colours, radii, shadows) drive cards, badges, buttons,
  tables, and the sidebar. No external CSS/CDN and no extra JS, so the UI stays
  fast and works fully offline.
* Read-only API calls are wrapped in ``@st.cache_data(ttl=30)`` so navigating
  between pages does not re-hit the backend on every render. Any create / run /
  import action clears the cache so the UI stays fresh. Mutations and exports are
  never cached.
* Evaluation only runs on an explicit button click (inside a form), never on
  page load.
"""

from __future__ import annotations

import os

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

DEFAULT_API = os.environ.get("API_BASE_URL", "http://localhost:8000")
CACHE_TTL = 30  # seconds — read-only calls are memoised this long

st.set_page_config(
    page_title="AgentOps EvalBench MCP",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# Global styling — one inline stylesheet (design tokens + components).
# No external CSS/CDN and no web fonts, so the look loads instantly and offline.
# --------------------------------------------------------------------------- #
def inject_css() -> None:
    st.markdown(
        """
        <style>
          /* ---------- Design tokens ---------- */
          :root {
            --bg: #f3f6fc;
            --surface: #ffffff;
            --surface-2: #f8fafc;
            --border: #e6eaf2;
            --border-strong: #d6ddea;
            --text: #0f1b2d;
            --text-muted: #5b6b7f;
            --text-subtle: #8a97a8;
            --primary: #2f6feb;
            --primary-dark: #1c46b6;
            --primary-soft: #eaf1fe;
            --good: #0f9d6a;   --good-bg: #e7f6ee;
            --warn: #c77700;   --warn-bg: #fdf1de;
            --bad:  #d1382c;   --bad-bg:  #fdeae8;
            --radius: 16px;
            --radius-sm: 11px;
            --shadow-sm: 0 1px 2px rgba(15,23,42,.06), 0 1px 3px rgba(15,23,42,.05);
            --shadow-md: 0 6px 18px rgba(15,23,42,.07), 0 2px 6px rgba(15,23,42,.05);
            --shadow-lg: 0 18px 40px rgba(15,23,42,.13);
          }

          /* ---------- Layout & typography ---------- */
          .stApp {
            background:
              radial-gradient(1100px 480px at 12% -8%, #e9f0ff 0%, rgba(233,240,255,0) 55%),
              radial-gradient(900px 420px at 100% 0%, #eef6f1 0%, rgba(238,246,241,0) 50%),
              var(--bg);
          }
          .block-container { padding-top: 2.2rem; padding-bottom: 3.2rem; max-width: 1200px; }
          html, body, [class*="css"] {
            font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
              Helvetica, Arial, sans-serif;
            -webkit-font-smoothing: antialiased;
          }
          h1 { font-size: 2.5rem !important; font-weight: 800 !important;
               letter-spacing: -0.025em; color: var(--text); }
          h2 { font-size: 1.7rem !important; font-weight: 700 !important;
               letter-spacing: -0.01em; color: var(--text); }
          h3 { font-size: 1.3rem !important; font-weight: 700 !important;
               letter-spacing: -0.01em; color: var(--text); margin-top: 0.4rem; }
          h4 { font-size: 1.08rem !important; font-weight: 700 !important; color: var(--text); }
          .stMarkdown p, .stMarkdown li { font-size: 1.06rem; line-height: 1.7; color: #3c4a5c; }
          .stMarkdown code { background: var(--primary-soft); color: var(--primary-dark);
                             padding: 1px 7px; border-radius: 6px; font-size: 0.92em; font-weight: 600; }
          hr { border-color: var(--border); }

          /* ---------- Page header ---------- */
          .page-head { margin: 0 0 1.3rem; }
          .page-head .title { font-size: 2.2rem; font-weight: 800; letter-spacing: -0.025em;
                              color: var(--text); line-height: 1.15; }
          .page-head .subtitle { font-size: 1.08rem; color: var(--text-muted); margin-top: 4px; }

          /* ---------- Hero (home) ---------- */
          .hero { position: relative; overflow: hidden;
                  background: linear-gradient(125deg, #3a78f2 0%, #2456c8 55%, #1a3ea6 100%);
                  border-radius: 22px; padding: 34px 38px; margin-bottom: 24px;
                  box-shadow: 0 20px 44px rgba(36, 86, 200, .30); }
          .hero::after { content: ""; position: absolute; top: -60%; right: -8%; width: 420px; height: 420px;
                         background: radial-gradient(circle, rgba(255,255,255,.20) 0%, rgba(255,255,255,0) 62%);
                         pointer-events: none; }
          .hero .h-title { font-size: 2.5rem; font-weight: 800; color: #ffffff;
                           letter-spacing: -0.028em; line-height: 1.1; }
          .hero .h-sub { font-size: 1.12rem; color: #e2ebff; margin-top: 10px; max-width: 760px;
                         line-height: 1.6; }
          .hero-tags { margin-top: 18px; display: flex; gap: 10px; flex-wrap: wrap; position: relative; }
          .hero-tag { background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.28);
                      color: #ffffff; font-size: 0.86rem; font-weight: 600; padding: 6px 14px;
                      border-radius: 999px; }

          /* ---------- Native metric cards (kept for any st.metric) ---------- */
          [data-testid="stMetric"] {
            background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
            padding: 17px 20px; box-shadow: var(--shadow-sm);
          }
          [data-testid="stMetricLabel"] p { font-size: 0.9rem !important; font-weight: 600;
                                            color: var(--text-muted) !important; }
          [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important;
                                          color: var(--text); }

          /* ---------- Custom metric row ---------- */
          .metric-row { display: flex; gap: 16px; flex-wrap: wrap; margin: 6px 0 14px; }
          .metric-card { flex: 1; min-width: 158px; position: relative; overflow: hidden;
                         background: var(--surface); border: 1px solid var(--border);
                         border-radius: var(--radius); padding: 18px 20px 16px;
                         box-shadow: var(--shadow-sm); transition: transform .15s ease, box-shadow .15s ease; }
          .metric-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
          .metric-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
                                 background: var(--accent, #98a2b3); }
          .metric-card .m-label { font-size: 0.76rem; font-weight: 700; color: var(--text-muted);
                                  text-transform: uppercase; letter-spacing: 0.06em; }
          .metric-card .m-value { font-size: 2.05rem; font-weight: 800; color: var(--text);
                                  margin-top: 6px; line-height: 1.05; letter-spacing: -0.02em; }
          .metric-card .m-sub { font-size: 0.83rem; color: var(--text-subtle); margin-top: 4px;
                                font-weight: 500; }
          .metric-card.good { --accent: var(--good); }
          .metric-card.warn { --accent: var(--warn); }
          .metric-card.bad  { --accent: var(--bad); }
          .metric-card.info { --accent: var(--primary); }
          /* Compact variant: word-values (status text) instead of big numbers. */
          .metric-card.compact .m-value { font-size: 1.5rem; font-weight: 750; line-height: 1.2; }

          /* ---------- Feature cards (home) ---------- */
          .feature-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px;
                          margin: 8px 0 6px; }
          .feature-card { background: var(--surface); border: 1px solid var(--border);
                          border-radius: var(--radius); padding: 22px 24px; box-shadow: var(--shadow-sm);
                          transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease; }
          .feature-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md);
                                border-color: var(--border-strong); }
          .feature-card .f-icon { display: inline-flex; align-items: center; justify-content: center;
                                  width: 42px; height: 42px; border-radius: 12px; font-size: 1.35rem;
                                  background: var(--primary-soft); }
          .feature-card .f-title { font-size: 1.16rem; font-weight: 700; color: var(--text);
                                   margin: 12px 0 5px; }
          .feature-card .f-desc { font-size: 0.99rem; color: var(--text-muted); line-height: 1.55; }

          /* ---------- Badges ---------- */
          .badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 13px;
                   border-radius: 999px; font-size: 0.84rem; font-weight: 700; letter-spacing: 0.02em; }
          .badge::before { content: ""; width: 7px; height: 7px; border-radius: 50%;
                           background: currentColor; opacity: .85; }
          .badge-pass { background: var(--good-bg); color: var(--good); }
          .badge-fail { background: var(--bad-bg); color: var(--bad); }
          .badge-neutral { background: #eef1f5; color: #52606d; }

          /* ---------- Offline card ---------- */
          .offline-card { background: linear-gradient(180deg, #fff8ef 0%, #fff4e5 100%);
                          border: 1px solid #fbd9a8; border-left: 5px solid #f59e0b;
                          border-radius: var(--radius-sm); padding: 20px 22px; margin: 6px 0 14px;
                          box-shadow: var(--shadow-sm); }
          .offline-card .o-title { font-size: 1.18rem; font-weight: 700; color: #9a3412; }
          .offline-card .o-body { font-size: 1.02rem; color: #7c2d12; margin-top: 4px; }

          /* ---------- Buttons ---------- */
          .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button,
          .stLinkButton > a {
            border-radius: 10px; font-weight: 650; font-size: 1rem; padding: 0.55rem 1.2rem;
            border: 1px solid var(--border-strong); box-shadow: var(--shadow-sm);
            transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
          }
          .stButton > button:hover, .stFormSubmitButton > button:hover,
          .stDownloadButton > button:hover, .stLinkButton > a:hover {
            transform: translateY(-1px); box-shadow: var(--shadow-md);
          }
          .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primaryFormSubmit"],
          .stFormSubmitButton > button, .stDownloadButton > button[kind="primary"] {
            background: linear-gradient(180deg, #3a78f2 0%, var(--primary) 100%);
            border-color: var(--primary-dark); color: #ffffff;
            box-shadow: 0 4px 12px rgba(47,111,235,.28);
          }
          .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
            filter: brightness(1.04);
          }

          /* ---------- Tables ---------- */
          [data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: var(--radius-sm);
                                        overflow: hidden; box-shadow: var(--shadow-sm); }
          [data-testid="stDataFrame"] * { font-size: 0.99rem; }

          /* ---------- Alerts ---------- */
          [data-testid="stAlert"] { border-radius: var(--radius-sm); }

          /* ---------- Sidebar ---------- */
          [data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
          [data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
          .brand { display: flex; align-items: center; gap: 12px; margin: 2px 4px 14px; }
          .brand .logo { width: 42px; height: 42px; border-radius: 12px; display: flex;
                         align-items: center; justify-content: center; font-size: 1.4rem;
                         background: linear-gradient(135deg, #3a78f2, #1c46b6);
                         box-shadow: 0 6px 14px rgba(36,86,200,.32); }
          .brand .b-name { font-size: 1.18rem; font-weight: 800; color: var(--text);
                           letter-spacing: -0.02em; line-height: 1.1; }
          .brand .b-tag { font-size: 0.76rem; color: var(--text-subtle); font-weight: 600; }
          [data-testid="stSidebar"] [role="radiogroup"] > label {
            padding: 8px 13px; border-radius: 10px; margin-bottom: 3px; font-size: 1.02rem;
            font-weight: 550; transition: background .12s ease;
          }
          [data-testid="stSidebar"] [role="radiogroup"] > label:hover { background: var(--primary-soft); }
          .sidebar-status { display: flex; align-items: center; gap: 8px; font-size: 0.92rem;
                            font-weight: 700; padding: 8px 13px; border-radius: 10px; margin: 4px 0 8px; }
          .status-online { background: var(--good-bg); color: var(--good); }
          .status-offline { background: var(--bad-bg); color: var(--bad); }

          /* ---------- Expanders ---------- */
          [data-testid="stExpander"] { border-radius: var(--radius-sm); border: 1px solid var(--border);
                                       box-shadow: var(--shadow-sm); }
          [data-testid="stExpander"] summary { font-weight: 650; font-size: 1.02rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Tiny API client with graceful offline handling
# --------------------------------------------------------------------------- #
class ApiClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            resp = httpx.request(method, url, timeout=self.timeout, **kwargs)
        except httpx.HTTPError as exc:  # connection refused / timeout / DNS
            return False, {"error": f"Cannot reach API at {self.base_url} ({exc})"}
        if resp.status_code >= 400:
            detail = (
                resp.json().get("detail", resp.text)
                if resp.headers.get("content-type", "").startswith("application/json")
                else resp.text
            )
            return False, {"error": f"{resp.status_code}: {detail}"}
        return True, (resp.json() if resp.content else {})

    def get(self, path: str, **kw):
        return self._request("GET", path, **kw)

    def post(self, path: str, **kw):
        return self._request("POST", path, **kw)


def get_base_url() -> str:
    return st.session_state.get("api_base_url", DEFAULT_API)


def get_client() -> ApiClient:
    """Client for write actions (create/run/export). Reads use the cached helpers."""
    return ApiClient(get_base_url())


# --------------------------------------------------------------------------- #
# Cached read-only API calls (keyed by base_url so the cache is per-backend).
# ``st.cache_data`` needs hashable args, so these take the URL string, not the
# client object. Any create/run action calls ``st.cache_data.clear()``.
# Write actions (create/run/import/compare/export) never go through here.
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_health(base_url: str):
    return ApiClient(base_url).get("/health")


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_projects(base_url: str):
    return ApiClient(base_url).get("/projects")


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_test_cases(base_url: str, project_id: int):
    return ApiClient(base_url).get(f"/projects/{project_id}/test-cases")


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_eval_runs(base_url: str, project_id: int):
    return ApiClient(base_url).get(f"/projects/{project_id}/eval-runs")


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_run_detail(base_url: str, run_id: int):
    return ApiClient(base_url).get(f"/eval-runs/{run_id}")


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_run_results(base_url: str, run_id: int):
    return ApiClient(base_url).get(f"/eval-runs/{run_id}/results")


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fetch_failed_cases(base_url: str, run_id: int):
    return ApiClient(base_url).get(f"/eval-runs/{run_id}/failed-cases")


def clear_cache() -> None:
    """Drop all memoised reads after a create/run/mutation action."""
    st.cache_data.clear()


# --------------------------------------------------------------------------- #
# Small UI helpers
# --------------------------------------------------------------------------- #
def page_header(title: str, subtitle: str = "") -> None:
    sub = f'<div class="subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="page-head"><div class="title">{title}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


def pass_fail_badge(passed: bool) -> str:
    return (
        '<span class="badge badge-pass">PASS</span>'
        if passed
        else '<span class="badge badge-fail">FAIL</span>'
    )


def render_offline(error: str = "") -> None:
    """Friendly offline card + the exact command to start the FastAPI backend."""
    st.markdown(
        '<div class="offline-card">'
        '<div class="o-title">⚠️ Backend API is not reachable</div>'
        '<div class="o-body">Start the FastAPI backend in a terminal, then refresh this page.</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.code("uvicorn agentops_evalbench.api.main:app --reload --port 8000", language="bash")
    if error:
        st.caption(error)


def require_online() -> dict:
    """Return the health payload or stop the page with a friendly offline card."""
    ok, data = fetch_health(get_base_url())
    if not ok:
        render_offline(data.get("error", ""))
        st.stop()
    return data


def _score_tone(value, threshold, higher_is_better: bool) -> str:
    if value is None or threshold is None:
        return "info"
    ok = value >= threshold if higher_is_better else value <= threshold
    return "good" if ok else "bad"


def _metric_card_html(c: dict, extra_cls: str = "") -> str:
    """One tone-coded metric card. c = {label, value, sub?, tone?}."""
    tone = c.get("tone", "info")
    sub = f'<div class="m-sub">{c["sub"]}</div>' if c.get("sub") else ""
    cls = f"metric-card {tone} {extra_cls}".strip()
    return (
        f'<div class="{cls}">'
        f'<div class="m-label">{c["label"]}</div>'
        f'<div class="m-value">{c["value"]}</div>{sub}</div>'
    )


def render_metric_row(cards: list[dict]) -> None:
    """cards: list of {label, value, sub?, tone?} → one flex row of metric cards."""
    inner = "".join(_metric_card_html(c) for c in cards)
    st.markdown(f'<div class="metric-row">{inner}</div>', unsafe_allow_html=True)


def render_metric_columns(cards: list[dict], compact: bool = False) -> None:
    """Fixed, equal-width metric cards via ``st.columns`` — stays a clean N-across
    at any screen width (used for the small, screenshot-critical status rows).
    ``compact`` uses a smaller value font so word-values never break mid-word."""
    extra = "compact" if compact else ""
    cols = st.columns(len(cards))
    for col, c in zip(cols, cards, strict=True):
        col.markdown(_metric_card_html(c, extra), unsafe_allow_html=True)


def pick_project() -> dict | None:
    """Shared project selector backed by the cached projects list."""
    ok, projects = fetch_projects(get_base_url())
    if not ok or not projects:
        st.info("No projects yet. Create one on the **Projects** page.")
        return None
    labels = {f"#{p['id']} — {p['name']}": p for p in projects}
    choice = st.selectbox("Project", list(labels.keys()), key="project_pick")
    return labels[choice]


def pick_run(project_id: int, label: str = "Run") -> dict | None:
    ok, runs = fetch_eval_runs(get_base_url(), project_id)
    if not ok or not runs:
        st.info("No evaluation runs yet. Start one on the **Run Evaluation** page.")
        return None
    labels = {f"#{r['id']} — {r['run_name']} ({r['prompt_version']})": r for r in runs}
    choice = st.selectbox(label, list(labels.keys()), key=f"run_pick_{label}")
    return labels[choice]


def goto(page: str) -> None:
    """Queue a navigation change (applied before the sidebar radio is built)."""
    st.session_state["_goto"] = page
    st.rerun()


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def page_home() -> None:
    st.markdown(
        '<div class="hero">'
        '<div class="h-title">🧪 AgentOps EvalBench MCP</div>'
        '<div class="h-sub">LLM evaluation &amp; observability for RAG systems — measure '
        "groundedness, hallucination risk, retrieval quality, answer relevance, latency, "
        "and cost across every prompt version.</div>"
        '<div class="hero-tags">'
        '<span class="hero-tag">⚡ Offline-first</span>'
        '<span class="hero-tag">🔌 MCP-native</span>'
        '<span class="hero-tag">🚦 CI quality gate</span>'
        '<span class="hero-tag">📊 One core · four interfaces</span>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Live backend status shown as consistent, tone-coded metric cards.
    ok, data = fetch_health(get_base_url())
    if ok:
        cfg = data.get("config", {})
        db_ok = bool(data.get("database_connected"))
        openai_on = bool(cfg.get("openai_configured"))
        # Fixed 3-across, compact so word-values never break — screenshot-ready.
        render_metric_columns(
            [
                {
                    "label": "API",
                    "value": "Online",
                    "sub": f"v{data.get('version', '—')}",
                    "tone": "good",
                },
                {
                    "label": "Database",
                    "value": "Connected" if db_ok else "Down",
                    "sub": "persistence layer",
                    "tone": "good" if db_ok else "bad",
                },
                {
                    "label": "OpenAI",
                    "value": "Configured" if openai_on else "Offline mode",
                    "sub": cfg.get("default_model", "custom evaluators"),
                    "tone": "info",
                },
            ],
            compact=True,
        )
    else:
        render_offline(data.get("error", ""))

    st.markdown("### What's inside")
    st.markdown(
        '<div class="feature-grid">'
        '<div class="feature-card"><div class="f-icon">🔍</div>'
        '<div class="f-title">RAG Evaluation</div>'
        '<div class="f-desc">Score generated answers on groundedness, hallucination risk, '
        "retrieval quality, and relevance against thresholds.</div></div>"
        '<div class="feature-card"><div class="f-icon">🛠️</div>'
        '<div class="f-title">MCP Tools</div>'
        '<div class="f-desc">Run evals, score answers, compare runs, and export reports '
        "straight from an MCP-compatible client.</div></div>"
        '<div class="feature-card"><div class="f-icon">⌨️</div>'
        '<div class="f-title">CLI Runner</div>'
        '<div class="f-desc">Drive the full pipeline from the terminal — <code>init</code>, '
        "<code>run</code>, <code>results</code>, <code>compare</code>, <code>export</code>.</div></div>"
        '<div class="feature-card"><div class="f-icon">🚦</div>'
        '<div class="f-title">CI/CD Gate</div>'
        '<div class="f-desc">Fail a build when quality drops — the <code>gate</code> command '
        "exits non-zero on threshold or pass-rate regressions.</div></div>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("### Quickstart")
    st.markdown(
        "1. **Projects** → create a project\n"
        "2. **Load Sample Documents** → index the bundled docs\n"
        "3. **Create Test Cases** → import the sample test set\n"
        "4. **Run Evaluation** → score answers against thresholds\n"
        "5. **Results / Failed Cases / Compare / Export** → analyze and report"
    )

    st.markdown("### Quick links")
    base = get_base_url()
    q1, q2, q3 = st.columns(3)
    with q1:
        st.link_button("📘 FastAPI docs", f"{base}/docs", use_container_width=True)
    with q2:
        st.link_button("🩺 System Status", f"{base}/status", use_container_width=True)
    with q3:
        if st.button("▶️ Run evaluation", use_container_width=True, type="primary"):
            goto("Run Evaluation")


def page_projects() -> None:
    page_header("📁 Projects", "Create and manage evaluation projects.")
    require_online()

    with st.form("create_project"):
        st.markdown("#### Create a new project")
        name = st.text_input("Project name", placeholder="e.g. Northwind RAG")
        description = st.text_area("Description", "", placeholder="Optional")
        # Create is a write action — not cached, and it clears the read cache on success.
        if st.form_submit_button("Create project", type="primary") and name.strip():
            ok, data = get_client().post(
                "/projects", json={"name": name, "description": description}
            )
            if ok:
                clear_cache()
                st.success(f"✅ Created project #{data['id']} — {data['name']}")
            else:
                st.error(data["error"])

    st.markdown("#### Existing projects")
    ok, projects = fetch_projects(get_base_url())
    if ok and projects:
        st.dataframe(pd.DataFrame(projects), use_container_width=True, hide_index=True)
    else:
        st.info("No projects yet — create one above to get started.")


def page_load_docs() -> None:
    page_header("📄 Load Sample Documents", "Index the bundled sample corpus for a project.")
    require_online()
    project = pick_project()
    if not project:
        return
    if st.button("Load bundled sample documents", type="primary"):
        with st.spinner("Loading and indexing sample documents…"):
            ok, data = get_client().post(f"/projects/{project['id']}/documents/load-sample")
        if ok:
            clear_cache()
            st.success(
                f"✅ Loaded {data['documents_loaded']} docs → "
                f"{data['chunks_indexed']} chunks indexed"
            )
            st.dataframe(pd.DataFrame(data["documents"]), use_container_width=True, hide_index=True)
        else:
            st.error(data["error"])


def page_test_cases() -> None:
    page_header("📝 Create Test Cases", "Import the sample test set or add your own questions.")
    require_online()
    project = pick_project()
    if not project:
        return
    pid = project["id"]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Import samples")
        st.caption("Bulk-load the bundled 8-case test set.")
        if st.button("Import sample test set (8 cases)", type="primary"):
            ok, data = get_client().post(f"/projects/{pid}/test-cases/import-sample")
            if ok:
                clear_cache()
                st.success(f"✅ Imported {len(data)} test cases")
            else:
                st.error(data["error"])
    with col2:
        with st.form("add_tc"):
            st.markdown("#### Add a test case")
            q = st.text_input("Question")
            exp = st.text_input("Expected answer (optional)")
            if st.form_submit_button("Add test case", type="primary") and q.strip():
                payload = {"question": q, "expected_answer": exp or None}
                ok, data = get_client().post(f"/projects/{pid}/test-cases", json=payload)
                if ok:
                    clear_cache()
                    st.success(f"✅ Added test case #{data['id']}")
                else:
                    st.error(data["error"])

    st.markdown("#### Current test cases")
    ok, tcs = fetch_test_cases(get_base_url(), pid)
    if ok and tcs:
        st.dataframe(
            pd.DataFrame(tcs)[["id", "question", "expected_answer"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "question": st.column_config.TextColumn("Question", width="large"),
                "expected_answer": st.column_config.TextColumn("Expected answer"),
            },
        )
    else:
        st.info("No test cases yet — import the sample set or add one above.")


def page_run() -> None:
    page_header("▶️ Run Evaluation", "Run the RAG pipeline over the test cases and score answers.")
    require_online()
    project = pick_project()
    if not project:
        return
    pid = project["id"]

    # Evaluation is expensive, so it only fires on an explicit submit — never on
    # page load. The form gates everything below behind ``submitted``.
    with st.form("run_form"):
        c1, c2, c3 = st.columns(3)
        run_name = c1.text_input("Run name", "baseline")
        prompt_version = c2.selectbox("Prompt version", ["v1", "v2"])
        model_name = c3.text_input("Model (blank = default)", "")
        submitted = st.form_submit_button("Run evaluation", type="primary")
    if submitted:
        payload = {
            "run_name": run_name,
            "prompt_version": prompt_version,
            "model_name": model_name or None,
        }
        with st.spinner("Running evaluation… this may take a moment."):
            ok, run = get_client().post(f"/projects/{pid}/eval-runs", json=payload)
        if not ok:
            st.error(run["error"])
            return
        clear_cache()
        st.success(f"✅ Run #{run['id']} completed ({run['status']}).")
        render_metric_row(
            [
                {"label": "Groundedness", "value": _fmt(run["avg_groundedness"]), "tone": "info"},
                {
                    "label": "Halluc. risk",
                    "value": _fmt(run["avg_hallucination_risk"]),
                    "tone": "info",
                },
                {"label": "Retrieval", "value": _fmt(run["avg_retrieval_score"]), "tone": "info"},
                {
                    "label": "Cost (USD)",
                    "value": f"${run['total_estimated_cost']:.5f}",
                    "tone": "info",
                },
            ]
        )
        st.caption("See the **Results Dashboard** page for the full per-case breakdown.")


def page_results() -> None:
    page_header("📊 Results Dashboard", "Summary metrics, thresholds, and per-case scores.")
    health = require_online()
    thresholds = health.get("config", {}).get("thresholds", {})
    project = pick_project()
    if not project:
        return
    run = pick_run(project["id"])
    if not run:
        return

    with st.spinner("Loading evaluation results…"):
        ok, detail = fetch_run_detail(get_base_url(), run["id"])
    if not ok:
        st.error(detail["error"])
        return

    total = detail["total_cases"]
    passed = detail["passed_cases"]
    pass_rate = (passed / total * 100) if total else 0.0
    rate_tone = "good" if pass_rate >= 80 else "warn" if pass_rate >= 50 else "bad"

    render_metric_row(
        [
            {
                "label": "Pass rate",
                "value": f"{pass_rate:.0f}%",
                "sub": f"{passed}/{total} cases",
                "tone": rate_tone,
            },
            {
                "label": "Groundedness",
                "value": _fmt(detail["avg_groundedness"]),
                "sub": "higher is better",
                "tone": _score_tone(
                    detail["avg_groundedness"], thresholds.get("min_groundedness"), True
                ),
            },
            {
                "label": "Halluc. risk",
                "value": _fmt(detail["avg_hallucination_risk"]),
                "sub": "lower is better",
                "tone": _score_tone(
                    detail["avg_hallucination_risk"],
                    thresholds.get("max_hallucination_risk"),
                    False,
                ),
            },
            {
                "label": "Retrieval",
                "value": _fmt(detail["avg_retrieval_score"]),
                "sub": "higher is better",
                "tone": _score_tone(
                    detail["avg_retrieval_score"], thresholds.get("min_retrieval_score"), True
                ),
            },
            {
                "label": "Avg latency",
                "value": _fmt_secs(detail["avg_latency_seconds"]),
                "sub": "per case",
                "tone": "info",
            },
        ]
    )

    # Averages vs thresholds bar chart (kept compact so it doesn't dominate).
    with st.expander("📈 Averages vs thresholds", expanded=True):
        metric_map = [
            ("Groundedness", detail["avg_groundedness"], thresholds.get("min_groundedness")),
            (
                "Answer relevance",
                detail["avg_answer_relevance"],
                thresholds.get("min_answer_relevance"),
            ),
            (
                "Retrieval quality",
                detail["avg_retrieval_score"],
                thresholds.get("min_retrieval_score"),
            ),
            (
                "Hallucination risk",
                detail["avg_hallucination_risk"],
                thresholds.get("max_hallucination_risk"),
            ),
        ]
        df = pd.DataFrame(
            [{"metric": m, "average": v or 0, "threshold": t} for m, v, t in metric_map]
        )
        fig = px.bar(df, x="metric", y="average", range_y=[0, 1], text_auto=".2f")
        fig.update_traces(marker_color="#2f6feb", marker_line_width=0)
        fig.add_scatter(
            x=df["metric"],
            y=df["threshold"],
            mode="markers",
            name="threshold",
            marker=dict(color="#f04438", size=13, symbol="line-ew-open"),
        )
        fig.update_layout(
            height=330,
            margin=dict(l=10, r=10, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(size=13, color="#3c4a5c"),
            legend=dict(orientation="h", y=1.12, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Per-case results")
    ok, results = fetch_run_results(get_base_url(), run["id"])
    if ok and results:
        rdf = pd.DataFrame(results)
        rdf["Status"] = rdf["passed"].map(lambda p: "✅ PASS" if p else "❌ FAIL")
        show = rdf[
            [
                "question",
                "Status",
                "groundedness",
                "hallucination_risk",
                "answer_relevance",
                "retrieval_score",
                "latency_seconds",
                "estimated_cost",
            ]
        ]
        st.dataframe(
            show,
            use_container_width=True,
            hide_index=True,
            column_config={
                "question": st.column_config.TextColumn("Question", width="large"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "groundedness": st.column_config.NumberColumn("Grounded", format="%.2f"),
                "hallucination_risk": st.column_config.NumberColumn("Halluc.", format="%.2f"),
                "answer_relevance": st.column_config.NumberColumn("Relevance", format="%.2f"),
                "retrieval_score": st.column_config.NumberColumn("Retrieval", format="%.2f"),
                "latency_seconds": st.column_config.NumberColumn("Latency (s)", format="%.2f"),
                "estimated_cost": st.column_config.NumberColumn("Cost ($)", format="%.5f"),
            },
        )
    else:
        st.info("No per-case results found for this run.")


def page_failed() -> None:
    page_header("❌ Failed Cases", "Drill into every case that missed a threshold.")
    require_online()
    project = pick_project()
    if not project:
        return
    run = pick_run(project["id"])
    if not run:
        return
    with st.spinner("Loading failed cases…"):
        ok, failed = fetch_failed_cases(get_base_url(), run["id"])
    if not ok:
        st.error(failed["error"])
        return
    if not failed:
        st.success("🎉 No failed cases in this run — every case passed its thresholds.")
        return
    st.warning(f"⚠️ {len(failed)} failed case(s) in this run.")
    for r in failed:
        with st.expander(f"❌  {r['question']}"):
            st.markdown(pass_fail_badge(False), unsafe_allow_html=True)
            st.markdown(f"**Answer:** {r['generated_answer']}")
            st.markdown(f"**Why it failed:** `{r['failure_reason']}`")
            render_metric_row(
                [
                    {"label": "Groundedness", "value": _fmt(r["groundedness"]), "tone": "bad"},
                    {
                        "label": "Halluc. risk",
                        "value": _fmt(r["hallucination_risk"]),
                        "tone": "bad",
                    },
                    {"label": "Relevance", "value": _fmt(r["answer_relevance"]), "tone": "info"},
                    {"label": "Retrieval", "value": _fmt(r["retrieval_score"]), "tone": "info"},
                    {"label": "Latency", "value": _fmt_secs(r["latency_seconds"]), "tone": "info"},
                ]
            )
            if r.get("retrieved_context"):
                st.caption("Retrieved context")
                st.text(r["retrieved_context"][:1500])


def page_compare() -> None:
    page_header("🔀 Compare Runs", "Diff two runs metric-by-metric to spot regressions.")
    require_online()
    project = pick_project()
    if not project:
        return
    baseline = pick_run(project["id"], "Baseline")
    candidate = pick_run(project["id"], "Candidate")
    if not baseline or not candidate:
        return
    # Compare is a read-only computation on the backend but it is user-triggered,
    # so it runs on click (not cached) with a spinner.
    if st.button("Compare", type="primary"):
        with st.spinner("Comparing runs…"):
            ok, data = get_client().post(
                "/eval-runs/compare",
                json={"baseline_run_id": baseline["id"], "candidate_run_id": candidate["id"]},
            )
        if not ok:
            st.error(data["error"])
            return
        st.info(data["summary"])
        df = pd.DataFrame(data["deltas"])
        st.dataframe(df, use_container_width=True, hide_index=True)
        plot_df = df.dropna(subset=["baseline", "candidate"]).melt(
            id_vars="metric",
            value_vars=["baseline", "candidate"],
            var_name="run",
            value_name="value",
        )
        if not plot_df.empty:
            fig = px.bar(
                plot_df,
                x="metric",
                y="value",
                color="run",
                barmode="group",
                title="Baseline vs Candidate",
                color_discrete_map={"baseline": "#98a2b3", "candidate": "#2f6feb"},
            )
            fig.update_layout(
                height=360,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(size=13, color="#3c4a5c"),
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)


def page_export() -> None:
    page_header("📤 Export Report", "Generate a shareable Markdown or JSON evaluation report.")
    require_online()
    project = pick_project()
    if not project:
        return
    run = pick_run(project["id"])
    if not run:
        return
    fmt = st.radio("Format", ["markdown", "json"], horizontal=True)
    # Export is an on-demand action — run on click with a spinner, never cached.
    if st.button("Generate report", type="primary"):
        with st.spinner("Building report…"):
            ok, data = get_client().get(f"/eval-runs/{run['id']}/export", params={"format": fmt})
        if not ok:
            st.error(data["error"])
            return
        content = data["content"]
        st.download_button(
            "⬇️ Download report",
            content,
            file_name=f"eval_report_run_{run['id']}.{'md' if fmt == 'markdown' else 'json'}",
            type="primary",
        )
        st.divider()
        if fmt == "markdown":
            st.markdown(content)
        else:
            st.code(content, language="json")


# --------------------------------------------------------------------------- #
# Helpers + navigation
# --------------------------------------------------------------------------- #
def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def _fmt_secs(v) -> str:
    return "n/a" if v is None else f"{v:.2f}s"


PAGES = {
    "Home": page_home,
    "Projects": page_projects,
    "Load Sample Documents": page_load_docs,
    "Create Test Cases": page_test_cases,
    "Run Evaluation": page_run,
    "Results Dashboard": page_results,
    "Failed Cases": page_failed,
    "Compare Runs": page_compare,
    "Export Report": page_export,
}


def main() -> None:
    inject_css()

    # Apply any queued navigation *before* the radio widget is instantiated.
    if "_goto" in st.session_state:
        target = st.session_state.pop("_goto")
        if target in PAGES:
            st.session_state["nav_page"] = target

    # Sidebar brand lockup (gradient badge + name + tagline).
    st.sidebar.markdown(
        '<div class="brand">'
        '<div class="logo">🧪</div>'
        '<div><div class="b-name">EvalBench</div>'
        '<div class="b-tag">LLM eval &amp; observability</div></div>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.session_state["api_base_url"] = st.sidebar.text_input("API base URL", DEFAULT_API)

    # Single cached /health call powers the sidebar badge (pages reuse the cache).
    ok, _ = fetch_health(get_base_url())
    status_cls = "status-online" if ok else "status-offline"
    status_txt = "🟢 API online" if ok else "🔴 API offline"
    st.sidebar.markdown(
        f'<div class="sidebar-status {status_cls}">{status_txt}</div>', unsafe_allow_html=True
    )

    page = st.sidebar.radio("Navigate", list(PAGES.keys()), key="nav_page")
    st.sidebar.divider()
    st.sidebar.caption("Offline mode works without an OpenAI key (custom evaluators).")
    PAGES[page]()


main()
