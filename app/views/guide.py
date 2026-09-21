"""Help & Guide: everything a staff member needs to use the app on their own. Limits and field lists
are read from the code, so this page cannot drift from what the app actually does."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import sec_base  # isort: skip

import auth
import live_estimate as LE
from rag import chat as rag_chat

user = auth.current_user(st.session_state)
if not user:
    st.stop()

st.title("Help & Guide")
st.markdown("How to use this app, step by step: what every page shows, how to enter data, what each message means, "
            "and how much you can use the AI assistant. Nothing here needs technical knowledge.")

tabs = st.tabs(["🚀 Start here", "🗂️ The pages", "📝 Entering data", "💬 Ask the Data", "⚠️ Messages & errors", "❓ Questions"])

# ---------------------------------------------------------------- start here
with tabs[0]:
    st.subheader("What this app is")
    st.markdown(
        """
NIRF ranks engineering colleges every year out of 100 marks, but publishes scores only for the top 100. Saveetha
Engineering College has been placed in the 201-300 band, so it has **no published score**. This app:

1. **Estimates** the college's score in each NIRF area from the numbers it filed with NIRF.
2. **Compares** it with the colleges that made the top 100.
3. **Forecasts** the 2026 result as chances for each rank band.
4. **Updates the forecast as soon as you enter newer figures**, such as this year's publications or PhD scholars.

All college scores here are **estimates** from a model trained on 700 published results. NIRF's own figures may differ.
"""
    )
    st.subheader("Your first 5 minutes")
    st.markdown(
        """
1. **Sign in** with the username and password you were given. There is no sign-up page.
2. **Change your password.** Open **My account** in the left menu, enter the current password and a new one of at
   least 10 characters, and click *Change password*.
3. **Look around.** Open **Overview** for the headline numbers, then **Prediction 2026**.
4. **Enter one real figure.** Open **Live Data Entry**, type the college's publications for the last three years,
   choose the academic year, add a short note on where the number came from, and click **Save entries**.
5. **Watch it update.** The estimate and forecast just below the form change straight away, and so do the Overview
   and Prediction pages.
"""
    )
    st.subheader("The five NIRF areas")
    st.markdown(
        """
| Short name | Full name | Weight | What it looks at |
|---|---|---|---|
| **TLR** | Teaching, Learning & Resources | 30% | Students, faculty, PhD scholars, faculty with PhD, money spent per student |
| **RPC** | Research & Professional Practice | 30% | Publications, citations, patents, research funding, consultancy |
| **GO** | Graduation Outcomes | 20% | Placements, higher studies, median salary, PhDs awarded |
| **OI** | Outreach & Inclusivity | 10% | Students from other states, women students, fee reimbursement, facilities |
| **PR** | Perception | 10% | A survey of employers and academics; it cannot be calculated, so the app assumes a typical value |

Total score = 0.30 × TLR + 0.30 × RPC + 0.20 × GO + 0.10 × OI + 0.10 × PR.
"""
    )

# ---------------------------------------------------------------- pages
with tabs[1]:
    st.markdown(
        """
| Page | Use it to | Tips |
|---|---|---|
| 🏠 **Overview** | See the headline numbers: last result, the rank-100 cut-off, the college's estimated 2026 score and most likely band | Cards marked *incl. staff data* already use your entries |
| 📊 **Top 100 Explorer** | Browse every ranked engineering college 2017-2025, filter by year, state and type, open any college's history | *Download CSV* gives you the table in Excel |
| 🎯 **Saveetha Position** | The college's full NIRF history, estimated scores, and the gap to colleges ranked 76-100 | The raw-numbers table shows exactly where the college is behind |
| 🧮 **Gap & What-If** | Move sliders (PhDs, salary, spending, publications…) and see how the score would change | Nothing here is saved. Experiment freely |
| 🔮 **Prediction 2026** | The forecast: estimated total, expected rank, chance of each band, and model accuracy | A green banner means staff entries are included |
| 📝 **Live Data Entry** | Enter the college's current figures; see the re-calculated estimate; view and undo entries | Every entry keeps your name and the time |
| 💬 **Ask the Data** | Ask questions in plain English (or Tamil) about rankings, formulas and the college | See the *Ask the Data* tab for limits |
| 👤 **My account** | Change your password | |
| 📘 **Help & Guide** | This page | |

