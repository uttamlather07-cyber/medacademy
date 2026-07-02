"""
sidebar.py
The on-duty roster shown in the left sidebar for logged-in users.
"""

import time
import streamlit as st

from config import ONLINE_THRESHOLD_SECONDS
from styles import pulse_dot_html
from chat import has_unread_messages, unread_message_count


def render_roster(db):
    with st.sidebar:
        current_user = st.session_state.get("username", "")
        if current_user and has_unread_messages(db, current_user):
            count = unread_message_count(db, current_user)
            st.markdown(
                f"<div class='badge-pill' style='background:#e8465c;border-color:#e8465c;color:#fff;"
                f"width:100%;box-sizing:border-box;justify-content:center;'>"
                f"🔴 {count} new chat {'message' if count == 1 else 'messages'}</div>",
                unsafe_allow_html=True,
            )
            st.write("")

        st.markdown("### 🏥 On-Duty Roster")
        st.divider()

        current_time = time.time()
        # Sort: online first, then alphabetically
        users_sorted = sorted(
            db["users"].items(),
            key=lambda kv: (current_time - kv[1].get("last_seen", 0) >= ONLINE_THRESHOLD_SECONDS, kv[0]),
        )

        for user, info in users_sorted:
            is_online = current_time - info.get("last_seen", 0) < ONLINE_THRESHOLD_SECONDS
            role_tag = "ADMIN" if info.get("role") == "admin" else "STUDENT"
            blocked_tag = " · 🚫" if info.get("blocked") else ""
            name_class = "roster-name" if is_online else "roster-name offline"

            st.markdown(
                f"""
                <div class="roster-row">
                    {pulse_dot_html(is_online)}
                    <span class="{name_class}">{user.capitalize()}{blocked_tag}</span>
                    <span class="roster-role-tag">{role_tag}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()
        if st.button("🚪 Log Out", key="logout_btn"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.role = ""
            st.rerun()
