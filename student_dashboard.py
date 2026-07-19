"""
student_dashboard.py
The student console: live quiz (read-only + answer submission), full-length
timed test taking, and the leaderboard.

CRITICAL - READ BEFORE ADDING ANY QUIZ-STATE CODE HERE:
This file must be STRICTLY READ-ONLY with respect to shared quiz_state.
The only quiz.py functions this file may call are:
    - submit_answer(db, username, choice)       - writes ONLY the caller's
      own answer, never touches anyone else's state
    - start_full_test_attempt / save_full_test_answer / toggle_mark_for_review
      / submit_full_test - all scoped to the caller's OWN submission record
      inside test["submissions"][username], never anyone else's

This file must NEVER call advance_auto_quiz, lock_and_reveal, start_quiz,
start_auto_quiz, start_bank_quiz, clear_quiz, create_full_test,
open_full_test, or close_full_test. Every one of those is admin_dashboard.py's
job, and ONLY admin_dashboard.py's job.

WHY THIS MATTERS: the previous version of this app had student_dashboard.py
independently calling advance_auto_quiz() on every connected student's own
autorefresh tick. With N students connected, that meant N browsers
simultaneously generating "the next question" (2-6 blocking AI calls each)
and overwriting each other's writes to the database - that's what crashed
the app at question 2 with just 6 users. See quiz.py's module docstring
for the complete explanation. Keeping this file read-only for shared state
is not a style preference, it's the actual fix for that bug.
"""

import time
import html as html_lib
import streamlit as st

from quiz import (
    submit_answer, time_left, is_time_up, render_leaderboard,
    start_full_test_attempt, save_full_test_answer, toggle_mark_for_review,
    submit_full_test, full_test_time_left, render_full_test_leaderboard,
)
from sidebar import render_nav, render_roster


def render_student_dashboard(db):
    username = st.session_state.username
    st.markdown("<h1>Dashboard</h1>", unsafe_allow_html=True)
    page = render_nav(admin=False)
    render_roster(db)

    if page == "Tests":
        _render_tests_page(db, username)
    elif page == "Practice":
        _render_live_quiz_view(db, username)
    elif page == "Leaderboard":
        _render_leaderboard_page(db, username)


# ========================================================================
# FULL-LENGTH TIMED TESTS - the professional exam-taking experience
# ========================================================================

