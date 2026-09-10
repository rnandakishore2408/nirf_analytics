"""Where staff-entered live metrics are stored.

Two backends, chosen automatically:
  * Supabase (hosted PostgreSQL) when SUPABASE_DB_URL is set — used by the deployed app, because
    Streamlit Community Cloud wipes its own disk on every restart.
  * The local SQLite file (db/nirf.db, table saveetha_live) otherwise — used when running on a laptop.

The credential is read from the environment / .env locally, and from Streamlit secrets when deployed.
Every other part of the project keeps reading db/nirf.db, which is static reference data.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SQLITE_DB = ROOT / "db" / "nirf.db"

COLUMNS = ["entered_at", "entered_by", "academic_year", "metric", "value", "note"]

CREATE_PG = """
CREATE TABLE IF NOT EXISTS saveetha_live (
    id            bigserial PRIMARY KEY,
    entered_at    timestamptz NOT NULL DEFAULT now(),
    entered_by    text,
    academic_year text,
    metric        text NOT NULL,
    value         double precision NOT NULL,
    note          text
);
CREATE INDEX IF NOT EXISTS ix_saveetha_live_metric ON saveetha_live (metric, id DESC);
"""


def db_url() -> str | None:
    """The Supabase connection string, or None when it is absent or still a placeholder."""
    url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not url:
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


def backend() -> str:
    return "supabase" if db_url() else "sqlite"


def describe() -> str:
    url = db_url()
    if not url:
        return "Local file (db/nirf.db). Entries stay on this computer."
    host = re.sub(r"//[^@]*@", "//", url).split("/")[2]
    return f"Supabase ({host}). Entries are kept online and survive restarts."


def _pg():
    import psycopg

    return psycopg.connect(db_url(), connect_timeout=15)


def _sqlite() -> sqlite3.Connection:
    return sqlite3.connect(SQLITE_DB, check_same_thread=False)


def ensure_schema() -> None:
    """Create the table if it does not exist. Safe to call repeatedly."""
    if backend() == "supabase":
        with _pg() as con, con.cursor() as cur:
            cur.execute(CREATE_PG)
            con.commit()
    else:
        with _sqlite() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS saveetha_live (
                id INTEGER PRIMARY KEY AUTOINCREMENT, entered_at TEXT DEFAULT (datetime('now')),
                entered_by TEXT, academic_year TEXT, metric TEXT NOT NULL, value REAL NOT NULL, note TEXT)""")
            con.commit()


def add_entries(rows: list[tuple]) -> int:
    """rows: (entered_by, academic_year, metric, value, note). Returns how many were stored."""
    if not rows:
        return 0
    ensure_schema()
    if backend() == "supabase":
        with _pg() as con, con.cursor() as cur:
            cur.executemany(
                "INSERT INTO saveetha_live (entered_by, academic_year, metric, value, note) VALUES (%s,%s,%s,%s,%s)", rows)
            con.commit()
    else:
        with _sqlite() as con:
            con.executemany(
                "INSERT INTO saveetha_live (entered_by, academic_year, metric, value, note) VALUES (?,?,?,?,?)", rows)
            con.commit()
    return len(rows)


def latest_metrics() -> pd.DataFrame:
    """Most recent value per metric."""
    sql_pg = ("SELECT DISTINCT ON (metric) metric, value, academic_year, entered_at, entered_by, note "
              "FROM saveetha_live ORDER BY metric, id DESC")
    sql_lite = ("SELECT metric, value, academic_year, entered_at, entered_by, note FROM saveetha_live "
                "WHERE id IN (SELECT MAX(id) FROM saveetha_live GROUP BY metric) ORDER BY metric")
    return _read(sql_pg, sql_lite)


def history(limit: int = 500) -> pd.DataFrame:
    sql = f"SELECT entered_at, entered_by, academic_year, metric, value, note FROM saveetha_live ORDER BY id DESC LIMIT {int(limit)}"
    return _read(sql, sql)


def delete_last() -> None:
    ensure_schema()
    if backend() == "supabase":
        with _pg() as con, con.cursor() as cur:
            cur.execute("DELETE FROM saveetha_live WHERE id = (SELECT MAX(id) FROM saveetha_live)")
            con.commit()
    else:
        with _sqlite() as con:
            con.execute("DELETE FROM saveetha_live WHERE id=(SELECT MAX(id) FROM saveetha_live)")
            con.commit()


def _read(sql_pg: str, sql_lite: str) -> pd.DataFrame:
    try:
        ensure_schema()
        if backend() == "supabase":
            with _pg() as con, con.cursor() as cur:
                cur.execute(sql_pg)
                cols = [d.name for d in cur.description]
                return pd.DataFrame(cur.fetchall(), columns=cols)
        with _sqlite() as con:
            return pd.read_sql(sql_lite, con)
    except Exception as e:  # noqa: BLE001 - never take the dashboard down over the live table
        print(f"live_store: read failed ({e})")
        return pd.DataFrame(columns=COLUMNS)


def health() -> tuple[bool, str]:
    """(ok, message) — used by the app to show connection status."""
    try:
        ensure_schema()
        n = len(history(1))
        return True, f"{backend()} reachable, table ready ({'has entries' if n else 'empty'})"
    except Exception as e:  # noqa: BLE001
        return False, str(e).strip().splitlines()[0][:200]


if __name__ == "__main__":
    print("backend:", backend())
    print("where:  ", describe())
    ok, msg = health()
    print("health: ", "OK" if ok else "FAILED", "-", msg)
