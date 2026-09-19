"""The live re-scoring and forecast behave sensibly and agree with the saved forecast."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import live_estimate as LE
from score_model import ScoreModel, fq_marks, retraction_deduction

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ctx():
    con = sqlite3.connect(f"file:{ROOT / 'db' / 'nirf.db'}?mode=ro", uri=True)
    base = pd.read_sql("SELECT * FROM submissions WHERE institute_id='IR-E-C-16590' ORDER BY year DESC LIMIT 1", con)
    r = pd.read_sql('SELECT year, institute_id, rank, pr FROM rankings WHERE category="Engineering"', con)
    pred = json.loads((ROOT / "data" / "processed" / "prediction_2026.json").read_text())
    return {"sm": ScoreModel.load(), "base": base, "pool": LE.pr_pool_from(r), "pred": pred, "phd": float(base.faculty_phd_pct.iloc[0])}


def run(ctx, entries: dict):
    live = pd.DataFrame({"metric": list(entries), "value": list(entries.values())})
    e = LE.estimate(ctx["sm"], ctx["base"], live, ctx["phd"])
    return e, LE.forecast(e["params"], e["sd"], ctx["sm"].weights, ctx["pred"]["thresholds"], ctx["pool"])


def test_no_entries_reproduces_the_saved_forecast(ctx):
    e, f = run(ctx, {})
    saved = ctx["pred"]["saveetha"]
    assert e["params"] == e["filed"]
    for k in ("param_estimates", "total_score", "expected_rank", "most_likely_band", "band_probabilities", "gap_to_top100", "pr_assumption"):
        assert f[k] == saved[k], k


def test_forecast_is_deterministic_and_probabilities_sum_to_one(ctx):
    _, a = run(ctx, {"scopus_publications_3y": 1500})
    _, b = run(ctx, {"scopus_publications_3y": 1500})
    assert a == b
    assert abs(sum(a["band_probabilities"].values()) - 1) < 0.002


@pytest.mark.parametrize("metric,param,values,direction", [
    ("scopus_publications_3y", "rpc", [100, 400, 900, 2000, 5000], +1),
    ("scopus_citations_3y", "rpc", [1000, 5000, 20000, 60000], +1),
    ("phd_pursuing_ft", "tlr", [40, 80, 150, 300], +1),
    ("phd_grad_3y_avg", "go", [5, 12, 30, 80], +1),
    ("median_salary_ug", "go", [400000, 550000, 800000, 1200000], +1),
    ("faculty_phd_pct", "tlr", [30, 54.8, 75, 95, 100], +1),
    ("retracted_papers_3y", "rpc", [0, 2, 5, 20], -1),
])
def test_entries_move_scores_in_the_right_direction(ctx, metric, param, values, direction):
    extra = {"scopus_publications_3y": 1200} if metric == "retracted_papers_3y" else {}
    scores = [run(ctx, {**extra, metric: v})[0]["params"][param] for v in values]
    diffs = np.diff(scores) * direction
    assert (diffs >= -1e-6).all(), f"{metric} -> {param}: {scores}"
    assert scores[-1] != scores[0], f"{metric} should change {param}"


def test_more_publications_improve_the_forecast(ctx):
    _, low = run(ctx, {"scopus_publications_3y": 300})
    _, high = run(ctx, {"scopus_publications_3y": 3000})
    assert high["total_score"]["median"] > low["total_score"]["median"]
    assert high["expected_rank"] < low["expected_rank"]


def test_typical_publications_leave_research_unchanged(ctx):
    typical = LE.implied_publications(ctx["sm"], ctx["base"])
    e, _ = run(ctx, {"scopus_publications_3y": typical})
    assert abs(e["params"]["rpc"] - e["filed"]["rpc"]) < 0.05


def test_recorded_only_fields_do_not_change_scores(ctx):
    e, _ = run(ctx, {"patents_granted_3y": 50, "patents_published_3y": 900, "phd_pursuing_pt": 400})
    assert e["params"] == e["filed"] and set(e["recorded_only"]) == {"patents_granted_3y", "patents_published_3y", "phd_pursuing_pt"}


def test_notes_explain_assumptions(ctx):
    e, _ = run(ctx, {"scopus_publications_3y": 1200, "retracted_papers_3y": 3, "faculty_phd_pct": 70})
    text = " ".join(e["notes"])
    assert "Citations not entered" in text and "retracted" in text and "FQ formula" in text


def test_nirf_fq_formula():
    assert fq_marks(95, 400, 5000) == pytest.approx(10)
    assert fq_marks(100, 400, 5000) == pytest.approx(10)
    assert fq_marks(47.5, 400, 5000) == pytest.approx(5)
    # when a 1:15 ratio needs more faculty than exist, the PhD share is taken of the larger number
    assert fq_marks(95, 300, 9000) == pytest.approx(10 * (95 * 300 / 600) / 95)


def test_retraction_deduction_is_bounded():
    assert retraction_deduction(0, 1000) == 0
    assert retraction_deduction(5, 1000) == pytest.approx(2.5)
    assert retraction_deduction(1000, 1000) == 5


def test_scores_stay_within_0_and_100(ctx):
    e, _ = run(ctx, {"scopus_publications_3y": 100000, "scopus_citations_3y": 5000000, "phd_pursuing_ft": 20000, "faculty_phd_pct": 100})
    assert all(0 <= v <= 100 for v in e["params"].values())
    e, _ = run(ctx, {"scopus_publications_3y": 0, "scopus_citations_3y": 0, "retracted_papers_3y": 10000})
    assert all(0 <= v <= 100 for v in e["params"].values())


def test_publication_adjustment_was_validated(ctx):
    adj = ctx["sm"].pub_adj
    assert adj and adj["n"] >= 200 and adj["cv_rmse_with"] < adj["cv_rmse_without"]
    assert abs(adj["cv_bias_rank_over_100_with"]) < 2
