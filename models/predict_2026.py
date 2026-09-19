"""Predict NIRF 2026 (Engineering).

Three pieces:
 1. Threshold forecast  - score needed for rank 100 / 150 / 200 / 250 / 300 in 2026, from the
                          2017-2025 cutoff trend and the 2019-2022 score-vs-rank curve (years with
                          200 numeric ranks).
 2. Top-100 forecast    - next-year score for every 2025 top-100 institute from a ridge model on
                          previous scores/parameters (validated by predicting 2025 from <=2024).
 3. Saveetha forecast   - parameter scores from its NIRF-2026 submission through the calibrated
                          score model, Monte-Carlo over model error and the unknown Perception score,
                          mapped to a rank band with probabilities.
Results -> predictions table (db/nirf.db) and data/processed/prediction_2026.json
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "models"))
from live_estimate import forecast, pr_pool_from  # noqa: E402
from score_model import ScoreModel  # noqa: E402

DB = ROOT / "db" / "nirf.db"
SEC_ID = "IR-E-C-16590"
TARGET = 2026


def thresholds(r: pd.DataFrame) -> dict:
    """Forecast score cut-offs for 2026 at ranks 100..300."""
    cut = r[r["rank"] <= 100].groupby("year").score.min()  # score at rank 100
    yrs = cut.index.values.astype(float)
    # linear trend on the last 6 years (cut-offs rise ~1.5/yr since 2020)
    sel = yrs >= 2020
    slope, intercept = np.polyfit(yrs[sel], cut.values[sel], 1)
    c100 = float(slope * TARGET + intercept)
    resid_sd = float(np.std(cut.values[sel] - (slope * yrs[sel] + intercept), ddof=1))
    # score/rank curve from years with 200 ranks: ratio of score at rank k to score at rank 100
    ratios = {}
    for k in (125, 150, 175, 200):
        rs = []
        for y, g in r[r.year.between(2019, 2022)].groupby("year"):
            if g["rank"].max() >= 200:
                rs.append(g[g["rank"] <= k].score.min() / g[g["rank"] <= 100].score.min())
        ratios[k] = float(np.mean(rs))
    # extrapolate the (log-rank -> ratio) line to 250 and 300
    ks = np.array(sorted(ratios)); rv = np.array([ratios[k] for k in ks])
    a, b = np.polyfit(np.log(ks), rv, 1)
    for k in (250, 300):
        ratios[k] = float(a * np.log(k) + b)
    ratios[100] = 1.0
    out = {"cutoff_history": {int(k): round(float(v), 2) for k, v in cut.items()},
           "trend_slope_per_year": round(slope, 3), "trend_resid_sd": round(resid_sd, 2),
           "forecast_2026": {int(k): round(c100 * ratios[k], 2) for k in sorted(ratios)},
           "ratio_to_rank100": {int(k): round(v, 4) for k, v in sorted(ratios.items())}}
    return out


def top100_forecast(r: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Ridge on previous-year features -> next-year score; validate on 2025, then forecast 2026."""
    cols = ["score", "tlr", "rpc", "go", "oi", "pr"]
    prev = r[cols + ["year", "institute_id"]].copy(); prev["year"] += 1
    prev = prev.rename(columns={c: c + "_prev" for c in cols})
    prev2 = r[["score", "year", "institute_id"]].rename(columns={"score": "score_prev2"}); prev2["year"] += 2
    m = r[["year", "institute_id", "name", "score", "rank"]].merge(prev, on=["year", "institute_id"])
    m = m.merge(prev2, on=["year", "institute_id"], how="left")
    m["momentum"] = (m.score_prev - m.score_prev2).fillna(0)
    feats = ["score_prev", "tlr_prev", "rpc_prev", "go_prev", "oi_prev", "pr_prev", "momentum"]
    train = m[m.year <= 2024]; test = m[m.year == 2025]
    mdl = Ridge(alpha=3.0).fit(train[feats], train.score)
    pred = mdl.predict(test[feats])
    val = {"val_year": 2025, "n": int(len(test)), "mae": round(float(np.abs(pred - test.score).mean()), 2),
           "rmse": round(float(np.sqrt(((pred - test.score) ** 2).mean())), 2),
           "naive_mae_no_change": round(float(np.abs(test.score_prev - test.score).mean()), 2)}
    # spearman of predicted order vs actual rank inside 2025 top-100
    t = test.assign(pred=pred); t = t[t["rank"] <= 100]
    val["rank_spearman_top100"] = round(float(t.pred.rank(ascending=False).corr(t["rank"], method="spearman")), 3)
    # refit on everything, forecast 2026 for 2025's ranked list
    mdl = Ridge(alpha=3.0).fit(m[feats], m.score)
    last = r[r.year == 2025][["institute_id", "name", "city", "state", "score", "tlr", "rpc", "go", "oi", "pr", "rank"]].copy()
    p24 = r[r.year == 2024][["institute_id", "score"]].rename(columns={"score": "score_prev2"})
    last = last.merge(p24, on="institute_id", how="left")
    X = pd.DataFrame({"score_prev": last.score, "tlr_prev": last.tlr, "rpc_prev": last.rpc, "go_prev": last.go,
                      "oi_prev": last.oi, "pr_prev": last.pr, "momentum": (last.score - last.score_prev2).fillna(0)})
    last["pred_score_2026"] = mdl.predict(X).round(2)
    last["pred_rank_2026"] = last.pred_score_2026.rank(ascending=False, method="min").astype(int)
    last["rank_2025"] = last["rank"]
    return last.sort_values("pred_rank_2026"), val


