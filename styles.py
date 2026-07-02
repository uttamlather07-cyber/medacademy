"""
styles.py
The complete visual identity for MedAcademy.

DESIGN CONCEPT — "Clinical Ledger"
- Palette: ink navy background, parchment card surfaces, one arterial-red
  accent used sparingly (like a highlighter on an anatomy chart), and a
  phosphor-green "vitals" accent reserved ONLY for live/online states —
  like a heart-rate monitor.
- Type: a serif display face (journal / textbook authority) paired with a
  monospace face for all numbers, scores, timers (lab-readout feel).
- Signature element: an animated ECG heartbeat line used as a section
  divider and as a "live pulse" indicator — functional, not decorative.
"""

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700;8..60,900&family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --ink: #090d14;
    --ink-2: #0e1420;
    --ink-3: #141b2b;
    --parchment: #f6f3ec;
    --parchment-dim: #e8e3d6;
    --arterial: #e8465c;
    --arterial-dim: rgba(232, 70, 92, 0.15);
    --vitals: #6bffb0;
    --vitals-dim: rgba(107, 255, 176, 0.15);
    --azure: #5b8def;
    --ink-text: #e9e6dd;
    --ink-text-dim: #9a9689;
    --ink-text-faint: #5c5a52;
    --border-line: rgba(233, 230, 221, 0.09);
    --border-line-strong: rgba(233, 230, 221, 0.18);
    --serif: 'Source Serif 4', Georgia, serif;
    --mono: 'JetBrains Mono', 'Courier New', monospace;
    --sans: 'Inter', -apple-system, sans-serif;
}

/* ============ GLOBAL RESET ============ */
.stApp {
    background: var(--ink);
    background-image:
        radial-gradient(ellipse 80% 50% at 50% -10%, rgba(91, 141, 239, 0.08), transparent),
        radial-gradient(ellipse 60% 40% at 100% 100%, rgba(232, 70, 92, 0.05), transparent);
}

html, body, [class*="css"] { font-family: var(--sans); color: var(--ink-text); }

#MainMenu, footer, header[data-testid="stHeader"] { visibility: visible; }
header[data-testid="stHeader"] { background: transparent; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--ink-2); }
::-webkit-scrollbar-thumb { background: var(--border-line-strong); border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: var(--ink-text-faint); }

/* ============ TYPOGRAPHY ============ */
h1, h2, h3 { font-family: var(--serif) !important; color: var(--ink-text) !important; letter-spacing: -0.01em; }

.mono-num { font-family: var(--mono); font-variant-numeric: tabular-nums; }

/* ============ SIGNATURE: ECG PULSE DIVIDER ============ */
.ecg-wrap { width: 100%; height: 36px; overflow: hidden; margin: 4px 0 18px 0; opacity: 0.85; }
.ecg-line {
    stroke: var(--vitals);
    stroke-width: 2;
    fill: none;
    filter: drop-shadow(0 0 4px rgba(107,255,176,0.5));
    stroke-dasharray: 1000;
    stroke-dashoffset: 1000;
    animation: ecgDraw 3.2s linear infinite;
}
@keyframes ecgDraw {
    0% { stroke-dashoffset: 1000; }
    70% { stroke-dashoffset: 0; }
    100% { stroke-dashoffset: -20; }
}

/* Small live pulse dot, used next to "online" labels */
.pulse-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: var(--vitals); box-shadow: 0 0 0 rgba(107,255,176,0.5);
    animation: pulseDot 1.8s infinite;
}
@keyframes pulseDot {
    0% { box-shadow: 0 0 0 0 rgba(107,255,176,0.55); }
    70% { box-shadow: 0 0 0 8px rgba(107,255,176,0); }
    100% { box-shadow: 0 0 0 0 rgba(107,255,176,0); }
}
.offline-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background: var(--ink-text-faint); }

