from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import C_PRIMARY, SEC_ID, card, live_state, load_json, q

st.title("NIRF 2026 forecast")

pred = load_json("prediction_2026.json")
rep = load_json("model_report.json")
if not pred:
    st.error("Run `python models/predict_2026.py` first.")
    st.stop()
thr = pred["thresholds"]; val = pred["top100_model_validation"]
state = live_state()
s = {**pred["saveetha"], **state["forecast"]}
if state["has_live"]:
    st.success(f"Includes staff-entered data: {state['n_metrics']} metric(s), latest entry {state['last_entry']}. "
               f"Using the filing alone the estimate was {pred['saveetha']['total_score']['median']} (≈ rank {pred['saveetha']['expected_rank']}).", icon="📝")
    if state["estimate"]["notes"]:
        with st.expander("How the staff entries were used"):
            st.markdown("\n".join(f"- {n}" for n in state["estimate"]["notes"]))
st.caption(f"Forecast model run at {pred['run_at']} · based on Saveetha's NIRF {s['submission_year_used']} filing"
           + (" plus the latest staff entries" if state["has_live"] else "") + " and rankings 2017-2025 · recomputed on every visit")
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    card("Estimated 2026 total", f"{s['total_score']['median']}", f"80% range {s['total_score']['p10']} – {s['total_score']['p90']}")
with c2:
    card("Expected position", f"≈ rank {s['expected_rank']}", f"most likely band: {s['most_likely_band']}")
with c3:
    card("P(top 100)", f"{100 * s['band_probabilities']['top 100']:.0f}%", f"P(top 200) = {100 * sum(v for k, v in s['band_probabilities'].items() if k in ('top 100', '101-150', '151-200')):.0f}%")
with c4:
    card("Rank-100 cut-off 2026", f"{thr['forecast_2026']['100']}", f"trend +{thr['trend_slope_per_year']}/yr")
with c5:
    card("Gap to top 100", f"{s['gap_to_top100']:+.1f}", f"gap to top 200: {s['gap_to_top200']:+.1f}")

left, right = st.columns([3, 2])
with left:
    st.subheader("Band probabilities for Saveetha in 2026")
    bp = s["band_probabilities"]
    order = ["top 100", "101-150", "151-200", "201-250", "251-300", "below 300"]
    fig = go.Figure(go.Bar(x=order, y=[100 * bp[k] for k in order], marker_color=[C_PRIMARY if k == s["most_likely_band"] else "#94A3B8" for k in order],
                           text=[f"{100 * bp[k]:.0f}%" for k in order], textposition="outside", hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="Probability (%)", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,.15)")
    st.plotly_chart(fig, width="stretch")
    st.markdown(f"**Estimated parameter scores (2026 filing{' + staff entries' if state['has_live'] else ''}):** " + " · ".join(f"{k.upper()} {v}" for k, v in s["param_estimates"].items())
                + f" · PR assumed {s['pr_assumption']['median']} (p10 {s['pr_assumption']['p10']}, p90 {s['pr_assumption']['p90']})")
    st.markdown("**How this was built:** parameter scores come from a monotone gradient-boosting model per parameter, fitted on 700 institute-years "
                "(2021-2025, ranks 1-200) with both the raw NIRF submission and the published score. 20,000 Monte-Carlo draws add each model's "
                "cross-validated error and a Perception score drawn from private colleges ranked 60-100 in 2025. Totals are compared with the "
                "2026 threshold curve (rank-100 trend since 2020 × the 2019-22 score-vs-rank shape).")
with right:
    st.subheader("Score needed at each rank, 2026 forecast")
    f = thr["forecast_2026"]
    tf = pd.DataFrame({"rank": [int(k) for k in f], "score needed": list(f.values())})
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=tf["rank"], y=tf["score needed"], mode="lines+markers", name="2026 threshold", line=dict(color=C_PRIMARY, width=2), marker=dict(size=8)))
    fig2.add_hline(y=s["total_score"]["median"], line=dict(color="#D64D7A", width=2, dash="dot"), annotation_text=f"Saveetha est. {s['total_score']['median']}", annotation_position="top right")
    fig2.add_hrect(y0=s["total_score"]["p10"], y1=s["total_score"]["p90"], fillcolor="#D64D7A", opacity=0.08, line_width=0)
    fig2.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Rank", yaxis_title="Total score", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig2.update_yaxes(gridcolor="rgba(128,128,128,.15)")
    st.plotly_chart(fig2, width="stretch")
    st.dataframe(pd.DataFrame([thr["cutoff_history"]], index=["rank-100 cut-off"]), width="stretch")

st.divider()
st.subheader("Model accuracy")
m1, m2 = st.columns(2)
with m1:
    st.markdown("**Score model (raw data → parameter score), grouped 5-fold cross-validation**")
    pr = rep.get("params", {})
    st.dataframe(pd.DataFrame([{"parameter": k.upper(), "n": v["n"], "CV R²": v["cv_r2"], "CV MAE": v["cv_mae"], "CV RMSE": v["cv_rmse"],
                                "top drivers": ", ".join(list(v["importance"])[:3])} for k, v in pr.items()]), hide_index=True, width="stretch")
    tf_ = rep.get("total_score_fit", {})
    st.caption(f"Total score reproduced with published PR: MAE {tf_.get('mae')} points, R² {tf_.get('r2')}. Validation of the approach: the 2025 filing is "
               f"estimated at ≈37, which lands in the 201-300 band NIRF actually published for Saveetha in 2025.")
with m2:
    st.markdown("**Top-100 forecast model (last year's scores → this year's), tested on 2025**")
    st.dataframe(pd.DataFrame([{"validation year": val["val_year"], "institutes": val["n"], "MAE": val["mae"], "RMSE": val["rmse"],
                                "naive 'no change' MAE": val["naive_mae_no_change"], "rank order Spearman (top 100)": val["rank_spearman_top100"]}]), hide_index=True, width="stretch")
    st.caption("Ridge regression on previous score, parameters and momentum, trained on 2018-2024 pairs.")

st.divider()
st.subheader("Projected 2026 order of the 2025 top-100 (Engineering)")
top = pd.DataFrame(pred["top100_forecast"])
top["change"] = top.rank_2025 - top.pred_rank_2026
st.dataframe(top[["pred_rank_2026", "rank_2025", "change", "name", "state", "score", "pred_score_2026"]].rename(columns={"score": "score_2025"}).head(100)
             .style.format({"score_2025": "{:.2f}", "pred_score_2026": "{:.2f}"}), hide_index=True, width="stretch", height=500)
st.caption("Ordering only among institutes ranked in 2025; new entrants and the un-modelled Perception survey will reshuffle the middle of the list.")

st.divider()
st.subheader("Previous predictions saved in the database")
st.dataframe(q("SELECT run_at, model, target_year, name, pred_score, pred_rank, pred_band, score_low, score_high FROM predictions WHERE institute_id=? ORDER BY run_at DESC", (SEC_ID,)),
             hide_index=True, width="stretch")
