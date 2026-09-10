"""Staff enter the college's current numbers; the model re-scores instantly and the values are
stored (with who/when) in the saveetha_live table so the chatbot and what-if page can use them."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

import live_store
from common import SEC_ID, WEIGHTS, card, fmt_inr, inject_css, live_metrics, load_json, submissions

st.set_page_config(page_title="Live Data Entry", page_icon="📝", layout="wide")
inject_css()
st.title("Live data — Saveetha's current numbers")
ok, msg = live_store.health()
st.caption(("🟢 " if ok else "🔴 ") + live_store.describe() + ("" if ok else f"  ·  problem: {msg}"))
st.markdown("Enter the figures the college tracks internally (same definitions as the NIRF data-capture form). Every entry is time-stamped and kept, "
            "so you can see the trend and the model re-scores with the latest values. Leave a field blank to keep the filed value.")
st.info("**Publications and citations matter most.** They carry 75 of the 100 marks in the Research parameter and are the largest "
        "single source of uncertainty in our estimate. NIRF's public PDFs omit them, and this college is not catalogued in the open "
        "publication databases we use for peer institutes, so the figures you enter here are the only reliable source we have.", icon="🔬")

METRICS = [
    ("students_total", "Total students enrolled (UG+PG, all years)", "count"),
    ("students_female", "Women students (count)", "count"),
    ("students_outside_state", "Students from other states (count)", "count"),
    ("faculty_parsed", "Full-time faculty (count)", "count"),
    ("faculty_phd_pct", "Faculty with PhD (%)", "pct"),
    ("phd_pursuing_ft", "Full-time PhD scholars enrolled", "count"),
    ("phd_pursuing_pt", "Part-time PhD scholars enrolled", "count"),
    ("phd_grad_3y_avg", "PhDs awarded per year (3-yr average)", "count"),
    ("graduated_total", "Students graduated in stipulated time (latest batch)", "count"),
    ("placed_total", "Students placed (latest batch)", "count"),
    ("higher_studies_total", "Students gone for higher studies (latest batch)", "count"),
    ("median_salary_ug", "Median UG salary (₹ per annum)", "inr"),
    ("capex_per_student", "Capital expenditure per student per year (₹)", "inr"),
    ("opex_per_student", "Operational expenditure per student per year (₹)", "inr"),
    ("sponsored_amount_3y_avg", "Sponsored research received per year (₹, 3-yr avg)", "inr"),
    ("sponsored_projects_3y", "Sponsored projects (count, last 3 years)", "count"),
    ("consultancy_amount_3y_avg", "Consultancy received per year (₹, 3-yr avg)", "inr"),
    ("patents_published_3y", "Patents published (last 3 years)", "count"),
    ("patents_granted_3y", "Patents granted (last 3 years)", "count"),
    ("scopus_publications_3y", "Publications, last 3 years (Scopus/WoS) — 35 of RPC's 100 marks", "count"),
    ("scopus_citations_3y", "Citations, last 3 years — 40 of RPC's 100 marks", "count"),
    ("retracted_papers_3y", "Retracted papers (last 3 years) — NIRF 2025+ negative marking", "count"),
    ("women_students_pct", "Women students (%)", "pct"),
    ("outside_state_pct", "Students from other states (%)", "pct"),
    ("full_fee_reimb_pct", "Students on full tuition-fee reimbursement (%)", "pct"),
]

sub = submissions()
base = sub[sub.institute_id == SEC_ID].sort_values("year").tail(1).reset_index(drop=True)
live = live_metrics()
live_map = dict(zip(live.metric, live.value)) if not live.empty else {}

with st.form("entry"):
    c0, c1 = st.columns([1, 1])
    entered_by = c0.text_input("Your name / role", placeholder="e.g. Dr. X, IQAC coordinator")
    ay = c1.text_input("Academic year these numbers refer to", value="2025-26")
    vals = {}
    cols = st.columns(3)
    for i, (key, label, kind) in enumerate(METRICS):
        filed = base[key].iloc[0] if key in base.columns and pd.notna(base[key].iloc[0]) else None
        hint = f"filed {fmt_inr(filed) if kind == 'inr' else f'{filed:g}'}" if filed is not None else "not in filing"
        if key in live_map:
            hint += f" · live {live_map[key]:g}"
        with cols[i % 3]:
            vals[key] = st.number_input(f"{label}  ({hint})", min_value=0.0, value=None, step=1.0, format="%f", key=key)
    note = st.text_area("Note (optional)", placeholder="e.g. placement data as of Aug 2026, salary from 620 offers")
    ok = st.form_submit_button("Save entries", type="primary")

if ok:
    rows = [(entered_by or "staff", ay, k, float(v), note) for k, v in vals.items() if v is not None]
    if not rows:
        st.warning("Nothing to save — fill at least one field.")
    else:
        try:
            n = live_store.add_entries(rows)
            st.success(f"Saved {n} value(s) to {live_store.backend()}. The what-if page and the chatbot now see them.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not save: {e}")

st.divider()
st.subheader("Instant re-score with live values")


@st.cache_resource
def model():
    from score_model import ScoreModel
    return ScoreModel.load()


sm = model()
live = live_metrics()
if live.empty:
    st.info("No live values yet — the estimate below uses the filed numbers.")
from score_model import apply_live
w, applied = apply_live(base, live)
if applied:
    st.caption("Live values applied to the estimate below: " + ", ".join(sorted(applied)))
p0 = sm.predict_params(base).iloc[0]; p1 = sm.predict_params(w).iloc[0]
pr = load_json("prediction_2026.json").get("saveetha", {}).get("pr_assumption", {}).get("median", 5.0)
t0 = sum(p0[p] * WEIGHTS[p] for p in ("tlr", "rpc", "go", "oi")) + WEIGHTS["pr"] * pr
t1 = sum(p1[p] * WEIGHTS[p] for p in ("tlr", "rpc", "go", "oi")) + WEIGHTS["pr"] * pr
k1, k2, k3, k4, k5 = st.columns(5)
for col, p in zip((k1, k2, k3, k4), ("tlr", "rpc", "go", "oi")):
    with col:
        card(f"{p.upper()} (est.)", f"{p1[p]:.1f}", f"filed: {p0[p]:.1f}")
with k5:
    card("Total (est.)", f"{t1:.1f}", f"filed: {t0:.1f} · PR assumed {pr}")

st.divider()
st.subheader("Entry history")
hist = live_store.history(500)
if hist.empty:
    st.caption("No entries yet.")
else:
    st.dataframe(hist, hide_index=True, use_container_width=True, height=360)
    st.download_button("Download history CSV", hist.to_csv(index=False).encode(), "saveetha_live_history.csv", "text/csv")
    with st.expander("Delete the most recent entry (mistakes)"):
        if st.button("Delete last entry"):
            live_store.delete_last()
            st.cache_data.clear()
            st.rerun()
