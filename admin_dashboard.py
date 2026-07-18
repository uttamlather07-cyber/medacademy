"""
admin_dashboard.py
The admin console: live practice quizzes, full-length timed test builder,
and the leaderboard.

CRITICAL - READ BEFORE ADDING ANY QUIZ-STATE CODE HERE:
This file is the ONLY place allowed to call quiz.advance_auto_quiz(),
quiz.lock_and_reveal(), quiz.start_quiz(), quiz.start_auto_quiz(),
quiz.start_bank_quiz(), quiz.clear_quiz(), or any quiz.create_full_test /
open_full_test / close_full_test function. There is exactly ONE admin
session at a time (one person logged in as "admin"), so these functions
being admin-only means they can only ever be called by ONE browser - never
a race between multiple simultaneous callers.

student_dashboard.py must NEVER import or call any of the above. If you're
tempted to add a "the student's browser also checks and advances the quiz"
code path - don't. That exact pattern (every connected browser
independently calling advance_auto_quiz on its own autorefresh tick) is
what crashed the previous version of this app at question 2 with just 6
concurrent students: N browsers each blocking on 2-6 sequential AI calls
AND overwriting the database with their own version of "question 2",
simultaneously. See quiz.py's module docstring for the full explanation.
"""

import time
import html as html_lib
import streamlit as st

from database import save_db
from quiz import (
    generate_question, start_quiz, lock_and_reveal, clear_quiz,
    start_auto_quiz, advance_auto_quiz, time_left, is_time_up,
    parse_pasted_questions, start_bank_quiz, render_leaderboard,
    create_full_test, open_full_test, close_full_test, render_full_test_leaderboard,
)
from ai_providers import has_any_keys_configured, AllProvidersExhaustedError
from sidebar import render_nav, render_roster
from chapters import SUBJECTS, get_chapters
from config import DEFAULT_TEST_DURATION_MINUTES, DEFAULT_TEST_QUESTION_COUNT, DEFAULT_MARKS_CORRECT, DEFAULT_MARKS_WRONG, DIFFICULTY_LEVELS


def render_admin_dashboard(db):
    if not has_any_keys_configured():
        st.warning(
            "No AI provider keys are configured yet. Add GROQ_API_KEYS and/or GEMINI_API_KEYS "
            "to .streamlit/secrets.toml (a list of keys, or a single key string) to generate questions."
        )

    st.markdown("<h1>Admin Console</h1>", unsafe_allow_html=True)
    page = render_nav(admin=True)
    render_roster(db)

    if page == "Tests":
        _render_full_test_builder(db)
    elif page == "Live Quiz":
        _render_live_quiz_tab(db)
    elif page == "Leaderboard":
        _render_leaderboard_tab(db)


# ========================================================================
# FULL-LENGTH TIMED TESTS
# ========================================================================

def _render_full_test_builder(db):
    st.subheader("Full-Length Timed Tests")
    st.caption(
        "The complete question set is generated up front, before the test opens — nothing "
        "is generated live while students are attempting it, so a slow AI response can never "
        "block or time out anyone mid-exam."
    )

    tab_new, tab_manage = st.tabs(["Create a Test", "Manage Existing Tests"])

    with tab_new:
        _render_new_test_form(db)

    with tab_manage:
        _render_existing_tests(db)


