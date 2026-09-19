# Test and security report

Date: 19 September 2026 · Scope: the Streamlit app, staff sign-in, live data entry, live re-forecast,
AI assistant, and the Supabase database it uses.

## Summary

| Check | Result |
|---|---|
| Automated tests (`pytest`) | **105 passed**, 0 failed: sign-in 20, security 60, scoring 17, full app flows 8 |
| Static security scan (`bandit`) | **0 open issues** (5 flagged, each fixed or reviewed and annotated) |
| Known vulnerabilities in dependencies (`pip-audit`) | **None found** |
| Supabase exposure | Row-level security on, public API roles have no access (verified from the database's own grant tables) |
| Stress test, 50 simultaneous users | **0 failures** in 350 requests; memory peaked at 780 MB and returned to 330 MB |
| Live database round trip, one Supabase query | 92 ms (was 480 ms before the connection fix) |

## Vulnerabilities found and fixed

| # | Severity | Problem | Fix |
|---|---|---|---|
| 1 | High | The Supabase table holding staff entries had row-level security off, and Supabase's public `anon` role could read, change and delete it through the REST API. | Row-level security enabled on every table, and all grants to `anon` and `authenticated` revoked. Applied automatically on start-up. |
| 2 | High | No sign-in: anyone with the link could see internal figures, enter or delete data, and use the AI quota. | Sign-in gate with no sign-up. Pages are registered only after sign-in, so they cannot be opened by URL. Accounts are created by the administrator only. |
| 3 | High | The chatbot's web-fetch tool would fetch any address, including internal networks and the cloud metadata service (server-side request forgery). | Only public internet addresses on ports 80/443, every redirect re-checked, 8 MB cap, HTML/text/PDF only, proxies ignored. |
| 4 | Medium | "Delete last entry" permanently deleted whichever entry was newest, whoever made it. | Soft delete: staff can remove only their own entries, admins any. Removed rows stay in the audit log with who and when. |
| 5 | Medium | "Entered by" was free text, so anyone could enter data in someone else's name. | The author is taken from the signed-in account. |
| 6 | Medium | No server-side checks: negative, impossible or inconsistent numbers were accepted. | Range checks on every field, plus consistency checks (women ≤ students, placed + higher studies ≤ graduated, retractions ≤ papers). Nothing is saved if any check fails. |
| 7 | Medium | The chatbot's SQL tool relied on a keyword filter. | The database engine now enforces read-only access (no ATTACH, PRAGMA or writes), one statement only, 5-second limit. Accounts are kept in a separate database the tool cannot open. |
| 8 | Medium | Unlimited AI questions could exhaust the free API quota. | 40 questions per hour and 200 per day per user, 2,000-character limit, conversation history capped. |
| 9 | Low | Database errors were shown on screen and could reveal the host. | Generic messages for users; details go only to the server log. |
| 10 | Low | CSV exports could carry spreadsheet formulas (formula injection). | Cells starting with `= + - @` are neutralised. |
| 11 | Low | A web page the chatbot read could make it display a remote image that leaks data in the image address. | Images are stripped from AI answers. |
| 12 | Low | Visitors saw full error tracebacks and the developer menu. | Tracebacks and developer options hidden in production settings. |
| 13 | Low | Dependency versions were not pinned. | Exact versions pinned to what the tests passed with. |

### Password and session protection

- Passwords are stored as salted scrypt hashes, never in plain text, and never logged.
- Five wrong passwords lock that username for 15 minutes. Unknown usernames behave identically, so
  the form never reveals which accounts exist, and they take the same time to check.
- Sessions end after 60 idle minutes, after 12 hours, or when the browser tab is refreshed. Disabling
  an account signs the person out within 5 minutes.
- Every sign-in attempt is recorded: `python scripts/manage_users.py events`.

## Bugs the tests caught (all fixed)

- Any staff entry, even one only recorded, shifted the diversity score by 0.02, because percentages were
  re-derived from filed counts. They are now re-derived only when a count was entered.
- The CSV formula guard skipped text columns under pandas 3's new string type.
- Local database connections were committed but not explicitly closed.
- Each Supabase query cost four or five network round trips (480 ms). Autocommit and removing the
  per-checkout health query brought this to one round trip (92 ms).
- The live forecast rounded inputs before the simulation, so it differed from the saved forecast by 0.01.
  It now matches exactly.

## Stress test

`scripts/load_test.py` behaves like a browser. Each simulated user opens a connection, signs in through
the real form, and opens five pages. All users start within a second or two.

Local server with the Supabase database (runs Python on one core):

| Users at once | Sign-in (median) | Pages (median) | Failures |
|---|---|---|---|
| 1 | 6.6 s the first time after a restart (loading the model); then pages 0.1-0.9 s | 0.1-0.2 s | 0 |
| 5 | 1.6 s | 0.3-0.7 s | 0 |
| 25 | 9.3 s | 1.7-5.3 s | 0 |
| 50 (local database) | 10 s | 3.7-9.4 s | 0 |

Realistic use is a handful of staff, where pages load in under a second. The free Streamlit host has
less CPU than the test machine, so expect somewhat slower times there. The first visit after the app has
been asleep takes up to a minute while it wakes.

## Remaining risks (accepted, low)

- **Web fetch, DNS re-binding.** The address is checked, then fetched. A hostile domain could in principle
  change its address in between. Exploiting this needs a signed-in user and a manipulated AI answer.
- **Deliberate lock-outs.** Someone who knows a username could lock it for 15 minutes. Usernames are not
  published.
- **Rate limits reset** when the server restarts, because they are kept in memory.
- **AI providers.** Questions to the assistant, and the college's entered figures it looks up, are sent
  to Groq or Google. Their free tiers may keep prompts, so do not type personal data into the chat.
- **Public repository.** The code and the public NIRF data are visible on GitHub. No secrets are in it;
  a test checks every tracked file. Making the repository private is optional; Streamlit hosting works
  either way.

## Re-running

```bash
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest                                  # 105 tests, ~20 s, never touches Supabase
.venv/bin/python -m bandit -q -r app models scripts         # static scan
.venv/bin/python -m pip_audit --local                       # known vulnerabilities
.venv/bin/python scripts/load_test.py --url http://localhost:8501 --users 25 --username <test user> --password <pw>
```

Use a throw-away account for load tests and remove it afterwards (`manage_users.py disable`, or delete
its rows), because every simulated sign-in is logged.
