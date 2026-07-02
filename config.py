"""
config.py
Central place for theme colors, constants, and page configuration.
Change colors here to re-theme the entire app.
"""

import streamlit as st

# ----------------------------
# PAGE CONFIG
# ----------------------------
def setup_page():
    st.set_page_config(
        page_title="MedAcademy | Elite NEET Prep",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

# ----------------------------
# THEME — Deep Space Clinical (navy / violet / cyan accent)
# ----------------------------
THEME = {
    "bg_primary": "#0a0e1a",
    "bg_secondary": "#0f1420",
    "bg_card": "#131a2b",
    "bg_card_hover": "#182140",
    "accent_primary": "#6366f1",      # indigo
    "accent_secondary": "#22d3ee",    # cyan
    "accent_success": "#34d399",      # emerald
    "accent_danger": "#fb7185",       # rose
    "accent_warning": "#fbbf24",      # amber
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "border": "rgba(148, 163, 184, 0.12)",
    "gradient_main": "linear-gradient(135deg, #6366f1 0%, #22d3ee 100%)",
    "gradient_dark": "linear-gradient(180deg, #0a0e1a 0%, #131a2b 100%)",
}

# ----------------------------
# FILE UPLOAD CONSTRAINTS
# ----------------------------
UPLOAD_DIR = "uploads"
MAX_FILE_SIZE_MB = 8
ALLOWED_IMAGE_TYPES = ["png", "jpg", "jpeg", "gif", "webp"]
ALLOWED_FILE_TYPES = ["pdf", "docx", "doc", "txt", "pptx", "xlsx", "zip", "csv"]
ALLOWED_ALL_TYPES = ALLOWED_IMAGE_TYPES + ALLOWED_FILE_TYPES

# ----------------------------
# MISC
# ----------------------------
DB_FILE = "database.json"
ONLINE_THRESHOLD_SECONDS = 15
AUTOREFRESH_MS = 3000
CHAT_HISTORY_LIMIT = 60
