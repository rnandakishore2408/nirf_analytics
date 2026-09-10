"""Fetch publication and citation counts for ranked institutes from OpenAlex (free, no key).

Why: publications and citations are 75 of the 100 marks in NIRF's Research parameter (PU 35 + QP 40),
and they appear nowhere in the per-institute NIRF PDFs. Without them the Research score can only be
guessed from proxies, which is the single largest source of error in our model. OpenAlex covers ~95%
of the ranked Engineering institutes, so it supplies the missing side of the training data.

NIRF counts the three calendar years before the ranking year (India Rankings 2025 -> 2021-2023).

Output: data/processed/publications.csv  (year, institute_id, publications_3y, citations_3y, source)
Institution name -> OpenAlex id matches are cached in data/processed/openalex_ids.json so re-runs are cheap
and so a wrong match can be corrected by hand.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "nirf.db"
OUT = ROOT / "data" / "processed" / "publications.csv"
IDS = ROOT / "data" / "processed" / "openalex_ids.json"
API = "https://api.openalex.org"
HEADERS = {"User-Agent": "NIRF-analytics research (contact via github.com/rnandakishore2408/nirf_analytics)"}

# Institutes whose automatic match is wrong or missing; fill in by hand as they are found.
MANUAL: dict[str, str | None] = {
    # "NIRF name": "OpenAlex short id (I…)" or None when genuinely absent / too ambiguous to trust.
    # None is deliberate: a missing value is handled natively by the model, a wrong one is not.
    "Saveetha Engineering College": None,          # not catalogued; staff-entered figures are used instead
    "S.R.M. Institute of Science and Technology": "I145286018",   # only found without the dots
    "Manipal Institute of Technology": None,       # only exists inside Manipal Academy of Higher Education, which would overstate it
    "College of Engineering, Pune": None,          # search returns a different Pune college
    "PSG College of Technology": None,             # OpenAlex entry exists but holds no works
}
MIN_SIMILARITY = 0.55  # reject a candidate whose name is not recognisably the same institution


def _get(path: str, params: dict, tries: int = 3):
    for i in range(tries):
        try:
            r = requests.get(f"{API}/{path}", params=params, headers=HEADERS, timeout=45)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def clean(name: str) -> str:
    n = re.sub(r"\(.*?\)", " ", name)
    n = re.sub(r"\b(A|Deemed to be University|Deemed University)\b", " ", n, flags=re.I)
    n = re.sub(r"\b([A-Z])\.(?=[A-Z]\.)", r"\1", n)     # S.R.M. -> SRM, so the search can find it
    n = n.replace(".", " ")
    return re.sub(r"\s+", " ", n).strip()


def _norm(s: str) -> str:
    """Reduce a name to its distinctive words so two spellings can be compared."""
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(the|of|and|a|deemed|to|be|university|institute|college|technology|science|sciences|national)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def match_institution(name: str, cache: dict) -> str | None:
    """NIRF name -> OpenAlex institution id, cached. None means 'no match, do not retry'."""
    if name in MANUAL:
        return MANUAL[name]
    if name in cache:
        return cache[name]
    js = _get("institutions", {"search": clean(name), "per-page": 10, "filter": "country_code:IN"})
    best = None
    if js and js.get("results"):
        # OpenAlex often holds an empty duplicate entry that outranks the real one, so score every
        # candidate: it must actually have works, and its name must be recognisably the same place.
        cands = [(similarity(name, c["display_name"]), c.get("works_count", 0), c["id"].split("/")[-1], c["display_name"])
                 for c in js["results"] if c.get("works_count", 0) > 0]
        cands = [c for c in cands if c[0] >= MIN_SIMILARITY]
        if cands:
            cands.sort(key=lambda t: (-t[0], -t[1]))
            best = cands[0][2]
    cache[name] = best
    IDS.write_text(json.dumps(cache, indent=1, sort_keys=True))
    time.sleep(0.12)
    return best


def counts_by_year(inst_id: str, cache: dict) -> dict[int, tuple[int, int]]:
    """{calendar year: (works, citations)} from the institution's own yearly counts (one API call)."""
    if inst_id in cache:
        return {int(k): tuple(v) for k, v in cache[inst_id].items()}
    js = _get(f"institutions/{inst_id}", {})
    out = {}
    if js:
        for row in js.get("counts_by_year", []):
            out[int(row["year"])] = (int(row.get("works_count", 0)), int(row.get("cited_by_count", 0)))
    cache[inst_id] = {str(k): list(v) for k, v in out.items()}
    time.sleep(0.12)
    return out


def main(years: list[int], max_rank: int = 200) -> None:
    con = sqlite3.connect(DB)
    todo = pd.read_sql(
        f"SELECT DISTINCT year, institute_id, name FROM rankings WHERE category='Engineering' "
        f"AND year IN ({','.join(map(str, years))}) AND rank<={max_rank} ORDER BY year, rank", con)
    ids_cache = json.loads(IDS.read_text()) if IDS.exists() else {}
    counts_cache_path = ROOT / "data" / "processed" / "openalex_counts.json"
    counts_cache = json.loads(counts_cache_path.read_text()) if counts_cache_path.exists() else {}

    rows, unmatched = [], []
    for i, rec in enumerate(todo.itertuples(), 1):
        oid = match_institution(rec.name, ids_cache)
        if not oid:
            unmatched.append(rec.name)
            continue
        by_year = counts_by_year(oid, counts_cache)
        window = range(rec.year - 4, rec.year - 1)  # NIRF 2025 -> 2021, 2022, 2023
        pubs = sum(by_year.get(y, (0, 0))[0] for y in window)
        cites = sum(by_year.get(y, (0, 0))[1] for y in window)
        if pubs:
            rows.append({"year": rec.year, "institute_id": rec.institute_id, "name": rec.name,
                         "openalex_id": oid, "publications_3y": pubs, "citations_3y": cites, "source": "openalex"})
        if i % 40 == 0:
            counts_cache_path.write_text(json.dumps(counts_cache))
            print(f"  {i}/{len(todo)} processed, {len(rows)} with data", flush=True)
    counts_cache_path.write_text(json.dumps(counts_cache))

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\nwrote {len(df)} institute-years to {OUT}")
    if len(df):
        cov = df.groupby("year").size()
        tot = todo.groupby("year").size()
        print("coverage by year:")
        for y in cov.index:
            print(f"  {y}: {cov[y]}/{tot[y]} ({100 * cov[y] / tot[y]:.0f}%)")
    print(f"unmatched institutes ({len(set(unmatched))}): {sorted(set(unmatched))[:8]}")


if __name__ == "__main__":
    yrs = [int(y) for y in sys.argv[1].split(",")] if len(sys.argv) > 1 else [2021, 2022, 2023, 2024, 2025]
    main(yrs, int(sys.argv[2]) if len(sys.argv) > 2 else 200)