/* ============ LANDING / HERO ============ */
.hero-wrap {
    text-align: center; padding: 56px 20px 28px 20px; position: relative;
}
.hero-eyebrow {
    font-family: var(--mono); font-size: 0.78rem; letter-spacing: 0.18em;
    color: var(--vitals); text-transform: uppercase; margin-bottom: 14px;
    display: inline-flex; align-items: center; gap: 8px;
}
.hero-title {
    font-family: var(--serif); font-weight: 700; font-size: 3.4rem; line-height: 1.05;
    color: var(--ink-text); margin: 0 0 14px 0; letter-spacing: -0.02em;
}
.hero-title em { color: var(--arterial); font-style: normal; }
.hero-sub {
    font-family: var(--sans); font-size: 1.08rem; color: var(--ink-text-dim);
    max-width: 560px; margin: 0 auto 8px auto; line-height: 1.6;
}

@keyframes fadeSlideIn {
    0% { opacity: 0; transform: translateY(14px); }
    100% { opacity: 1; transform: translateY(0); }
}
.anim-in { animation: fadeSlideIn 0.6s cubic-bezier(0.16,1,0.3,1) forwards; }
.anim-in-delay-1 { animation: fadeSlideIn 0.6s cubic-bezier(0.16,1,0.3,1) 0.1s forwards; opacity:0; }
.anim-in-delay-2 { animation: fadeSlideIn 0.6s cubic-bezier(0.16,1,0.3,1) 0.2s forwards; opacity:0; }
.anim-in-delay-3 { animation: fadeSlideIn 0.6s cubic-bezier(0.16,1,0.3,1) 0.3s forwards; opacity:0; }

/* Vitals stat strip on landing */
.vitals-strip { display: flex; justify-content: center; gap: 0; flex-wrap: wrap; margin: 30px 0 10px 0; }
.vital-stat { padding: 0 28px; text-align: center; border-right: 1px solid var(--border-line); }
.vital-stat:last-child { border-right: none; }
.vital-stat .num { font-family: var(--mono); font-size: 1.7rem; font-weight: 700; color: var(--vitals); }
.vital-stat .label { font-family: var(--sans); font-size: 0.72rem; color: var(--ink-text-faint); text-transform: uppercase; letter-spacing: 0.08em; margin-top: 2px; }

/* ============ CARDS / CONTAINERS ============ */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--ink-2) !important;
    border: 1px solid var(--border-line) !important;
    border-radius: 14px !important;
    transition: border-color 0.25s ease, transform 0.25s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover { border-color: var(--border-line-strong) !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--border-line); }
.stTabs [data-baseweb="tab"] {
    font-family: var(--sans); font-weight: 600; font-size: 0.92rem; color: var(--ink-text-dim);
    background: transparent; border-radius: 8px 8px 0 0; padding: 10px 18px;
}
.stTabs [aria-selected="true"] { color: var(--vitals) !important; border-bottom: 2px solid var(--vitals) !important; }

