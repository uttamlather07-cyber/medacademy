"""
sidebar.py
Sidebar navigation + who's currently online, shown for logged-in users.
"""

import time
import streamlit as st

from config import ONLINE_THRESHOLD_SECONDS
from styles import pulse_dot_html


def render_nav(admin: bool) -> str:
    """Renders the nav section links and returns the selected page key.
    Uses st.session_state["nav_page"] so the selection survives reruns
    (autorefresh ticks) without resetting to the first tab every time."""
    pages = (
        ["Tests", "Live Quiz", "Leaderboard"] if admin
        else ["Tests", "Practice", "Leaderboard"]
    )
    if "nav_page" not in st.session_state or st.session_state.nav_page not in pages:
        st.session_state.nav_page = pages[0]

    with st.sidebar:
        st.markdown("### Navigate")
        for page in pages:
            is_active = st.session_state.nav_page == page
            if st.button(page, key=f"nav_{page}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state.nav_page = page
                st.rerun()
        st.divider()

    return st.session_state.nav_page


def render_roster(db):
    with st.sidebar:
        st.markdown("### Online Now")

        current_time = time.time()
        users_sorted = sorted(
            db["users"].items(),
            key=lambda kv: (current_time - kv[1].get("last_seen", 0) >= ONLINE_THRESHOLD_SECONDS, kv[0]),
        )

        for user, info in users_sorted:
            is_online = current_time - info.get("last_seen", 0) < ONLINE_THRESHOLD_SECONDS
            role_tag = "ADMIN" if info.get("role") == "admin" else "STUDENT"
            name_class = "roster-name" if is_online else "roster-name offline"

            st.markdown(
                f"""
                <div class="roster-row">
                    {pulse_dot_html(is_online)}
                    <span class="{name_class}">{user.capitalize()}</span>
                    <span class="roster-role-tag">{role_tag}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()
        if st.button("Log Out", key="logout_btn", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.role = ""
            st.session_state.pop("nav_page", None)
            st.rerun()
