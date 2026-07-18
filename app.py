"""
app.py
Entry point. Handles page config, session state, live sync, and routing
between the login screen, admin dashboard, and student dashboard.

Run with:  streamlit run app.py
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import setup_page, AUTOREFRESH_MS
from styles import inject_css
from database import load_db, touch_user_last_seen, DatabaseUnavailableError
from auth import render_login_signup
from admin_dashboard import render_admin_dashboard
from student_dashboard import render_student_dashboard

# ---------------- PAGE SETUP ----------------
setup_page()
inject_css()

# ---------------- SESSION STATE ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

# ---------------- LOGIN GATE ----------------
if not st.session_state.logged_in:
    render_login_signup()
    # render_login_signup() calls st.stop() internally after rendering

# ---------------- LIVE SYNC (only once logged in, keeps polling light) ----------------
st_autorefresh(interval=AUTOREFRESH_MS, limit=None, key="live_classroom_sync")

# ---------------- LOAD + TOUCH PRESENCE ----------------
# If Supabase is temporarily unreachable, show a friendly retry message
# instead of crashing OR silently continuing with an empty database (the
# old behavior here is what wiped real data during connection hiccups).
try:
    db = load_db()
except DatabaseUnavailableError:
    st.error("Lost connection to the database. This page will retry automatically in a few seconds — your data is safe, please don't refresh manually.")
    st.stop()

touch_user_last_seen(st.session_state.username)

# ---------------- ROUTING (each dashboard renders its own sidebar: nav then roster) ----------------
if st.session_state.role == "admin":
    render_admin_dashboard(db)
elif st.session_state.role == "student":
    render_student_dashboard(db)
