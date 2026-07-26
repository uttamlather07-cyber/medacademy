"""
app.py
Entry point. Handles page config, session state, and routing between the
login screen, admin dashboard, and student dashboard.

Run with:  streamlit run app.py

MUCH SIMPLER than the old app.py — the old version had to coordinate
app-wide st_autorefresh against every possible screen (live quiz,
full-test attempts, everything), which was the actual source of the
"clicks need 2-3 tries" bug. That whole coordination problem is gone
here: this app has no app-wide autorefresh at all. The ONE place that
needs periodic ticking (the test-taking screen's auto-submit-on-expiry
check) uses a narrowly-scoped st.fragment instead, isolated to just that
one screen and containing no interactive widgets — see
student_dashboard.py's _timer_watchdog_fragment docstring for the full
reasoning. Nothing here needs to know about it or coordinate with it.
"""

import streamlit as st

from config import setup_page, PRESENCE_TOUCH_INTERVAL_SECONDS
from styles import inject_css
from database import touch_last_seen, DatabaseUnavailableError
from auth import render_login_signup, try_resume_session
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

# ---------------- RESUME PERSISTENT LOGIN (before the gate) ----------------
# Checks for a valid session cookie and, if found, populates
# st.session_state as if the student had just logged in — see
# auth.py's module docstring for the full reasoning (a database-backed
# token, never the actual password, in the cookie). Must run BEFORE the
# login gate below, or a returning student with a perfectly valid
# session would still see the login screen every time.
if not st.session_state.logged_in:
    try_resume_session()

# ---------------- LOGIN GATE ----------------
if not st.session_state.logged_in:
    render_login_signup()
    # render_login_signup() calls st.stop() internally after rendering

# ---------------- PRESENCE (throttled, best-effort) ----------------
import time
_last_touch = st.session_state.get("_last_presence_touch", 0)
if time.time() - _last_touch > PRESENCE_TOUCH_INTERVAL_SECONDS:
    try:
        touch_last_seen(st.session_state.username)
    except DatabaseUnavailableError:
        pass  # presence is a nicety — never block the page over it
    st.session_state["_last_presence_touch"] = time.time()

# ---------------- ROUTING ----------------
if st.session_state.role == "admin":
    render_admin_dashboard()
elif st.session_state.role == "student":
    render_student_dashboard()
else:
    st.error("Unknown role — please log out and log back in.")
    if st.button("Log Out"):
        for key in ("logged_in", "username", "role"):
            st.session_state.pop(key, None)
        st.rerun()
