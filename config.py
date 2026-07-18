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
AUTOREFRESH_MS = 3000

# ----------------------------
# FULL-LENGTH TEST DEFAULTS
# ----------------------------
DEFAULT_TEST_DURATION_MINUTES = 180  # 3 hours
DEFAULT_TEST_QUESTION_COUNT = 180
DEFAULT_MARKS_CORRECT = 4
DEFAULT_MARKS_WRONG = -1
DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard"]
