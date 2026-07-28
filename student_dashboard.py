"""
student_dashboard.py
Everything a logged-in student sees: the list of open tests to join, and
the test-taking screen itself.

CONCURRENCY MODEL — read before touching this file:
Every write here (submit_answer, start_or_resume_attempt, finalize_attempt)
routes through database.py's targeted per-row functions, NEVER a full
load/save of "the database." A student answering a question touches
exactly one row (their own test_answers row for that question) — this is
what lets 20-30 students act simultaneously without contending with each
other. If you're tempted to add a "load everything, mutate in Python,
save everything back" pattern here, don't; that's the exact design that
caused the original lag (see database.py's module docstring).

TIMER MODEL — the countdown display is a client-side JS clock (zero
server cost to just LOOK at), but actual expiry enforcement is a
server-side check inside a narrowly-scoped st.fragment(run_every=...)
that contains NO interactive widgets — see _timer_watchdog_fragment's
docstring for exactly why it's built this way and what breaks if you
add a button inside it.
"""

import html
import time
import streamlit as st
import streamlit.components.v1 as components

from database import (
    get_open_tests, get_test, get_test_questions,
    start_or_resume_attempt, get_attempt, set_current_question,
    submit_answer, get_attempt_answers, finalize_attempt,
    get_test_leaderboard, get_todays_daily_set, get_active_attempt,
    set_daily_target, mark_my_target_complete, get_my_todays_target,
    get_todays_target_feed, DatabaseUnavailableError,
)
from sidebar import render_nav, render_roster

LETTERS = ["A", "B", "C", "D", "E", "F"]


def render_student_dashboard(db_unused=None):
    """db_unused kept only so app.py's existing call signature
    (render_student_dashboard(db)) doesn't need touching elsewhere in
    this same commit — this file no longer uses a blob 'db' parameter
    at all, every screen below fetches exactly the rows it needs
    directly from database.py."""
    st.markdown("<h1>Student Dashboard</h1>", unsafe_allow_html=True)

    # A student mid-attempt should land straight back on the test
    # screen even after a page reload — check this BEFORE rendering any
    # nav, so a refresh mid-test can't accidentally strand them on a
    # test list they have to re-navigate from.
    active = st.session_state.get("active_attempt_id")
    if active:
        attempt = get_attempt(active)
        if attempt and attempt["status"] == "in_progress":
            _render_test_taking_screen(attempt)
            return
        else:
            st.session_state.pop("active_attempt_id", None)

    page = render_nav(admin=False)
    render_roster()

    if page == "Tests":
        _render_test_list()
    elif page == "Daily":
        _render_daily_page()
    elif page == "Leaderboard":
        _render_leaderboard_picker()


# ============================================================
# TEST LIST
# ============================================================

def _render_test_list():
    st.subheader("Available Tests")
    try:
        tests = get_open_tests()
    except DatabaseUnavailableError:
        st.error("Lost connection to the database. Please try again in a moment.")
        return

    if not tests:
        st.caption("No tests are open right now — check back later.")
        return

    for test in tests:
        with st.container(border=True):
            st.markdown(f"**{html.escape(test['title'])}**")
            st.caption(
                f"{test['duration_minutes']} minutes · "
                f"+{test['marks_correct']:g} correct / {test['marks_wrong']:g} wrong"
            )
            if st.button("Begin Test", key=f"begin_{test['id']}", type="primary"):
                _begin_or_resume(test["id"])


def _begin_or_resume(test_id: int):
    username = st.session_state.username
    try:
        attempt_id = start_or_resume_attempt(test_id, username)
    except DatabaseUnavailableError:
        st.error("Couldn't reach the database — please try again.")
        return
    st.session_state.active_attempt_id = attempt_id
    st.rerun()


# ============================================================
# TEST-TAKING SCREEN
# ============================================================

