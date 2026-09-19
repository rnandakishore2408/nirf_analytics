"""Where staff-entered live metrics and staff accounts are stored.

Two backends, chosen automatically:
  * Supabase (hosted PostgreSQL) when SUPABASE_DB_URL is set: used by the deployed app, because
    Streamlit Community Cloud wipes its own disk on every restart.
  * A local SQLite file, db/local_store.db (git-ignored), otherwise. db/nirf.db stays read-only
    reference data, so the chatbot's SQL tool can never see accounts or password hashes.

Tables
  saveetha_live   one row per value entered; rows are never deleted, only marked deleted_at/by,
                  so every change stays auditable.
  app_users       staff accounts (no sign-up; created with scripts/manage_users.py).
  login_events    every sign-in attempt, used for lock-outs and the audit trail.

On Supabase the tables get row-level security with no policies and no grants to the public `anon` /
`authenticated` roles, so the Supabase REST API cannot read or change them; only this app's direct
database connection can.

The credential is read from the environment / .env locally, and from Streamlit secrets when deployed.
"""
from __future__ import annotations

import atexit
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

COLUMNS = ["id", "entered_at", "entered_by", "username", "academic_year", "metric", "value", "note"]

PG_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS saveetha_live (
        id            bigserial PRIMARY KEY,
        entered_at    timestamptz NOT NULL DEFAULT now(),
        entered_by    text,
        academic_year text,
        metric        text NOT NULL,
        value         double precision NOT NULL,
        note          text
    )""",
    "ALTER TABLE saveetha_live ADD COLUMN IF NOT EXISTS username text",
    "ALTER TABLE saveetha_live ADD COLUMN IF NOT EXISTS deleted_at timestamptz",
    "ALTER TABLE saveetha_live ADD COLUMN IF NOT EXISTS deleted_by text",
    "CREATE INDEX IF NOT EXISTS ix_saveetha_live_metric ON saveetha_live (metric, id DESC)",
    """CREATE TABLE IF NOT EXISTS app_users (
        username      text PRIMARY KEY,
        display_name  text NOT NULL,
        role          text NOT NULL CHECK (role IN ('admin', 'staff')),
        pw_hash       text NOT NULL,
        active        boolean NOT NULL DEFAULT true,
        created_at    timestamptz NOT NULL DEFAULT now(),
        last_login_at timestamptz,
        pw_changed_at timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS login_events (
        id        bigserial PRIMARY KEY,
        ts        double precision NOT NULL,
        username  text NOT NULL,
        success   boolean NOT NULL,
        detail    text
    )""",
    "CREATE INDEX IF NOT EXISTS ix_login_events_user_ts ON login_events (username, ts DESC)",
]
PG_LOCKDOWN = """
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['saveetha_live', 'app_users', 'login_events'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
      EXECUTE format('REVOKE ALL ON TABLE %I FROM anon', t);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
      EXECUTE format('REVOKE ALL ON TABLE %I FROM authenticated', t);
    END IF;
  END LOOP;
END $$;
"""
SQLITE_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS saveetha_live (
        id INTEGER PRIMARY KEY AUTOINCREMENT, entered_at TEXT DEFAULT (datetime('now')),
        entered_by TEXT, academic_year TEXT, metric TEXT NOT NULL, value REAL NOT NULL, note TEXT,
        username TEXT, deleted_at TEXT, deleted_by TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_saveetha_live_metric ON saveetha_live (metric, id DESC)",
    """CREATE TABLE IF NOT EXISTS app_users (
        username TEXT PRIMARY KEY, display_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'staff')), pw_hash TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT (datetime('now')),
        last_login_at TEXT, pw_changed_at TEXT DEFAULT (datetime('now')))""",
    """CREATE TABLE IF NOT EXISTS login_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, username TEXT NOT NULL,
        success INTEGER NOT NULL, detail TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_login_events_user_ts ON login_events (username, ts DESC)",
]


