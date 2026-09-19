"""Staff enter the college's current numbers. Each value is checked, stored with who and when, and the
estimate and 2026 forecast are recomputed on every page straight away."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import C_PRIMARY, card, clear_live_caches, csv_safe, fmt_inr, live_metrics, live_state, load_json, sec_base, store_health  # isort: skip

import auth
import live_estimate as LE
import live_store

user = auth.current_user(st.session_state)
if not user:
    st.stop()
is_admin = user["role"] == "admin"

st.title("Live data: the college's current numbers")
ok, msg = store_health()
st.caption(("🟢 " if ok else "🔴 ") + live_store.describe() + ("" if ok else f"  ·  {msg}"))
st.markdown("Enter the figures the college tracks (same definitions as the NIRF data-capture form). Leave a field blank to keep "
            "the current value. Every entry is kept with your name and the time, and every page, including the 2026 forecast, "
            "updates as soon as you save.")
st.info("**Publications and citations matter most.** They carry 75 of the 100 marks in the Research parameter and are the "
        "largest source of uncertainty in the estimate. The college is not catalogued in the open databases used for peer "
        "institutes, so the figures entered here are the only reliable source. Use Scopus: *Affiliation → Documents* for "
        "papers, and the *citation overview* (sum of the last three years) for citations.", icon="🔬")

base = sec_base()
live = live_metrics()
live_map = dict(zip(live.metric, live.value)) if not live.empty else {}
filed_year = int(base.year.iloc[0])


def filed_value(key: str) -> float | None:
    if key == "faculty_phd_pct":
        v = base.get("faculty_phd_pct", pd.Series([None])).iloc[0]
    else:
        v = base[key].iloc[0] if key in base.columns else None
    return float(v) if v is not None and pd.notna(v) else None


def show(v: float | None, kind: str) -> str:
    if v is None:
        return "–"
    return fmt_inr(v) if kind == "inr" else f"{v:,.1f}%" if kind == "pct" else f"{v:,.0f}"


SECTIONS = [
    ("🔬 Research", ["scopus_publications_3y", "scopus_citations_3y", "retracted_papers_3y", "sponsored_amount_3y_avg",
                    "sponsored_projects_3y", "consultancy_amount_3y_avg", "patents_published_3y", "patents_granted_3y"]),
    ("🎓 PhD", ["phd_pursuing_ft", "phd_pursuing_pt", "phd_grad_3y_avg"]),
    ("👩‍🏫 Faculty and students", ["faculty_parsed", "faculty_phd_pct", "students_total", "students_female", "students_outside_state"]),
    ("💼 Outcomes", ["graduated_total", "placed_total", "higher_studies_total", "median_salary_ug"]),
    ("💰 Spending", ["capex_per_student", "opex_per_student"]),
    ("🌍 Diversity (percentages)", ["women_students_pct", "outside_state_pct", "full_fee_reimb_pct"]),
]
if sorted(k for _, ks in SECTIONS for k in ks) != sorted(m.key for m in LE.METRICS):
    raise RuntimeError("every metric in live_estimate.METRICS must appear on the form exactly once")

with st.form("entry", clear_on_submit=True):
    c0, c1 = st.columns([2, 1])
    c0.markdown(f"Entering as **{user['display_name']}** (`{user['username']}`)")
    ay = c1.selectbox("Academic year these numbers refer to", ["2025-26", "2026-27", "2024-25"], index=0)
    vals: dict[str, float | None] = {}
    for title, keys in SECTIONS:
        st.markdown(f"**{title}**")
        cols = st.columns(3)
        for i, key in enumerate(keys):
            m = LE.METRIC_BY_KEY[key]
            fv = filed_value(key)
            hint = f"Filed ({filed_year}): {show(fv, m.kind)}"
            if key in live_map:
                hint += f" · latest entry: {show(live_map[key], m.kind)}"
            with cols[i % 3]:
                vals[key] = st.number_input(m.label, min_value=0.0, max_value=float(m.max), value=None, step=1.0,
                                            format="%.2f" if m.kind == "pct" else "%.0f", key=f"in_{key}",
                                            help=f"{hint}\n\nMoves: {m.moves}")
                st.caption(("✅ " if m.scored else "📋 ") + m.moves)
    note = st.text_area("Note (optional)", max_chars=500, placeholder="e.g. placement data as of Aug 2026, salary from 620 offers")
    submitted = st.form_submit_button("Save entries", type="primary")

if submitted:
    entered = {k: float(v) for k, v in vals.items() if v is not None}
    current = {m.key: v for m in LE.METRICS if (v := filed_value(m.key)) is not None}
    current.update({k: float(v) for k, v in live_map.items()})
    problems = LE.validate(entered, current)
    if not entered:
        st.warning("Nothing to save: fill at least one field.")
    elif problems:
        st.error("Nothing was saved. Please fix:\n\n" + "\n".join(f"- {p}" for p in problems))
    elif not auth.allow(user["username"], "entry", 30, 3600):
        st.error("Too many saves in the last hour. Please wait a little and try again.")
    else:
        rows = [(user["display_name"], ay, k, v, (note or "").strip()[:500]) for k, v in entered.items()]
        try:
            n = live_store.add_entries(rows, user["username"])
            clear_live_caches()
            st.session_state["saved_msg"] = f"Saved {n} value(s). The estimate and the 2026 forecast below now include them."
            st.rerun()
        except Exception as e:  # noqa: BLE001
            print(f"live entry save failed with {type(e).__name__}: {str(e)[:200]}")
            st.error("Could not save right now; the database did not respond. Nothing was stored. Please try again.")

if msg_ok := st.session_state.pop("saved_msg", None):
    st.success(msg_ok)

st.divider()
st.subheader("Re-scored with the latest entries")
state = live_state()
est, fc = state["estimate"], state["forecast"]
if not state["has_live"]:
    st.info("No staff entries yet: the figures below use the filed numbers only.")
else:
    st.caption(f"{state['n_metrics']} metric(s) entered · latest entry {state['last_entry']}")
k = st.columns(6)
for col, p in zip(k, ("tlr", "rpc", "go", "oi")):
    with col:
        card(f"{p.upper()} (est.)", f"{est['params'][p]:.1f}", f"filed only: {est['filed'][p]:.1f}")
static = load_json("prediction_2026.json").get("saveetha", {})
with k[4]:
    card("2026 total (est.)", f"{fc['total_score']['median']:.1f}", f"filed only: {static.get('total_score', {}).get('median', '–')}")
with k[5]:
    card("Expected position", f"≈ rank {fc['expected_rank']}", f"filed only: ≈ {static.get('expected_rank', '–')}")

bp = fc["band_probabilities"]
fig = go.Figure(go.Bar(x=LE.BAND_ORDER, y=[100 * bp[b] for b in LE.BAND_ORDER], text=[f"{100 * bp[b]:.0f}%" for b in LE.BAND_ORDER],
                       textposition="outside", marker_color=[C_PRIMARY if b == fc["most_likely_band"] else "#94A3B8" for b in LE.BAND_ORDER]))
fig.update_layout(height=260, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="Chance (%)", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
st.plotly_chart(fig, width="stretch")
if est["notes"]:
    st.markdown("**How the entries were used**\n" + "\n".join(f"- {n}" for n in est["notes"]))
if est["recorded_only"]:
    st.caption("Recorded but not scored: " + ", ".join(LE.METRIC_BY_KEY[k].label for k in est["recorded_only"]) + ".")

st.divider()
st.subheader("Entry history")
hist = live_store.history(500)
if hist.empty:
    st.caption("No entries yet.")
else:
    show_hist = hist.assign(field=hist.metric.map(lambda k: LE.METRIC_BY_KEY[k].label if k in LE.METRIC_BY_KEY else k))
    st.dataframe(show_hist[["id", "entered_at", "entered_by", "academic_year", "field", "value", "note"]], hide_index=True,
                 width="stretch", height=360)
    st.download_button("Download history (CSV)", csv_safe(show_hist.drop(columns=["username"])), "saveetha_live_history.csv", "text/csv")
    mine = hist if is_admin else hist[hist.username == user["username"]]
    with st.expander("Remove an entry made by mistake" + ("" if is_admin else " (your own entries)")):
        if mine.empty:
            st.caption("You have no entries to remove.")
        else:
            opts = {int(r.id): f"#{int(r.id)} · {r.entered_at} · {LE.METRIC_BY_KEY[r.metric].label if r.metric in LE.METRIC_BY_KEY else r.metric} = {r.value:g}"
                    for r in mine.head(100).itertuples()}
            pick = st.selectbox("Entry", list(opts), format_func=opts.get)
            sure = st.checkbox("Yes, remove this entry. It stays in the audit log, marked as removed.")
            if st.button("Remove entry", disabled=not sure):
                if live_store.soft_delete(pick, user["username"], is_admin):
                    clear_live_caches()
                    st.session_state["saved_msg"] = f"Entry #{pick} removed. The previous value for that field applies again."
                    st.rerun()
                else:
                    st.error("That entry could not be removed (already removed, or not yours).")
