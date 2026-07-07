"""Application configuration.

Loads settings from environment variables (and a local ``.env`` at runtime via
pydantic-settings). Design rules for this module:

* Secrets are stored as ``SecretStr`` so they are never accidentally printed.
* ``safe_summary()`` exposes only non-secret status for logs / health output.
* Sensible defaults let the whole app run locally with **zero** external
  services: no ``DATABASE_URL`` -> local SQLite; no ``OPENAI_API_KEY`` -> the
  evaluators fall back to custom (non-LLM) logic.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (src/agentops_evalbench/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "agentops.db"
DISABLE_DOTENV_ENV_VAR = "AGENTOPS_EVALBENCH_DISABLE_DOTENV"


class Settings(BaseSettings):
    """Typed application settings.

    Values are read from the process environment; a local ``.env`` file is
    loaded automatically at runtime (never inspected by tooling).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Required-ish secrets (blank is allowed so the app still boots) ----
    openai_api_key: SecretStr = SecretStr("")
    database_url: str = ""

    # ---- Model configuration ----
    default_model: str = "gpt-4o-mini"
    default_embedding_model: str = "text-embedding-3-small"

    # ---- RAG / vector store ----
    chroma_persist_dir: str = "./data/chroma"

    # ---- Optional tracing ----
    langsmith_api_key: SecretStr = SecretStr("")
    langsmith_tracing: bool = False
    langsmith_project: str = "agentops-evalbench"

    # ---- App / service URLs ----
    app_env: str = "development"
    api_base_url: str = "http://localhost:8000"
    dashboard_url: str = "http://localhost:8501"

    # ---- Evaluation thresholds (deployment-readiness gate) ----
    eval_min_groundedness: float = Field(default=0.80, ge=0.0, le=1.0)
    eval_max_hallucination_risk: float = Field(default=0.20, ge=0.0, le=1.0)
    eval_min_retrieval_score: float = Field(default=0.75, ge=0.0, le=1.0)
    eval_min_answer_relevance: float = Field(default=0.70, ge=0.0, le=1.0)
    eval_max_latency_seconds: float = Field(default=5.0, ge=0.0)

    # ------------------------------------------------------------------ #
    # Derived / helper properties
    # ------------------------------------------------------------------ #
    @property
    def has_openai_key(self) -> bool:
        """True when a non-empty OpenAI key is configured."""
        return bool(self.openai_api_key.get_secret_value().strip())

    @property
    def uses_sqlite(self) -> bool:
        """True when no Postgres URL is set and we fall back to SQLite."""
        return not bool(self.database_url.strip())

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return a SQLAlchemy-ready connection URL.

        * Empty ``DATABASE_URL`` -> local SQLite file (zero-config demo mode).
        * Supabase/Postgres URLs are normalized to the psycopg3 driver so
          ``postgres://`` and ``postgresql://`` both work out of the box.
        """
        raw = self.database_url.strip()
        if not raw:
            DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"

        # Normalize common Postgres prefixes to the psycopg3 dialect.
        if raw.startswith("postgres://"):
            raw = "postgresql+psycopg://" + raw[len("postgres://") :]
        elif raw.startswith("postgresql://"):
            raw = "postgresql+psycopg://" + raw[len("postgresql://") :]
        return raw

    @property
    def chroma_dir(self) -> Path:
        """Absolute path to the Chroma persistence directory."""
        p = Path(self.chroma_persist_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    def safe_summary(self) -> dict[str, object]:
        """Non-secret snapshot for logs / the ``/health`` endpoint.

        Never returns API keys or the raw (password-bearing) database URL.
        """
        # Report the *actual* driver from the resolved URL, not just whether
        # DATABASE_URL was set (so an explicit sqlite:// URL reads as sqlite).
        if self.sqlalchemy_database_url.startswith("sqlite"):
            database = "sqlite (local fallback)" if self.uses_sqlite else "sqlite"
        else:
            database = "postgresql"
        return {
            "app_env": self.app_env,
            "default_model": self.default_model,
            "default_embedding_model": self.default_embedding_model,
            "openai_configured": self.has_openai_key,
            "database": database,
            "langsmith_tracing": self.langsmith_tracing,
            "thresholds": {
                "min_groundedness": self.eval_min_groundedness,
                "max_hallucination_risk": self.eval_max_hallucination_risk,
                "min_retrieval_score": self.eval_min_retrieval_score,
                "min_answer_relevance": self.eval_min_answer_relevance,
                "max_latency_seconds": self.eval_max_latency_seconds,
            },
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (read once per process)."""
    disabled = os.getenv(DISABLE_DOTENV_ENV_VAR, "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return Settings(_env_file=None)
    return Settings()


# Convenience module-level singleton for simple imports.
settings = get_settings()
