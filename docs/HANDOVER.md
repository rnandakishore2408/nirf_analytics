# Handover — NIRF Analytics for Saveetha Engineering College

Last updated: 21 September 2026

Client: **Saveetha Engineering College**, Sriperumbudur, Tamil Nadu. NIRF id `IR-E-C-16590`.
Not to be confused with **Saveetha Institute of Medical and Technical Sciences** (`IR-E-I-1441`),
a deemed university in Chennai ranked 45 in 2025. They are separate NIRF entities.

## Status at a glance (21 September 2026)

| | |
|---|---|
| Live site | https://saveetha-nirf.streamlit.app (Streamlit Community Cloud, free) |
| Deploys | Automatically, 1-2 minutes after every push to `main` on GitHub |
| Database for staff entries and accounts | Supabase (free, Mumbai region), tables locked down with row-level security |
| Accounts | `saveetha.admin` (admin), `saveetha.staff` (staff); passwords are never stored in this repository |
| Staff entries | None yet: all test entries were removed on 21 September, so the site shows the filing-only forecast |
| Tests | 105 passing (`.venv/bin/python -m pytest`) |
| In-app help | *Help & Guide* page (`app/views/guide.py`): steps, every field, every message, chatbot limits |
| Instructions for coding assistants | [AGENTS.md](../AGENTS.md) at the repository root |

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
./run.sh          # dashboard at http://localhost:8501 (staff sign-in required)
./pipeline.sh     # re-scrape, re-parse, rebuild, retrain, re-forecast (30-60 min, network bound)
python docs/build_report.py    # rebuild the staff PDF
.venv/bin/python -m pytest     # 105 tests (needs requirements-dev.txt)
```

Requires `pdftotext` (poppler-utils). Dependencies live in `.venv`; `requirements.txt` lists them
(pinned), `requirements-dev.txt` adds the test and report tools.

### Accounts (no sign-up)

Accounts are created by the administrator and handed out. The script writes to the same database as the
app (Supabase when `SUPABASE_DB_URL` is in `.env`), so a new account works on the hosted site at once.

```bash
python scripts/manage_users.py add <username> "<Display name>" [--role admin]   # prints a random password once
python scripts/manage_users.py reset <username>      # new random password
python scripts/manage_users.py disable <username>    # signs them out within 5 minutes
python scripts/manage_users.py list
python scripts/manage_users.py events [<username>]   # recent sign-in attempts
```

Existing accounts: `saveetha.admin` (admin) and `saveetha.staff` (staff). Staff can change their own
password on the *My account* page. Staff can remove only their own entries; admins can remove any.
Removed entries stay in the audit trail.

## 4. Layout

```
scraper/    scrape_rankings.py · download_pdfs.py · parse_pdfs.py · build_db.py · fetch_publications.py
models/     score_model.py (learns NIRF's hidden curves) · live_estimate.py (staff entries -> forecast) · predict_2026.py · artifacts/
analysis/   analyze.py -> data/processed/analysis.json
app/        Home.py (sign-in gate) · auth.py · live_store.py · common.py · views/*.py · rag/index.py · rag/chat.py
scripts/    manage_users.py · load_test.py
tests/      pytest suite (see docs/TEST_REPORT.md)
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

`app/live_store.py` writes staff entries, accounts and the sign-in log to Supabase when the connection
string is present, and to `db/local_store.db` (git-ignored) otherwise. `db/nirf.db` is never written by
the app. On Supabase the tables have row-level security on and no grants to the public API roles; this
is applied automatically at start-up. Supabase free projects pause after about a week of inactivity;
one click in their dashboard wakes it.

On Streamlit Community Cloud the same three keys go in the app's **Secrets** box, in TOML form:

```toml
GROQ_API_KEY = "..."
GEMINI_API_KEY = "..."
SUPABASE_DB_URL = "postgresql://..."
```

## 6. Publication data and live re-scoring

Publications and citations are 75 of the 100 marks in the Research parameter and appear nowhere in
NIRF's public PDFs. Peer counts come from OpenAlex (free): 215 institute-years so far, with 53 of them
ranked 101-200.

That is still too narrow to put publications inside the main model: the coverage guard in
`models/score_model.py` (`publications_usable`) keeps them out, and the headline estimates are unchanged.
They are used instead as a **validated adjustment** (`fit_pub_adjustment`):

- The Research model implicitly assumes the college publishes like a typical institute with its funding,
  PhD and faculty profile (about 960 papers over three years for the 2026 filing).
- When staff enter the real counts, Research moves by how far they sit above or below that. The size of
  the move is fitted on the model's own out-of-sample errors, so it only claims what publications add.
- Tested on institutes the fit never saw, it cuts Research error from 9.72 to 8.62 points, with no bias
  for institutes ranked 101-200.

`models/live_estimate.py` turns staff entries into new parameter estimates and re-runs the 2026 Monte
Carlo with the same code as `predict_2026.py`. With no entries it reproduces the saved forecast exactly.
Every page and the chatbot read the same result.

| Entry | What it moves |
|---|---|
| Publications, citations | Research (adjustment above); a missing one is assumed at 16.75 citations per paper |
| Retracted papers | Research, up to −5 (NIRF's rule; the scale is unpublished, full deduction assumed at 1% of papers) |
| Faculty with PhD % | Teaching, through NIRF's published FQ formula (up to 10 marks) |
| PhD scholars, PhDs awarded, faculty, students, placements, salary, spend, funding, diversity | Through the trained model |
| Patents, part-time PhD scholars | Recorded only: no peer data to fit a scale |

The college itself is **not catalogued in OpenAlex**, so its own counts must come from staff (Scopus).
To extend the peer data when the OpenAlex daily quota allows:

```bash
.venv/bin/python scraper/fetch_publications.py 2021,2022,2023,2024,2025 200
.venv/bin/python models/score_model.py
```

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

## 8. Hosting (free) and next steps

Hosting on Streamlit Community Cloud, done once:

1. Sign in at https://share.streamlit.io with the GitHub account `rnandakishore2408`.
2. **Create app** → repository `rnandakishore2408/nirf_analytics`, branch `main`, main file `app/Home.py`.
3. **Advanced settings** → Python 3.13, and paste the three secrets from section 5 in TOML form.
4. Deploy. `packages.txt` installs `pdftotext`; `requirements.txt` installs pinned versions.
5. Open the link and sign in. Give staff the link plus their username and password.

Done on 21 September 2026: the app is live at https://saveetha-nirf.streamlit.app with the three
secrets set. To change a secret later: open the site → **Manage app** (bottom right) → ⋮ → **Settings** →
**Secrets**; the app restarts by itself.

Free-plan pauses (normal, no data is lost):

- **Streamlit** puts the app to sleep after about 12 hours without visitors. The visitor sees *"This app
  has gone to sleep"*, clicks *"Yes, get this app back up!"* and waits 30-60 seconds.
- **Supabase** pauses the database after about 7 days without activity. The site still opens, but saving
  fails with *"Could not save right now"* and the Live Data page shows a red dot. Fix: supabase.com →
  the project → **Restore project**, wait two minutes.

Next steps:

1. Staff enter the college's Scopus publication and citation counts for the last three years. This is
   the single highest-value input.
2. Extend the OpenAlex peer data when quota allows (section 6).
3. Re-run `./pipeline.sh` when NIRF 2026 results are published.

Repository: https://github.com/rnandakishore2408/nirf_analytics