def _render_new_test_form(db):
    with st.container(border=True):
        title = st.text_input("Test title", placeholder="e.g. NEET Full Syllabus Mock #3")

        scope = st.radio(
            "Coverage",
            ["Single Chapter", "Multiple Chapters", "Full Subject", "Full Syllabus (all subjects)"],
            horizontal=True,
        )

        chapter_pairs = []
        if scope == "Single Chapter":
            col_s, col_c = st.columns(2)
            with col_s:
                subject = st.selectbox("Subject", SUBJECTS, key="test_single_subject")
            with col_c:
                chapter = st.selectbox("Chapter", get_chapters(subject), key="test_single_chapter")
            chapter_pairs = [(subject, chapter)]

        elif scope == "Multiple Chapters":
            subject = st.selectbox("Subject", SUBJECTS, key="test_multi_subject")
            chapters = st.multiselect("Chapters", get_chapters(subject), key="test_multi_chapters")
            chapter_pairs = [(subject, ch) for ch in chapters]

        elif scope == "Full Subject":
            subject = st.selectbox("Subject", SUBJECTS, key="test_fullsubj_subject")
            chapter_pairs = [(subject, ch) for ch in get_chapters(subject)]
            st.caption(f"Covers all {len(chapter_pairs)} chapters of {subject}.")

        else:  # Full Syllabus
            chapter_pairs = [(subj, ch) for subj in SUBJECTS for ch in get_chapters(subj)]
            st.caption(f"Covers all {len(chapter_pairs)} chapters across all {len(SUBJECTS)} subjects.")

        col_diff, col_pyq = st.columns(2)
        with col_diff:
            difficulty = st.selectbox("Difficulty", DIFFICULTY_LEVELS, index=1)
        with col_pyq:
            pyq_style = st.checkbox("PYQ-style phrasing", help="Write questions in the style of actual NEET Previous Year Questions (still AI-generated, not real past papers).")

        col_count, col_dur = st.columns(2)
        with col_count:
            question_count = st.number_input(
                "Number of questions", min_value=5, max_value=200,
                value=DEFAULT_TEST_QUESTION_COUNT, step=5,
            )
        with col_dur:
            duration_minutes = st.number_input(
                "Duration (minutes)", min_value=10, max_value=360,
                value=DEFAULT_TEST_DURATION_MINUTES, step=10,
            )

        col_correct, col_wrong = st.columns(2)
        with col_correct:
            marks_correct = st.number_input("Marks per correct answer", value=float(DEFAULT_MARKS_CORRECT), step=0.5)
        with col_wrong:
            marks_wrong = st.number_input("Marks per wrong answer (negative marking)", value=float(DEFAULT_MARKS_WRONG), step=0.5)

        st.divider()
        can_generate = bool(title.strip()) and len(chapter_pairs) > 0
        if not chapter_pairs:
            st.info("Select at least one chapter before generating.")

        if st.button("Generate Test", type="primary", disabled=not can_generate, use_container_width=True):
            _generate_full_test(db, title.strip(), chapter_pairs, int(question_count),
                                 int(duration_minutes), difficulty, pyq_style,
                                 marks_correct, marks_wrong)


def _generate_full_test(db, title, chapter_pairs, question_count, duration_minutes,
                         difficulty, pyq_style, marks_correct, marks_wrong):
    """Generates every question up front with a live progress bar, then
    creates the test in draft status. Questions are drawn round-robin
    across chapter_pairs so counts are spread evenly, not skewed toward
    whichever chapter happens to generate fastest."""
    progress = st.progress(0.0, text=f"Generating question 1 of {question_count}...")
    questions = []
    failures = 0

    for i in range(question_count):
        subject, chapter = chapter_pairs[i % len(chapter_pairs)]
        try:
            q = generate_question(subject, chapter, difficulty=difficulty, pyq_style=pyq_style)
            questions.append(q)
        except AllProvidersExhaustedError as e:
            failures += 1
            if failures >= 3:
                progress.empty()
                st.error(
                    f"Stopped after {failures} consecutive generation failures — every configured "
                    f"AI key is failing. Generated {len(questions)} of {question_count} questions "
                    f"before stopping. Check your API keys in secrets.toml, or try again later. ({e})"
                )
                return
        except RuntimeError as e:
            failures += 1

        progress.progress((i + 1) / question_count, text=f"Generating question {min(i + 2, question_count)} of {question_count}... ({len(questions)} succeeded)")

    progress.empty()

    if len(questions) < question_count:
        st.warning(f"Generated {len(questions)} of {question_count} requested questions ({failures} failed). You can still create the test with what succeeded, or try again.")

    if not questions:
        st.error("No questions could be generated. Check your AI provider keys and try again.")
        return

    test_id = create_full_test(db, title, questions, duration_minutes, marks_correct, marks_wrong)
    st.success(f"Test \"{title}\" created with {len(questions)} question(s) — go to **Manage Existing Tests** to review and open it.")
    st.session_state[f"just_created_{test_id}"] = True