def _render_test_taking_screen(attempt: dict):
    test = get_test(attempt["test_id"])
    if not test:
        st.error("This test no longer exists.")
        st.session_state.pop("active_attempt_id", None)
        return

    questions = get_test_questions(test["id"])
    if not questions:
        st.warning("This test has no questions yet.")
        return

    # THE WATCHDOG — see its own docstring for the full explanation of
    # why it's isolated like this. Placed first so an already-expired
    # attempt gets caught and finalized before rendering anything else
    # below it.
    _timer_watchdog_fragment(attempt["id"], test)

    # Re-fetch AFTER the watchdog — if it just auto-submitted (status
    # flipped to 'expired'), this render should show the results screen
    # instead of a now-stale question screen underneath it.
    attempt = get_attempt(attempt["id"])
    if attempt["status"] != "in_progress":
        _render_results_screen(attempt, test, questions)
        return

    answers = get_attempt_answers(attempt["id"])
    current_qid = attempt.get("current_question_id") or questions[0]["id"]
    current_q = next((q for q in questions if q["id"] == current_qid), questions[0])

    subjects = list(dict.fromkeys(q["subject"] for q in questions))  # first-seen order, de-duplicated

    _render_countdown_display(attempt, test)

    # Subject tabs — only shown when a test actually has more than one
    # subject, same reasoning as the Telegram bot: a single-subject (or
    # un-tagged 'General') test has nothing to switch between, so
    # showing a one-item tab row would just be noise.
    if len(subjects) > 1:
        _render_subject_tabs(attempt, subjects, current_q)

    st.divider()

    section_qs = [q for q in questions if q["subject"] == current_q["subject"]]
    col_main, col_palette = st.columns([2.2, 1])
    with col_main:
        _render_question_panel(attempt, test, current_q, section_qs, answers, all_questions=questions)
    with col_palette:
        _render_palette(attempt, section_qs, answers, current_q)


def _render_subject_tabs(attempt, subjects, current_q):
    """One button per subject; clicking a subject that isn't the
    current one jumps straight to that subject's FIRST question — same
    'click Physics, land on Physics Q1' behavior as the Telegram bot's
    subject tabs, rather than just relabeling something while leaving
    the student stranded on whatever question they were on."""
    from database import get_test_questions
    cols = st.columns(len(subjects))
    for i, subj in enumerate(subjects):
        with cols[i]:
            is_current = subj == current_q["subject"]
            if st.button(subj, key=f"subjtab_{attempt['id']}_{subj}", type=("primary" if is_current else "secondary"), use_container_width=True):
                if not is_current:
                    all_qs = get_test_questions(attempt["test_id"])
                    first_q = next(q for q in all_qs if q["subject"] == subj)
                    set_current_question(attempt["id"], first_q["id"])
                    st.rerun()


def _render_countdown_display(attempt: dict, test: dict):
    """Purely visual client-side ticking clock — zero server calls per
    second, so this costs nothing under load no matter how many
    students have it open simultaneously. Computes its own remaining
    time locally from a fixed deadline timestamp sent once at render
    time; does NOT and cannot enforce anything by itself (see this
    file's module docstring) — _timer_watchdog_fragment is what
    actually enforces expiry. If this clock and the watchdog ever
    disagree by a second or two, the watchdog's server-computed time is
    always the one that's actually authoritative."""
    started = attempt["started_at"]
    deadline_js = f"new Date('{started}').getTime() + {test['duration_minutes']} * 60000"
    components.html(
        f"""
        <div id="exam-clock" style="font-family:'JetBrains Mono',monospace;font-size:1.6rem;
             font-weight:700;color:#e7eaf0;padding:10px 0;">--:--:--</div>
        <script>
        const deadline = {deadline_js};
        function tick() {{
            const remaining = Math.max(0, deadline - Date.now());
            const h = Math.floor(remaining / 3600000);
            const m = Math.floor((remaining % 3600000) / 60000);
            const s = Math.floor((remaining % 60000) / 1000);
            const el = document.getElementById('exam-clock');
            if (el) {{
                el.textContent = String(h).padStart(2,'0') + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
                el.style.color = remaining < 60000 ? '#f5a623' : '#e7eaf0';
            }}
        }}
        tick();
        setInterval(tick, 1000);
        </script>
        """,
        height=50,
    )


