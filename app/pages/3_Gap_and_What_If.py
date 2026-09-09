from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import C_PARAM, C_PRIMARY, PARAMS, SEC_ID, WEIGHTS, card, fmt_inr, inject_css, live_metrics, load_json, submissions

st.set_page_config(page_title="Gap & What-If", page_icon="🧮", layout="wide")
inject_css()
st.title("Gap & What-If — what moves Saveetha's score")


@st.cache_resource
def model():
    from score_model import ScoreModel
    return ScoreModel.load()


sm = model()
sub = submissions()
base = sub[sub.institute_id == SEC_ID].sort_values("year").tail(1).reset_index(drop=True)
pred = load_json("prediction_2026.json")
cut26 = pred.get("thresholds", {}).get("forecast_2026", {}).get("100", 47.0)
cut25 = 45.55

st.markdown(f"Baseline = the numbers in Saveetha's **NIRF {int(base.year.iloc[0])} filing**. Move the sliders to the values the college can realistically "
            f"reach and watch the estimated parameter scores and total move. Targets: **{cut25}** (2025 cut-off) and **≈{cut26}** (2026 forecast).")

live = live_metrics()
use_live = st.toggle("Start from staff-entered live values where available", value=not live.empty)
b = base.copy()
if use_live and not live.empty:
    for _, row in live.iterrows():
        if row.metric in b.columns:
            b.loc[0, row.metric] = row.value
    st.caption("Live values applied: " + ", ".join(f"{m}={v:g}" for m, v in zip(live.metric, live.value) if m in b.columns))

st.subheader("Levers")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("**Research & PhD**")
    phd_ft = st.slider("Full-time PhD scholars enrolled", 0, 600, int(b.phd_pursuing_ft.iloc[0] or 0), 5)
    phd_grad = st.slider("PhDs graduated per year (3-yr avg)", 0, 150, int(b.phd_grad_3y_avg.iloc[0] or 0), 1)
    spons = st.slider("Sponsored research per year (₹ lakh)", 0, 2000, int((b.sponsored_amount_3y_avg.iloc[0] or 0) / 1e5), 10)
    cons = st.slider("Consultancy per year (₹ lakh)", 0, 1000, int((b.consultancy_amount_3y_avg.iloc[0] or 0) / 1e5), 5)
with c2:
    st.markdown("**Money & faculty**")
    opex = st.slider("Operating spend per student per year (₹ thousand)", 20, 600, int((b.opex_per_student.iloc[0] or 0) / 1e3), 5)
    capex = st.slider("Capital spend per student per year (₹ thousand)", 0, 300, int((b.capex_per_student.iloc[0] or 0) / 1e3), 2)
    fac = st.slider("Faculty count", 100, 900, int(b.faculty_parsed.fillna(b.faculty_entered).iloc[0] or 300), 5)
    students = st.slider("Total students (UG+PG)", 1000, 12000, int(b.students_total.iloc[0]), 50)
with c3:
    st.markdown("**Outcomes & inclusivity**")
    salary = st.slider("Median UG salary (₹ lakh)", 2.0, 25.0, float((b.median_salary_ug.iloc[0] or 0) / 1e5), 0.25)
    placed = st.slider("Placed + higher studies (% of graduates)", 40, 100, int(100 * min(1, b.placed_or_hs_rate.iloc[0] or 0)), 1)
    grad = st.slider("Graduating in stipulated time (% of intake)", 40, 100, int(100 * min(1, b.graduation_rate.iloc[0] or 0)), 1)
    out_state = st.slider("Students from other states (%)", 0, 80, int(b.outside_state_pct.iloc[0] or 0), 1)
    women = st.slider("Women students (%)", 0, 60, int(b.women_students_pct.iloc[0] or 0), 1)
    fee = st.slider("Students on full fee reimbursement (%)", 0, 100, int(b.full_fee_reimb_pct.iloc[0] or 0), 1)
pr = st.slider("Perception score (unknown — survey based; colleges ranked 60-100 score 1-25)", 0.0, 40.0, float(pred.get("saveetha", {}).get("pr_assumption", {}).get("median", 5.0)), 0.5)

