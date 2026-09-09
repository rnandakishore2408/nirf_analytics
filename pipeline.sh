#!/usr/bin/env bash
# Re-run the whole data pipeline: scrape -> PDFs -> parse -> database -> model -> forecast -> analysis -> search index.
# Safe to re-run: pages and PDFs are cached under data/raw/, everything else is rebuilt.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python

echo "1/7 rankings, bands, participants (2016-2025; 2016 pages are dropped later as duplicates of 2017)"
$PY scraper/scrape_rankings.py 2016,2017,2018,2019,2020,2021,2022,2023,2024,2025 Engineering,Overall,College,University
echo "2/7 per-institute PDFs (Engineering top-100 2023-25, top-200 2021-22) + methodology PDFs"
$PY scraper/download_pdfs.py 2023,2024,2025 Engineering
$PY -c "import sys; sys.path.insert(0,'scraper'); from download_pdfs import download_institutes; download_institutes([2021,2022],['Engineering'],top_n=200)"
for f in data/raw/methodology/*.pdf; do pdftotext -layout "$f" "${f%.pdf}.txt"; done
echo "3/7 parse PDFs"
$PY scraper/parse_pdfs.py
echo "4/7 build database"
$PY scraper/build_db.py
echo "5/7 score model"
$PY models/score_model.py
echo "6/7 2026 forecast + analysis"
$PY models/predict_2026.py
$PY analysis/analyze.py
echo "7/7 search index"
$PY app/rag/index.py
echo "done. run:  ./run.sh"
