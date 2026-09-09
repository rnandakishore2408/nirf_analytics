"""Download per-institute NIRF data PDFs (the raw data every ranked institute submitted)
for the top-N institutes in given years/categories, plus the yearly methodology PDFs.

Files land in data/raw/pdf/<year>/<category>/<institute_id>.pdf
and data/raw/methodology/<year>_<category>.pdf
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw" / "pdf"
METH_DIR = ROOT / "data" / "raw" / "methodology"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) NIRF-analytics-research"}

METHODOLOGY_URLS = {
    # candidates tried in order; first 200 wins
    "Engineering": [
        "https://www.nirfindia.org/nirfpdfcdn/{y}/framework/Engineering.pdf",
        "https://www.nirfindia.org/Docs/{y}/Engineering.pdf",
        "https://www.nirfindia.org/nirfpdfcdn/{y}/framework/Engg.pdf",
    ],
    "Overall": [
        "https://www.nirfindia.org/nirfpdfcdn/{y}/framework/Overall.pdf",
        "https://www.nirfindia.org/Docs/{y}/Overall.pdf",
    ],
    "College": [
        "https://www.nirfindia.org/nirfpdfcdn/{y}/framework/College.pdf",
        "https://www.nirfindia.org/nirfpdfcdn/{y}/framework/Colleges.pdf",
    ],
}


def _get(url: str, dest: Path, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        return True
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=90)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                return True
            if r.status_code == 404:
                return False
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return False


def download_institutes(years: list[int], categories: list[str], top_n: int = 100, workers: int = 6) -> None:
    df = pd.read_csv(ROOT / "data" / "processed" / "rankings.csv")
    df = df[df.year.isin(years) & df.category.isin(categories) & (df["rank"] <= top_n)]
    jobs = []
    for _, r in df.iterrows():
        url = r.pdf_url if isinstance(r.pdf_url, str) else (
            f"https://www.nirfindia.org/nirfpdfcdn/{r.year}/pdf/{r.category}/{r.institute_id}.pdf"
        )
        jobs.append((url, PDF_DIR / str(r.year) / r.category / f"{r.institute_id}.pdf"))
    print(f"{len(jobs)} institute PDFs to fetch")
    ok = 0
    with ThreadPoolExecutor(workers) as ex:
        for i, res in enumerate(ex.map(lambda j: _get(*j), jobs), 1):
            ok += bool(res)
            if i % 25 == 0:
                print(f"  {i}/{len(jobs)} done, {ok} ok", flush=True)
    print(f"institute PDFs: {ok}/{len(jobs)} downloaded")


def download_methodology(years: list[int], categories: list[str]) -> None:
    for y in years:
        for c in categories:
            dest = METH_DIR / f"{y}_{c}.pdf"
            got = any(_get(u.format(y=y), dest) for u in METHODOLOGY_URLS.get(c, []))
            print(f"methodology {y} {c}: {'ok' if got else 'not found'}")


if __name__ == "__main__":
    yrs = [int(y) for y in sys.argv[1].split(",")] if len(sys.argv) > 1 else [2023, 2024, 2025]
    cats = sys.argv[2].split(",") if len(sys.argv) > 2 else ["Engineering"]
    download_methodology(yrs, list(set(cats) | {"Overall", "College"}))
    download_institutes(yrs, cats)
