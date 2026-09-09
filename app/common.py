"""Shared helpers for the Streamlit app: DB access, cached loaders, constants, styling."""
from __future__ import annotations

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


def live_metrics() -> pd.DataFrame:
    """Latest staff-entered value per metric (not cached: changes as staff type)."""
    with connect() as con:
        return pd.read_sql("SELECT metric, value, academic_year, entered_at, entered_by, note FROM saveetha_live "
                           "WHERE id IN (SELECT MAX(id) FROM saveetha_live GROUP BY metric) ORDER BY metric", con)


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
    st.markdown(f'<div class="metric-card"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>',
                unsafe_allow_html=True)
