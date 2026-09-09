"""Scrape NIRF ranking tables (top-100 with parameter scores), rank-band pages and
participant lists from nirfindia.org for the requested years and categories.

Outputs (data/processed):
  rankings.csv      one row per institute-year-category with TLR/RPC/GO/OI/PR, score, rank
  rank_bands.csv    institutes placed in bands (101-150, 151-200, 201-300, ...)
  participants.csv  all institutions that applied (name/city/state)
Raw HTML is cached under data/raw/html/<year>/ so re-runs are offline.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "html"
OUT = ROOT / "data" / "processed"
BASE = "https://www.nirfindia.org/Rankings/{year}/{page}"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) NIRF-analytics-research"}

# category -> page stem on nirfindia.org
CATEGORY_PAGES = {
    "Engineering": "EngineeringRanking",
    "Overall": "OverallRanking",
    "College": "CollegeRanking",
    "University": "UniversityRanking",
}
BAND_SUFFIXES = {"150": "101-150", "200": "151-200", "250": "201-250", "300": "201-300"}


def fetch(year: int, page: str, force: bool = False) -> str | None:
    """Return cached HTML for a page, downloading it if needed. None on 404."""
    cache = RAW / str(year) / page
    if cache.exists() and not force:
        return cache.read_text(encoding="utf-8", errors="ignore")
    url = BASE.format(year=year, page=page)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            break
        except requests.RequestException as e:  # noqa: PERF203
            if attempt == 2:
                print(f"  !! failed {url}: {e}")
                return None
            time.sleep(2)
    if r.status_code != 200 or len(r.text) < 2000:
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(r.text, encoding="utf-8")
    time.sleep(0.5)
    return r.text


def _num(s: str) -> float | None:
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_ranked(html: str, year: int, category: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="tbl_overall") or soup.find("table")
    rows = []
    if table is None:
        return rows
    for tr in table.find("tbody").find_all("tr", recursive=False):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 6:
            continue
        inst_id = tds[0].get_text(strip=True)
        name_td = tds[1]
        name = name_td.find(string=True, recursive=False)
        name = (name or name_td.get_text(" ", strip=True).split("More Details")[0]).strip()
        pdf = name_td.find("a", href=re.compile(r"\.pdf$"))
        graph = name_td.find("a", href=re.compile(r"\.(jpg|png)$"))
        sub = name_td.find("div", class_="tbl_hidden")
        params = {}
        if sub is not None:
            heads = [th.get_text(strip=True).split(" ")[0].upper() for th in sub.find_all("th")]
            vals = [td.get_text(strip=True) for td in sub.find("tbody").find_all("td")]
            params = dict(zip(heads, vals))
        rows.append(
            {
                "year": year,
                "category": category,
                "institute_id": inst_id,
                "name": name,
                "city": tds[2].get_text(strip=True),
                "state": tds[3].get_text(strip=True),
                "tlr": _num(params.get("TLR", "")),
                "rpc": _num(params.get("RPC", params.get("RP", ""))),
                "go": _num(params.get("GO", "")),
                "oi": _num(params.get("OI", "")),
                "pr": _num(params.get("PERCEPTION", params.get("PR", ""))),
                "score": _num(tds[4].get_text(strip=True)),
                "rank": int(re.sub(r"\D", "", tds[5].get_text(strip=True)) or 0),
                "pdf_url": pdf["href"] if pdf else None,
                "graph_url": graph["href"] if graph else None,
            }
        )
    return rows


def parse_simple_list(html: str, year: int, category: str, band: str | None) -> list[dict]:
    """Band pages and participant lists: institute id (sometimes), name, city, state."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="tbl_overall") or soup.find("table")
    rows = []
    if table is None:
        return rows
    heads = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) < 3:
            continue
        rec = {"year": year, "category": category, "band": band}
        if "institute id" in heads and len(tds) >= 4:
            rec.update(institute_id=tds[0], name=tds[1], city=tds[2], state=tds[3])
        else:
            rec.update(institute_id=None, name=tds[0], city=tds[1], state=tds[2])
        rec["name"] = rec["name"].split("More Details")[0].strip()
        rows.append(rec)
    return rows


def scrape(years: list[int], categories: list[str]) -> None:
    ranked, bands, parts = [], [], []
    for year in years:
        for cat in categories:
            stem = CATEGORY_PAGES[cat]
            html = fetch(year, f"{stem}.html")
            if html is None:
                print(f"{year} {cat}: no page")
                continue
            r = parse_ranked(html, year, cat)
            ranked += r
            print(f"{year} {cat}: {len(r)} ranked", end="")
            for suf, label in BAND_SUFFIXES.items():
                h = fetch(year, f"{stem}{suf}.html")
                if h:
                    b = parse_simple_list(h, year, cat, label)
                    bands += b
                    print(f" | band {label}: {len(b)}", end="")
            h = fetch(year, f"{stem}ALL.html")
            if h:
                p = parse_simple_list(h, year, cat, None)
                parts += p
                print(f" | participants: {len(p)}", end="")
            print()
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ranked).to_csv(OUT / "rankings.csv", index=False)
    pd.DataFrame(bands).to_csv(OUT / "rank_bands.csv", index=False)
    pd.DataFrame(parts).to_csv(OUT / "participants.csv", index=False)
    print(f"\nwrote {len(ranked)} ranked, {len(bands)} band rows, {len(parts)} participants -> {OUT}")


if __name__ == "__main__":
    yrs = [int(y) for y in sys.argv[1].split(",")] if len(sys.argv) > 1 else list(range(2016, 2026))
    cats = sys.argv[2].split(",") if len(sys.argv) > 2 else ["Engineering", "Overall", "College", "University"]
    scrape(yrs, cats)
