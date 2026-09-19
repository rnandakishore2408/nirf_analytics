"""Test setup: every test runs against a throw-away local database, never Supabase, and with the AI keys
blanked so no test can call an external API."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_TMP = tempfile.mkdtemp(prefix="nirf-tests-")
# set before any project module loads .env (load_dotenv never overrides variables that already exist)
os.environ["SUPABASE_DB_URL"] = ""
os.environ["NIRF_LOCAL_DB"] = str(Path(_TMP) / "store.db")
os.environ["GROQ_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
for p in (ROOT / "app", ROOT / "models", ROOT):
    sys.path.insert(0, str(p))

import pytest  # noqa: E402

import auth  # noqa: E402
import live_store  # noqa: E402

PASSWORDS = {"t.admin": "Adm1n-Test-Pass-9x", "t.staff": "St4ff-Test-Pass-7q", "t.other": "0ther-Test-Pass-5k"}


@pytest.fixture(scope="session", autouse=True)
def users():
    assert live_store.backend() == "sqlite", "tests must never touch Supabase"
    for u, role in (("t.admin", "admin"), ("t.staff", "staff"), ("t.other", "staff")):
        if not auth.get_user(u):
            auth.create_user(u, u.replace("t.", "Test ").title(), role, PASSWORDS[u])
    return PASSWORDS


@pytest.fixture()
def clean_live():
    live_store.run("DELETE FROM saveetha_live")
    live_store.run("DELETE FROM login_events")
    yield
    live_store.run("DELETE FROM saveetha_live")
    live_store.run("DELETE FROM login_events")