def _timer_watchdog_fragment(attempt_id: int, test: dict):
    """THE actual enforcement mechanism for 'submit automatically when
    time's up' — see this file's module docstring for the full
    reasoning. Rebuilt fresh (not decorated at module level) each call
    so it can close over attempt_id/test without needing them threaded
    through session state.

    DELIBERATELY CONTAINS NO INTERACTIVE WIDGETS. A plain st.button
    placed inside a run_every fragment is known to sometimes fail to
    register clicks — every real button on this screen (answers,
    Next/Prev, palette, Submit) lives OUTSIDE this fragment in the
    normal page body, completely unaffected by this fragment's
    independent 5s rerun cycle. Do not add a button in here.

    5s interval: frequent enough that auto-submit feels prompt relative
    to a 1-3hr test, infrequent enough that even 30 concurrent students
    each polling this is a trivial number of read-only Supabase calls —
    a READ (recomputing elapsed time), never a write, so there's no
    contention risk here at all, unlike the old blob-write pattern."""
    @st.fragment(run_every=5)
    def _watchdog():
        attempt = get_attempt(attempt_id)
        if not attempt or attempt["status"] != "in_progress":
            return  # already finalized by a manual submit — nothing to do
        elapsed = time.time() - _parse_ts(attempt["started_at"])
        remaining = test["duration_minutes"] * 60 - elapsed
        if remaining <= 0:
            finalize_attempt(attempt_id, expired=True)
            st.rerun()  # whole-app rerun from inside a fragment — supported
    _watchdog()


def _parse_ts(ts) -> float:
    """Supabase returns timestamptz as an ISO string; accepts either
    that or an already-numeric value defensively, since exactly which
    shape comes back can depend on the client version."""
    if isinstance(ts, (int, float)):
        return ts
    import datetime
    # Supabase ISO strings look like 2026-07-25T10:00:00+00:00 or with
    # a trailing Z — normalize Z to +00:00 for fromisoformat.
    return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()