**Reading the forecast.** "Most likely band 151-200 (34%)" means that in 34 of every 100 simulated futures the
college landed in 151-200. Neighbouring bands are often close, so read it as a range, not a promise.
"""
    )

# ---------------------------------------------------------------- data entry
with tabs[2]:
    st.subheader("Step by step")
    st.markdown(
        """
1. Open **📝 Live Data Entry**.
2. Choose the **academic year** the numbers belong to (top right of the form).
3. Fill **only the fields you have new numbers for**. Leave the rest blank; blank means "keep the current value".
   Hover over the **?** next to a field to see the value filed with NIRF and the latest entry.
4. Write a **note** saying where the figures came from (e.g. *"Scopus, 20 Sep 2026"*). It helps anyone checking later.
5. Click **Save entries**. A green message confirms how many values were saved.
6. Scroll down to **Re-scored with the latest entries** to see the new estimate and band chances.

**Made a mistake?** Enter the correct value and save again: the newest entry for a field is always the one used.
Or open **Remove an entry made by mistake**, pick the entry, tick the box and click **Remove entry**. The field then
goes back to its previous value. Removed entries stay in the history as removed, so nothing is lost.

**Who can remove what:** staff can remove their own entries; the administrator can remove anyone's.
"""
    )
    st.subheader("Where to find the numbers")
    st.markdown(
        """
- **Publications (last 3 calendar years):** Scopus → search the college under *Affiliations* → open it → *Documents*,
  filter to the last three years, and use the total count (all document types).
- **Citations received (last 3 calendar years):** on the same Scopus affiliation page, open the citation overview and
  add up the citations received in each of the last three years.
- **Everything else** uses the same definitions as the NIRF Data Capturing System form the college fills in every year.
"""
    )
    st.subheader("Every field, and what it changes")
    st.caption("✅ changes the estimate  ·  📋 recorded only (kept on file but not scored; the reason is given)")
    base = sec_base()
    rows = []
    for m in LE.METRICS:
        v = base.get(m.key, pd.Series([None])).iloc[0] if m.key in base else None
        filed = "–" if v is None or pd.isna(v) else (f"{v:,.1f}%" if m.kind == "pct" else f"{v:,.0f}")
        unit = {"count": "number", "pct": "percent (0-100)", "inr": "rupees"}[m.kind]
        rows.append({"": "✅" if m.scored else "📋", "Field": m.label, "Enter as": unit,
                     f"Filed ({int(base.year.iloc[0])})": filed, "What it changes": m.moves})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=560)
    st.subheader("Checks the app makes before saving")
    st.markdown(
        """
- No negative numbers, and nothing above a sensible maximum. Percentages must be 0-100.
- Women students, and students from other states, cannot exceed total students.
- Placed plus higher studies cannot exceed the number who graduated.
- Retracted papers cannot exceed publications.

If any check fails, **nothing** from that form is saved and the red message lists what to fix.
"""
    )
    st.info("**Tip on amounts in rupees:** type the full number without commas or symbols: 3 crore is `30000000`, "
            "5.5 lakh is `550000`.", icon="💡")

# ---------------------------------------------------------------- ask the data
with tabs[3]:
    st.subheader("What it can do")
    st.markdown(
        """
The assistant reads the app's database (rankings 2017-2025, 700+ college submissions, NIRF's methodology documents,
the college's estimates, forecast and your entries) and can open public web pages such as nirfindia.org. Good questions:

- *Which private colleges in Tamil Nadu were in the 2025 top 100, and what were their research scores?*
- *How is the Graduation Outcomes score calculated?*
- *With our latest entries, what is the fastest way to reach the 101-150 band?*
- *Has NIRF 2026 been released? Check nirfindia.org.*

Click **N tool call(s)** under an answer to see exactly which data it looked at.
"""
    )
    st.subheader("How much you can use it")
    st.markdown(
        f"""
| Limit | Value | Why |
|---|---|---|
| Questions per person per hour | **{rag_chat.PER_HOUR}** | The AI services are free tiers shared by everyone using this app |
| Questions per person per day | **{rag_chat.PER_DAY}** | Same reason |
| Length of one question | **{rag_chat.MAX_PROMPT_CHARS:,} characters** (about a page) | Keeps answers fast and within the free quota |
| Conversation memory | The last **{rag_chat.MAX_HISTORY_MESSAGES}** messages | Older parts of a long chat are forgotten; click *Clear conversation* to start fresh |

On top of the app's own limits, the free AI services have their own per-minute and per-day allowances shared by all
users. The app tries three services in turn (Groq, a second Groq model, then Google Gemini) before giving up. If all
three are busy you will see *"All providers failed … try again in a minute"*. Wait a minute and ask again.

The per-person counters reset when the app restarts (for example after it has been asleep).
"""
    )
    st.subheader("Use it wisely")
    st.markdown(
        """
- **Check important numbers** on the dashboard pages before using them in a report. The assistant is usually right
  but can misread a table.
- **Do not type personal or confidential information** (names, phone numbers, salaries of individuals, passwords).
  Questions are processed by Groq and Google, whose free services may keep what is sent.
