"""
student_dashboard.py
The student console: live quiz (read-only + answer submission), full-length
timed test / DPP taking (with unlimited reattempts), and the leaderboard.

CRITICAL - READ BEFORE ADDING ANY QUIZ-STATE CODE HERE:
This file must be STRICTLY READ-ONLY with respect to shared quiz_state.
The only quiz.py functions this file may call are:
    - submit_answer(db, username, choice)       - writes ONLY the caller's
      own answer, never touches anyone else's state
    - start_full_test_attempt / sync_full_test_progress / submit_full_test -
      all scoped to the caller's OWN submission record inside
      test["submissions"][username], never anyone else's

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

ANSWER-SAVE BATCHING (load protection): while a student is working through
a test/DPP, their in-progress answers/marks live in st.session_state and
are only flushed to the database (sync_full_test_progress) when they move
to another question, toggle a mark, or submit - not on every single radio
click. This is the main defense against database load from a full class
answering concurrently; see sync_full_test_progress's docstring in quiz.py.
"""

import time
import html as html_lib
import streamlit as st

from quiz import (
    submit_answer, time_left, is_time_up, render_leaderboard,
    start_full_test_attempt, sync_full_test_progress,
    submit_full_test, full_test_time_left,
    render_full_test_leaderboard,
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
# FULL-LENGTH TIMED TESTS + DPPs - the professional exam-taking experience
# ========================================================================
# EVERY test and DPP ever created stays here permanently - nothing is ever
# deleted. A student can revisit any of them at any time and retake as
# many times as they want; only their single best-scoring attempt counts
# for the leaderboard and is shown as "Your best score" below.

def _render_tests_page(db, username):
    all_tests = db.get("full_tests", {})

    # If the student already has an attempt in progress on anything that's
    # still open, jump straight into it - avoids losing their place in a
    # long exam to a stray rerun.
    for test_id, test in all_tests.items():
        if test["status"] != "open":
            continue
        sub = test["submissions"].get(username)
        if sub is not None and sub.get("submitted_at") is None:
            _render_test_taking_ui(db, test_id, test, username)
            return

    type_choice = st.radio("Show", ["Tests", "DPPs"], horizontal=True, key="student_test_type_filter")
    wanted_type = "test" if type_choice == "Tests" else "dpp"
    tests = {tid: t for tid, t in all_tests.items() if t.get("test_type", "test") == wanted_type}

    open_tests = {tid: t for tid, t in tests.items() if t["status"] == "open"}
    closed_tests = {tid: t for tid, t in tests.items() if t["status"] == "closed"}
    noun = "test" if wanted_type == "test" else "DPP"

    st.subheader(f"Available {type_choice}")
    if not open_tests:
        st.caption(f"No {noun}s are open right now. Check back once your instructor opens one.")
    for test_id, test in open_tests.items():
        _render_available_card(db, test_id, test, username, wanted_type)

    if closed_tests:
        st.divider()
        st.subheader(f"Past {type_choice}")
        st.caption("Nothing here ever disappears — revisit and retake any of these whenever you like.")
        for test_id, test in sorted(closed_tests.items(), key=lambda kv: kv[1]["created_at"], reverse=True):
            _render_past_card(db, test_id, test, username, wanted_type)


def _render_available_card(db, test_id, test, username, wanted_type):
    sub = test["submissions"].get(username)
    best = sub.get("best") if sub else None
    with st.container(border=True):
        if wanted_type == "test":
            remaining = full_test_time_left(db, test_id)
            mins = int(remaining // 60) if remaining is not None else test["duration_minutes"]
            st.markdown(f"**{test['title']}**")
            st.caption(f"{len(test['questions'])} questions - {test['duration_minutes']} minutes - +{test['marks_correct']} / {test['marks_wrong']} marking")
            if remaining is not None and remaining <= 0:
                st.caption("This test's time window has ended, but it stays available under Past Tests to review and retake.")
                return
            st.caption(f"~{mins} min left on the shared clock.")
        else:
            st.markdown(f"**{test['title']}**")
            st.caption(f"{len(test['questions'])} questions - untimed - +{test['marks_correct']} / {test['marks_wrong']} marking")

        if best is not None:
            st.caption(f"Your best score so far: **{best['score']}** ({sub.get('attempt_count', 0)} attempt(s))")

        button_label = "Retake" if best is not None else "Start"
        if st.button(f"{button_label} {'Test' if wanted_type == 'test' else 'DPP'}", key=f"start_{test_id}", type="primary"):
            start_full_test_attempt(db, test_id, username)
            st.rerun()


def _render_past_card(db, test_id, test, username, wanted_type):
    sub = test["submissions"].get(username)
    best = sub.get("best") if sub else None
    with st.container(border=True):
        st.markdown(f"**{test['title']}**")
        if best is not None:
            st.write(
                f"Your best score: **{best['score']}** - Correct: {best['correct_count']} - "
                f"Wrong: {best['wrong_count']} - Unattempted: {best['unattempted_count']} "
                f"- ({sub.get('attempt_count', 0)} attempt(s))"
            )
            with st.expander("Review your best attempt"):
                _render_test_review(test, best)
            with st.expander("Leaderboard"):
                render_full_test_leaderboard(test, highlight_user=username)
        else:
            st.caption("You haven't attempted this one yet.")

        if st.button(f"{'Retake' if best is not None else 'Attempt'} anytime", key=f"retake_closed_{test_id}"):
            start_full_test_attempt(db, test_id, username)
            st.rerun()


def _render_test_review(test, best):
    for i, q in enumerate(test["questions"]):
        chosen = best["answers"].get(str(i))
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


def _get_working_copy(sub, test_id):
    """Local (session_state) working copy of this attempt's answers/marks.
    Every click updates ONLY this in-memory copy; sync_full_test_progress
    flushes it to the database at natural checkpoints (Next/Previous/
    Mark/Submit) instead of on every single radio click - see the module
    docstring for why this matters under classroom-scale concurrent load."""
    key = f"working_{test_id}"
    if key not in st.session_state:
        st.session_state[key] = {
            "answers": dict(sub["answers"]),
            "marked_for_review": list(sub.get("marked_for_review", [])),
        }
    return st.session_state[key]


def _flush_working_copy(db, test_id, username):
    working = st.session_state.get(f"working_{test_id}")
    if working is not None:
        sync_full_test_progress(db, test_id, username, working["answers"], working["marked_for_review"])


def _render_test_taking_ui(db, test_id, test, username):
    """The signature exam experience: sticky top bar (with a shared
    countdown for timed Tests, or a plain "untimed" label for DPPs and any
    test being retaken after its live window closed) + live
    answered/marked/unattempted counts, a question palette to jump
    anywhere, and free navigation with no per-question timer - matches how
    a real full-length proctored exam actually works, unlike the live quiz
    below which is deliberately lockstep/synchronous."""
    sub = test["submissions"][username]
    questions = test["questions"]
    total = len(questions)
    is_untimed = test.get("test_type") == "dpp" or test["status"] != "open"

    remaining = full_test_time_left(db, test_id)
    if remaining is not None and remaining <= 0:
        _flush_working_copy(db, test_id, username)
        submit_full_test(db, test_id, username)
        st.session_state.pop(f"working_{test_id}", None)
        st.warning("Time's up - your attempt has been auto-submitted.")
        time.sleep(1.5)
        st.rerun()
        return

    working = _get_working_copy(sub, test_id)

    if f"qidx_{test_id}" not in st.session_state:
        st.session_state[f"qidx_{test_id}"] = 0
    current_idx = st.session_state[f"qidx_{test_id}"]

    answered_count = len(working["answers"])
    marked_count = len(working["marked_for_review"])
    unattempted_count = total - answered_count

    if remaining is not None:
        mins, secs = int(remaining // 60), int(remaining % 60)
        urgent = remaining <= 300  # last 5 minutes
        clock_class = "exam-bar-clock urgent" if urgent else "exam-bar-clock"
        clock_html = f'<div class="{clock_class}">{mins:02d}:{secs:02d}</div>'
    else:
        clock_html = '<div class="exam-bar-clock">Untimed</div>'

    st.markdown(
        f"""
        <div class="exam-bar">
            <div class="exam-bar-title">{html_lib.escape(test['title'])}</div>
            {clock_html}
            <div class="exam-bar-stats">
                <div class="exam-stat answered"><div class="n">{answered_count}</div><div class="l">Answered</div></div>
                <div class="exam-stat marked"><div class="n">{marked_count}</div><div class="l">Marked</div></div>
                <div class="exam-stat unattempted"><div class="n">{unattempted_count}</div><div class="l">Remaining</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if is_untimed and test.get("test_type") != "dpp":
        st.caption("This test's live window has ended, but you're free to practice it now — self-paced, no clock, doesn't affect anyone else's result.")

    col_main, col_palette = st.columns([3, 1])

    with col_main:
        q = questions[current_idx]
        st.caption(f"Question {current_idx + 1} of {total}")
        st.markdown(f"### {html_lib.escape(q['question'])}")

        existing_answer = working["answers"].get(str(current_idx))
        choice = st.radio(
            "Choose an answer",
            q["options"],
            index=q["options"].index(existing_answer) if existing_answer in q["options"] else None,
            key=f"choice_{test_id}_{current_idx}",
            label_visibility="collapsed",
        )
        if choice is not None and choice != existing_answer:
            working["answers"][str(current_idx)] = choice  # local only - flushed on navigation below

        # Periodic autosave: even if the student never clicks Next/Mark on
        # this question (e.g. they pick an answer and then just sit on
        # this screen), the app's existing autorefresh tick (every few
        # seconds) still reruns this page - use that to flush at most once
        # every ~20s per test, so a closed tab or dead connection never
        # loses more than a few seconds of an answer that was already picked.
        autosave_key = f"last_autosave_{test_id}"
        now = time.time()
        if now - st.session_state.get(autosave_key, 0) > 20:
            _flush_working_copy(db, test_id, username)
            st.session_state[autosave_key] = now

        st.write("")
        col_prev, col_mark, col_clear, col_next = st.columns(4)
        with col_prev:
            if st.button("Previous", disabled=current_idx == 0, use_container_width=True):
                _flush_working_copy(db, test_id, username)
                st.session_state[f"qidx_{test_id}"] = max(0, current_idx - 1)
                st.rerun()
        with col_mark:
            is_marked = current_idx in working["marked_for_review"]
            if st.button("Unmark" if is_marked else "Mark for Review", use_container_width=True):
                if is_marked:
                    working["marked_for_review"].remove(current_idx)
                else:
                    working["marked_for_review"].append(current_idx)
                _flush_working_copy(db, test_id, username)
                st.rerun()
        with col_clear:
            if st.button("Clear Answer", use_container_width=True, disabled=existing_answer is None):
                working["answers"].pop(str(current_idx), None)
                _flush_working_copy(db, test_id, username)
                st.rerun()
        with col_next:
            if st.button("Next", disabled=current_idx >= total - 1, use_container_width=True, type="primary"):
                _flush_working_copy(db, test_id, username)
                st.session_state[f"qidx_{test_id}"] = min(total - 1, current_idx + 1)
                st.rerun()

        st.divider()
        if st.button("Submit", type="primary", use_container_width=True):
            _flush_working_copy(db, test_id, username)
            st.session_state[f"confirm_submit_{test_id}"] = True

        if st.session_state.get(f"confirm_submit_{test_id}"):
            st.warning(f"You've answered {answered_count} of {total} questions. Submit anyway?")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, Submit Now", type="primary", use_container_width=True):
                    _flush_working_copy(db, test_id, username)
                    submit_full_test(db, test_id, username)
                    st.session_state.pop(f"confirm_submit_{test_id}", None)
                    st.session_state.pop(f"working_{test_id}", None)
                    st.session_state.pop(f"qidx_{test_id}", None)
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
                is_answered = str(idx) in working["answers"]
                is_marked = idx in working["marked_for_review"]
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
                        _flush_working_copy(db, test_id, username)
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
