"""
styles.py
Visual identity — kept from the original design almost unchanged (it was
already a good match for a focused test-platform aesthetic: dark neutral
base, one indigo accent, monospace numbers for timers/scores). Stripped
of classes that only ever applied to the removed live-quiz/auto-quiz
screens (.quiz-header-row, .progress-badge, .timer-badge, .reveal-box) —
everything test-related (.exam-bar, .lb-row, palette buttons, cards,
buttons, inputs) is kept, since the rebuilt test-taking screen still
needs exactly that.
"""

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

:root {
    --bg: #0b0f17;
    --bg-raised: #10151f;
    --bg-card: #131a26;
    --bg-card-hover: #17202f;
    --accent: #5b5fef;
    --accent-hover: #7477f2;
    --accent-dim: rgba(91, 95, 239, 0.14);
    --success: #22c55e;
    --success-dim: rgba(34, 197, 94, 0.14);
    --danger: #ef4444;
    --danger-dim: rgba(239, 68, 68, 0.14);
    --warning: #f5a623;
    --warning-dim: rgba(245, 166, 35, 0.14);
    --text: #e7eaf0;
    --text-dim: #9aa4b6;
    --text-faint: #5b6577;
    --border: rgba(231, 234, 240, 0.08);
    --border-strong: rgba(231, 234, 240, 0.16);
    --sans: 'Inter', -apple-system, sans-serif;
    --mono: 'JetBrains Mono', 'Courier New', monospace;
}

/* ============ GLOBAL ============ */
.stApp { background: var(--bg); }
html, body, [class*="css"] { font-family: var(--sans); color: var(--text); }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--bg-raised); }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 8px; }

h1, h2, h3 { font-family: var(--sans) !important; color: var(--text) !important; font-weight: 700 !important; letter-spacing: -0.01em; }

.mono-num { font-family: var(--mono); font-variant-numeric: tabular-nums; font-weight: 600; }

/* ============ LIVE STATUS DOT (presence roster) ============ */
.pulse-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    background: var(--success); box-shadow: 0 0 0 rgba(34,197,94,0.5);
    animation: pulseDot 1.8s infinite;
}
@keyframes pulseDot {
    0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.55); }
    70% { box-shadow: 0 0 0 6px rgba(34,197,94,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}
.offline-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background: var(--text-faint); }

/* ============ CARDS ============ */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--bg-card) !important; border: 1px solid var(--border) !important;
    border-radius: 12px !important; transition: border-color 0.2s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover { border-color: var(--border-strong) !important; }

.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] {
    font-weight: 600; font-size: 0.9rem; color: var(--text-dim);
    background: transparent; border-radius: 8px 8px 0 0; padding: 10px 16px;
}
.stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }

/* Inputs */
.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"], .stNumberInput input {
    background: var(--bg) !important; border: 1px solid var(--border-strong) !important;
    border-radius: 8px !important; color: var(--text) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 1px var(--accent) !important; }

/* Buttons */
.stButton>button, .stFormSubmitButton>button {
    width: 100%; border-radius: 8px; font-weight: 600;
    border: 1px solid var(--border-strong); background: var(--bg-raised); color: var(--text);
    transition: all 0.15s ease; padding: 0.55rem 1rem;
}
.stButton>button:hover, .stFormSubmitButton>button:hover {
    border-color: var(--accent); color: var(--accent-hover);
}
.stButton>button[kind="primary"], .stFormSubmitButton>button[kind="primary"] {
    background: var(--accent); border-color: var(--accent); color: #fff;
}
.stButton>button[kind="primary"]:hover { background: var(--accent-hover); border-color: var(--accent-hover); }

/* ============ METRIC / SCORE TILES ============ */
.metric-tile {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px; text-align: center;
}
.metric-tile .val { font-family: var(--mono); font-size: 1.9rem; font-weight: 700; color: var(--accent); line-height: 1.1; }
.metric-tile .lbl { font-size: 0.74rem; color: var(--text-dim); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.05em; }

.badge-pill {
    display: inline-flex; align-items: center; gap: 6px; background: var(--bg-raised);
    border: 1px solid var(--border-strong); color: var(--text);
    padding: 5px 12px; border-radius: 100px; font-size: 0.82rem; font-weight: 600;
    font-family: var(--mono); margin: 2px;
}

/* ============ EXAM MODE — signature element ============ */
/* The JS countdown injected by student_dashboard.py's
   _render_countdown_display renders its own inline styles (it has to,
   since components.html is a sandboxed iframe that doesn't inherit
   this page's CSS) — this block styles everything AROUND it: the
   question card, palette grid, and the exam-style top divider. */
.exam-bar {
    position: sticky; top: 0; z-index: 999;
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; background: var(--bg-raised); border: 1px solid var(--border-strong);
    border-radius: 12px; padding: 14px 20px; margin-bottom: 18px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.35);
}

/* Question palette grid buttons — base sizing/shape here; per-button
   green/orange/grey COLOR is injected dynamically per attempt by
   student_dashboard.py's _render_palette (via .st-key-<button-key>
   selectors), since which questions are answered changes constantly
   and can't be a static rule in this file. */
.qpalette-btn-wrap .stButton>button {
    aspect-ratio: 1; padding: 0; font-family: var(--mono); font-weight: 700; font-size: 0.85rem;
}

/* ============ SIDEBAR ============ */
section[data-testid="stSidebar"] { background: var(--bg-raised); border-right: 1px solid var(--border); }
.roster-row { display: flex; align-items: center; gap: 8px; padding: 6px 4px; font-size: 0.86rem; }
.roster-name { color: var(--text); font-weight: 500; }
.roster-name.offline { color: var(--text-faint); }
.roster-role-tag { font-family: var(--mono); font-size: 0.62rem; padding: 1px 6px; border-radius: 6px; background: var(--bg-card); color: var(--text-faint); margin-left: auto; }

/* ============ LEADERBOARD ============ */
.lb-row {
    display: flex; align-items: center; gap: 14px; padding: 12px 16px;
    border-radius: 10px; margin-bottom: 6px; background: var(--bg-card);
    border: 1px solid var(--border);
}
.lb-row.me { border-color: var(--accent); background: var(--accent-dim); }
.lb-row.top3 { border-color: var(--warning); }
.lb-rank { font-family: var(--mono); font-weight: 800; font-size: 1.1rem; color: var(--text-dim); min-width: 34px; }
.lb-rank.top3 { color: var(--warning); }
.lb-name { flex: 1; font-weight: 600; }
.lb-score { font-family: var(--mono); font-weight: 700; color: var(--accent); font-size: 1.05rem; }
.lb-meta { font-size: 0.74rem; color: var(--text-faint); font-family: var(--mono); }

hr, [data-testid="stDivider"] { border-color: var(--border) !important; }

@media (max-width: 640px) {
    .exam-bar { flex-direction: column; align-items: stretch; gap: 10px; }
}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def pulse_dot_html(online: bool) -> str:
    return "<span class='pulse-dot'></span>" if online else "<span class='offline-dot'></span>"
