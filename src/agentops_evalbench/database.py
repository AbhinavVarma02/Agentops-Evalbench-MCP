"""Database engine, session factory, and declarative base.

Uses SQLAlchemy 2.0. The connection URL comes from ``Settings`` and transparently
falls back to a local SQLite file when ``DATABASE_URL`` is not set, so the app is
always runnable. When ``DATABASE_URL`` points at Supabase/Postgres, the same code
path is used with the psycopg3 driver.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
_DATABASE_URL = settings.sqlalchemy_database_url

# SQLite needs check_same_thread=False so the connection can be shared across
# FastAPI's threadpool; Postgres needs pre-ping to survive idle disconnects
# (common with hosted Supabase poolers).
if _DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    _engine_kwargs: dict = {"connect_args": _connect_args}
else:
    _engine_kwargs = {"pool_pre_ping": True}

engine = create_engine(_DATABASE_URL, future=True, **_engine_kwargs)

# ``expire_on_commit=False`` lets us keep reading ORM objects after commit,
# which the CLI and MCP tools rely on when returning results.
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session
)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager that ensures tables exist, yields a session, then closes it.

    Used by the CLI and MCP server (which run without the API's lifespan hook).
    """
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (no-op if they exist).

    Import ``models`` here (not at module top) to avoid a circular import while
    still ensuring every table is registered on ``Base.metadata`` before create.
    """
    from . import models  # noqa: F401  (registers models on Base.metadata)

    Base.metadata.create_all(bind=engine)


def db_health() -> bool:
    """Return True if a trivial query succeeds against the database."""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
