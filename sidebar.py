"""
sidebar.py
Nav menu (admin sees Tests/Leaderboard, student sees Tests/Leaderboard)
and the presence roster underneath it.
"""

import time
import streamlit as st
from database import get_all_users, DatabaseUnavailableError
from styles import pulse_dot_html
from config import ONLINE_THRESHOLD_SECONDS


def render_nav(admin: bool) -> str:
    with st.sidebar:
        st.markdown(f"**Logged in as** `{st.session_state.username}`")
        pages = ["Tests", "Leaderboard"]
        page = st.radio("Navigate", pages, label_visibility="collapsed")
        st.divider()
        if st.button("Log Out", use_container_width=True):
            for key in ("logged_in", "username", "role", "active_attempt_id"):
                st.session_state.pop(key, None)
            st.rerun()
    return page


def render_roster():
    try:
        users = get_all_users()
    except DatabaseUnavailableError:
        return  # roster is a nicety, not worth erroring the whole page over

    now = time.time()
    with st.sidebar:
        st.divider()
        st.caption("ONLINE NOW")
        for u in sorted(users, key=lambda x: x["username"]):
            last_seen = u.get("last_seen")
            is_online = False
            if last_seen:
                try:
                    import datetime
                    ts = datetime.datetime.fromisoformat(str(last_seen).replace("Z", "+00:00")).timestamp()
                    is_online = (now - ts) < ONLINE_THRESHOLD_SECONDS
                except Exception:
                    is_online = False
            dot = pulse_dot_html(is_online)
            offline_class = "" if is_online else "offline"
            st.markdown(
                f"<div class='roster-row'>{dot}<span class='roster-name {offline_class}'>{u['username']}</span>"
                f"<span class='roster-role-tag'>{u['role']}</span></div>",
                unsafe_allow_html=True,
            )
