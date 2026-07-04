"""Pytest configuration.

Point the app at a throwaway SQLite database BEFORE any project module (and its
cached ``Settings``) is imported, so tests never touch a real database and start
from a clean slate each session.
"""

import os
import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.gettempdir()) / "agentops_evalbench_test.db"
if _TEST_DB.exists():
    _TEST_DB.unlink()

# Force the SQLite fallback for the whole test session.
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
# Keep OpenAI off so tests exercise the deterministic offline evaluators.
os.environ.pop("OPENAI_API_KEY", None)
