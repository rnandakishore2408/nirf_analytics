"""Reverse-engineer NIRF parameter scores from the raw data institutes submit.

NIRF publishes formulas (TLR = SS + FSR + FQE + FRU, GO = GPH + GUE + GMS + GPHD, ...) but hides
the normalising functions f(). We have both the raw submission and the published TLR/RPC/GO/OI
score for 300 top-100 Engineering rows (2023-25), so we fit one monotone gradient-boosting model
per parameter using only the inputs NIRF says that parameter depends on. Monotone constraints keep
the fitted functions economically sensible (more placements never lowers GO, etc.).

Usage
  python models/score_model.py            # train, cross-validate, save artifacts, score Saveetha
Artifacts -> models/artifacts/score_model.joblib ; data/processed/model_report.json
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from joblib import dump, load
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "nirf.db"
ART = ROOT / "models" / "artifacts"
SEC_ID = "IR-E-C-16590"

# feature -> monotone direction (+1 higher is better, -1 lower is better, 0 free)
PARAM_FEATURES: dict[str, dict[str, int]] = {
    "tlr": {  # SS(20) FSR(30) FQE(20) FRU(30)
        "students_total": 1, "phd_pursuing_ft": 1, "faculty_per_student": 1,
        "log_capex_per_student": 1, "log_opex_per_student": 1, "intake_total_latest": 1,
    },
    "rpc": {  # PU(35) QP(40) IPR(15) FPPP(10)
        # PU / QP: publications and citations per faculty, from OpenAlex (NIRF's PDFs omit them).
        # XGBoost handles missing values natively, so institutes without publication data still score.
        "log_pubs_per_faculty": 1, "log_cites_per_faculty": 1,
        # FPPP and proxies for the rest
        "phd_grad_3y_avg": 1, "log_sponsored_amount": 1, "log_consultancy_amount": 1,
        "faculty_entered": 1, "phd_pursuing_ft": 1, "sponsored_projects_3y": 1, "log_opex_per_student": 1,
    },
    "go": {  # GPH(40) GUE(15) GMS(25) GPHD(20)
        "placed_or_hs_rate": 1, "graduation_rate_capped": 1, "log_median_salary": 1, "phd_grad_3y_avg": 1,
    },
    "oi": {  # RD(30) WD(30) ESCS(20) PCS(20)
        "outside_state_pct": 1, "outside_country_pct": 1, "women_students_pct": 1,
        "full_fee_reimb_pct": 1, "pcs_score_0_3": 1,
    },
}
ALL_FEATURES = sorted({f for d in PARAM_FEATURES.values() for f in d})


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Derive the model features from a submissions-shaped frame (also used for what-if)."""
    d = df.copy()
    f = d.get("faculty_parsed").fillna(d.get("faculty_entered")) if "faculty_parsed" in d else d["faculty_entered"]
    n = d["students_total"].fillna(0) + d["phd_pursuing_ft"].fillna(0)
    d["faculty_per_student"] = (f / n.replace(0, np.nan)).clip(upper=0.2)
    d["log_capex_per_student"] = np.log1p(d["capex_per_student"])
    d["log_opex_per_student"] = np.log1p(d["opex_per_student"])
    d["log_sponsored_amount"] = np.log1p(d["sponsored_amount_3y_avg"])
    d["log_consultancy_amount"] = np.log1p(d["consultancy_amount_3y_avg"])
    d["log_median_salary"] = np.log1p(d["median_salary_ug"])
    # publications / citations: OpenAlex column names, or the names the Live Data form uses
    pubs = d["publications_3y"] if "publications_3y" in d else d.get("scopus_publications_3y")
    cites = d["citations_3y"] if "citations_3y" in d else d.get("scopus_citations_3y")
    if pubs is None:
        pubs = pd.Series(np.nan, index=d.index)
    if cites is None:
        cites = pd.Series(np.nan, index=d.index)
    fac = pd.to_numeric(f, errors="coerce").replace(0, np.nan)
    d["log_pubs_per_faculty"] = np.log1p(pd.to_numeric(pubs, errors="coerce").astype(float) / fac)
    d["log_cites_per_faculty"] = np.log1p(pd.to_numeric(cites, errors="coerce").astype(float) / fac)
    d["graduation_rate_capped"] = d["graduation_rate"].clip(upper=1.0)
    d["placed_or_hs_rate"] = d["placed_or_hs_rate"].clip(upper=1.0)
    d["faculty_entered"] = f
    return d


