"""NIRF Analytics — Saveetha Engineering College. Entry point and sign-in gate.

Every page is registered through st.navigation only after sign-in, so a page that is not registered
cannot be opened by URL. There is no sign-up: accounts come from scripts/manage_users.py.
"""
from __future__ import annotations

import time

import streamlit as st

import auth
from common import inject_css

st.set_page_config(page_title="NIRF Analytics · Saveetha", page_icon="🎓", layout="wide")
inject_css()


def login_view() -> None:
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("## 🎓 NIRF Analytics")
        st.markdown("**Saveetha Engineering College** · staff sign-in")
        msg = st.session_state.pop("auth_message", None)
        if msg:
            st.info(msg)
        with st.form("login", clear_on_submit=False):
            username = st.text_input("Username", max_chars=64, autocomplete="username")
            password = st.text_input("Password", type="password", max_chars=128, autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            try:
                user, err = auth.authenticate(username, password)
            except Exception as e:  # noqa: BLE001
                print(f"sign-in failed with {type(e).__name__}: {str(e)[:200]}")
                user, err = None, "Sign-in is unavailable right now. Please try again in a minute."
            if user:
                auth.sign_in(st.session_state, user)
                st.rerun()
            time.sleep(1.0)  # slows scripted guessing from one session
            st.error(err)
        st.caption("There is no sign-up. Accounts are issued by the project administrator; "
                   "contact them if you need access or have forgotten your password.")


user = auth.current_user(st.session_state)
if not user:
    pg = st.navigation([st.Page(login_view, title="Sign in", icon="🔐", url_path="signin", default=True)], position="hidden")
else:
    pages = {
        "Dashboard": [
            st.Page("views/overview.py", title="Overview", icon="🏠", default=True),
            st.Page("views/explorer.py", title="Top 100 Explorer", icon="📊", url_path="explorer"),
            st.Page("views/position.py", title="Saveetha Position", icon="🎯", url_path="position"),
            st.Page("views/what_if.py", title="Gap & What-If", icon="🧮", url_path="what-if"),
            st.Page("views/prediction.py", title="Prediction 2026", icon="🔮", url_path="prediction"),
        ],
        "Work": [
            st.Page("views/live_entry.py", title="Live Data Entry", icon="📝", url_path="live-data"),
            st.Page("views/ask.py", title="Ask the Data", icon="💬", url_path="ask"),
        ],
        "Account": [st.Page("views/account.py", title="My account", icon="👤", url_path="account")],
    }
    pg = st.navigation(pages)
    with st.sidebar:
        st.markdown(f"Signed in as **{user['display_name']}**  \n`{user['username']}` · {user['role']}")
        if st.button("Sign out", width="stretch"):
            auth.sign_out(st.session_state, "You have signed out.")
            st.rerun()
pg.run()
