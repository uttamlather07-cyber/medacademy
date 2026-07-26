"""
config.py
Central place for page configuration and constants.

Stripped of everything AI/live-quiz related — AUTOREFRESH_MS,
PRESENCE_TOUCH_INTERVAL_SECONDS's old app-wide autorefresh use, and the
DIFFICULTY_LEVELS/AI generation defaults are all gone, since this build
has no live quiz and no AI generation. The one remaining timing constant
that matters (the test auto-submit watchdog's poll interval) lives in
student_dashboard.py right next to the fragment it configures, not here,
since it's tightly coupled to that one piece of logic.
"""
import streamlit as st


def setup_page():
    st.set_page_config(
        page_title="NEET Test Console",
        page_icon="\u25c8",
        layout="wide",
        initial_sidebar_state="expanded",
    )


ONLINE_THRESHOLD_SECONDS = 15
# Presence pings are cheap, targeted single-row updates now (touch_last_seen
# RPC) rather than a full-blob rewrite, so this can stay generous without
# worrying about load the way the old system had to.
PRESENCE_TOUCH_INTERVAL_SECONDS = 20

# ----------------------------
# TEST DEFAULTS
# ----------------------------
DEFAULT_TEST_DURATION_MINUTES = 180  # 3 hours
DEFAULT_MARKS_CORRECT = 4
DEFAULT_MARKS_WRONG = -1