def saveetha_forecast(con: sqlite3.Connection, sm: ScoreModel, thr: dict, r: pd.DataFrame) -> dict:
    sec = pd.read_sql("SELECT * FROM submissions WHERE institute_id=? AND category='Engineering' ORDER BY year", con, params=(SEC_ID,))
    row = sec[sec.year == TARGET]
    if row.empty:
        row = sec.tail(1)
    est = sm.predict_params(row).iloc[0]
    sd = {p: sm.report["params"][p]["cv_rmse"] for p in ("tlr", "rpc", "go", "oi")}
    # Perception: unknown. Saveetha's own published PR: 5.64 (2017), 0.41 (2019). Draw it from private
    # colleges ranked 60-100 in 2025. The Monte Carlo lives in live_estimate.forecast so the app's live
    # re-forecast and this file always agree.
    out = forecast({p: float(est[p]) for p in sd}, sd, sm.weights, thr, pr_pool_from(r))
    return {"institute_id": SEC_ID, "name": "Saveetha Engineering College", "submission_year_used": int(row.year.iloc[0]), **out}


def what_if_levers(con: sqlite3.Connection, sm: ScoreModel, base_total: float) -> list[dict]:
    """Single-lever what-ifs on the 2026 submission: what each realistic improvement is worth."""
    sec = pd.read_sql("SELECT * FROM submissions WHERE institute_id=? AND category='Engineering' ORDER BY year DESC LIMIT 1", con, params=(SEC_ID,))
    pr = 5.0
    def total_of(df):
        p = sm.predict_params(df); return float(sm.total(p, pr).iloc[0])
    base = total_of(sec)
    levers = [
        ("Median UG salary 5.5L -> 8L", {"median_salary_ug": 800000}),
        ("Median UG salary 5.5L -> 10L", {"median_salary_ug": 1000000}),
        ("PhD graduates/yr 12 -> 40", {"phd_grad_3y_avg": 40}),
        ("PhD graduates/yr 12 -> 80", {"phd_grad_3y_avg": 80}),
        ("Full-time PhD scholars 61 -> 200", {"phd_pursuing_ft": 200}),
        ("Sponsored research 30L -> 3Cr/yr", {"sponsored_amount_3y_avg": 30_000_000}),
        ("Sponsored research 30L -> 10Cr/yr", {"sponsored_amount_3y_avg": 100_000_000}),
        ("Consultancy 20L -> 2Cr/yr", {"consultancy_amount_3y_avg": 20_000_000}),
        ("Opex per student 1.1L -> 2L", {"opex_per_student": 200000}),
        ("Capex per student 18k -> 60k", {"capex_per_student": 60000}),
        ("Students from other states 7.6% -> 20%", {"outside_state_pct": 20}),
        ("Women students 32.6% -> 45%", {"women_students_pct": 45}),
        ("Graduation-in-time rate 81% -> 95%", {"graduation_rate": 0.95}),
    ]
    out = []
    for label, changes in levers:
        d = sec.copy()
        for k, v in changes.items():
            d[k] = v
        out.append({"lever": label, "delta_total": round(total_of(d) - base, 2)})
    return sorted(out, key=lambda x: -x["delta_total"])


def main() -> None:
    con = sqlite3.connect(DB)
    r = pd.read_sql('SELECT year, institute_id, name, city, state, score, tlr, rpc, "go" AS go, oi, pr, rank FROM rankings WHERE category="Engineering"', con)
    sm = ScoreModel.load()
    thr = thresholds(r)
    top, val = top100_forecast(r)
    sec = saveetha_forecast(con, sm, thr, r)
    levers = what_if_levers(con, sm, sec["total_score"]["median"])
    result = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "target_year": TARGET,
              "thresholds": thr, "top100_model_validation": val, "saveetha": sec, "what_if_levers": levers,
              "top100_forecast": top[["pred_rank_2026", "rank_2025", "institute_id", "name", "state", "score", "pred_score_2026"]].head(120).to_dict(orient="records")}
    (ROOT / "data" / "processed" / "prediction_2026.json").write_text(json.dumps(result, indent=2, default=float))
    # persist to DB
    con.execute("DELETE FROM predictions WHERE target_year=?", (TARGET,))
    rows = [(result["run_at"], "ridge_panel", TARGET, t.institute_id, t.name, None, None, None, None, None,
             float(t.pred_score_2026), int(t.pred_rank_2026), None, None, None, f"2025 rank {int(t.rank_2025)}") for t in top.itertuples()]
    pe = sec["param_estimates"]
    rows.append((result["run_at"], "score_model_montecarlo", TARGET, SEC_ID, sec["name"], pe["tlr"], pe["rpc"], pe["go"], pe["oi"],
                 sec["pr_assumption"]["median"], sec["total_score"]["median"], sec["expected_rank"], sec["most_likely_band"],
                 sec["total_score"]["p10"], sec["total_score"]["p90"], json.dumps(sec["band_probabilities"])))
    con.executemany("INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit(); con.close()
    print("2026 thresholds:", thr["forecast_2026"])
    print("top-100 model validation:", val)
    print("Saveetha:", json.dumps({k: sec[k] for k in ("param_estimates", "total_score", "expected_rank", "most_likely_band", "band_probabilities", "gap_to_top100")}, indent=1))
    print("levers:", *[f"  {l['lever']}: {l['delta_total']:+.2f}" for l in levers], sep="\n")


if __name__ == "__main__":
    main()
