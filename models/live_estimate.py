"""Re-score the college and re-run the 2026 forecast from the numbers staff enter.

Used by the app (Live Data, Prediction, What-If, Home) and the chatbot, so all of them show the
same figures. Three pieces:

  METRICS       every field staff can enter: label, unit, allowed range, and which NIRF parameter it
                moves (or why it is recorded only). The entry form and the server-side checks both
                read this list, so a field cannot be shown without being validated.
  estimate()    filed numbers + latest staff values -> estimated TLR / RPC / GO / OI, with notes on
                every assumption made.
  forecast()    parameter estimates -> Monte Carlo total, expected rank and band probabilities.
                predict_2026.py uses the same function, so the static and live forecasts cannot drift.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from score_model import (ScoreModel, apply_live, engineer, expected_output, fq_marks, pubs_for_index,
                         research_output_index, retraction_deduction)

PARAMS4 = ("tlr", "rpc", "go", "oi")
BAND_ORDER = ["top 100", "101-150", "151-200", "201-250", "251-300", "below 300"]


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    kind: str          # count | pct | inr
    max: float
    moves: str         # what it changes, shown next to the field
    scored: bool = True


METRICS: list[Metric] = [
    Metric("scopus_publications_3y", "Publications, last 3 calendar years (all document types)", "count", 100_000,
           "Research (RPC): publications are 35 of its 100 marks"),
    Metric("scopus_citations_3y", "Citations received in the last 3 calendar years (to all the college's papers)", "count", 5_000_000,
           "Research (RPC): citations are 40 of its 100 marks"),
    Metric("retracted_papers_3y", "Retracted papers, last 3 years", "count", 10_000,
           "Research (RPC): NIRF deducts up to 5 marks"),
    Metric("phd_pursuing_ft", "Full-time PhD scholars enrolled", "count", 20_000, "Teaching (TLR) and Research (RPC)"),
    Metric("phd_pursuing_pt", "Part-time PhD scholars enrolled", "count", 20_000,
           "Recorded only: the model is trained on full-time scholars", scored=False),
    Metric("phd_grad_3y_avg", "PhDs awarded per year (3-year average)", "count", 5_000, "Graduation (GO) and Research (RPC)"),
    Metric("faculty_parsed", "Full-time faculty", "count", 20_000, "Teaching (TLR): faculty-student ratio"),
    Metric("faculty_phd_pct", "Faculty with a PhD (%)", "pct", 100, "Teaching (TLR): NIRF's FQ formula, up to 10 marks"),
    Metric("students_total", "Students enrolled, UG + PG, all years", "count", 200_000, "Teaching (TLR) and the diversity percentages"),
    Metric("students_female", "Women students", "count", 200_000, "Outreach (OI): women's share"),
    Metric("students_outside_state", "Students from other states", "count", 200_000, "Outreach (OI): regional diversity"),
    Metric("graduated_total", "Students graduated in the stipulated time (latest batch)", "count", 100_000, "Graduation (GO): placement rate"),
    Metric("placed_total", "Students placed (latest batch)", "count", 100_000, "Graduation (GO): placement rate"),
    Metric("higher_studies_total", "Students gone for higher studies (latest batch)", "count", 100_000, "Graduation (GO): placement rate"),
    Metric("median_salary_ug", "Median UG salary (₹ per year)", "inr", 1e8, "Graduation (GO): median salary, 25 marks"),
    Metric("capex_per_student", "Capital spend per student per year (₹)", "inr", 1e8, "Teaching (TLR): financial resources"),
    Metric("opex_per_student", "Operating spend per student per year (₹)", "inr", 1e8, "Teaching (TLR): financial resources"),
    Metric("sponsored_amount_3y_avg", "Sponsored research received per year (₹, 3-year average)", "inr", 1e11, "Research (RPC)"),
    Metric("sponsored_projects_3y", "Sponsored projects, last 3 years", "count", 100_000, "Research (RPC)"),
    Metric("consultancy_amount_3y_avg", "Consultancy received per year (₹, 3-year average)", "inr", 1e11, "Research (RPC)"),
    Metric("patents_published_3y", "Patents published, last 3 years", "count", 100_000,
           "Recorded only: peer patent counts are not in NIRF's published data, so the scale cannot be fitted", scored=False),
    Metric("patents_granted_3y", "Patents granted, last 3 years", "count", 100_000,
           "Recorded only: peer patent counts are not in NIRF's published data, so the scale cannot be fitted", scored=False),
    Metric("women_students_pct", "Women students (%), if you do not have the count", "pct", 100, "Outreach (OI)"),
    Metric("outside_state_pct", "Students from other states (%), if you do not have the count", "pct", 100, "Outreach (OI)"),
    Metric("full_fee_reimb_pct", "Students on full tuition-fee reimbursement (%)", "pct", 100, "Outreach (OI): ESCS"),
]
METRIC_BY_KEY = {m.key: m for m in METRICS}


def validate(values: dict[str, float], current: dict[str, float]) -> list[str]:
    """Server-side checks. `values` is what was just typed; `current` is the latest known value of every
    metric (staff entry, else the filing). Returns human-readable problems; empty means accept."""
    errs: list[str] = []
    for k, v in values.items():
        m = METRIC_BY_KEY.get(k)
        if m is None:
            errs.append(f"Unknown field '{k}'.")
            continue
        if v is None or not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
            errs.append(f"{m.label}: not a number.")
            continue
        if v < 0 or v > m.max:
            errs.append(f"{m.label}: must be between 0 and {m.max:,.0f}.")
    if errs:
        return errs
    merged = {**current, **values}
    g = lambda k: merged.get(k)  # noqa: E731
    checks = [
        ("students_female", "students_total", "Women students cannot exceed total students."),
        ("students_outside_state", "students_total", "Students from other states cannot exceed total students."),
        ("retracted_papers_3y", "scopus_publications_3y", "Retracted papers cannot exceed publications."),
    ]
    for part, whole, msg in checks:
        if (part in values or whole in values) and g(part) is not None and g(whole) is not None and g(part) > g(whole):
            errs.append(msg)
    if {"placed_total", "higher_studies_total", "graduated_total"} & set(values):
        p, h, gr = g("placed_total") or 0, g("higher_studies_total") or 0, g("graduated_total")
        if gr and p + h > gr * 1.0001:
            errs.append("Placed plus higher studies cannot exceed the number who graduated.")
    return errs


def _row(d: pd.DataFrame, col: str) -> float:
    v = d[col].iloc[0] if col in d else np.nan
    return float(v) if pd.notna(v) else float("nan")


def pub_shift(sm: ScoreModel, base: pd.DataFrame, pubs: float | None, cites: float | None) -> tuple[float, list[str], float | None]:
    """RPC change implied by real publication/citation counts, against what the filed profile implies.
    Returns (shift, notes, publications used). The expectation always comes from the *filed* profile, so
    changing funding or PhDs never lowers RPC through this term."""
    adj = getattr(sm, "pub_adj", None)
    if not adj or (pubs is None and cites is None):
        return 0.0, [], None
    notes = []
    k = adj["cites_per_paper_rank_over_100"]
    if pubs is None:
        pubs = cites / k
        notes.append(f"Publications not entered; assumed {pubs:,.0f} from the citations at {k:g} citations per paper "
                     "(the median for institutes ranked 101-200).")
    if cites is None:
        cites = pubs * k
        notes.append(f"Citations not entered; assumed {cites:,.0f} at {k:g} citations per paper "
                     "(the median for institutes ranked 101-200).")
    expected = expected_output(adj, engineer(base))
    shift = adj["beta"] * (float(research_output_index(pubs, cites)) - expected)
    return shift, notes, float(pubs)


def implied_publications(sm: ScoreModel, base: pd.DataFrame) -> float | None:
    """Publications (3 years) a typical institute with the filed profile has: what the estimate assumes
    until staff enter the real figure."""
    adj = getattr(sm, "pub_adj", None)
    return pubs_for_index(adj, expected_output(adj, engineer(base))) if adj else None


def estimate(sm: ScoreModel, base: pd.DataFrame, live: pd.DataFrame | None, base_phd_pct: float | None) -> dict:
    """Filed row + latest staff values -> estimated parameter scores, with the reasoning attached."""
    base = base.reset_index(drop=True)
    live = live if live is not None else pd.DataFrame(columns=["metric", "value"])
    vals = {str(m): float(v) for m, v in zip(live.get("metric", []), live.get("value", []))}
    w, applied = apply_live(base, live)
    filed = sm.predict_params(base).iloc[0]
    p = sm.predict_params(w).iloc[0].astype(float).copy()
    notes: list[str] = []
    sd = {k: float(sm.report["params"][k]["cv_rmse"]) for k in PARAMS4}
    adjustments = {"tlr_faculty_phd": 0.0, "rpc_publications": 0.0, "rpc_retractions": 0.0}

    if "faculty_phd_pct" in vals and base_phd_pct is not None:
        before = fq_marks(base_phd_pct, _row(base, "faculty_parsed"), _row(base, "students_total") + _row(base, "phd_pursuing_ft"))
        after = fq_marks(vals["faculty_phd_pct"], _row(w, "faculty_parsed"), _row(w, "students_total") + _row(w, "phd_pursuing_ft"))
        p["tlr"] += after - before
        adjustments["tlr_faculty_phd"] = after - before
        applied.append("faculty_phd_pct")
        notes.append(f"Faculty with PhD {base_phd_pct:g}% → {vals['faculty_phd_pct']:g}%: NIRF's FQ formula moves TLR by {after - before:+.2f}.")

    pubs, cites = vals.get("scopus_publications_3y"), vals.get("scopus_citations_3y")
    shift, pnotes, pubs_used = pub_shift(sm, base, pubs, cites)
    if pubs is not None or cites is not None:
        p["rpc"] += shift
        adjustments["rpc_publications"] = shift
        notes += pnotes
        adj = sm.pub_adj
        if adj:
            notes.append(f"Publications and citations move RPC by {shift:+.2f} against a typical institute with the college's "
                         f"filed profile (about {implied_publications(sm, base):,.0f} papers over 3 years).")
            sd["rpc"] *= adj["cv_rmse_with"] / adj["cv_rmse_without"]

    retracted = vals.get("retracted_papers_3y")
    if retracted:
        ref = pubs_used if pubs_used is not None else implied_publications(sm, base) or 0
        ded = retraction_deduction(retracted, ref)
        p["rpc"] -= ded
        adjustments["rpc_retractions"] = -ded
        applied.append("retracted_papers_3y")
        notes.append(f"{retracted:g} retracted papers: RPC reduced by {ded:.2f} (NIRF deducts up to 5; we assume the full "
                     "deduction at 1% of papers, as NIRF has not published the scale).")

    for k in PARAMS4:
        p[k] = float(np.clip(p[k], 0, 100))
    recorded_only = sorted(k for k in vals if k in METRIC_BY_KEY and not METRIC_BY_KEY[k].scored)
    # full precision here (the forecast must match predict_2026.py exactly); pages round for display
    return {"params": {k: float(p[k]) for k in PARAMS4}, "filed": {k: float(filed[k]) for k in PARAMS4},
            "sd": sd, "applied": sorted(set(applied)), "recorded_only": recorded_only, "notes": notes,
            "adjustments": {k: round(v, 3) for k, v in adjustments.items()}}


def _int_keys(d: dict) -> dict:
    return {int(k): v for k, v in d.items()}


def forecast(params: dict, sd: dict, weights: dict, thr: dict, pr_pool: np.ndarray, n: int = 20000, seed: int = 42) -> dict:
    """Monte Carlo over model error, the unknown Perception score and the threshold trend."""
    rng = np.random.default_rng(seed)
    f = _int_keys(thr["forecast_2026"])
    ratios = _int_keys(thr["ratio_to_rank100"])
    sims = {p: np.clip(params[p] + rng.normal(0, sd[p], n), 0, 100) for p in PARAMS4}
    pr = rng.choice(pr_pool, n) if len(pr_pool) else rng.uniform(0.5, 12, n)
    total = sum(sims[p] * weights[p] for p in PARAMS4) + weights["pr"] * pr
    f100 = f[100] + rng.normal(0, thr["trend_resid_sd"], n)
    bands = {"top 100": (total >= f100).mean(),
             "101-150": ((total < f100) & (total >= f100 * ratios[150])).mean(),
             "151-200": ((total < f100 * ratios[150]) & (total >= f100 * ratios[200])).mean(),
             "201-250": ((total < f100 * ratios[200]) & (total >= f100 * ratios[250])).mean(),
             "251-300": ((total < f100 * ratios[250]) & (total >= f100 * ratios[300])).mean(),
             "below 300": (total < f100 * ratios[300]).mean()}
    ks = np.array([100, 125, 150, 175, 200, 250, 300])
    sc = np.array([f[k] for k in ks])
    exp_rank = float(np.interp(-np.median(total), -sc, ks))
    return {
        "param_estimates": {p: round(float(params[p]), 2) for p in PARAMS4},
        "pr_assumption": {"median": round(float(np.median(pr)), 2), "p10": round(float(np.percentile(pr, 10)), 2),
                          "p90": round(float(np.percentile(pr, 90)), 2)},
        "total_score": {"median": round(float(np.median(total)), 2), "p10": round(float(np.percentile(total, 10)), 2),
                        "p90": round(float(np.percentile(total, 90)), 2)},
        "expected_rank": int(round(exp_rank)), "most_likely_band": max(bands, key=bands.get),
        "band_probabilities": {k: round(float(v), 3) for k, v in bands.items()},
        "gap_to_top100": round(float(f[100] - np.median(total)), 2),
        "gap_to_top200": round(float(f[200] - np.median(total)), 2),
    }


def pr_pool_from(rankings: pd.DataFrame) -> np.ndarray:
    """Perception is unknown: draw it from private colleges ranked 60-100 in 2025."""
    r = rankings
    return r[(r.year == 2025) & (r["rank"].between(60, 100)) & r.institute_id.str.contains("-C-")].pr.values
