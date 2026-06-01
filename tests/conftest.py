"""
Shared pytest fixtures & environment setup.

We configure the app for hermetic, offline testing BEFORE any backend module is
imported: SQLite backend, a temp DB file, no Gemini key (forces the
deterministic fallback engine), tracing to console. This guarantees tests are
fast, repeatable, and require no cloud credentials.
"""
import os
import tempfile

# Must be set before `backend.app.config` is first imported (lru_cached).
_tmp_db = os.path.join(tempfile.gettempdir(), "goopher_test.db")
os.environ.update(
    {
        "DB_BACKEND": "sqlite",
        "SQLITE_PATH": _tmp_db,
        # Clear ALL LLM keys so tests use the deterministic template path and
        # assert on stable text (not natural OpenAI/Gemini phrasing, which varies
        # and would otherwise leak in from a developer's real .env).
        "GOOGLE_API_KEY": "",
        "OPENAI_API_KEY": "",
        "LLM_PROVIDER": "none",
        "USE_ADK_PATH": "false",
        "USE_VERTEXAI": "false",
        "JWT_SECRET": "test-secret",
        # Single-user lockdown: a known allowlist + master password for tests.
        "ALLOWED_EMAILS": "demo@goopher.app",
        "MASTER_PASSWORD": "test-master-password",
        "FULFILLMENT_STAGE_DELAY": "0",   # no demo delays in tests
        "ENABLE_TRACING": "false",
        "ENVIRONMENT": "test",
    }
)

# Remove any stale test DB so each run starts clean.
if os.path.exists(_tmp_db):
    os.remove(_tmp_db)

import pytest  # noqa: E402

from backend.app.db.database import get_repository  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_repo():
    """Seed the SQLite repo once for the whole test session."""
    repo = get_repository()
    repo.seed()
    return repo
