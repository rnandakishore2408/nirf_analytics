"""Shared helpers for the Streamlit app: DB access, cached loaders, constants, styling."""
from __future__ import annotations

import html
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "nirf.db"
PROC = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "models"))

SEC_ID = "IR-E-C-16590"
SEC_NAME = "Saveetha Engineering College"
PARAMS = ["tlr", "rpc", "go", "oi", "pr"]
PARAM_LABEL = {"tlr": "TLR · Teaching, Learning & Resources", "rpc": "RPC · Research & Professional Practice",
               "go": "GO · Graduation Outcomes", "oi": "OI · Outreach & Inclusivity", "pr": "PR · Perception"}
WEIGHTS = {"tlr": 0.30, "rpc": 0.30, "go": 0.20, "oi": 0.10, "pr": 0.10}

# palette (brand-neutral, works on light & dark)
C_PRIMARY = "#4F6DF5"   # Saveetha / highlight
C_MUTED = "#94A3B8"
C_SERIES = ["#4F6DF5", "#D64D7A", "#0E9AA7", "#C98A0A", "#8B5CF6"]
C_PARAM = {"tlr": "#4F6DF5", "rpc": "#D64D7A", "go": "#0E9AA7", "oi": "#C98A0A", "pr": "#8B5CF6"}


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB, check_same_thread=False)


@st.cache_data(ttl=300)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    with connect() as con:
        return pd.read_sql(sql, con, params=params)


@st.cache_data(ttl=300)
def load_json(name: str) -> dict:
    p = PROC / name
    return json.loads(p.read_text()) if p.exists() else {}


@st.cache_data(ttl=300)
def rankings(category: str = "Engineering") -> pd.DataFrame:
    df = q('SELECT r.year, r.rank, r.institute_id, r.name, r.city, r.state, i.type_label, r.tlr, r.rpc, r."go" AS go, r.oi, r.pr, r.score '
           'FROM rankings r LEFT JOIN institutions i USING(institute_id) WHERE r.category=? ORDER BY r.year, r.rank', (category,))
    return df


@st.cache_data(ttl=300)
def submissions() -> pd.DataFrame:
    return q("SELECT * FROM submissions WHERE category='Engineering'")


@st.cache_data(ttl=300)
def saveetha_history() -> pd.DataFrame:
    return q("SELECT * FROM v_saveetha_history")


@st.cache_data(ttl=60, show_spinner=False)
def live_metrics() -> pd.DataFrame:
    """Latest staff-entered value per metric (Supabase when configured, else the local file).
    Cached for a minute; saving or deleting an entry clears the cache immediately."""
    import live_store
    return live_store.latest_metrics()


@st.cache_data(ttl=30, show_spinner=False)
def store_health() -> tuple[bool, str]:
    import live_store
    return live_store.health()


@st.cache_resource(show_spinner=False)
def model():
    from score_model import ScoreModel
    return ScoreModel.load()


def sec_base() -> pd.DataFrame:
    """The college's latest NIRF filing, one row."""
    sub = submissions()
    return sub[sub.institute_id == SEC_ID].sort_values("year").tail(1).reset_index(drop=True)


def base_phd_pct() -> float | None:
    v = sec_base().get("faculty_phd_pct", pd.Series([None])).iloc[0]
    return float(v) if v is not None and pd.notna(v) else None


@st.cache_data(ttl=60, show_spinner=False)
def live_state() -> dict:
    """Estimate + 2026 forecast from the filing plus the latest staff entries. Everything that shows the
    college's score reads this, so every page agrees. `has_live` is False when nobody has entered data;
    the forecast then equals the saved one in prediction_2026.json."""
    import live_estimate as LE
    live = live_metrics()
    sm = model()
    est = LE.estimate(sm, sec_base(), live, base_phd_pct())
    thr = load_json("prediction_2026.json")["thresholds"]
    fc = LE.forecast(est["params"], est["sd"], sm.weights, thr, LE.pr_pool_from(rankings()))
    last = None
    if not live.empty:
        last = pd.to_datetime(live.entered_at, utc=True, errors="coerce").max()
    return {"has_live": not live.empty, "estimate": est, "forecast": fc, "n_metrics": int(len(live)),
            "last_entry": None if last is None or pd.isna(last) else last.strftime("%d %b %Y, %H:%M UTC")}


def clear_live_caches() -> None:
    live_metrics.clear()
    live_state.clear()


def csv_safe(df: pd.DataFrame) -> bytes:
    """CSV export that spreadsheet programs will not execute: text cells starting with = + - @ (or a tab/CR)
    are prefixed with an apostrophe, the standard defence against formula injection."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object or pd.api.types.is_string_dtype(out[c]):
            out[c] = out[c].map(lambda v: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v)
    return out.to_csv(index=False).encode()


def fmt_inr(x: float) -> str:
    if x is None or pd.isna(x):
        return "–"
    if x >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .metric-card {border:1px solid rgba(128,128,128,.25); border-radius:12px; padding:14px 16px; margin-bottom:8px;}
        .metric-card .label {font-size:.8rem; color:#94A3B8; letter-spacing:.02em;}
        .metric-card .value {font-size:1.6rem; font-weight:600; line-height:1.2;}
        .metric-card .sub {font-size:.8rem; color:#94A3B8;}
        .pill {display:inline-block; padding:2px 10px; border-radius:999px; font-size:.75rem; background:rgba(79,109,245,.12); color:#4F6DF5;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def card(label: str, value: str, sub: str = "") -> None:
    e = lambda x: html.escape(str(x))  # noqa: E731 - values are ours, but never render unescaped text as HTML
    st.markdown(f'<div class="metric-card"><div class="label">{e(label)}</div><div class="value">{e(value)}</div><div class="sub">{e(sub)}</div></div>',
                unsafe_allow_html=True)
