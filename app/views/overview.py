"""Overview: headline numbers, the rising rank-100 bar, and where the top 100 get their points."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import C_PARAM, C_PRIMARY, PARAMS, card, live_state, load_json, rankings, saveetha_history


st.title("NIRF Analytics — Saveetha Engineering College")
st.caption("Engineering category · data scraped from nirfindia.org (rankings 2017-2025, 700+ institute submissions) · "
           "calibrated scoring model · 2026 forecast · staff live data · AI analyst")

r = rankings()
pred = load_json("prediction_2026.json")
an = load_json("analysis.json")
hist = saveetha_history()
t25 = r[(r.year == 2025) & (r["rank"] <= 100)]

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    card("Saveetha · NIRF 2025", "Band 201-300", "Engineering · also 201-300 in 2024")
with c2:
    card("Rank-100 cut-off 2025", f"{t25.score.min():.2f}", f"2023: {an.get('cutoffs', {}).get('2023', {}).get('rank100', '–')} · 2024: {an.get('cutoffs', {}).get('2024', {}).get('rank100', '–')}")
state = live_state()
s = {**pred.get("saveetha", {}), **state["forecast"]}
tag = " · incl. staff data" if state["has_live"] else ""
with c3:
    card("Saveetha est. score 2026", f"{s.get('total_score', {}).get('median', '–')}", f"80% range {s.get('total_score', {}).get('p10', '–')} – {s.get('total_score', {}).get('p90', '–')}{tag}")
with c4:
    card("Most likely 2026 band", s.get("most_likely_band", "–"), f"P(top 100) = {100 * s.get('band_probabilities', {}).get('top 100', 0):.0f}%{tag}")
with c5:
    card("Forecast cut-off 2026", f"{pred.get('thresholds', {}).get('forecast_2026', {}).get('100', '–')}", f"gap ≈ {s.get('gap_to_top100', '–')} points")

st.divider()
left, right = st.columns([3, 2])

with left:
    st.subheader("The bar keeps rising: score needed for rank 100")
    cut = r[r["rank"] <= 100].groupby("year").score.min().reset_index()
    f2026 = pred.get("thresholds", {}).get("forecast_2026", {}).get("100")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cut.year, y=cut.score, mode="lines+markers", name="Rank-100 cut-off", line=dict(color=C_PRIMARY, width=2), marker=dict(size=8),
                             hovertemplate="%{x}: %{y:.2f}<extra></extra>"))
    if f2026:
        fig.add_trace(go.Scatter(x=[2025, 2026], y=[cut.score.iloc[-1], f2026], mode="lines+markers", name="2026 forecast",
                                 line=dict(color=C_PRIMARY, width=2, dash="dot"), marker=dict(size=8, symbol="diamond"), hovertemplate="2026 forecast: %{y:.2f}<extra></extra>"))
    sec_pts = hist[hist.status == "ranked"]
    fig.add_trace(go.Scatter(x=sec_pts.year, y=sec_pts.score, mode="markers+text", name="Saveetha (published)", marker=dict(color="#D64D7A", size=11),
                             text=[f"rank {int(x)}" for x in sec_pts.rank_or_band_low], textposition="bottom center", hovertemplate="%{x}: %{y:.2f}<extra>Saveetha</extra>"))
    est = load_json("model_report.json").get("saveetha_estimates", [])
    if est:
        fig.add_trace(go.Scatter(x=[e["year"] for e in est], y=[e["total_est"] for e in est], mode="markers+text", name="Saveetha (model estimate)",
                                 marker=dict(color="#D64D7A", size=11, symbol="diamond-open", line=dict(width=2)), text=["est."] * len(est), textposition="bottom center",
                                 hovertemplate="%{x}: %{y:.2f} (estimated)<extra>Saveetha</extra>"))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Total score (out of 100)", xaxis=dict(dtick=1),
                      legend=dict(orientation="h", y=1.1), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,.15)")
    st.plotly_chart(fig, width="stretch")
    st.caption("Saveetha's published scores (2017: 36.88, rank 91; 2019: 34.14, rank 124) would sit below today's cut-off. The model estimates its "
               "2025 filing at ≈37 and its 2026 filing at ≈40, while the top-100 line heads to ≈47.")

with right:
    st.subheader("Where the 2025 top-100 gets its points")
    tier = pd.DataFrame(an.get("tier_profile_2025", []))
    if not tier.empty:
        fig2 = go.Figure()
        for p in PARAMS:
            fig2.add_trace(go.Bar(name=p.upper(), x=tier.tier, y=tier[p], marker_color=C_PARAM[p], hovertemplate=f"{p.upper()} %{{y:.1f}}<extra>%{{x}}</extra>"))
        fig2.update_layout(barmode="group", height=380, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Average parameter score", xaxis_title="Rank tier",
                           legend=dict(orientation="h", y=1.12), bargap=0.25, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig2.update_yaxes(gridcolor="rgba(128,128,128,.15)")
        st.plotly_chart(fig2, width="stretch")
        st.caption("Research (RPC) and Perception separate the tiers most; TLR, GO and OI are flatter. Getting into the 76-100 tier needs RPC ≈ 30, GO ≈ 60, TLR ≈ 65.")

st.divider()
st.subheader("How to use this app")
st.markdown(
    """
| Page | What it does |
|---|---|
| **Top 100 Explorer** | Every ranked Engineering institute 2017-2025 with parameter scores, raw submission data and per-institute drill-down |
| **Saveetha Position** | Full NIRF history, estimated parameter scores, gap versus the rank-100 line and versus peer colleges |
| **Gap & What-If** | Move the levers the college controls (PhDs, salary, spend, research) and see the estimated score change |
| **Prediction 2026** | Forecast cut-offs, projected top-100 order, Saveetha's band probabilities and the most valuable levers |
| **Live Data Entry** | Staff enter current-year numbers (publications, PhD scholars, placements…); the estimate and the 2026 forecast on every page update immediately |
| **Ask the Data** | Chat with an AI analyst that queries the database, reads the methodology, and can scrape nirfindia.org for updates |
"""
)