/* Inputs */
.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] {
    background: var(--ink) !important; border: 1px solid var(--border-line-strong) !important;
    border-radius: 10px !important; color: var(--ink-text) !important; font-family: var(--sans) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus { border-color: var(--vitals) !important; box-shadow: 0 0 0 1px var(--vitals) !important; }

/* Buttons */
.stButton>button, .stFormSubmitButton>button {
    width: 100%; border-radius: 10px; font-weight: 600; font-family: var(--sans);
    border: 1px solid var(--border-line-strong); background: var(--ink-3); color: var(--ink-text);
    transition: all 0.2s ease; padding: 0.55rem 1rem;
}
.stButton>button:hover, .stFormSubmitButton>button:hover {
    border-color: var(--vitals); color: var(--vitals); transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(107,255,176,0.12);
}
.stButton>button[kind="primary"], .stFormSubmitButton>button[kind="primary"] {
    background: var(--arterial); border-color: var(--arterial); color: #fff;
}
.stButton>button[kind="primary"]:hover { background: #d63850; box-shadow: 0 4px 18px rgba(232,70,92,0.35); }

/* ============ SCORE / METRIC CARDS ============ */
.metric-tile {
    background: linear-gradient(160deg, var(--ink-3) 0%, var(--ink-2) 100%);
    border: 1px solid var(--border-line); border-radius: 14px; padding: 20px;
    text-align: center; transition: transform 0.25s ease, border-color 0.25s ease;
}
.metric-tile:hover { transform: translateY(-3px); border-color: var(--vitals-dim); }
.metric-tile .val { font-family: var(--mono); font-size: 2.1rem; font-weight: 700; color: var(--vitals); line-height: 1.1; }
.metric-tile .lbl { font-family: var(--sans); font-size: 0.78rem; color: var(--ink-text-dim); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.06em; }

.badge-pill {
    display: inline-flex; align-items: center; gap: 6px; background: var(--ink-3);
    border: 1px solid var(--border-line-strong); color: var(--ink-text);
    padding: 6px 14px; border-radius: 100px; font-size: 0.85rem; font-weight: 600;
    font-family: var(--mono); margin: 3px;
}

/* ============ ANNOUNCEMENT BANNER ============ */
@keyframes bannerGlow {
    0%, 100% { box-shadow: 0 0 0 0 rgba(232, 70, 92, 0.35); }
    50% { box-shadow: 0 0 0 8px rgba(232, 70, 92, 0); }
}
.announce-banner {
    background: linear-gradient(90deg, var(--arterial), #c0304a);
    color: #fff; padding: 14px 22px; border-radius: 12px; font-weight: 600;
    text-align: center; margin-bottom: 18px; animation: bannerGlow 2.4s infinite;
    font-family: var(--sans); font-size: 0.98rem;
}

/* ============ QUIZ TIMER (small corner badge, not a full-width tile) ============ */
.quiz-header-row {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 14px; margin-bottom: 4px;
}
.quiz-header-row .quiz-heading { flex: 1; min-width: 0; }
.quiz-badges { flex-shrink: 0; display: flex; gap: 8px; }
.progress-badge {
    flex-shrink: 0; display: flex; flex-direction: column; align-items: center;
    justify-content: center; min-width: 64px; padding: 6px 12px;
    border-radius: 10px; background: var(--ink-3); border: 1px solid rgba(91,141,239,0.35);
    line-height: 1.1;
}
.progress-badge .t-val {
    font-family: var(--mono); font-size: 1.2rem; font-weight: 700; color: var(--azure);
    font-variant-numeric: tabular-nums;
}
.progress-badge .t-lbl {
    font-family: var(--sans); font-size: 0.6rem; color: var(--ink-text-faint);
    text-transform: uppercase; letter-spacing: 0.05em; margin-top: 1px;
}
.timer-badge {
    flex-shrink: 0; display: flex; flex-direction: column; align-items: center;
    justify-content: center; min-width: 64px; padding: 6px 12px;
    border-radius: 10px; background: var(--ink-3); border: 1px solid var(--vitals-dim);
    line-height: 1.1;
}
.timer-badge .t-val {
    font-family: var(--mono); font-size: 1.2rem; font-weight: 700; color: var(--vitals);
    font-variant-numeric: tabular-nums;
}
.timer-badge .t-lbl {
    font-family: var(--sans); font-size: 0.6rem; color: var(--ink-text-faint);
    text-transform: uppercase; letter-spacing: 0.05em; margin-top: 1px;
}
.timer-badge.urgent { border-color: var(--arterial); background: rgba(232,70,92,0.08); animation: bannerGlow 1s infinite; }
.timer-badge.urgent .t-val { color: var(--arterial); }

/* ============ QUIZ REVEAL ============ */
@keyframes popIn { 0% { opacity:0; transform: scale(0.94); } 100% { opacity:1; transform: scale(1); } }
.reveal-box { animation: popIn 0.45s cubic-bezier(0.16,1,0.3,1) forwards; background: rgba(107,255,176,0.06); border: 1px solid var(--vitals-dim); padding: 20px; border-radius: 12px; margin-top: 14px; }
.reveal-box.wrong { background: rgba(232,70,92,0.06); border: 1px solid var(--arterial-dim); }

/* ============ CHAT ============ */
.chat-scroll-anchor { animation: fadeSlideIn 0.3s ease forwards; }

.chat-row { display: flex; margin-bottom: 14px; animation: fadeSlideIn 0.35s cubic-bezier(0.16,1,0.3,1) forwards; width: 100%; }
.chat-row.me { justify-content: flex-end; }
.chat-row.other { justify-content: flex-start; }

.chat-bubble {
    max-width: 74%; padding: 12px 16px; border-radius: 16px; color: #fff;
    box-shadow: 0 3px 10px rgba(0,0,0,0.25); position: relative;
}
.chat-bubble.admin { background: linear-gradient(135deg, #c0304a, #7d1f30); border-bottom-left-radius: 4px; }
.chat-bubble.student-me { background: linear-gradient(135deg, #3f6fd6, #24408f); border-bottom-right-radius: 4px; }
.chat-bubble.student-other { background: linear-gradient(135deg, #232b3d, #171d2c); border: 1px solid var(--border-line-strong); border-bottom-left-radius: 4px; }

.chat-sender { font-size: 0.74rem; font-weight: 700; margin-bottom: 4px; opacity: 0.85; font-family: var(--sans); text-transform: uppercase; letter-spacing: 0.03em; }
.chat-text { font-size: 0.96rem; font-family: var(--sans); line-height: 1.45; word-wrap: break-word; }
.chat-time { font-size: 0.66rem; opacity: 0.55; margin-top: 5px; font-family: var(--mono); text-align: right; }

.chat-image-wrap { margin-top: 6px; border-radius: 10px; overflow: hidden; border: 1px solid rgba(255,255,255,0.15); }
.chat-image-wrap img { width: 100%; display: block; max-height: 320px; object-fit: cover; }

.chat-file-chip {
    display: flex; align-items: center; gap: 10px; background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.15); border-radius: 10px; padding: 10px 12px; margin-top: 6px;
    text-decoration: none; color: #fff; transition: background 0.2s ease;
}
.chat-file-chip:hover { background: rgba(255,255,255,0.18); }
.chat-file-icon { font-size: 1.4rem; }
.chat-file-name { font-size: 0.85rem; font-weight: 600; word-break: break-all; }
.chat-file-meta { font-size: 0.7rem; opacity: 0.7; font-family: var(--mono); }

.typing-hint { font-family: var(--mono); font-size: 0.75rem; color: var(--ink-text-faint); padding: 4px 2px; }

/* ============ SIDEBAR ROSTER ============ */
section[data-testid="stSidebar"] { background: var(--ink-2); border-right: 1px solid var(--border-line); }
.roster-row { display: flex; align-items: center; gap: 8px; padding: 6px 4px; font-family: var(--sans); font-size: 0.88rem; }
.roster-name { color: var(--ink-text); font-weight: 500; }
.roster-name.offline { color: var(--ink-text-faint); }
.roster-role-tag { font-family: var(--mono); font-size: 0.65rem; padding: 1px 6px; border-radius: 6px; background: var(--ink-3); color: var(--ink-text-faint); margin-left: auto; }

/* ============ MISC ============ */
hr, [data-testid="stDivider"] { border-color: var(--border-line) !important; }

@media (max-width: 640px) {
    .hero-title { font-size: 2.2rem; }
    .vitals-strip { gap: 6px; }
    .vital-stat { padding: 0 14px; border-right: none; }
}
</style>
"""

# Reusable ECG SVG divider (the "signature element")
ECG_SVG = """
<div class="ecg-wrap">
<svg class="ecg-wrap" viewBox="0 0 1000 36" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
  <path class="ecg-line" d="M0,18 L120,18 L145,18 L160,4 L175,32 L190,10 L205,18 L230,18 L500,18 L520,18 L545,18 L560,4 L575,32 L590,10 L605,18 L630,18 L1000,18" />
</svg>
</div>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def ecg_divider():
    st.markdown(ECG_SVG, unsafe_allow_html=True)


def pulse_dot_html(online: bool) -> str:
    return "<span class='pulse-dot'></span>" if online else "<span class='offline-dot'></span>"
