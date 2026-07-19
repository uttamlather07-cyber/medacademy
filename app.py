"""
app.py
Entry point. Handles page config, session state, live sync, and routing
between the login screen, admin dashboard, and student dashboard.

Run with:  streamlit run app.py
"""

import time
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import setup_page, AUTOREFRESH_MS, PRESENCE_TOUCH_INTERVAL_SECONDS
from styles import inject_css
from database import load_db, touch_user_last_seen, DatabaseUnavailableError
from quiz import get_active_attempt
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

# ---------------- LOAD DATABASE ----------------
# Loaded BEFORE the autorefresh decision below (unlike before) so we can
# check whether the logged-in student actually has a test in progress
# right now. Cheap to do here even every rerun — see database.py's
# short-TTL cache, the other half of this lag fix.
# If Supabase is temporarily unreachable, show a friendly retry message
# instead of crashing OR silently continuing with an empty database (the
# old behavior here is what wiped real data during connection hiccups).
try:
    db = load_db()
except DatabaseUnavailableError:
    st.error("Lost connection to the database. This page will retry automatically in a few seconds — your data is safe, please don't refresh manually.")
    st.stop()

# ---------------- LIVE SYNC ----------------
# IMPORTANT — this is the main fix for "clicks need 2-3 tries" /
# "clicks don't register near a timer ending": st_autorefresh forces a
# full script rerun on a timer, completely uncoordinated with the rerun
# your own click already triggers. If a timer-driven rerun starts right
# as you click (or right as a countdown hits zero and the UI is about to
# change), Streamlit can drop or ignore that click. Two changes here:
#   1. Autorefresh is OFF ENTIRELY while the logged-in student has an
#      in-progress full-length test attempt right now. There is no
#      live-sync need there (a student only ever needs to see their OWN
#      answers), and it's exactly the worst place to risk eating a click
#      (e.g. Submit Test). Checked directly against real DB state here,
#      not a flag the dashboard sets — a flag set during the dashboard's
#      OWN render would only take effect on the NEXT rerun, one rerun too
#      late to prevent the very autorefresh call it's meant to guard.
#   2. Everywhere else, the interval is slower (see config.py) than
#      before — still fresh enough for a live quiz/poll to feel real-time,
#      but far less likely to collide with an in-progress click.
_student_mid_test = False
if st.session_state.role == "student":
    for test in db.get("full_tests", {}).values():
        if get_active_attempt(test, st.session_state.username) is not None:
            _student_mid_test = True
            break

if not _student_mid_test:
    st_autorefresh(interval=AUTOREFRESH_MS, limit=None, key="live_classroom_sync")

# ---------------- PRESENCE (throttled) ----------------
# touch_user_last_seen() used to fire on EVERY rerun (every click AND every
# autorefresh tick) — a presence indicator doesn't need sub-second
# freshness, so this now only actually writes once every
# PRESENCE_TOUCH_INTERVAL_SECONDS per session, cutting a large fraction of
# redundant network calls without making "Online Now" feel noticeably stale.
_last_touch = st.session_state.get("_last_presence_touch", 0)
if time.time() - _last_touch > PRESENCE_TOUCH_INTERVAL_SECONDS:
    touch_user_last_seen(st.session_state.username)
    st.session_state["_last_presence_touch"] = time.time()

# ---------------- ROUTING (each dashboard renders its own sidebar: nav then roster) ----------------
if st.session_state.role == "admin":
    render_admin_dashboard(db)
elif st.session_state.role == "student":
    render_student_dashboard(db)