# metrics the Live Data form collects that map straight onto model inputs
LIVE_TO_FEATURE = {
    "students_total": "students_total", "students_female": "students_female",
    "students_outside_state": "students_outside_state", "faculty_parsed": "faculty_parsed",
    "phd_pursuing_ft": "phd_pursuing_ft", "phd_grad_3y_avg": "phd_grad_3y_avg",
    "graduated_total": "graduated_total", "placed_total": "placed_total",
    "higher_studies_total": "higher_studies_total", "median_salary_ug": "median_salary_ug",
    "capex_per_student": "capex_per_student", "opex_per_student": "opex_per_student",
    "sponsored_amount_3y_avg": "sponsored_amount_3y_avg", "sponsored_projects_3y": "sponsored_projects_3y",
    "consultancy_amount_3y_avg": "consultancy_amount_3y_avg",
    "scopus_publications_3y": "publications_3y", "scopus_citations_3y": "citations_3y",
    "women_students_pct": "women_students_pct", "outside_state_pct": "outside_state_pct",
    "full_fee_reimb_pct": "full_fee_reimb_pct",
}


def apply_live(base: pd.DataFrame, live: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Overlay staff-entered values on the latest filing and recompute the fields derived from them.

    `live` is a frame of (metric, value) - the latest entry per metric. Returns the updated row and
    the list of metrics that were actually applied, so the app can show what changed.
    """
    d = base.copy().reset_index(drop=True)
    used = []
    if live is None or len(live) == 0:
        return d, used
    for _, r in live.iterrows():
        col = LIVE_TO_FEATURE.get(r["metric"])
        if col:
            d.loc[0, col] = float(r["value"])
            used.append(r["metric"])
    # keep the percentage/rate fields consistent with any counts that were entered
    tot = d.get("students_total", pd.Series([np.nan])).iloc[0]
    if tot and not pd.isna(tot):
        if "students_female" in d and pd.notna(d.students_female.iloc[0]):
            d.loc[0, "women_students_pct"] = 100 * d.students_female.iloc[0] / tot
        if "students_outside_state" in d and pd.notna(d.students_outside_state.iloc[0]):
            d.loc[0, "outside_state_pct"] = 100 * d.students_outside_state.iloc[0] / tot
    grad = d.get("graduated_total", pd.Series([np.nan])).iloc[0]
    if grad and not pd.isna(grad):
        placed = d.get("placed_total", pd.Series([0])).iloc[0] or 0
        hs = d.get("higher_studies_total", pd.Series([0])).iloc[0] or 0
        d.loc[0, "placement_rate"] = placed / grad
        d.loc[0, "placed_or_hs_rate"] = (placed + hs) / grad
    return d, used


# Publications are only used once the sample is broad enough to include institutes like the client.
# A partial sample (only elite institutes have data) makes the model extrapolate to ~0 for anyone
# below its trained range, which is worse than not using the feature at all.
MIN_PUB_COVERAGE = 0.60          # share of training rows that must carry publication data
MIN_PUB_LOW_RANK_ROWS = 60       # of which this many must be ranked outside the top 50


def publications_usable(df: pd.DataFrame, verbose: bool = True) -> bool:
    if "publications_3y" not in df:
        return False
    has = df["publications_3y"].notna()
    coverage = has.mean()
    low_rank = int((has & (df["rank"] > 50)).sum())
    ok = coverage >= MIN_PUB_COVERAGE and low_rank >= MIN_PUB_LOW_RANK_ROWS
    if verbose:
        print(f"publication coverage {100 * coverage:.0f}% ({has.sum()}/{len(df)}), "
              f"{low_rank} rows ranked outside the top 50 -> "
              + ("using publication features" if ok else "NOT using them (sample too narrow)"))
    return ok


def active_features(df: pd.DataFrame, verbose: bool = True) -> dict[str, dict[str, int]]:
    """PARAM_FEATURES, minus the publication inputs when the data cannot support them."""
    feats = {k: dict(v) for k, v in PARAM_FEATURES.items()}
    if not publications_usable(df, verbose):
        for k in ("log_pubs_per_faculty", "log_cites_per_faculty"):
            feats["rpc"].pop(k, None)
    return feats


def training_frame(con: sqlite3.Connection) -> pd.DataFrame:
    q = """
    SELECT s.*, r.tlr, r.rpc, r."go" AS go_score, r.oi, r.pr, r.score, r.rank
    FROM submissions s JOIN rankings r
      ON r.year=s.year AND r.institute_id=s.institute_id AND r.category=s.category
    WHERE s.category='Engineering' AND r.rank<=200
    """
    df = pd.read_sql(q, con)
    pub_csv = ROOT / "data" / "processed" / "publications.csv"
    if pub_csv.exists():
        pubs = pd.read_csv(pub_csv)[["year", "institute_id", "publications_3y", "citations_3y"]]
        df = df.merge(pubs, on=["year", "institute_id"], how="left")
        n = df.publications_3y.notna().sum()
        print(f"publication data joined for {n}/{len(df)} institute-years ({100 * n / len(df):.0f}%)")
    return engineer(df)


def fit_param(df: pd.DataFrame, target: str, feats: dict[str, int], seed: int = 7) -> tuple[xgb.XGBRegressor, dict]:
    X = df[list(feats)].astype(float)
    y = df[target].astype(float)
    groups = df["institute_id"]
    params = dict(
        n_estimators=400, max_depth=3, learning_rate=0.04, subsample=0.9, colsample_bytree=0.9,
        min_child_weight=4, reg_lambda=2.0, monotone_constraints=tuple(feats.values()),
        objective="reg:squarederror", random_state=seed,
    )
    # grouped CV by institute so the same college's other years never leak
    preds = np.zeros(len(df))
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        m = xgb.XGBRegressor(**params).fit(X.iloc[tr], y.iloc[tr])
        preds[te] = m.predict(X.iloc[te])
    resid = y - preds
    report = {
        "n": int(len(df)),
        "cv_r2": round(1 - float((resid ** 2).sum() / ((y - y.mean()) ** 2).sum()), 3),
        "cv_mae": round(float(resid.abs().mean()), 2),
        "cv_rmse": round(float(np.sqrt((resid ** 2).mean())), 2),
        "features": list(feats),
    }
    model = xgb.XGBRegressor(**params).fit(X, y)
    imp = model.get_booster().get_score(importance_type="gain")
    tot = sum(imp.values()) or 1
    report["importance"] = {k: round(v / tot, 3) for k, v in sorted(imp.items(), key=lambda kv: -kv[1])}
    return model, report


class ScoreModel:
    """Bundle of per-parameter models + the published weights, with explain()."""

    def __init__(self, models: dict[str, xgb.XGBRegressor], weights: dict[str, float], report: dict,
                 features: dict[str, dict[str, int]] | None = None):
        self.models, self.weights, self.report = models, weights, report
        self.features = features or {k: dict(v) for k, v in PARAM_FEATURES.items()}

    def predict_params(self, raw: pd.DataFrame) -> pd.DataFrame:
        d = engineer(raw)
        out = pd.DataFrame(index=d.index)
        for p, feats in self.features.items():
            out[p] = np.clip(self.models[p].predict(d[list(feats)].astype(float)), 0, 100)
        return out

    def total(self, params: pd.DataFrame, pr: float | pd.Series) -> pd.Series:
        return sum(params[p] * self.weights[p] for p in ("tlr", "rpc", "go", "oi")) + self.weights["pr"] * pr

    def contributions(self, raw: pd.DataFrame, param: str) -> pd.DataFrame:
        """Per-feature contribution to the predicted parameter score (SHAP-style, from XGBoost)."""
        d = engineer(raw)
        feats = list(self.features[param])
        booster = self.models[param].get_booster()
        c = booster.predict(xgb.DMatrix(d[feats].astype(float)), pred_contribs=True)
        return pd.DataFrame(c, columns=feats + ["baseline"], index=d.index)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        dump(self, path)

    @staticmethod
    def load(path: Path | None = None) -> "ScoreModel":
        import sys
        sys.modules["__main__"].ScoreModel = ScoreModel  # tolerate artifacts pickled from a __main__ run
        return load(path or ART / "score_model.joblib")


def main() -> None:
    con = sqlite3.connect(DB)
    df = training_frame(con)
    w = pd.read_sql("SELECT parameter, parameter_weight FROM methodology WHERE year=2025 AND category='Engineering'", con)
    weights = {k.lower(): float(v) for k, v in w.drop_duplicates("parameter").values}
    weights = {"tlr": weights.get("tlr", 0.3), "rpc": weights.get("rpc", 0.3), "go": weights.get("go", 0.2),
               "oi": weights.get("oi", 0.1), "pr": weights.get("pr", 0.1)}
    feature_set = active_features(df)
    models, report = {}, {"weights": weights, "params": {}, "uses_publications": "log_pubs_per_faculty" in feature_set["rpc"]}
    target_col = {"tlr": "tlr", "rpc": "rpc", "go": "go_score", "oi": "oi"}
    for p, feats in feature_set.items():
        m, rep = fit_param(df, target_col[p], feats)
        models[p], report["params"][p] = m, rep
        print(f"{p.upper():4s} n={rep['n']} CV R2={rep['cv_r2']:.3f} MAE={rep['cv_mae']:.2f}  top: "
              + ", ".join(f"{k}={v:.2f}" for k, v in list(rep["importance"].items())[:3]))
    # construct through the importable module so the pickle references score_model.ScoreModel, not __main__
    import importlib
    sm = importlib.import_module("score_model").ScoreModel(models, weights, report, feature_set)
    # sanity: reproduced total for the training rows
    pp = sm.predict_params(df)
    tot = sm.total(pp, df["pr"])
    report["total_score_fit"] = {"mae": round(float((tot - df["score"]).abs().mean()), 2),
                                 "r2": round(1 - float(((tot - df["score"]) ** 2).sum() / ((df["score"] - df["score"].mean()) ** 2).sum()), 3)}
    print("total score (in-sample, with published PR):", report["total_score_fit"])
    sm.save(ART / "score_model.joblib")

    # score Saveetha Engineering College from its own submissions (2025 and 2026 filings)
    sec = pd.read_sql(f"SELECT * FROM submissions WHERE institute_id='{SEC_ID}' AND category='Engineering' ORDER BY year", con)
    if len(sec):
        est = sm.predict_params(sec)
        est.insert(0, "year", sec["year"].values)
        # PR: Saveetha's own published PR was 5.64 (2017) and 0.41 (2019); colleges ranked 60-100 have low PR
        pr_ref = pd.read_sql("SELECT pr FROM rankings WHERE category='Engineering' AND year=2025 AND rank BETWEEN 60 AND 100 AND institute_id LIKE 'IR-E-C-%'", con)["pr"]
        est["pr_assumed"] = round(float(pr_ref.median()), 2)
        est["total_est"] = sm.total(est, est["pr_assumed"]).round(2)
        report["saveetha_estimates"] = est.round(2).to_dict(orient="records")
        print("\nSaveetha Engineering College estimated parameter scores:")
        print(est.round(2).to_string(index=False))
    (ROOT / "data" / "processed" / "model_report.json").write_text(json.dumps(report, indent=2))
    con.close()


if __name__ == "__main__":
    main()