def _render_tests_page(db, username):
    from quiz import get_active_attempt, get_past_attempts

    tests = db.get("full_tests", {})
    open_tests = {tid: t for tid, t in tests.items() if t["status"] == "open"}
    closed_tests = {tid: t for tid, t in tests.items() if t["status"] == "closed"}

    # If the student has ANY in-progress attempt right now (live test or a
    # self-paced retake of a closed one), jump straight into it - avoids
    # accidentally losing their place in a long exam to a stray rerun.
    for test_id, test in tests.items():
        if get_active_attempt(test, username) is not None:
            _render_test_taking_ui(db, test_id, test, username)
            return

    st.subheader("Available Tests")
    if not open_tests:
        st.caption("No tests are open right now. Check back once your instructor opens one, or practice a past test below.")
    for test_id, test in open_tests.items():
        with st.container(border=True):
            remaining = full_test_time_left(db, test_id)
            mins = int(remaining // 60) if remaining is not None else test["duration_minutes"]
            st.markdown(f"**{test['title']}**")
            st.caption(f"{len(test['questions'])} questions - {test['duration_minutes']} minutes - +{test['marks_correct']} / {test['marks_wrong']} marking")
            if remaining is not None and remaining <= 0:
                st.caption("This test's live window has ended — see it under Past Tests below to practice it anytime.")
                continue
            st.caption(f"~{mins} min left on the shared clock.")
            if st.button("Start Test", key=f"start_{test_id}", type="primary"):
                start_full_test_attempt(db, test_id, username)
                st.rerun()

    if closed_tests:
        st.divider()
        st.subheader("Past Tests")
        st.caption("These are permanently available — retake any of them as many times as you like for extra practice.")
        for test_id, test in closed_tests.items():
            past_attempts = get_past_attempts(test, username)
            with st.container(border=True):
                st.markdown(f"**{test['title']}**")
                if past_attempts:
                    best = max(past_attempts, key=lambda a: a["score"])
                    st.write(
                        f"Best score: **{best['score']}** over {len(past_attempts)} attempt(s) - "
                        f"Correct: {best['correct_count']} - Wrong: {best['wrong_count']} - Unattempted: {best['unattempted_count']}"
                    )
                    with st.expander(f"Review attempt history ({len(past_attempts)})"):
                        for i, attempt in enumerate(past_attempts):
                            attempt_num = len(past_attempts) - i
                            st.markdown(f"**Attempt {attempt_num}** — score {attempt['score']}")
                            _render_test_review(test, attempt)
                            st.divider()
                    with st.expander("Leaderboard for this test"):
                        render_full_test_leaderboard(test, highlight_user=username)
                else:
                    st.caption("You haven't attempted this test yet.")
                if st.button("Retake as Practice" if past_attempts else "Attempt This Test", key=f"retake_{test_id}"):
                    start_full_test_attempt(db, test_id, username)
                    st.rerun()


def _render_test_review(test, sub):
    for i, q in enumerate(test["questions"]):
        chosen = sub["answers"].get(str(i))
        correct = q["answer"]
        st.markdown(f"**Q{i + 1}.** {q['question']}")
        for opt in q["options"]:
            if opt == correct and opt == chosen:
                st.markdown(f"[correct - your answer] {opt}")
            elif opt == correct:
                st.markdown(f"[correct answer] {opt}")
            elif opt == chosen:
                st.markdown(f"[your answer - wrong] {opt}")
            else:
                st.markdown(f"{opt}")
        st.caption(q.get("explanation", ""))
        st.divider()


def _render_test_taking_ui(db, test_id, test, username):
    """The signature exam experience: sticky top bar with countdown + live
    answered/marked/unattempted counts, a question palette to jump
    anywhere, and free navigation with no per-question timer - matches how
    a real full-length proctored exam actually works, unlike the live quiz
    below which is deliberately lockstep/synchronous.

    Works identically whether this is an official live-window attempt OR
    a self-paced retake of a closed test - full_test_time_left is passed
    THIS ATTEMPT's own started_at, so a retake always gets its own fresh
    full-duration clock rather than being tied to (or blocked by) whatever
    the original live window's clock was doing."""
    from quiz import get_active_attempt

    sub = get_active_attempt(test, username)
    questions = test["questions"]
    total = len(questions)

    remaining = full_test_time_left(db, test_id, started_at=sub["started_at"])
    if remaining is not None and remaining <= 0:
        submit_full_test(db, test_id, username)
        st.warning("Time's up - your test has been auto-submitted.")
        time.sleep(1.5)
        st.rerun()
        return

    if f"qidx_{test_id}" not in st.session_state:
        st.session_state[f"qidx_{test_id}"] = 0
    current_idx = st.session_state[f"qidx_{test_id}"]

    answered_count = len(sub["answers"])
    marked_count = len(sub.get("marked_for_review", []))
    unattempted_count = total - answered_count

    mins, secs = int(remaining // 60), int(remaining % 60)
    urgent = remaining <= 300  # last 5 minutes
    clock_class = "exam-bar-clock urgent" if urgent else "exam-bar-clock"

    st.markdown(
        f"""
        <div class="exam-bar">
            <div class="exam-bar-title">{html_lib.escape(test['title'])}</div>
            <div class="{clock_class}">{mins:02d}:{secs:02d}</div>
            <div class="exam-bar-stats">
                <div class="exam-stat answered"><div class="n">{answered_count}</div><div class="l">Answered</div></div>
                <div class="exam-stat marked"><div class="n">{marked_count}</div><div class="l">Marked</div></div>
                <div class="exam-stat unattempted"><div class="n">{unattempted_count}</div><div class="l">Remaining</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_main, col_palette = st.columns([3, 1])

    with col_main:
        q = questions[current_idx]
        st.caption(f"Question {current_idx + 1} of {total}")
        st.markdown(f"### {html_lib.escape(q['question'])}")

        existing_answer = sub["answers"].get(str(current_idx))
        choice = st.radio(
            "Choose an answer",
            q["options"],
            index=q["options"].index(existing_answer) if existing_answer in q["options"] else None,
            key=f"choice_{test_id}_{current_idx}",
            label_visibility="collapsed",
        )
        if choice is not None and choice != existing_answer:
            save_full_test_answer(db, test_id, username, current_idx, choice)

        st.write("")
        col_prev, col_mark, col_clear, col_next = st.columns(4)
        with col_prev:
            if st.button("Previous", disabled=current_idx == 0, use_container_width=True):
                st.session_state[f"qidx_{test_id}"] = max(0, current_idx - 1)
                st.rerun()
        with col_mark:
            is_marked = current_idx in sub.get("marked_for_review", [])
            if st.button("Unmark" if is_marked else "Mark for Review", use_container_width=True):
                toggle_mark_for_review(db, test_id, username, current_idx)
                st.rerun()
        with col_clear:
            if st.button("Clear Answer", use_container_width=True, disabled=existing_answer is None):
                save_full_test_answer(db, test_id, username, current_idx, None)
                st.rerun()
        with col_next:
            if st.button("Next", disabled=current_idx >= total - 1, use_container_width=True, type="primary"):
                st.session_state[f"qidx_{test_id}"] = min(total - 1, current_idx + 1)
                st.rerun()

        st.divider()
        if st.button("Submit Test", type="primary", use_container_width=True):
            st.session_state[f"confirm_submit_{test_id}"] = True

        if st.session_state.get(f"confirm_submit_{test_id}"):
            st.warning(f"You've answered {answered_count} of {total} questions. Submit anyway?")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, Submit Now", type="primary", use_container_width=True):
                    submit_full_test(db, test_id, username)
                    st.session_state.pop(f"confirm_submit_{test_id}", None)
                    st.rerun()
            with col_no:
                if st.button("Keep Working", use_container_width=True):
                    st.session_state.pop(f"confirm_submit_{test_id}", None)
                    st.rerun()

    with col_palette:
        st.caption("Question Palette")
        st.markdown('<div class="qpalette-btn-wrap">', unsafe_allow_html=True)
        cols_per_row = 5
        for row_start in range(0, total, cols_per_row):
            row_cols = st.columns(cols_per_row)
            for offset, col in enumerate(row_cols):
                idx = row_start + offset
                if idx >= total:
                    continue
                is_answered = str(idx) in sub["answers"]
                is_marked = idx in sub.get("marked_for_review", [])
                is_current = idx == current_idx
                if is_current:
                    label = f"[{idx + 1}]"
                elif is_marked:
                    label = f"*{idx + 1}"
                elif is_answered:
                    label = f"+{idx + 1}"
                else:
                    label = str(idx + 1)
                with col:
                    if st.button(label, key=f"pal_{test_id}_{idx}", use_container_width=True):
                        st.session_state[f"qidx_{test_id}"] = idx
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


# ========================================================================
# LIVE QUIZ - read-only view + answer submission only
# ========================================================================

def _render_live_quiz_view(db, username):
    st.subheader("Live Practice")

    if not db["quiz_state"]["active"]:
        st.caption("No live quiz running right now.")
        return

    qs = db["quiz_state"]
    q_data = qs["question_data"]

    badges_html = ""
    if qs.get("auto_mode"):
        badges_html += f"<div class='progress-badge'><div class='t-val'>{qs['current_index']}/{qs['total_questions']}</div><div class='t-lbl'>Question</div></div>"
    if qs.get("timer_seconds") and not qs["revealed"]:
        remaining = time_left(db)
        urgent = remaining is not None and remaining <= 10
        badge_class = "timer-badge urgent" if urgent else "timer-badge"
        badges_html += f"<div class='{badge_class}'><div class='t-val'>{int(remaining)}s</div><div class='t-lbl'>Remaining</div></div>"

    safe_question = html_lib.escape(str(q_data["question"]))
    st.markdown(
        f"<div class='quiz-header-row'><div class='quiz-heading'>{safe_question}</div>"
        f"<div class='quiz-badges'>{badges_html}</div></div>",
        unsafe_allow_html=True,
    )

    if not qs["revealed"]:
        already_answered = username in qs["answers"]
        time_up = qs.get("timer_seconds") and is_time_up(db)

        if already_answered:
            st.success(f"Answer submitted: {qs['answers'][username]}")
        elif time_up:
            st.warning("Time's up - waiting for the instructor to reveal the answer.")
        else:
            choice = st.radio("Your answer", q_data["options"], index=None, key=f"live_choice_{qs.get('current_index', 0)}")
            if choice is not None:
                if st.button("Submit Answer", type="primary"):
                    submit_answer(db, username, choice)
                    st.rerun()
    else:
        correct = qs["answers"].get(username) == q_data["answer"]
        box_class = "reveal-box" if correct else "reveal-box wrong"
        result_text = "Correct!" if correct else ("Incorrect" if username in qs["answers"] else "No answer submitted")
        st.markdown(
            f"<div class='{box_class}'><strong>{result_text}</strong><br/>"
            f"Correct answer: {html_lib.escape(q_data['answer'])}<br/>"
            f"<span style='color:var(--text-dim);font-size:0.9rem'>{html_lib.escape(q_data.get('explanation', ''))}</span></div>",
            unsafe_allow_html=True,
        )
        st.divider()
        render_leaderboard(db, highlight_user=username)


# ========================================================================
# LEADERBOARD
# ========================================================================

def _render_leaderboard_page(db, username):
    st.subheader("Leaderboard")
    render_leaderboard(db, highlight_user=username)