def db_url() -> str | None:
    """The Supabase connection string, or None when it is absent or still a placeholder."""
    url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not url and "SUPABASE_DB_URL" not in os.environ:
        try:  # deployed: Streamlit secrets
            import streamlit as st

            url = str(st.secrets.get("SUPABASE_DB_URL", "")).strip()
        except Exception:  # noqa: BLE001 - no streamlit, or no secrets file
            url = ""
    if not url or "[YOUR-PASSWORD]" in url or not url.startswith(("postgresql://", "postgres://")):
        return None
    # Supabase prints the password as [PLACEHOLDER]; people often keep the brackets when pasting.
    m = re.match(r"^(postgres(?:ql)?://[^:]+:)\[([A-Za-z0-9]+)\](@.*)$", url)
    if m:
        url = m.group(1) + m.group(2) + m.group(3)
    return url


def sqlite_path() -> Path:
    return Path(os.getenv("NIRF_LOCAL_DB", str(ROOT / "db" / "local_store.db")))


def backend() -> str:
    return "supabase" if db_url() else "sqlite"


def describe() -> str:
    url = db_url()
    if not url:
        return f"Local file ({sqlite_path().name}). Entries stay on this computer."
    host = re.sub(r"//[^@]*@", "//", url).split("/")[2].split(":")[0]
    return f"Supabase ({host}). Entries are kept online and survive restarts."


# ---------- connections ----------
_pool = None
_pool_lock = threading.Lock()
_schema_ready: set[str] = set()
_schema_lock = threading.Lock()


def _pg_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            from psycopg_pool import ConnectionPool

            # A handful of connections is plenty for a staff tool and stays well inside Supabase's free
            # pooler limit. Autocommit: every statement here is a single atomic statement, so there is no
            # BEGIN/COMMIT round trip (the multi-row insert opens its own transaction). Each round trip to
            # Supabase costs ~100 ms from India and more from the host, so this matters more than anything.
            _pool = ConnectionPool(db_url(), min_size=1, max_size=4, timeout=20, max_idle=300,
                                   kwargs={"connect_timeout": 15, "autocommit": True}, open=True)
            atexit.register(_pool.close, timeout=2)
        return _pool


@contextmanager
def _sqlite():
    """One short-lived connection: commit on success, roll back on error, always close."""
    p = sqlite_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=15)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def ensure_schema() -> None:
    """Create or migrate the tables once per process. Safe to call repeatedly."""
    key = f"{backend()}:{db_url() or sqlite_path()}"
    if key in _schema_ready:
        return
    with _schema_lock:
        if key in _schema_ready:
            return
        if backend() == "supabase":
            with _pg_pool().connection() as con, con.transaction(), con.cursor() as cur:
                for stmt in PG_SCHEMA:
                    cur.execute(stmt)
                cur.execute(PG_LOCKDOWN)
        else:
            with _sqlite() as con:
                for stmt in SQLITE_SCHEMA:
                    con.execute(stmt)
                cols = {r[1] for r in con.execute("PRAGMA table_info(saveetha_live)")}
                for c in ("username", "deleted_at", "deleted_by"):
                    if c not in cols:
                        con.execute(f"ALTER TABLE saveetha_live ADD COLUMN {c} TEXT")  # nosec B608 - fixed names
        _schema_ready.add(key)


def _pg(fn):
    """Run fn(cursor) on a pooled connection. A connection the pooler closed while idle fails on first use;
    that one error is retried once on a fresh connection instead of reaching the user."""
    import psycopg

    for attempt in (1, 2):
        try:
            with _pg_pool().connection() as con, con.cursor() as cur:
                return fn(cur)
        except psycopg.OperationalError:
            if attempt == 2:
                raise


def run(sql: str, params: tuple = (), fetch: bool = False) -> list[tuple] | int:
    """Execute one parameterised statement on whichever backend is active. Write the SQL with %s
    placeholders; they become ? for SQLite. Returns rows when fetch=True, else the affected row count."""
    ensure_schema()
    if backend() == "supabase":
        def go(cur):
            cur.execute(sql, params)
            return cur.fetchall() if fetch else cur.rowcount
        return _pg(go)
    with _sqlite() as con:
        cur = con.execute(sql.replace("%s", "?"), params)
        return cur.fetchall() if fetch else cur.rowcount