def _render_existing_tests(db):
    tests = db.get("full_tests", {})
    if not tests:
        st.caption("No tests created yet.")
        return

    for test_id, test in sorted(tests.items(), key=lambda kv: kv[1]["created_at"], reverse=True):
        with st.container(border=True):
            status_label = {"draft": "Draft", "open": "Open", "closed": "Closed"}[test["status"]]
            st.markdown(f"**{test['title']}** — {len(test['questions'])} questions, {test['duration_minutes']} min — *{status_label}*")

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if test["status"] == "draft":
                    if st.button("Open to Students", key=f"open_{test_id}", type="primary"):
                        open_full_test(db, test_id)
                        st.rerun()
            with col_b:
                if test["status"] == "open":
                    remaining = None
                    from quiz import full_test_time_left
                    remaining = full_test_time_left(db, test_id)
                    if remaining is not None:
                        mins = int(remaining // 60)
                        st.caption(f"{mins} min remaining on shared clock")
                    if st.button("Close Test Now", key=f"close_{test_id}"):
                        close_full_test(db, test_id)
                        st.rerun()
            with col_c:
                submitted_count = len([s for s in test["submissions"].values() if s.get("submitted_at")])
                started_count = len(test["submissions"])
                st.caption(f"{submitted_count} submitted / {started_count} started")

            if test["status"] == "closed":
                with st.expander("Results"):
                    render_full_test_leaderboard(test)


# ========================================================================
# LIVE QUIZ (practice sessions — single question or auto-quiz series)
# ========================================================================

def _render_live_quiz_tab(db):
    st.subheader("Live Practice Quiz")
    st.caption("Runs in real time with everyone watching the same question at once — best for a focused class session, not unattended practice.")

    if not db["quiz_state"]["active"]:
        with st.container(border=True):
            quiz_mode = st.radio(
                "Mode",
                ["Single Question", "Auto Quiz (multiple, timed)", "My Question Bank"],
                horizontal=True,
            )

            if quiz_mode == "Single Question":
                col_s, col_c = st.columns(2)
                with col_s:
                    subject = st.selectbox("Subject", SUBJECTS, key="single_subject")
                with col_c:
                    topic = st.selectbox("Chapter", get_chapters(subject), key="single_topic")

                col_diff, col_timer = st.columns(2)
                with col_diff:
                    difficulty = st.selectbox("Difficulty", DIFFICULTY_LEVELS, index=1, key="single_difficulty")
                with col_timer:
                    use_timer = st.checkbox("Add a countdown timer")
                timer_secs = st.slider("Seconds per question", 10, 120, 30, step=5) if use_timer else 0

                if st.button("Generate & Send", type="primary"):
                    with st.spinner("Generating and verifying..."):
                        try:
                            q_data = generate_question(subject, topic, difficulty=difficulty)
                            start_quiz(db, q_data, timer_seconds=timer_secs)
                            st.rerun()
                        except AllProvidersExhaustedError as e:
                            st.error(f"Generation failed: {e}")

            elif quiz_mode == "Auto Quiz (multiple, timed)":
                col_s, col_c = st.columns(2)
                with col_s:
                    subject = st.selectbox("Subject", SUBJECTS, key="auto_subject")
                with col_c:
                    topic = st.selectbox("Chapter", get_chapters(subject), key="auto_topic")

                col_diff, col_pyq = st.columns(2)
                with col_diff:
                    difficulty = st.selectbox("Difficulty", DIFFICULTY_LEVELS, index=1, key="auto_difficulty")
                with col_pyq:
                    pyq_style = st.checkbox("PYQ-style", key="auto_pyq")

                num_questions = st.slider("Number of questions", 2, 20, 5)
                timer_secs = st.slider("Seconds per question", 10, 120, 30, step=5)

                if st.button("Start Auto Quiz", type="primary"):
                    with st.spinner("Generating question 1..."):
                        try:
                            start_auto_quiz(db, subject, topic, num_questions, timer_secs, difficulty, pyq_style)
                            st.rerun()
                        except AllProvidersExhaustedError as e:
                            st.error(f"Generation failed: {e}")

            else:
                st.caption("Paste questions below (blank line between each). One-time use — not saved permanently.")
                st.code(
                    "Q: What is the powerhouse of the cell?\n"
                    "A) Nucleus\nB) Mitochondria\nC) Ribosome\nD) Golgi body\n"
                    "Answer: B\n"
                    "Explanation: Mitochondria generate ATP via oxidative phosphorylation.",
                    language=None,
                )
                raw_bank_text = st.text_area("Paste your questions here", height=220, key="bank_paste_area")

                if st.button("Parse & Preview"):
                    parsed, errors = parse_pasted_questions(raw_bank_text)
                    st.session_state.question_bank = parsed
                    st.session_state.question_bank_errors = errors

                if "question_bank" in st.session_state:
                    parsed = st.session_state.question_bank
                    errors = st.session_state.get("question_bank_errors", [])
                    if parsed:
                        st.success(f"{len(parsed)} question(s) parsed.")
                    if errors:
                        st.warning(f"{len(errors)} block(s) skipped:")
                        for e in errors:
                            st.caption(f"• {e}")
                    if parsed:
                        bank_timer = st.slider("Seconds per question", 10, 120, 30, step=5, key="bank_timer")
                        bank_count = st.slider("Number of questions to use", 1, len(parsed), len(parsed), key="bank_count")
                        if st.button("Start Quiz from Bank", type="primary"):
                            start_bank_quiz(db, parsed, bank_timer, bank_count)
                            st.rerun()
    else:
        _render_active_live_quiz(db)


def _render_active_live_quiz(db):
    qs = db["quiz_state"]
    q_data = qs["question_data"]

    if qs.get("auto_mode"):
        st.info(f"Auto Quiz running — question {qs['current_index']}/{qs['total_questions']}")
    else:
        st.info("Live question active.")

    if q_data.get("_correction_made"):
        st.caption("Note: the verification pass corrected this question's answer before it was sent.")

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
        if qs.get("timer_seconds") and is_time_up(db):
            lock_and_reveal(db)
            st.rerun()

        st.caption(f"{len(qs['answers'])} response(s) received")
        if st.button("Lock & Reveal Answer", type="primary"):
            lock_and_reveal(db)
            st.rerun()
    else:
        st.success(f"Correct answer: {q_data['answer']}")
        _render_results_table(qs, q_data, db)
        st.divider()
        render_leaderboard(db)

        if qs.get("auto_mode"):
            st.caption("Advancing to the next question...")
            time.sleep(2.5)
            advance_auto_quiz(db)  # ADMIN-ONLY — see module docstring
            st.rerun()
        else:
            if st.button("Clear & Return"):
                clear_quiz(db)
                st.rerun()


def _render_results_table(qs, q_data, db):
    st.write("**Results:**")
    answers = qs.get("answers", {})
    answer_times = qs.get("answer_times", {})
    all_students = [u for u, info in db["users"].items() if info["role"] == "student"]
    rows = []
    for student in all_students:
        chosen = answers.get(student)
        if chosen is None:
            rows.append({"Student": student.capitalize(), "Answer": "— no answer —", "Result": "Timed out", "Time": "—"})
        else:
            correct = chosen == q_data["answer"]
            t = answer_times.get(student)
            rows.append({
                "Student": student.capitalize(), "Answer": chosen,
                "Result": "Correct" if correct else "Wrong",
                "Time": f"{t}s" if t is not None else "—",
            })
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No responses yet.")


# ========================================================================
# LEADERBOARD
# ========================================================================

def _render_leaderboard_tab(db):
    st.subheader("Leaderboard")
    if st.button("Reset Today's Session Scores"):
        db["current_session_scores"] = {u: 0 for u in db["users"] if db["users"][u]["role"] == "student"}
        save_db(db)
        st.success("Session scores reset.")
    render_leaderboard(db)
