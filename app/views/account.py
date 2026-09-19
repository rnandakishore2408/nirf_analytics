"""The signed-in user's account: details and password change."""
from __future__ import annotations

import streamlit as st

import auth

user = auth.current_user(st.session_state)
if not user:  # the router never shows this page signed out; defence in depth
    st.stop()

st.title("My account")
st.markdown(f"**{user['display_name']}** · username `{user['username']}` · role **{user['role']}**")
st.caption("Sessions end after 60 minutes without activity. Refreshing the browser tab also signs you out.")

st.subheader("Change password")
with st.form("pw", clear_on_submit=True):
    cur = st.text_input("Current password", type="password", max_chars=128, autocomplete="current-password")
    new = st.text_input(f"New password (at least {auth.MIN_PASSWORD_LEN} characters)", type="password", max_chars=128, autocomplete="new-password")
    rep = st.text_input("Repeat new password", type="password", max_chars=128, autocomplete="new-password")
    go = st.form_submit_button("Change password", type="primary")
if go:
    if not auth.allow(user["username"], "pwchange", 5, 15 * 60):
        st.error("Too many attempts. Please wait 15 minutes.")
    elif new != rep:
        st.error("The two new passwords do not match.")
    else:
        try:
            ok, msg = auth.change_password(user["username"], cur, new)
        except Exception as e:  # noqa: BLE001
            print(f"password change failed with {type(e).__name__}: {str(e)[:200]}")
            ok, msg = False, "Could not change the password right now. Please try again later."
        (st.success if ok else st.error)(msg)
