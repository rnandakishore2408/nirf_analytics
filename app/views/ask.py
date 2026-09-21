"""Chat with an AI analyst over the NIRF database (RAG + tools + live web fetch)."""
from __future__ import annotations

import json

import streamlit as st

import auth
from rag import chat as rag_chat

MAX_PROMPT_CHARS, MAX_HISTORY_MESSAGES = rag_chat.MAX_PROMPT_CHARS, rag_chat.MAX_HISTORY_MESSAGES
PER_HOUR, PER_DAY = rag_chat.PER_HOUR, rag_chat.PER_DAY

user = auth.current_user(st.session_state)
if not user:
    st.stop()

safe_markdown = rag_chat.safe_markdown


st.title("Ask the Data: NIRF analyst")

if not rag_chat.has_credentials():
    st.error("The AI assistant is not configured (no API key). The rest of the dashboard works without it; ask the administrator to add "
             "GROQ_API_KEY or GEMINI_API_KEY to the app's secrets.")
    st.stop()

st.caption(f"Providers (free tiers): {rag_chat.provider_label()} · tools: SQL over the NIRF database, document search (methodology + 700 submissions), live web fetch, Saveetha status")
with st.expander("Example questions"):
    st.markdown(
        """
- Which private colleges entered the Engineering top 100 in 2025 and what were their RPC scores?
- How exactly is the Graduation Outcomes (GO) score computed in 2025? What is GMS?
- Compare Saveetha's 2026 filing with Sri Sivasubramaniya Nadar College's 2025 submission.
- What did NIRF change in 2025 about retracted papers? Search the methodology.
- Has NIRF 2026 been released? Check https://www.nirfindia.org/Rankings/2026/EngineeringRanking.html
- Given our live data, what is the fastest path to the top 150?
"""
    )

if "chat" not in st.session_state:
    st.session_state.chat = []       # API messages
    st.session_state.display = []    # (role, text, tool_events)

for role, text, events in st.session_state.display:
    with st.chat_message(role):
        if events:
            with st.expander(f"{len(events)} tool call(s)"):
                for name, args, out in events:
                    st.markdown(f"**{name}** `{json.dumps(args)[:300]}`")
                    st.code(out[:1200], language="json")
        st.markdown(safe_markdown(text) if role == "assistant" else text)

if st.session_state.display and st.button("Clear conversation"):
    st.session_state.chat, st.session_state.display = [], []
    st.rerun()

prompt = st.chat_input("Ask about rankings, formulas, Saveetha's position, or tell me to check nirfindia.org…", max_chars=MAX_PROMPT_CHARS)
if prompt and not (auth.allow(user["username"], "chat-hour", PER_HOUR, 3600) and auth.allow(user["username"], "chat-day", PER_DAY, 86400)):
    st.warning(f"Question limit reached ({PER_HOUR} per hour, {PER_DAY} per day per user) to keep the free AI quota available. Please try later.")
    prompt = None
if prompt:
    prompt = prompt[:MAX_PROMPT_CHARS]
    st.session_state.chat = st.session_state.chat[-MAX_HISTORY_MESSAGES:]
    while st.session_state.chat and st.session_state.chat[0].get("role") != "user":
        st.session_state.chat.pop(0)  # never start the history on a dangling tool result
    st.session_state.chat.append({"role": "user", "content": prompt})
    st.session_state.display.append(("user", prompt, []))
    with st.chat_message("user"):
        st.markdown(prompt)
    events: list = []
    with st.chat_message("assistant"):
        status = st.status("Thinking…", expanded=False)

        def on_tool(name, args, out):
            events.append((name, args, out))
            status.write(f"🔧 {name} · {json.dumps(args)[:140]}")

        try:
            answer, st.session_state.chat = rag_chat.run_turn(st.session_state.chat, on_tool=on_tool)
            status.update(label=f"Done · {len(events)} tool call(s)", state="complete")
        except Exception as e:  # noqa: BLE001
            print(f"chat turn failed with {type(e).__name__}: {str(e)[:300]}")
            answer = "Sorry, the AI service did not respond. Please try again in a minute."
            status.update(label="Failed", state="error")
        st.markdown(safe_markdown(answer))
    st.session_state.display.append(("assistant", answer, events))