w = b.copy()
w["phd_pursuing_ft"], w["phd_grad_3y_avg"], w["sponsored_amount_3y_avg"], w["consultancy_amount_3y_avg"] = phd_ft, phd_grad, spons * 1e5, cons * 1e5
w["opex_per_student"], w["capex_per_student"], w["faculty_parsed"], w["faculty_entered"], w["students_total"] = opex * 1e3, capex * 1e3, fac, fac, students
w["median_salary_ug"], w["placed_or_hs_rate"], w["graduation_rate"] = salary * 1e5, placed / 100, grad / 100
w["outside_state_pct"], w["women_students_pct"], w["full_fee_reimb_pct"] = out_state, women, fee
w["sponsored_projects_3y"] = max(int(b.sponsored_projects_3y.iloc[0] or 0), int(spons / 5))

p0 = sm.predict_params(b).iloc[0]
p1 = sm.predict_params(w).iloc[0]
t0 = float(sum(p0[p] * WEIGHTS[p] for p in ("tlr", "rpc", "go", "oi")) + WEIGHTS["pr"] * pr)
t1 = float(sum(p1[p] * WEIGHTS[p] for p in ("tlr", "rpc", "go", "oi")) + WEIGHTS["pr"] * pr)

st.divider()
k1, k2, k3, k4 = st.columns(4)
with k1:
    card("Baseline estimated total", f"{t0:.1f}", "from the filing (+ chosen PR)")
with k2:
    card("What-if estimated total", f"{t1:.1f}", f"{t1 - t0:+.1f} points")
with k3:
    card("Gap to 2026 forecast cut-off", f"{cut26 - t1:+.1f}", "negative = inside the top 100")
with k4:
    band = "top 100" if t1 >= cut26 else "101-150" if t1 >= cut26 * 0.903 else "151-200" if t1 >= cut26 * 0.836 else "201-250" if t1 >= cut26 * 0.787 else "251-300" if t1 >= cut26 * 0.745 else "below 300"
    card("Implied 2026 band", band, "using the forecast threshold curve")

fig = go.Figure()
x = [p.upper() for p in ("tlr", "rpc", "go", "oi")]
fig.add_trace(go.Bar(name="Baseline", x=x, y=[p0[p] for p in ("tlr", "rpc", "go", "oi")], marker_color="#94A3B8", text=[f"{p0[p]:.0f}" for p in ("tlr", "rpc", "go", "oi")], textposition="outside"))
fig.add_trace(go.Bar(name="What-if", x=x, y=[p1[p] for p in ("tlr", "rpc", "go", "oi")], marker_color=C_PRIMARY, text=[f"{p1[p]:.0f}" for p in ("tlr", "rpc", "go", "oi")], textposition="outside"))
fig.update_layout(barmode="group", height=360, margin=dict(l=10, r=10, t=20, b=10), yaxis=dict(range=[0, 100], title="Estimated parameter score"),
                  legend=dict(orientation="h", y=1.12), bargap=0.3, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
fig.update_yaxes(gridcolor="rgba(128,128,128,.15)")
st.plotly_chart(fig, use_container_width=True)

st.subheader("What each single change is worth (from the 2026 filing)")
lev = pd.DataFrame(pred.get("what_if_levers", []))
if not lev.empty:
    fig2 = go.Figure(go.Bar(x=lev.delta_total, y=lev.lever, orientation="h", marker_color=C_PRIMARY, text=[f"{v:+.2f}" for v in lev.delta_total], textposition="outside",
                            hovertemplate="%{y}: %{x:+.2f} pts<extra></extra>"))
    fig2.update_layout(height=460, margin=dict(l=10, r=40, t=10, b=10), xaxis_title="Estimated change in total score (points)", yaxis=dict(autorange="reversed"),
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig2.update_xaxes(gridcolor="rgba(128,128,128,.15)")
    st.plotly_chart(fig2, use_container_width=True)
st.info("Caveat: the model learns from institutes that are already in the top 200, so it is most reliable inside that range. Publications and citations "
        "(75 of RPC's 100 marks) are not in the PDFs, so RPC is estimated from PhD output, funding and faculty size; a Scopus-based publication push "
        "will add points the model cannot see. Use the Live Data page to record publication counts so future versions can include them.")

with st.expander("What drives each estimated parameter (feature contributions for the baseline)"):
    for p in ("tlr", "rpc", "go", "oi"):
        c = sm.contributions(b, p).iloc[0].drop("baseline").sort_values()
        st.markdown(f"**{p.upper()}** = baseline {sm.contributions(b, p).iloc[0]['baseline']:.1f} " + " ".join(f"{'+' if v >= 0 else ''}{v:.1f} ({k})" for k, v in c.items()))
