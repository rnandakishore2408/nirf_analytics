from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import C_PARAM, C_PRIMARY, PARAMS, fmt_inr, rankings, submissions

st.title("Top 100 Explorer — NIRF Engineering")

r = rankings()
sub = submissions()

f1, f2, f3, f4 = st.columns([1, 1, 2, 2])
year = f1.selectbox("Year", sorted(r.year.unique(), reverse=True), index=0)
top_n = f2.selectbox("Show ranks", [100, 50, 25, 200], index=0)
states = f3.multiselect("State", sorted(r.state.dropna().unique()))
types = f4.multiselect("Institution type", sorted(r.type_label.dropna().unique()))

d = r[(r.year == year) & (r["rank"] <= top_n)]
if states:
    d = d[d.state.isin(states)]
if types:
    d = d[d.type_label.isin(types)]

st.markdown(f"**{len(d)} institutions** · rank-{top_n} cut-off in {year}: **{r[(r.year == year) & (r['rank'] <= top_n)].score.min():.2f}**")

tab1, tab2, tab3, tab4 = st.tabs(["Table", "Score anatomy", "Raw submission data", "Institute drill-down"])

with tab1:
    show = d[["rank", "name", "city", "state", "type_label", "tlr", "rpc", "go", "oi", "pr", "score"]].rename(columns={"type_label": "type"})
    cfg = {p: st.column_config.ProgressColumn(p.upper(), min_value=0, max_value=100, format="%.2f") for p in PARAMS}
    cfg["score"] = st.column_config.NumberColumn("score", format="%.2f")
    st.dataframe(show, column_config=cfg, width="stretch", height=600, hide_index=True)
    st.download_button("Download CSV", show.to_csv(index=False).encode(), f"nirf_engineering_{year}_top{top_n}.csv", "text/csv")

with tab2:
    st.markdown("Each institute's total = 0.30·TLR + 0.30·RPC + 0.20·GO + 0.10·OI + 0.10·PR. Bars show the weighted contribution of each parameter.")
    dd = d.sort_values("rank").head(60)
    fig = go.Figure()
    for p in PARAMS:
        w = {"tlr": .3, "rpc": .3, "go": .2, "oi": .1, "pr": .1}[p]
        fig.add_trace(go.Bar(name=p.upper(), x=dd.name, y=dd[p] * w, marker_color=C_PARAM[p], marker_line=dict(width=1, color="#FCFCFB"),
                             hovertemplate=f"{p.upper()}: %{{customdata:.1f}} → %{{y:.1f}} pts<extra>%{{x}}</extra>", customdata=dd[p]))
    fig.update_layout(barmode="stack", height=520, margin=dict(l=10, r=10, t=10, b=140), yaxis_title="Weighted points (sum = total score)", xaxis_tickangle=-60,
                      legend=dict(orientation="h", y=1.08), bargap=0.2, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,.15)")
    st.plotly_chart(fig, width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Which parameter explains the total?** (correlation with score, this selection)")
        st.dataframe(pd.DataFrame({"parameter": [p.upper() for p in PARAMS], "corr with total": [round(d[p].corr(d.score), 3) for p in PARAMS],
                                   "mean": [round(d[p].mean(), 1) for p in PARAMS], "std": [round(d[p].std(), 1) for p in PARAMS]}), hide_index=True, width="stretch")
    with c2:
        px_fig = px.scatter(d, x="rpc", y="score", color="type_label", hover_name="name", color_discrete_sequence=[C_PRIMARY, "#E4A11B", "#D64D7A"],
                            labels={"rpc": "RPC (research) score", "score": "Total score", "type_label": "type"})
        px_fig.update_traces(marker=dict(size=9, line=dict(width=1, color="#FCFCFB")))
        px_fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.1), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(px_fig, width="stretch")

with tab3:
    m = d.merge(sub.drop(columns=["name", "category"]), on=["year", "institute_id"], how="left")
    cols = ["rank", "name", "students_total", "faculty_entered", "students_per_faculty", "phd_pursuing_ft", "phd_grad_3y_avg", "graduation_rate",
            "placement_rate", "placed_or_hs_rate", "median_salary_ug", "capex_per_student", "opex_per_student", "sponsored_amount_3y_avg",
            "consultancy_amount_3y_avg", "women_students_pct", "outside_state_pct", "full_fee_reimb_pct"]
    have = [c for c in cols if c in m]
    if m[have].drop(columns=["rank", "name"]).notna().any().any():
        st.markdown("Numbers each institute submitted to NIRF (parsed from its official data PDF). 3y = averaged over the last three years.")
        st.dataframe(m[have].style.format({"median_salary_ug": lambda v: fmt_inr(v), "capex_per_student": lambda v: fmt_inr(v), "opex_per_student": lambda v: fmt_inr(v),
                                           "sponsored_amount_3y_avg": lambda v: fmt_inr(v), "consultancy_amount_3y_avg": lambda v: fmt_inr(v),
                                           "graduation_rate": "{:.0%}", "placement_rate": "{:.0%}", "placed_or_hs_rate": "{:.0%}", "students_per_faculty": "{:.1f}",
                                           "phd_grad_3y_avg": "{:.0f}", "women_students_pct": "{:.0f}%", "outside_state_pct": "{:.0f}%", "full_fee_reimb_pct": "{:.0f}%"}, na_rep="–"),
                     width="stretch", height=600, hide_index=True)
        st.download_button("Download raw data CSV", m[have].to_csv(index=False).encode(), f"nirf_raw_{year}.csv", "text/csv")
    else:
        st.info("Raw submission PDFs were downloaded for 2021-2025 only.")

with tab4:
    name = st.selectbox("Institute", d.sort_values("rank").name.tolist())
    inst_id = d[d.name == name].institute_id.iloc[0]
    hist = r[r.institute_id == inst_id].sort_values("year")
    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown(f"**{name}** · `{inst_id}` · {hist.iloc[-1].city}, {hist.iloc[-1].state}")
        st.dataframe(hist[["year", "rank", "score"] + PARAMS].style.format({p: "{:.2f}" for p in PARAMS + ["score"]}), hide_index=True, width="stretch")
    with c2:
        fig = go.Figure()
        for p in PARAMS:
            fig.add_trace(go.Scatter(x=hist.year, y=hist[p], mode="lines+markers", name=p.upper(), line=dict(color=C_PARAM[p], width=2), marker=dict(size=7)))
        fig.add_trace(go.Scatter(x=hist.year, y=hist.score, mode="lines+markers", name="TOTAL", line=dict(color="#1F2937", width=3), marker=dict(size=8)))
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100], title="Score"), xaxis=dict(dtick=1),
                          legend=dict(orientation="h", y=1.12), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig.update_yaxes(gridcolor="rgba(128,128,128,.15)")
        st.plotly_chart(fig, width="stretch")
    s = sub[(sub.institute_id == inst_id)].sort_values("year")
    if not s.empty:
        st.markdown("**Submitted data by year**")
        keep = ["year", "students_total", "faculty_entered", "students_per_faculty", "phd_pursuing_ft", "phd_grad_3y_avg", "graduated_total", "placed_total",
                "higher_studies_total", "placement_rate", "graduation_rate", "median_salary_ug", "capex_per_student", "opex_per_student",
                "sponsored_amount_3y_avg", "consultancy_amount_3y_avg", "women_students_pct", "outside_state_pct", "full_fee_reimb_pct", "pcs_score_0_3"]
        st.dataframe(s[[k for k in keep if k in s]].set_index("year").T, width="stretch")
        st.caption(f"Source PDF: {s.iloc[-1].source_pdf}")