def frame(sql: str, params: tuple = ()) -> pd.DataFrame:
    ensure_schema()
    if backend() == "supabase":
        def go(cur):
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        return _pg(go)
    with _sqlite() as con:
        return pd.read_sql(sql.replace("%s", "?"), con, params=params)


# ---------- live metrics ----------
def add_entries(rows: list[tuple], username: str) -> int:
    """rows: (entered_by, academic_year, metric, value, note). Returns how many were stored."""
    if not rows:
        return 0
    ensure_schema()
    sql = "INSERT INTO saveetha_live (entered_by, academic_year, metric, value, note, username) VALUES (%s,%s,%s,%s,%s,%s)"
    full = [tuple(r) + (username,) for r in rows]
    if backend() == "supabase":
        with _pg_pool().connection() as con, con.transaction(), con.cursor() as cur:  # all rows or none
            cur.executemany(sql, full)
    else:
        with _sqlite() as con:
            con.executemany(sql.replace("%s", "?"), full)
    return len(rows)


def latest_metrics() -> pd.DataFrame:
    """Most recent non-deleted value per metric."""
    sql_pg = ("SELECT DISTINCT ON (metric) metric, value, academic_year, entered_at, entered_by, note "
              "FROM saveetha_live WHERE deleted_at IS NULL ORDER BY metric, id DESC")
    sql_lite = ("SELECT metric, value, academic_year, entered_at, entered_by, note FROM saveetha_live "
                "WHERE id IN (SELECT MAX(id) FROM saveetha_live WHERE deleted_at IS NULL GROUP BY metric) ORDER BY metric")
    return _read(sql_pg if backend() == "supabase" else sql_lite)


def history(limit: int = 500, include_deleted: bool = False) -> pd.DataFrame:
    where = "" if include_deleted else "WHERE deleted_at IS NULL "
    extra = ", deleted_at, deleted_by" if include_deleted else ""
    sql = (f"SELECT id, entered_at, entered_by, username, academic_year, metric, value, note{extra} "  # nosec B608 - fixed fragments
           f"FROM saveetha_live {where}ORDER BY id DESC LIMIT %s")
    return _read(sql, (int(limit),))


def soft_delete(entry_id: int, username: str, is_admin: bool) -> bool:
    """Mark one entry deleted. Staff may delete only their own entries; admins any. Returns success."""
    if is_admin:
        n = run("UPDATE saveetha_live SET deleted_at = CURRENT_TIMESTAMP, deleted_by = %s WHERE id = %s AND deleted_at IS NULL",
                (username, int(entry_id)))
    else:
        n = run("UPDATE saveetha_live SET deleted_at = CURRENT_TIMESTAMP, deleted_by = %s "
                "WHERE id = %s AND username = %s AND deleted_at IS NULL", (username, int(entry_id), username))
    return n == 1


def _read(sql: str, params: tuple = ()) -> pd.DataFrame:
    try:
        return frame(sql, params)
    except Exception as e:  # noqa: BLE001 - never take the dashboard down over the live table
        print(f"live_store: read failed ({type(e).__name__}: {str(e)[:200]})")
        return pd.DataFrame(columns=COLUMNS)


def health() -> tuple[bool, str]:
    """(ok, message) for the status line. The message never contains the connection string."""
    try:
        run("SELECT 1 FROM saveetha_live LIMIT 1", fetch=True)
        return True, f"{backend()} reachable"
    except Exception as e:  # noqa: BLE001
        print(f"live_store: health check failed ({type(e).__name__}: {str(e)[:200]})")
        return False, "the database could not be reached; entries cannot be saved right now"


if __name__ == "__main__":
    print("backend:", backend())
    print("where:  ", describe())
    ok, msg = health()
    print("health: ", "OK" if ok else "FAILED", "-", msg)
