"""
config.py
Central place for page configuration and constants.
"""

import streamlit as st

# ----------------------------
# PAGE CONFIG
# ----------------------------
def setup_page():
    st.set_page_config(
        page_title="NEET Test Console",
        page_icon="\u25c8",
        layout="wide",
        initial_sidebar_state="expanded",
    )

# ----------------------------
# MISC
# ----------------------------
ONLINE_THRESHOLD_SECONDS = 15
# Was 3000ms — a timer-driven rerun every 3s, uncoordinated with your own
# click-driven reruns, was the main cause of "have to click 2-3 times" /
# dropped clicks near a countdown ending (see app.py's LIVE SYNC comment
# for the full explanation). 6s keeps live quiz/poll updates feeling
# real-time while giving your own click's rerun much more room to
# complete without a timer tick landing on top of it.
AUTOREFRESH_MS = 6000
# How often (per session) touch_user_last_seen() is actually allowed to
# fire — a presence dot doesn't need sub-second freshness, so this cuts a
# meaningful fraction of redundant Supabase calls without making "Online
# Now" feel noticeably stale (ONLINE_THRESHOLD_SECONDS above is 15s
# anyway, so touching every 8s is still well within that window).
PRESENCE_TOUCH_INTERVAL_SECONDS = 8

# ----------------------------
# FULL-LENGTH TEST DEFAULTS
# ----------------------------
DEFAULT_TEST_DURATION_MINUTES = 180  # 3 hours
DEFAULT_TEST_QUESTION_COUNT = 180
DEFAULT_MARKS_CORRECT = 4
DEFAULT_MARKS_WRONG = -1
DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard"]