- It cannot change any data. Only the Live Data Entry page saves figures.
"""
    )

# ---------------------------------------------------------------- messages
with tabs[4]:
    st.markdown("Every message the app can show, what it means, and what to do.")
    msgs = [
        ("Signing in", "Incorrect username or password.", "The username or password is wrong (the app does not say which, for security).",
         "Check spelling and capital letters in the password. Usernames are lower-case."),
        ("Signing in", "Too many attempts for this username. Please wait 15 minutes and try again.",
         f"{auth.MAX_FAILS} wrong passwords in 15 minutes locked this username.", "Wait 15 minutes. If you have forgotten the password, ask the administrator to reset it."),
        ("Signing in", "Sign-in is unavailable right now.", "The app could not reach its database.", "Wait a minute and try again. If it continues, tell the administrator."),
        ("Signing in", "Your session expired. Please sign in again.", "No activity for 60 minutes, or signed in for more than 12 hours.", "Sign in again. Nothing you saved is lost."),
        ("Signing in", "This account has been disabled.", "The administrator switched the account off.", "Contact the administrator."),
        ("Signing in", "Page not found … Running the app's main page.", "You opened a page link while signed out, or a link that does not exist.", "Sign in, then use the left menu."),
        ("Any page", "The sign-in page appears after refreshing", "Refreshing the browser tab ends the session (by design, for security).", "Sign in again. Use the left menu instead of the browser's refresh button."),
        ("Any page", "\"This app has gone to sleep due to inactivity\"", "The free host pauses the app when nobody has used it for a while.", "Click the button to wake it and wait up to a minute."),
        ("Live Data Entry", "Nothing to save: fill at least one field.", "You clicked Save with every box empty.", "Type at least one value."),
        ("Live Data Entry", "Nothing was saved. Please fix: …", "One of the checks failed (listed under the message).", "Correct the listed fields and save again. Your other values were not saved either, so re-enter them."),
        ("Live Data Entry", "Too many saves in the last hour.", "More than 30 saves by one person in an hour.", "Wait a little. Put several values in one save instead of saving each separately."),
        ("Live Data Entry", "Could not save right now; the database did not respond.", "The online database did not answer. Nothing was stored.", "Try again in a minute. If it keeps failing, tell the administrator (the free database may be paused)."),
        ("Live Data Entry", "🔴 red dot beside the database name", "The app cannot reach the database, so saving will fail.", "Tell the administrator. Viewing the dashboards still works."),
        ("Live Data Entry", "That entry could not be removed (already removed, or not yours).", "Staff can only remove their own entries, and each entry once.", "Ask the administrator to remove someone else's entry."),
        ("Live Data Entry", "Recorded but not scored: …", "Those fields are kept on file but do not change the estimate (the reason is shown next to each field).", "Nothing to do; this is expected."),
        ("My account", "Your current password is incorrect.", "The first box does not match your password.", "Type your current password again."),
        ("My account", "The two new passwords do not match.", "The new and repeated passwords differ.", "Type the same new password in both boxes."),
        ("My account", "Use at least 10 characters. / That password is too common. / Do not include the username.", "The new password is too weak.", "Choose a longer password that does not contain your username."),
        ("My account", "Too many attempts. Please wait 15 minutes.", "Five password-change attempts in 15 minutes.", "Wait 15 minutes."),
        ("Ask the Data", "Question limit reached …", f"You asked {rag_chat.PER_HOUR} questions this hour or {rag_chat.PER_DAY} today.", "Try again later."),
        ("Ask the Data", "All providers failed … try again in a minute.", "All three free AI services are busy or at their limit.", "Wait a minute and ask again."),
        ("Ask the Data", "Sorry, the AI service did not respond.", "A temporary network problem with the AI service.", "Ask again."),
        ("Ask the Data", "Stopped after too many tool steps; please narrow the question.", "The question needed too many lookups.", "Split it into smaller, more specific questions."),
        ("Ask the Data", "refused: that address is not a public web site", "The assistant only opens public internet pages.", "Give it a public web address (e.g. nirfindia.org)."),
        ("Ask the Data", "The AI assistant is not configured (no API key).", "The AI keys are missing from the app's settings.", "Tell the administrator. The rest of the app works."),
    ]
    st.dataframe(pd.DataFrame(msgs, columns=["Where", "Message", "What it means", "What to do"]), hide_index=True, width="stretch", height=720)

# ---------------------------------------------------------------- FAQ
with tabs[5]:
    faq = [
        ("Is the estimated score official?",
         "No. NIRF publishes no scores below rank 100. The estimates come from a model trained on 700 published results; "
         "the college's 2025 estimate lands inside the band NIRF actually published, which is a good sign, but treat them as estimates."),
        ("Why did the forecast change?",
         "Someone saved new figures. The Live Data Entry page shows who entered what and when, and a list of *How the entries were used*."),
        ("I entered a number and nothing changed.",
         "Check whether the field is marked 📋 *recorded only*. Also, a value close to the one the college filed changes the estimate very little."),
        ("Do other people see my entries?",
         "Yes. Everyone signed in sees the same, latest figures. Others see a change within about a minute."),
        ("Can I break anything by experimenting?",
         "Not on **Gap & What-If**: nothing there is saved. On **Live Data Entry**, every save counts, but any entry can be removed."),
        ("What does 'filed only' mean under a number?",
         "The value using only the college's NIRF filing, before any staff entries, so you can see what your entries changed."),
        ("Why is Perception (PR) always assumed?",
         "It comes from a survey NIRF runs among employers and academics; no data the college holds can predict it. The app assumes a value "
         "typical of private colleges ranked 60-100 and includes that uncertainty in the band chances."),
        ("How often should we update?",
         "Whenever new figures are confirmed, and certainly before the college submits its next NIRF data. Publications and citations matter most."),
        ("I forgot my password.", "Ask the administrator to reset it; you will get a new one to change on My account."),
        ("Can I use it on a phone?", "Yes; the pages rearrange for small screens. Data entry is easier on a laptop."),
    ]
    for q, a in faq:
        with st.expander(q):
            st.markdown(a)
    st.caption("Still stuck? Contact the project administrator.")
