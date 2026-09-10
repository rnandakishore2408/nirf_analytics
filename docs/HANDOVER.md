# Handover — NIRF Analytics for Saveetha Engineering College

Last updated: 10 September 2026

Client: **Saveetha Engineering College**, Sriperumbudur, Tamil Nadu. NIRF id `IR-E-C-16590`.
Not to be confused with **Saveetha Institute of Medical and Technical Sciences** (`IR-E-I-1441`),
a deemed university in Chennai ranked 45 in 2025. They are separate NIRF entities.

---

## 1. What this project answers

Where the college stands in the NIRF Engineering ranking, why, what 2026 is likely to bring, and
which changes would move the score most. NIRF publishes no scores below rank 100, so the college's
own parameter scores are **model estimates**, not official figures. Say "estimated" when quoting them.

## 2. Current findings

| | |
|---|---|
| NIRF 2024 and 2025 result | Band 201-300 |
| Last numeric rank | 124 in 2019 (rank 91 in 2017) |
| Estimated score, 2025 filing | 37.2 |
| Estimated score, 2026 filing | 39.7 |
| Score needed for rank 100 in 2026 | about 47.0 |
| Most likely 2026 band | 151-200 (31%); top 200 58%; top 100 4% |
| Largest gap | Research (RPC), estimated 13.4 against about 30 for institutes ranked 76-100 |

Full year-by-year record, verified live against nirfindia.org:

| Year | Result |
|---|---|
| 2017 | Rank 91 (score 36.88) |
| 2018 | Band 101-150 |
| 2019 | Rank 124 (score 34.14) |
| 2020 | Band 201-250 |
| 2021 | Band 201-250 |
| 2022 | Applied, not placed in any published list |
| 2023 | Applied, not placed in any published list |
| 2024 | Band 201-300 |
| 2025 | Band 201-300 |

## 3. Running it

```bash
./run.sh          # dashboard at http://localhost:8501
./pipeline.sh     # re-scrape, re-parse, rebuild, retrain, re-forecast (30-60 min, network bound)
python docs/build_report.py    # rebuild the staff PDF
```

Requires `pdftotext` (poppler-utils). Dependencies live in `.venv`; `requirements.txt` lists them.

## 4. Layout

```
scraper/    scrape_rankings.py · download_pdfs.py · parse_pdfs.py · build_db.py · fetch_publications.py
models/     score_model.py (learns NIRF's hidden curves) · predict_2026.py · artifacts/
analysis/   analyze.py -> data/processed/analysis.json
app/        Home.py · common.py · live_store.py · pages/1-6 · rag/index.py · rag/chat.py
data/raw/   html/ pdf/ pdf_text/ methodology/ saveetha/   (everything downloaded, kept for audit)
data/processed/   CSVs + analysis.json, prediction_2026.json, model_report.json, publications.csv
db/nirf.db  the single SQLite database
docs/       NIRF_Analytics_Report.pdf · build_report.py · this file
```

## 5. Credentials

All in `.env`, which is git-ignored and must never be committed or pasted into chat.

| Key | Purpose | Free? |
|---|---|---|
| `GROQ_API_KEY` | Chat model for the AI assistant | Yes, no card |
| `GEMINI_API_KEY` | Fallback chat model | Yes, no card |
| `SUPABASE_DB_URL` | Hosted store for staff-entered live data | Yes, no card |

The chatbot tries Groq `openai/gpt-oss-120b`, then Groq `qwen/qwen3.8-27b`, then Gemini
`gemini-3.1-flash-lite`. Override any of them in `.env` if a model is retired.

`app/live_store.py` writes staff entries to Supabase when the connection string is present and to the
local SQLite file otherwise, so the app works either way. Supabase free projects pause after about a
week of inactivity; one click in their dashboard wakes it.

## 6. Open item: publication data

**Status: incomplete, deliberately not in use.**

Publications and citations are 75 of the 100 marks in the Research parameter and appear nowhere in
NIRF's public PDFs. We fetch them for peer institutes from OpenAlex (free, no key).

What happened on 10 September: a parallel fetch exhausted OpenAlex's free daily budget. Two problems
followed, both now fixed.

1. While the budget was spent, every request failed, and the code recorded 195 institutes as
   "not in OpenAlex" when they were simply unreachable. Those false entries were purged.
   `scraper/fetch_publications.py` now raises `LookupFailed` instead of caching a miss, and
   `BudgetExhausted` stops the run cleanly with a message.
2. Only 36 institutes were collected and they were nearly all elite (median NIRF rank 19, 7 to 52
   papers per faculty). Trained on that, the model pushed a modest college's Research score to near
   zero, because Saveetha's real rate sits below anything the model had seen. Entering honest data
   would have made the estimate worse.

`models/score_model.py` now has a coverage guard (`publications_usable`, `MIN_PUB_COVERAGE`,
`MIN_PUB_LOW_RANK_ROWS`). It refuses the publication features unless coverage is broad enough to
include institutes like the client, and prints why. Today it reports 21% coverage with 3 rows outside
the top 50, and trains exactly as it did before. **No current number is affected by this work.**

A scheduled task, `nirf-fetch-publications`, runs at 09:00 on 11 September to finish the fetch
sequentially, retrain, and re-check. It will only adopt the new features if a sanity test shows a
modest college's Research score rises with more papers rather than collapsing.

To run it by hand instead:

```bash
.venv/bin/python scraper/fetch_publications.py 2021,2022,2023,2024,2025 200
.venv/bin/python models/score_model.py
```

The college itself is **not catalogued in OpenAlex** under any name variant tried, so its own
publication counts must come from staff through the Live Data page. That page flags them as the
highest-value entry.

## 7. Known limits, to state whenever quoting numbers

- The college's parameter scores are estimates. NIRF has published none since 2019.
- Research carries most of the uncertainty (59% of the variance in the total), because publications
  are not observable. Perception adds another 15% and is a survey that cannot be modelled.
- The "most likely 151-200 band" is weak: 101-150 sits at 23% and 201-250 at 22%. Treat the result as
  "the 100s to low 200s" rather than a specific band. "Not the top 100 in 2026" is the safe call, at
  1.8 standard deviations.
- The model is trained on institutes ranked 1-200 and is most reliable there.
- The 2026 forecast assumes NIRF keeps its 2025 methodology.
- NIRF's site has two traps, both handled: the 2016 pages serve 2017 data, and in years with 200
  numeric ranks the pages labelled 101-150 and 151-200 actually hold 201-250 and 251-300.

## 8. Next steps

1. Let the scheduled fetch complete, then judge whether publication features are usable.
2. Get the college's own Scopus publication and citation counts for the last three years. This is the
   single highest-value input; it would replace the weakest part of the model with real data.
3. Deploy to Streamlit Community Cloud for a public link: sign in at share.streamlit.io with the
   GitHub account, pick the repository, set the main file to `app/Home.py`, and paste the three
   secrets from `.env` into the Secrets box.

Repository: https://github.com/rnandakishore2408/nirf_analytics
