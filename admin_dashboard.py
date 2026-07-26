"""
admin_dashboard.py
The admin console: create tests (paste questions in), manage existing
tests (open/close/delete), and view leaderboards.

No AI generation, no live quiz — stripped entirely per the rebuild's
scope. Admin pastes questions using the same Q:/A)/Answer:/Explanation:
format the bot already uses (see question_parser.py).
"""

import html
import streamlit as st

from database import (
    create_test, add_questions, get_all_tests, open_test,
    close_test, delete_test, get_test_questions, get_test_leaderboard,
    DatabaseUnavailableError,
)
from question_parser import parse_pasted_questions
from sidebar import render_nav, render_roster
from config import DEFAULT_TEST_DURATION_MINUTES, DEFAULT_MARKS_CORRECT, DEFAULT_MARKS_WRONG


def render_admin_dashboard(db_unused=None):
    st.markdown("<h1>Admin Console</h1>", unsafe_allow_html=True)
    page = render_nav(admin=True)
    render_roster()

    if page == "Tests":
        _render_test_manager()
    elif page == "Leaderboard":
        _render_leaderboard_tab()


def _render_test_manager():
    tab_new, tab_manage = st.tabs(["Create a Test", "Manage Existing Tests"])
    with tab_new:
        _render_new_test_form()
    with tab_manage:
        _render_existing_tests()


# ============================================================
# CREATE TEST
# ============================================================

def _render_new_test_form():
    with st.container(border=True):
        title = st.text_input("Test title", placeholder="e.g. NEET Full Syllabus Mock #3")

        col_dur, col_correct, col_wrong = st.columns(3)
        with col_dur:
            duration_minutes = st.number_input(
                "Duration (minutes)", min_value=5, max_value=360,
                value=DEFAULT_TEST_DURATION_MINUTES, step=5,
            )
        with col_correct:
            marks_correct = st.number_input("Marks per correct", value=float(DEFAULT_MARKS_CORRECT), step=0.5)
        with col_wrong:
            marks_wrong = st.number_input("Marks per wrong (negative marking)", value=float(DEFAULT_MARKS_WRONG), step=0.5)

        st.caption("Paste questions below (blank line between each).")
        st.code(
            "Q: What is the powerhouse of the cell?\n"
            "A) Nucleus\nB) Mitochondria\nC) Ribosome\nD) Golgi body\n"
            "Answer: B\n"
            "Explanation: Mitochondria generate ATP via oxidative phosphorylation.",
            language=None,
        )
        raw_text = st.text_area("Paste your questions here", height=280, key="new_test_paste")

        if st.button("Parse & Preview"):
            parsed, errors = parse_pasted_questions(raw_text)
            st.session_state.pending_questions = parsed
            st.session_state.pending_errors = errors

        if "pending_questions" in st.session_state:
            parsed = st.session_state.pending_questions
            errors = st.session_state.get("pending_errors", [])
            if parsed:
                st.success(f"{len(parsed)} question(s) parsed successfully.")
            if errors:
                st.warning(f"{len(errors)} block(s) skipped:")
                for e in errors:
                    st.caption(f"• {e}")

            can_create = bool(title.strip()) and len(parsed) > 0
            if st.button("Create Test", type="primary", disabled=not can_create, use_container_width=True):
                _create_test_with_questions(title.strip(), int(duration_minutes), marks_correct, marks_wrong, parsed)


def _create_test_with_questions(title, duration_minutes, marks_correct, marks_wrong, questions):
    try:
        test_id = create_test(
            title=title, duration_minutes=duration_minutes,
            marks_correct=marks_correct, marks_wrong=marks_wrong,
            created_by=st.session_state.username,
        )
        add_questions(test_id, questions)
    except DatabaseUnavailableError:
        st.error("Lost connection to the database — the test may not have saved. Please check Manage Existing Tests and try again if needed.")
        return

    st.success(f"Test \"{title}\" created with {len(questions)} question(s) — go to **Manage Existing Tests** to open it to students.")
    st.session_state.pop("pending_questions", None)
    st.session_state.pop("pending_errors", None)


# ============================================================
# MANAGE TESTS
# ============================================================

def _render_existing_tests():
    try:
        tests = get_all_tests()
    except DatabaseUnavailableError:
        st.error("Lost connection to the database.")
        return

    if not tests:
        st.caption("No tests created yet.")
        return

    for test in tests:
        with st.container(border=True):
            status_label = {"draft": "Draft", "open": "Open", "closed": "Closed"}[test["status"]]
            try:
                q_count = len(get_test_questions(test["id"]))
            except DatabaseUnavailableError:
                q_count = "?"
            st.markdown(f"**{html.escape(test['title'])}** — {q_count} questions, {test['duration_minutes']} min — *{status_label}*")

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if test["status"] == "draft":
                    if st.button("Open to Students", key=f"open_{test['id']}", type="primary"):
                        open_test(test["id"])
                        st.rerun()
            with col_b:
                if test["status"] == "open":
                    if st.button("Close Test Now", key=f"close_{test['id']}"):
                        close_test(test["id"])
                        st.rerun()
            with col_c:
                confirm_key = f"confirm_del_{test['id']}"
                if st.session_state.get(confirm_key):
                    if st.button("⚠️ Confirm Delete", key=f"del_confirm_{test['id']}"):
                        delete_test(test["id"])
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                else:
                    if st.button("Delete", key=f"del_{test['id']}"):
                        st.session_state[confirm_key] = True
                        st.rerun()

            if test["status"] == "closed":
                with st.expander("Results"):
                    _render_leaderboard_for(test["id"])


# ============================================================
# LEADERBOARD
# ============================================================

def _render_leaderboard_tab():
    st.subheader("Leaderboard")
    try:
        tests = get_all_tests()
    except DatabaseUnavailableError:
        st.error("Lost connection to the database.")
        return
    if not tests:
        st.caption("No tests yet.")
        return
    titles = {t["id"]: t["title"] for t in tests}
    test_id = st.selectbox("Select a test", list(titles.keys()), format_func=lambda i: titles[i])
    if test_id:
        _render_leaderboard_for(test_id)


def _render_leaderboard_for(test_id: int):
    try:
        board = get_test_leaderboard(test_id, limit=20)
    except DatabaseUnavailableError:
        st.error("Lost connection to the database.")
        return
    if not board:
        st.caption("No scored attempts yet.")
        return
    for i, row in enumerate(board, start=1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        st.markdown(
            f"{medal} **{html.escape(row['username'])}** — {row['score']:g} pts "
            f"({row['correct_count']} correct, {row['wrong_count']} wrong)"
        )