def _render_question_panel(attempt, test, current_q, section_qs, answers, all_questions):
    """section_qs: only the CURRENT SUBJECT's questions (for Next/Prev/
    numbering within this subject). all_questions: every question in
    the whole test, regardless of subject (for the Submit confirmation's
    totals — those must reflect the ENTIRE test, not just whichever
    subject the student happens to be looking at right now)."""
    q_number = next((i for i, q in enumerate(section_qs, start=1) if q["id"] == current_q["id"]), 1)

    st.markdown(f"**Question {q_number} of {len(section_qs)}**")
    st.markdown(html.escape(current_q["question"]))

    entry = answers.get(current_q["id"])
    current_selection = entry["selected_option"] if entry and not entry["is_skipped"] else None

    options = current_q["options"]
    selected = st.radio(
        "options", options, index=options.index(current_selection) if current_selection in options else None,
        key=f"radio_{attempt['id']}_{current_q['id']}", label_visibility="collapsed",
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Skip", key=f"skip_{current_q['id']}", use_container_width=True):
            submit_answer(attempt["id"], current_q["id"], None, True)
            _go_to_relative(attempt, section_qs, current_q, +1)
    with col_b:
        if st.button("◀ Previous", key=f"prev_{current_q['id']}", use_container_width=True, disabled=(q_number == 1)):
            _go_to_relative(attempt, section_qs, current_q, -1)
    with col_c:
        label = "Save & Next ▶" if q_number < len(section_qs) else "Save"
        if st.button(label, key=f"next_{current_q['id']}", type="primary", use_container_width=True):
            if selected is not None:
                submit_answer(attempt["id"], current_q["id"], selected, False)
            if q_number < len(section_qs):
                _go_to_relative(attempt, section_qs, current_q, +1)
            else:
                st.rerun()

    st.divider()
    if st.button("Submit Test", type="primary", use_container_width=True):
        st.session_state[f"confirm_submit_{attempt['id']}"] = True

    if st.session_state.get(f"confirm_submit_{attempt['id']}"):
        # Deliberately counts against all_questions/answers (the WHOLE
        # test), not section_qs — a student sitting on the Chemistry tab
        # needs to see how much of the ENTIRE test they've answered
        # before submitting, not just Chemistry's count, or this would
        # understate their progress on every subject but the one
        # they're currently viewing.
        answered = len([a for a in answers.values() if not a["is_skipped"] and a["selected_option"]])
        st.warning(f"You've answered {answered} of {len(all_questions)} questions across the whole test. Submit now?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Yes, submit final answer", type="primary", key=f"confirm_yes_{attempt['id']}"):
                finalize_attempt(attempt["id"], expired=False)
                st.session_state.pop(f"confirm_submit_{attempt['id']}", None)
                st.rerun()
        with c2:
            if st.button("Go back", key=f"confirm_no_{attempt['id']}"):
                st.session_state.pop(f"confirm_submit_{attempt['id']}", None)
                st.rerun()


def _go_to_relative(attempt, section_qs, current_q, direction):
    idx = next((i for i, q in enumerate(section_qs) if q["id"] == current_q["id"]), 0)
    new_idx = max(0, min(len(section_qs) - 1, idx + direction))
    new_q = section_qs[new_idx]
    set_current_question(attempt["id"], new_q["id"])
    st.rerun()


def _render_palette(attempt, questions, answers, current_q):
    st.markdown("**Question Palette**")
    st.caption("🟩 Answered · 🟧 Current · ⬜ Unanswered/Skipped")

    # st.button has no native color parameter (only 'primary'/
    # 'secondary'/'tertiary'), so true green/red/grey palette buttons —
    # matching the reference image — need direct CSS. Every keyed
    # widget gets a `.st-key-<key>` class automatically (confirmed
    # Streamlit behavior), so each button below is individually
    # targetable by its own unique key. Built fresh every render
    # (rather than static styles.py CSS) since which questions are
    # answered changes attempt-to-attempt and question-to-question.
    css_rules = []
    for q in questions:
        key = f"pal_{attempt['id']}_{q['id']}"
        entry = answers.get(q["id"])
        is_current = q["id"] == current_q["id"]
        is_answered = entry and not entry["is_skipped"] and entry["selected_option"]
        if is_current:
            bg, border, color = "#f5a623", "#f5a623", "#1a1206"
        elif is_answered:
            bg, border, color = "#22c55e", "#22c55e", "#0d1f16"
        else:
            bg, border, color = "transparent", "rgba(231,234,240,0.24)", "#9aa4b6"
        css_rules.append(
            f".st-key-{key} button {{ background-color: {bg} !important; "
            f"border-color: {border} !important; color: {color} !important; }}"
        )
    st.markdown(f"<style>{''.join(css_rules)}</style>", unsafe_allow_html=True)

    cols_per_row = 5
    rows = [questions[i:i + cols_per_row] for i in range(0, len(questions), cols_per_row)]
    for row in rows:
        cols = st.columns(cols_per_row)
        for i, q in enumerate(row):
            with cols[i]:
                q_pos = questions.index(q) + 1
                if st.button(str(q_pos), key=f"pal_{attempt['id']}_{q['id']}", use_container_width=True):
                    set_current_question(attempt["id"], q["id"])
                    st.rerun()


# ============================================================
# RESULTS SCREEN (shown after submit/expiry — never live)
# ============================================================

def _render_results_screen(attempt, test, questions):
    st.success("Test submitted." if attempt["status"] == "submitted" else "Time's up — auto-submitted.")
    st.markdown(f"### {html.escape(test['title'])}")

    max_score = len(questions) * test["marks_correct"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score", f"{attempt['score']:g} / {max_score:g}")
    c2.metric("Correct", attempt["correct_count"])
    c3.metric("Wrong", attempt["wrong_count"])
    c4.metric("Unanswered", attempt["unanswered_count"])

    if st.button("Review Answers"):
        st.session_state[f"reviewing_{attempt['id']}"] = True

    if st.session_state.get(f"reviewing_{attempt['id']}"):
        _render_review(attempt, questions)

    if st.button("Back to Test List"):
        st.session_state.pop("active_attempt_id", None)
        st.session_state.pop(f"reviewing_{attempt['id']}", None)
        st.rerun()


def _render_review(attempt, questions):
    answers = get_attempt_answers(attempt["id"])
    last_subject = None
    subject_counter = 0
    for q in questions:
        if q["subject"] != last_subject:
            st.markdown(f"#### {html.escape(q['subject'])}")
            last_subject = q["subject"]
            subject_counter = 0
        subject_counter += 1

        entry = answers.get(q["id"])
        selected = entry["selected_option"] if entry and not entry["is_skipped"] else None
        is_correct = selected == q["correct_answer"]
        with st.container(border=True):
            if selected is None:
                status, color = "Unanswered", "#9aa4b6"
            elif is_correct:
                status, color = "Correct", "#22c55e"
            else:
                status, color = "Incorrect", "#ef4444"
            st.markdown(f"**Q{subject_counter}.** {html.escape(q['question'])}")
            st.markdown(f"<span style='color:{color};font-weight:600;'>{status}</span>", unsafe_allow_html=True)
            for opt in q["options"]:
                marker = ""
                if opt == q["correct_answer"]:
                    marker = " ✓ (correct answer)"
                elif opt == selected:
                    marker = " ✗ (your answer)"
                st.markdown(f"- {html.escape(opt)}{marker}")
            if q.get("explanation"):
                st.caption(f"Explanation: {html.escape(q['explanation'])}")


# ============================================================
# LEADERBOARD (student view — read-only)
# ============================================================

def _render_leaderboard_picker():
    st.subheader("Leaderboards")
    try:
        tests = get_open_tests()
    except DatabaseUnavailableError:
        st.error("Lost connection to the database.")
        return
    if not tests:
        st.caption("No tests available yet.")
        return
    titles = {t["id"]: t["title"] for t in tests}
    test_id = st.selectbox("Select a test", list(titles.keys()), format_func=lambda i: titles[i])
    if test_id:
        board = get_test_leaderboard(test_id, limit=10)
        if not board:
            st.caption("No scored attempts yet.")
            return
        for i, row in enumerate(board, start=1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            st.markdown(f"{medal} **{html.escape(row['username'])}** — {row['score']:g} pts")


# ============================================================
# DAILY SET + PERSONAL TARGET (student view)
# ============================================================

def _render_daily_page():
    st.subheader("Today's Daily Set")
    try:
        daily = get_todays_daily_set()
    except DatabaseUnavailableError:
        st.error("Lost connection to the database.")
        return

    if not daily:
        st.caption("Nothing posted yet today — check back later.")
    else:
        username = st.session_state.username
        try:
            already_attempted = get_active_attempt(daily["id"], username)
        except DatabaseUnavailableError:
            already_attempted = None
        with st.container(border=True):
            st.markdown(f"**{html.escape(daily['title'])}**")
            st.caption(f"{daily['duration_minutes']} minutes · +{daily['marks_correct']:g} correct / {daily['marks_wrong']:g} wrong")
            label = "Resume" if already_attempted else "Begin Today's Set"
            if st.button(label, type="primary", key="begin_daily"):
                _begin_or_resume(daily["id"])
        with st.expander("Today's leaderboard"):
            board = get_test_leaderboard(daily["id"], limit=10)
            if not board:
                st.caption("No scored attempts yet.")
            for i, row in enumerate(board, start=1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                st.markdown(f"{medal} **{html.escape(row['username'])}** — {row['score']:g} pts")

    st.divider()
    st.subheader("Your Target for Today")
    st.caption("A personal goal you set yourself — not graded, just for accountability and a bit of friendly competition.")

    username = st.session_state.username
    try:
        my_target = get_my_todays_target(username)
    except DatabaseUnavailableError:
        my_target = None

    with st.container(border=True):
        goal_text = st.text_input(
            "Today's goal", value=my_target["goal_text"] if my_target else "",
            placeholder="e.g. 8/10 on today's set, or 50 questions from my book",
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Save Goal", use_container_width=True):
                if goal_text.strip():
                    set_daily_target(username, goal_text.strip(), linked_test_id=daily["id"] if daily else None)
                    st.rerun()
        with col_b:
            already_done = my_target["is_complete"] if my_target else False
            if st.button("✅ Mark Complete" if not already_done else "✅ Completed", disabled=already_done, use_container_width=True):
                mark_my_target_complete(username)
                st.rerun()

    st.divider()
    st.subheader("Today's Targets — Everyone")
    try:
        feed = get_todays_target_feed()
    except DatabaseUnavailableError:
        st.error("Lost connection to the database.")
        return
    if not feed:
        st.caption("No targets set yet today — be the first.")
        return
    for row in feed:
        icon = "✅" if row["is_complete"] else "⏳"
        st.markdown(f"{icon} **{html.escape(row['username'])}** — {html.escape(row['goal_text'])}")
