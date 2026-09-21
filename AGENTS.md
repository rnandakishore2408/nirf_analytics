# Instructions for coding assistants

Read this whole file before changing anything. It applies to every AI coding tool (Claude Code, Codex,
Antigravity, Gemini, Cursor, Copilot, ...). Deeper background is in [docs/HANDOVER.md](docs/HANDOVER.md);
security and test results are in [docs/TEST_REPORT.md](docs/TEST_REPORT.md).

## What this is

NIRF (India's national college ranking) analytics for **Saveetha Engineering College**, Sriperumbudur
(NIRF id `IR-E-C-16590`). It is **not** Saveetha Institute of Medical and Technical Sciences
(`IR-E-I-1441`, a deemed university ranked ~45). Never merge or confuse the two.

NIRF publishes no scores below rank 100, so the college's scores in this project are **model estimates**.
Always say "estimated" when quoting them.

- **Live site:** https://saveetha-nirf.streamlit.app (Streamlit Community Cloud, free). It redeploys
  automatically 1-2 minutes after every push to `main`, so **a push is a production release**.
- **Users:** college staff sign in (no sign-up) and enter current figures; every page and the 2026 forecast
  recompute from them.
- **Repository:** github.com/rnandakishore2408/nirf_analytics (public).

## The owner

The owner is a beginner-to-intermediate developer who treats this as a freelance deliverable for the college.

- Explain things in plain, non-technical language, step by step.
- Report results honestly, including failures.
- Everything must stay on **free** services: Streamlit Community Cloud, Supabase free tier, Groq and Gemini free
  API tiers, OpenAlex. Never introduce a paid dependency.
- Documents for college staff: neutral wording (describe position, drivers and outlook; do not frame it as
  "getting back into the top 100"), a source for every number, colourful designed layout.

## Hard rules

1. **Git identity:** commit as `rnandakishore2408 <rnandakishore2408@gmail.com>`. The remote uses the SSH
   alias `git@github-nirf:rnandakishore2408/nirf_analytics.git`. Never use the `nandakishore-r24` account.
2. **No AI attribution** anywhere: no `Co-Authored-By`, no "Generated with ...", no tool names in commits,
   PR text, code comments or docs, even if your tool adds them by default.
3. **Secrets:** `.env` holds `GROQ_API_KEY`, `GEMINI_API_KEY` and `SUPABASE_DB_URL`. Never print, paste, log
   or commit its contents. On the live site the same keys are in Streamlit's Secrets settings.
4. **Passwords:** never write account passwords into any file. `scripts/manage_users.py` prints a new
   password once, to hand over privately.
5. **Production database:** `SUPABASE_DB_URL` in `.env` points at the **live** database. Scripts run on this
   laptop (for example `manage_users.py`) change the live site. Tests never touch it (see Testing). Look at
   rows before deleting them, and delete only what the owner asked for.
6. **Before every push:** run the test suite and make sure all tests pass. Pushing deploys.
7. `db/nirf.db` is read-only reference data for the app. The app never writes to it; only the data pipeline
   rebuilds it. Do not put accounts or staff data in it (the chatbot's SQL tool can read it).
8. Don't retrain the model or re-run the pipeline unless asked. That changes the numbers already given to the
   college in its PDF reports.
9. Don't schedule background or recurring tasks unless the owner asks.

## Architecture (where things live)

```
app/Home.py            entry point: sign-in gate + st.navigation. Pages exist only after sign-in,
                       so they cannot be opened by URL. Add new pages HERE (not an app/pages/ folder).
app/views/*.py         the pages: overview, explorer, position, what_if, prediction, live_entry, ask,
                       account, guide (Help & Guide)
app/auth.py            scrypt password hashing, lock-out (5 failures / 15 min), session timeouts,
                       per-user rate limits
app/live_store.py      the only code that talks to the mutable database: Supabase via a psycopg
                       pool (autocommit) when SUPABASE_DB_URL is set, else db/local_store.db.
                       Tables: saveetha_live (soft-delete + audit), app_users, login_events.
                       Enables row-level security and revokes the public API roles on start-up.
app/common.py          cached loaders; live_state() = estimate + forecast every page reads
app/rag/chat.py        AI assistant: Groq -> Groq backup -> Gemini, tools (read-only SQL, BM25 docs,
                       web fetch restricted to public addresses), limits (PER_HOUR, PER_DAY, ...)
models/score_model.py  monotone XGBoost per NIRF parameter + fit_pub_adjustment (publications)
models/live_estimate.py METRICS (every entry field: label, max, what it moves, scored or not),
                       validate(), estimate(), forecast() shared with predict_2026.py
models/predict_2026.py thresholds, top-100 forecast, college forecast -> data/processed/prediction_2026.json
scraper/, analysis/    data pipeline (./pipeline.sh)
scripts/manage_users.py accounts: add / reset / disable / enable / list / events
scripts/load_test.py   stress test against a running server
tests/                 pytest: auth, security, model, full app flows
docs/                  HANDOVER.md, TEST_REPORT.md, PDF reports and their build scripts
```

## Commands

```bash
./run.sh                                    # app on http://localhost:8501 (uses .env, so the LIVE database)
.venv/bin/python -m pytest                  # 105 tests, ~20 s
.venv/bin/python -m pyflakes app models scripts tests
.venv/bin/python -m bandit -q -r app models scripts
.venv/bin/python scripts/manage_users.py list
./pipeline.sh                               # full re-scrape + rebuild + retrain (only when asked)
python docs/build_report.py                 # rebuild the staff PDF report (needs requirements-dev.txt)
```

Setup: Python 3.13 in `.venv`, created with `uv`. Install with `uv pip install --python .venv/bin/python -r
requirements-dev.txt`. Requires `pdftotext` (poppler-utils).

## Testing

- `tests/conftest.py` forces `SUPABASE_DB_URL=""` and a throw-away SQLite file, and blanks the AI keys. Keep
  it that way: tests must never reach Supabase or a paid or rate-limited API.
- `tests/test_app.py` drives the real app headlessly (`streamlit.testing.v1.AppTest`). When you add a page,
  add it to `PAGES` there.
- Load test: create a throw-away account, run `scripts/load_test.py`, then delete that account and its
  `login_events` rows.

## Common tasks

- **New account or forgotten password:** `scripts/manage_users.py add|reset ...`, then give the printed
  password to the owner. Never store it.
- **Add a data-entry field:** add a `Metric` to `METRICS` in `models/live_estimate.py`. If it should affect
  the score, map it in `LIVE_TO_FEATURE` (score_model.py) or give it a formula in `estimate()`. Add it to a
  section in `app/views/live_entry.py` (the page refuses to load if a metric is missing). The Help page
  picks it up by itself. Add tests in `tests/test_model.py`.
- **Change a limit or message:** the Help & Guide page quotes limits from code (`rag_chat.PER_HOUR`,
  `auth.MAX_FAILS`, ...). Its "Messages & errors" table is written by hand in `app/views/guide.py`, so
  update it when you change a user-facing message.
- **New NIRF results published:** `./pipeline.sh`, check `data/processed/*.json`, run the tests, and
  rebuild the PDFs if the owner wants them.

## Gotchas

- Dependencies are pinned in `requirements.txt`, and Streamlit Cloud installs exactly those. Upgrade
  deliberately and run the tests. Use `width="stretch"`; `use_container_width` is deprecated.
- Streamlit keeps sessions in memory: a browser refresh signs the user out (by design, documented to staff).
- `live_metrics()` and `live_state()` are cached for 60 s. After a write, call `clear_live_caches()`.
- Every Supabase round trip costs about 100 ms. Keep the pool autocommit and avoid extra queries per page.
- Rate limits in `auth.allow()` are held in memory and reset when the app restarts.
- NIRF site quirks, already handled in `scraper/build_db.py`: the 2016 pages serve 2017 data. In 2019-22 the
  "101-150" and "151-200" band pages actually hold ranks 201-250 and 251-300.
- The college is not catalogued in OpenAlex. Its publications come only from staff entries.
- Free-plan pauses: Streamlit sleeps after about 12 hours idle. Supabase pauses after about 7 days idle; fix
  it with **Restore project** on supabase.com.
