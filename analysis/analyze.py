"""Deep analysis of the NIRF Engineering top-100 (2023-2025) and Saveetha Engineering College.

Writes data/processed/analysis.json (consumed by the dashboard and the chatbot) and prints a
readable summary. Everything here is derived from db/nirf.db.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "nirf.db"
OUT = ROOT / "data" / "processed" / "analysis.json"
SEC_ID = "IR-E-C-16590"
PARAMS = ["tlr", "rpc", "go", "oi", "pr"]
YEARS = [2023, 2024, 2025]


def tier(rank: int) -> str:
    return "1-10" if rank <= 10 else "11-25" if rank <= 25 else "26-50" if rank <= 50 else "51-75" if rank <= 75 else "76-100"


def main() -> None:
    con = sqlite3.connect(DB)
    r = pd.read_sql('SELECT r.*, r."go" AS go_, i.type_label FROM rankings r LEFT JOIN institutions i USING(institute_id) WHERE category="Engineering"', con)
    r["go"] = r["go_"]; r = r.drop(columns=["go_"])
    top = r[(r["rank"] <= 100) & r.year.isin(YEARS)].copy()
    top["tier"] = top["rank"].map(tier)
    sub = pd.read_sql("SELECT * FROM submissions WHERE category='Engineering'", con)
    m = top.merge(sub.drop(columns=["name", "category"]), on=["year", "institute_id"], how="left")
    A: dict = {}

    # 1. cut-offs and score distribution per year
    A["cutoffs"] = {int(y): {"rank1": float(g.score.max()), "rank10": float(g[g["rank"] <= 10].score.min()),
                             "rank50": float(g[g["rank"] <= 50].score.min()), "rank100": float(g.score.min()),
                             "mean": round(float(g.score.mean()), 2)} for y, g in top.groupby("year")}

    # 2. parameter profile by tier (2025) — what separates rank 1-10 from 76-100
    A["tier_profile_2025"] = (top[top.year == 2025].groupby("tier")[PARAMS + ["score"]].mean().round(1)
                              .reindex(["1-10", "11-25", "26-50", "51-75", "76-100"]).reset_index().to_dict(orient="records"))
    # spread of each parameter in the top-100: which parameter discriminates most?
    t25 = top[top.year == 2025]
    A["parameter_discrimination_2025"] = {p: {"std": round(float(t25[p].std()), 1), "corr_with_score": round(float(t25[p].corr(t25.score)), 3),
                                              "weighted_std": round(float(t25[p].std() * {"tlr": .3, "rpc": .3, "go": .2, "oi": .1, "pr": .1}[p]), 2)} for p in PARAMS}

    # 3. composition: institute types and states
    A["type_mix"] = {int(y): g.type_label.value_counts().to_dict() for y, g in top.groupby("year")}
    A["state_counts_2025"] = t25.state.value_counts().head(12).to_dict()
    A["tamil_nadu_2025"] = t25[t25.state == "Tamil Nadu"][["rank", "name", "type_label", "score"] + PARAMS].sort_values("rank").to_dict(orient="records")
    A["colleges_in_top100"] = {int(y): int((g.institute_id.str.contains("-C-")).sum()) for y, g in top.groupby("year")}
    A["private_colleges_2025"] = t25[t25.institute_id.str.contains("-C-")][["rank", "name", "state", "score"] + PARAMS].sort_values("rank").to_dict(orient="records")

    # 4. movers: biggest rank gains/losses 2023 -> 2025 among institutes in both lists
    w = top.pivot_table(index=["institute_id", "name"], columns="year", values=["rank", "score"])
    both = w.dropna(subset=[("rank", 2023), ("rank", 2025)])
    mv = pd.DataFrame({"name": [i[1] for i in both.index], "rank_2023": both[("rank", 2023)].astype(int).values,
                       "rank_2025": both[("rank", 2025)].astype(int).values,
                       "score_2023": both[("score", 2023)].values, "score_2025": both[("score", 2025)].values})
    mv["rank_change"] = mv.rank_2023 - mv.rank_2025
    A["top_movers_up"] = mv.sort_values("rank_change", ascending=False).head(10).to_dict(orient="records")
    A["top_movers_down"] = mv.sort_values("rank_change").head(10).to_dict(orient="records")
    A["entered_top100_2025"] = t25[~t25.institute_id.isin(top[top.year == 2024].institute_id)][["rank", "name", "state", "score"]].to_dict(orient="records")
    A["dropped_from_top100_2025"] = top[(top.year == 2024) & ~top.institute_id.isin(t25.institute_id)][["rank", "name", "state", "score"]].to_dict(orient="records")

    # 5. raw-data profile of the top-100 vs the rank 76-100 band vs Saveetha (2025 / 2026 filing)
    raw_cols = ["students_total", "faculty_entered", "students_per_faculty", "phd_pursuing_ft", "phd_grad_3y_avg",
                "placement_rate", "placed_or_hs_rate", "graduation_rate", "median_salary_ug", "capex_per_student",
                "opex_per_student", "sponsored_amount_3y_avg", "consultancy_amount_3y_avg", "women_students_pct",
                "outside_state_pct", "full_fee_reimb_pct"]
    m25 = m[m.year == 2025]
    prof = pd.DataFrame({
        "top10_median": m25[m25["rank"] <= 10][raw_cols].median(),
        "top100_median": m25[raw_cols].median(),
        "rank76_100_median": m25[m25["rank"] > 75][raw_cols].median(),
        "colleges_top100_median": m25[m25.institute_id.str.contains("-C-")][raw_cols].median(),
    })
    sec = sub[sub.institute_id == SEC_ID].sort_values("year")
    for _, row in sec.iterrows():
        prof[f"saveetha_{int(row.year)}_filing"] = row[raw_cols]
    A["raw_profile_2025"] = prof.round(3).reset_index().rename(columns={"index": "metric"}).to_dict(orient="records")

    # 6. Saveetha history + gap to cutoff
    hist = pd.read_sql("SELECT * FROM v_saveetha_history", con)
    A["saveetha_history"] = hist.to_dict(orient="records")
    A["saveetha_participation"] = pd.read_sql("SELECT year, category FROM participants WHERE name_key LIKE 'saveetha engineering%' ORDER BY year", con).to_dict(orient="records")
    model_rep = json.loads((ROOT / "data" / "processed" / "model_report.json").read_text()) if (ROOT / "data" / "processed" / "model_report.json").exists() else {}
    est = model_rep.get("saveetha_estimates", [])
    A["saveetha_estimated_scores"] = est
    if est:
        e = est[-1]; cutoff = A["cutoffs"][2025]["rank100"]
        r100 = t25[t25["rank"].between(90, 100)][PARAMS].mean()
        A["saveetha_gap_vs_rank90_100_avg"] = {p: round(float(r100[p] - e.get(p if p != "pr" else "pr_assumed", 0)), 1) for p in PARAMS}
        A["saveetha_gap_total_vs_2025_cutoff"] = round(cutoff - e["total_est"], 2)
        # how much of the gap does each parameter explain (weighted)
        wts = {"tlr": .3, "rpc": .3, "go": .2, "oi": .1, "pr": .1}
        A["saveetha_weighted_gap_by_param"] = {p: round(float(A["saveetha_gap_vs_rank90_100_avg"][p] * wts[p]), 2) for p in PARAMS}

    # 7. peers: Tamil Nadu private colleges that climbed into the top 100 (path examples)
    peers = r[(r.state == "Tamil Nadu") & r.institute_id.str.contains("-C-") & (r["rank"] <= 100)]
    A["tn_college_paths"] = {n: g.sort_values("year")[["year", "rank", "score"] + PARAMS].to_dict(orient="records")
                             for n, g in peers.groupby("name") if g.year.max() >= 2024}

    # 8. correlations between raw data and parameter scores (2023-25 top-100)
    mm = m.copy()
    for c in ("median_salary_ug", "opex_per_student", "capex_per_student", "sponsored_amount_3y_avg", "consultancy_amount_3y_avg", "phd_grad_3y_avg"):
        mm["log_" + c] = np.log1p(mm[c])
    cc = mm[["log_median_salary_ug", "log_opex_per_student", "log_capex_per_student", "log_sponsored_amount_3y_avg", "log_consultancy_amount_3y_avg",
             "log_phd_grad_3y_avg", "students_per_faculty", "placement_rate", "graduation_rate", "women_students_pct", "outside_state_pct", "full_fee_reimb_pct"] + PARAMS + ["score"]].corr()
    A["raw_vs_score_correlation"] = cc.loc[[c for c in cc.index if c not in PARAMS + ["score"]], PARAMS + ["score"]].round(2).reset_index().rename(columns={"index": "feature"}).to_dict(orient="records")

    OUT.write_text(json.dumps(A, indent=2, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o)))
    con.close()
    print("cut-offs:", json.dumps(A["cutoffs"]))
    print("\n2025 tier profile:"); print(pd.DataFrame(A["tier_profile_2025"]).to_string(index=False))
    print("\ncolleges in top100:", A["colleges_in_top100"], "| type mix 2025:", A["type_mix"][2025])
    print("\nTamil Nadu 2025:"); print(pd.DataFrame(A["tamil_nadu_2025"])[["rank", "name", "score"]].to_string(index=False))
    print("\nraw profile:"); print(pd.DataFrame(A["raw_profile_2025"]).to_string(index=False))
    if est:
        print("\nSaveetha gap vs rank 90-100 average:", A["saveetha_gap_vs_rank90_100_avg"], "| weighted:", A["saveetha_weighted_gap_by_param"])
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
