# NIRF Analytics — Saveetha Engineering College

End-to-end analytics on India's NIRF rankings (Engineering category), built around one question:
**where does Saveetha Engineering College (NIRF id `IR-E-C-16590`) stand, and what must change to reach the top 100?**

What is inside:

| Layer | What |
|---|---|
| **Data** | Rankings 2017-2025 for Engineering / Overall / College / University (scores for TLR, RPC, GO, OI, PR + total + rank), rank-band pages (101-300), all participants; the raw **data-submission PDF** of every Engineering institute ranked 1-100 in 2023-25 and 1-200 in 2021-22 (704 PDFs → intake, enrolment, diversity, placements, median salary, PhDs, expenditure, research funding); NIRF methodology PDFs 2023-25; Saveetha's own 2025 (Engineering, Innovation, SDG) and 2026 filings from saveetha.ac.in |
| **Database** | `db/nirf.db` (SQLite, read-only reference data): `institutions`, `rankings`, `rank_bands`, `participants`, `submissions`, `faculty`, `methodology`, `documents` (full text for RAG), `predictions`; views `v_engineering_top100`, `v_saveetha_history`. Staff entries and accounts live separately: Supabase when deployed, `db/local_store.db` locally (`app/live_store.py`) |
| **Model** | `models/score_model.py` — monotone gradient boosting per parameter, learns NIRF's hidden normalisation f() from 700 institute-years (raw data → published TLR/RPC/GO/OI). Grouped 5-fold CV R² ≈ 0.73 / 0.78 / 0.82 / 0.74 |
| **Forecast** | `models/predict_2026.py` — 2026 cut-off thresholds (rank 100…300), projected 2026 order of the 2025 top-100 (ridge, validated on 2025: MAE 1.36 vs 1.62 naive), Saveetha's 2026 score distribution and band probabilities (Monte Carlo over model error and the unknown Perception score), single-lever what-ifs |
| **Analysis** | `analysis/analyze.py` → `data/processed/analysis.json`: cut-offs, tier profiles, movers, Tamil Nadu peers, raw-data profile vs Saveetha, gap decomposition |
| **Live re-scoring** | `models/live_estimate.py` — staff entries (publications, citations, PhD scholars, faculty PhD %, placements, spend, …) → re-estimated TLR/RPC/GO/OI → 2026 forecast re-run on every page. Publications use a validated adjustment (RPC error 9.72 → 8.62 on 215 institute-years); faculty PhD % uses NIRF's published FQ formula |
| **App** | Streamlit dashboard behind a staff sign-in (no sign-up; accounts issued with `scripts/manage_users.py`): 7 pages incl. **Live Data Entry** and **Ask the Data**, an AI analyst (Groq gpt-oss-120b, then Groq Qwen 3.8, then Gemini 3.1 Flash Lite; all free tiers) with tools: read-only SQL, BM25 search over all documents, live web fetch (public sites only), Saveetha status |
| **Tests** | `tests/` — 105 automated tests (sign-in and lock-outs, attack attempts, scoring rules, full browser-level flows); `scripts/load_test.py` stress-tests a running server. Results: [docs/TEST_REPORT.md](docs/TEST_REPORT.md) |

**Start here:** [docs/HANDOVER.md](docs/HANDOVER.md) — current findings, credentials, open items and known limits.

## Run

```bash
# one-time
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt   # or: python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                    # paste GROQ_API_KEY (free, console.groq.com) and optionally GEMINI_API_KEY (free, aistudio.google.com) for the chatbot page

./run.sh                                # dashboard on http://localhost:8501 (sign in with an account below)
./pipeline.sh                           # re-scrape / re-parse / rebuild DB / retrain / re-forecast (≈15-30 min, network-bound)

python scripts/manage_users.py add <username> "<Display name>" [--role admin]   # accounts: add / reset / disable / enable / list / events
uv pip install --python .venv/bin/python -r requirements-dev.txt && .venv/bin/python -m pytest   # run the test suite
```

Requires `pdftotext` (poppler-utils) for PDF parsing.

## Key findings (as of the NIRF 2025 results)

- **Saveetha Engineering College**: rank 91 (2017, score 36.88), band 101-150 (2018), rank 124 (2019, 34.14), band 201-250 (2020), unranked 2021-23, **band 201-300 in 2024 and 2025**. Do not confuse with Saveetha Institute of Medical and Technical Sciences (deemed university, rank 45 in 2025).
- **The bar rises ~1.6 points/year**: rank-100 cut-off 41.93 (2023) → 43.95 (2024) → 45.55 (2025) → forecast ≈ 47.0 (2026).
- **Estimated scores from Saveetha's filings** (NIRF publishes none for bands): 2025 filing ≈ 37, 2026 filing ≈ 40 (TLR ≈ 59, RPC ≈ 13, GO ≈ 58, OI ≈ 50, PR assumed ≈ 5-12). The 2025 estimate lands in the band NIRF actually published, which validates the model.
- **2026 forecast**: median 40.1 (80 % range 35.6-45.2), expected position ≈ rank 187; P(top 100) ≈ 4 %, P(101-150) ≈ 23 %, P(151-200) ≈ 31 %, P(201-250) ≈ 22 %.
- **Where the gap is**: Research (RPC ≈ 13 vs ≈ 30 for the 76-100 tier) explains most of the ~7-point gap. PhD output (12/yr vs 24+), full-time PhD scholars (61 vs 163+), spend per student (₹1.1 L vs ₹2.7 L), research funding (₹30 L vs ₹3.7 Cr) and median salary (₹5.5 L vs ₹7.3 L) are the concrete numbers behind it. Placements (97 %) and women students (33 %) are already fine.
- **Most valuable levers** (model estimate, single change from the 2026 filing): PhDs/yr → 80: +3.7; opex per student → ₹2 L: +2.0; full-time PhD scholars → 200: +1.4; median salary → ₹10 L: +1.4; sponsored research → ₹10 Cr/yr: +1.0.

## Layout

```
scraper/    scrape_rankings.py  download_pdfs.py  parse_pdfs.py  build_db.py  fetch_publications.py
models/     score_model.py  live_estimate.py  predict_2026.py  artifacts/score_model.joblib
analysis/   analyze.py
app/        Home.py (sign-in gate + navigation)  auth.py  live_store.py  common.py  views/*.py
            rag/index.py (BM25)  rag/chat.py (Groq/Gemini tool loop)
scripts/    manage_users.py  load_test.py
tests/      test_auth.py  test_security.py  test_model.py  test_app.py
data/raw/   html/ pdf/ pdf_text/ methodology/ saveetha/         data/processed/  *.csv *.json
db/nirf.db
```

## Report

`python docs/build_report.py` rebuilds `docs/NIRF_Analytics_Report.pdf` (staff-facing report; all numbers read from the DB and JSON outputs).

## Caveats

- NIRF's normalisation functions f() are unpublished; parameter scores for Saveetha are model estimates, most reliable inside the top-200 range the model was trained on.
- Publications and citations (75 of RPC's 100 marks) are not in NIRF's PDFs. Peer figures come from OpenAlex (215 institute-years). Coverage is too narrow to put them inside the main model, so they enter as a validated adjustment once staff enter the college's own counts. See docs/HANDOVER.md section 6.
- Perception is a survey; it is treated as an uncertainty (drawn from private colleges ranked 60-100).
- The 2016 pages on nirfindia.org serve the 2017 tables; they are dropped. In years with 200 numeric ranks (2019-22) the "101-150"/"151-200" band pages actually hold 201-250/251-300 and are relabelled.
