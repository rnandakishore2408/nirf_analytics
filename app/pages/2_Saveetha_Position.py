from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import C_MUTED, C_PARAM, C_PRIMARY, PARAMS, SEC_ID, card, fmt_inr, inject_css, load_json, rankings, saveetha_history, submissions

st.set_page_config(page_title="Saveetha Position", page_icon="🎯", layout="wide")
inject_css()
st.title("Saveetha Engineering College — where we stand")

r = rankings()
hist = saveetha_history()
an = load_json("analysis.json")
rep = load_json("model_report.json")
est = pd.DataFrame(rep.get("saveetha_estimates", []))

st.subheader("NIRF history (Engineering unless noted)")
h = hist.copy()
h["position"] = h.apply(lambda x: f"Rank {int(x.rank_or_band_low)}" if x.status == "ranked" else f"Band {int(x.rank_or_band_low)}-{int(x.rank_or_band_high)}", axis=1)
h["note"] = h.category.where(h.category != "Engineering", "")
cols = ["year", "category", "position", "score"] + PARAMS
st.dataframe(h[cols].style.format({p: "{:.2f}" for p in PARAMS + ["score"]}, na_rep="– (not published for bands)"), hide_index=True, use_container_width=True)
part = pd.DataFrame(an.get("saveetha_participation", []))
if not part.empty:
    yrs = ", ".join(f"{int(y)} ({','.join(g.category)})" for y, g in part.groupby("year"))
    st.caption(f"Applied in: {yrs}. 2021-2023: applied but placed beyond rank 300 (2021-22 lists went to rank 200 + bands to 300).")

st.divider()
c1, c2 = st.columns([2, 3])
with c1:
    st.subheader("Estimated parameter scores")
    st.markdown("NIRF publishes no scores for band placements. These are **model estimates** from the numbers the college filed "
                "(model fitted on 700 institute-years with published scores; see Prediction page for accuracy).")
    if not est.empty:
        show = est.rename(columns={"pr_assumed": "pr (assumed)", "total_est": "total (est.)"})
        st.dataframe(show.style.format("{:.1f}", subset=[c for c in show if c != "year"]), hide_index=True, use_container_width=True)
    gap = an.get("saveetha_gap_vs_rank90_100_avg", {})
    wgap = an.get("saveetha_weighted_gap_by_param", {})
    if gap:
        st.markdown(f"**Gap to the 2025 rank 90-100 average** (weighted points lost): "
                    + " · ".join(f"{p.upper()} {gap[p]:+.1f} → {wgap[p]:+.2f} pts" for p in PARAMS))
        st.markdown(f"Total gap to the 2025 cut-off: **{an.get('saveetha_gap_total_vs_2025_cutoff', '–')} points**.")
with c2:
    st.subheader("Saveetha vs the rank 76-100 tier vs the top 10 (2025)")
    tier = pd.DataFrame(an.get("tier_profile_2025", []))
    if not tier.empty and not est.empty:
        e = est.iloc[-1]
        fig = go.Figure()
        t76 = tier[tier.tier == "76-100"].iloc[0]
        t10 = tier[tier.tier == "1-10"].iloc[0]
        fig.add_trace(go.Bar(name="Top 10 avg", x=[p.upper() for p in PARAMS], y=[t10[p] for p in PARAMS], marker_color="#CBD5E1"))
        fig.add_trace(go.Bar(name="Rank 76-100 avg", x=[p.upper() for p in PARAMS], y=[t76[p] for p in PARAMS], marker_color="#94A3B8"))
        fig.add_trace(go.Bar(name=f"Saveetha est. ({int(e.year)} filing)", x=[p.upper() for p in PARAMS],
                             y=[e["tlr"], e["rpc"], e["go"], e["oi"], e["pr_assumed"]], marker_color=C_PRIMARY))
        fig.update_layout(barmode="group", height=380, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100], title="Parameter score"),
                          legend=dict(orientation="h", y=1.12), bargap=0.25, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig.update_yaxes(gridcolor="rgba(128,128,128,.15)")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Research (RPC) is the whole story: Saveetha ≈ 13 vs ≈ 30 for the 76-100 tier. That alone is ~5 weighted points, i.e. most of the gap.")

st.divider()
st.subheader("Raw numbers: Saveetha's filings vs the top-100 (2025)")
prof = pd.DataFrame(an.get("raw_profile_2025", []))
if not prof.empty:
    money = {"median_salary_ug", "capex_per_student", "opex_per_student", "sponsored_amount_3y_avg", "consultancy_amount_3y_avg"}
    pct = {"placement_rate", "placed_or_hs_rate", "graduation_rate"}
    def fmt(v, metric):
        if pd.isna(v):
            return "–"
        if metric in money:
            return fmt_inr(v)
        if metric in pct:
            return f"{100 * v:.0f}%"
        return f"{v:,.1f}" if isinstance(v, float) and v % 1 else f"{v:,.0f}"
    disp = prof.copy()
    for c in disp.columns[1:]:
        disp[c] = [fmt(v, m) for v, m in zip(disp[c], disp.metric)]
    st.dataframe(disp, hide_index=True, use_container_width=True, height=620)
    st.markdown(
        """
**Reading the table**
- **PhD output** is where Saveetha is furthest behind: 12 PhDs/year and 61 full-time scholars against 24 PhDs/year and 163 scholars even for the rank 76-100 tier. This drives both TLR (student strength incl. doctoral) and GO (GPHD), and correlates with RPC.
- **Money spent per student** (≈₹1.1 L operating, ₹18k capital) is roughly half the 76-100 tier. FRU is 30 marks of TLR.
- **Median UG salary ₹5.5 L** vs ₹7.3 L for the 76-100 tier; GMS is 25 marks of GO.
- **Research funding** (₹30 L/yr sponsored) is a tiny fraction of the tier's ₹3.7 Cr; FPPP is 10 marks of RPC and PU/QP (75 marks) depend on Scopus publications, which the PDFs don't show.
- **Placements (97%) and graduation rate (81%)** are already at or above the tier: GO's GPH and GUE parts are not the problem.
- **Diversity**: women students 33% is above the tier average, but only 7.6% students from other states (tier: 57%). RD is 30 marks of OI.
"""
    )

st.divider()
st.subheader("Tamil Nadu colleges that made the top 100 — the paths")
paths = an.get("tn_college_paths", {})
if paths:
    fig = go.Figure()
    for i, (n, rows) in enumerate(paths.items()):
        df = pd.DataFrame(rows)
        fig.add_trace(go.Scatter(x=df.year, y=df.score, mode="lines+markers", name=n[:40], line=dict(width=2), marker=dict(size=7)))
    fig.add_trace(go.Scatter(x=hist[hist.status == "ranked"].year, y=hist[hist.status == "ranked"].score, mode="markers", name="Saveetha (published)", marker=dict(color="#D64D7A", size=12)))
    if not est.empty:
        fig.add_trace(go.Scatter(x=est.year, y=est.total_est, mode="markers", name="Saveetha (estimate)", marker=dict(color="#D64D7A", size=12, symbol="diamond-open", line=dict(width=2))))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Total score", xaxis=dict(dtick=1), legend=dict(orientation="v", x=1.01),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,.15)")
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Parameter detail for each peer"):
        for n, rows in paths.items():
            st.markdown(f"**{n}**")
            st.dataframe(pd.DataFrame(rows).style.format({p: "{:.1f}" for p in PARAMS + ["score"]}), hide_index=True, use_container_width=True)
