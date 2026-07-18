"""
styles.py
Visual identity for the platform.

DESIGN CONCEPT - "Study Console"
A focused, professional test/practice platform in the register of PW /
Unacademy dashboards: dark neutral base, one confident indigo accent for
actions and active states, and a strict, MEANINGFUL color contract for
status (green = correct, red = incorrect, amber = time running low -
these three colors are never used for anything else, so they stay legible
signals rather than decoration).

Sans-serif throughout (Inter) since this is a data-dense utility product,
not an editorial page. Numbers - timers, scores, question counts - always
render in a monospace face (JetBrains Mono) so they read as DATA at a
glance, distinct from surrounding prose. This is the one typographic
signature carried through the whole app.

Signature element: the exam-mode top bar used during full-length timed
tests - a persistent, slim status bar showing the countdown and a live
answered/marked/unattempted breakdown. It's the single place real design
attention goes, because it's the moment that most needs to feel like a
real, trustworthy testing platform.
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

/* ============ LIVE STATUS DOT ============ */
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

/* ============ HERO / LANDING ============ */
.hero-wrap { text-align: center; padding: 64px 20px 32px 20px; }
.hero-eyebrow {
    font-family: var(--mono); font-size: 0.74rem; letter-spacing: 0.14em;
    color: var(--accent); text-transform: uppercase; margin-bottom: 16px;
    display: inline-flex; align-items: center; gap: 8px;
}
.hero-title {
    font-family: var(--sans); font-weight: 800; font-size: 3rem; line-height: 1.08;
    color: var(--text); margin: 0 0 14px 0; letter-spacing: -0.02em;
}
.hero-title em { color: var(--accent); font-style: normal; }
.hero-sub {
    font-size: 1.05rem; color: var(--text-dim); max-width: 560px;
    margin: 0 auto 8px auto; line-height: 1.6;
}
@keyframes fadeSlideIn { 0% { opacity: 0; transform: translateY(12px); } 100% { opacity: 1; transform: translateY(0); } }
.anim-in { animation: fadeSlideIn 0.5s cubic-bezier(0.16,1,0.3,1) forwards; }
.anim-in-delay-1 { animation: fadeSlideIn 0.5s cubic-bezier(0.16,1,0.3,1) 0.08s forwards; opacity:0; }
.anim-in-delay-2 { animation: fadeSlideIn 0.5s cubic-bezier(0.16,1,0.3,1) 0.16s forwards; opacity:0; }

.vitals-strip { display: flex; justify-content: center; gap: 0; flex-wrap: wrap; margin: 28px 0 8px 0; }
.vital-stat { padding: 0 28px; text-align: center; border-right: 1px solid var(--border); }
.vital-stat:last-child { border-right: none; }
.vital-stat .num { font-family: var(--mono); font-size: 1.6rem; font-weight: 700; color: var(--accent); }
.vital-stat .label { font-size: 0.7rem; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; margin-top: 2px; }

/* ============ CARDS ============ */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--bg-card) !important; border: 1px solid var(--border) !important;
    border-radius: 12px !important; transition: border-color 0.2s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover { border-color: var(--border-strong) !important; }

/* Tabs (used sparingly now - sidebar nav is primary) */
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

/* ============ QUESTION CARD (live quiz) ============ */
.quiz-header-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; margin-bottom: 4px; }
.quiz-header-row .quiz-heading { flex: 1; min-width: 0; font-size: 1.05rem; line-height: 1.5; }
.quiz-badges { flex-shrink: 0; display: flex; gap: 8px; }
.progress-badge, .timer-badge {
    flex-shrink: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-width: 62px; padding: 6px 12px; border-radius: 8px; background: var(--bg-raised);
    border: 1px solid var(--border-strong); line-height: 1.1;
}
.progress-badge .t-val { font-family: var(--mono); font-size: 1.15rem; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }
.timer-badge .t-val { font-family: var(--mono); font-size: 1.15rem; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.progress-badge .t-lbl, .timer-badge .t-lbl { font-size: 0.6rem; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 1px; }
.timer-badge.urgent { border-color: var(--warning); background: var(--warning-dim); }
.timer-badge.urgent .t-val { color: var(--warning); }

@keyframes popIn { 0% { opacity:0; transform: scale(0.96); } 100% { opacity:1; transform: scale(1); } }
.reveal-box { animation: popIn 0.35s cubic-bezier(0.16,1,0.3,1) forwards; background: var(--success-dim); border: 1px solid rgba(34,197,94,0.3); padding: 18px; border-radius: 10px; margin-top: 12px; }
.reveal-box.wrong { background: var(--danger-dim); border: 1px solid rgba(239,68,68,0.3); }

/* ============ EXAM MODE - SIGNATURE ELEMENT ============ */
/* Persistent top bar during a full-length timed test: countdown clock +
   live answered/marked/unattempted counts. This is the one place real
   design attention goes - it's the moment that most needs to read as a
   serious, trustworthy exam platform, not a quiz toy. */
.exam-bar {
    position: sticky; top: 0; z-index: 999;
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; background: var(--bg-raised); border: 1px solid var(--border-strong);
    border-radius: 12px; padding: 14px 20px; margin-bottom: 18px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.35);
}
.exam-bar-title { font-weight: 700; font-size: 0.95rem; color: var(--text); }
.exam-bar-clock {
    font-family: var(--mono); font-size: 1.4rem; font-weight: 700; color: var(--text);
    font-variant-numeric: tabular-nums; letter-spacing: 0.02em;
}
.exam-bar-clock.urgent { color: var(--warning); animation: clockPulse 1s infinite; }
@keyframes clockPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.55; } }
.exam-bar-stats { display: flex; gap: 18px; }
.exam-stat { text-align: center; }
.exam-stat .n { font-family: var(--mono); font-size: 1.05rem; font-weight: 700; }
.exam-stat .l { font-size: 0.62rem; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.05em; }
.exam-stat.answered .n { color: var(--success); }
.exam-stat.marked .n { color: var(--warning); }
.exam-stat.unattempted .n { color: var(--text-faint); }

/* Question palette grid (jump to any question) */
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
    .hero-title { font-size: 2rem; }
    .vitals-strip { gap: 6px; }
    .vital-stat { padding: 0 14px; border-right: none; }
    .exam-bar { flex-direction: column; align-items: stretch; gap: 10px; }
}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def pulse_dot_html(online: bool) -> str:
    return "<span class='pulse-dot'></span>" if online else "<span class='offline-dot'></span>"
