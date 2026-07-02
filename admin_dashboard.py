"""
admin_dashboard.py
The Chief Medical Officer (admin) terminal.
"""

import time
import html as html_lib
import streamlit as st

from database import save_db
from chat import render_chat_messages, render_chat_composer, has_unread_messages, unread_message_count, mark_chat_seen
from quiz import (
    generate_question, start_quiz, lock_and_reveal, clear_quiz, submit_answer,
    start_auto_quiz, advance_auto_quiz, time_left, is_time_up,
    parse_pasted_questions, start_bank_quiz,
)
from polls import start_poll, start_tracking_poll, end_poll, TRACKING_OPTIONS
from styles import ecg_divider
from chapters import SUBJECTS, get_chapters
from library import render_library_browser, render_library_uploader


def render_admin_dashboard(db):
    st.markdown("<div class='hero-eyebrow'><span class='pulse-dot'></span> COMMAND CENTER</div>", unsafe_allow_html=True)
    st.markdown("<h1 style='margin-top:4px;'>Chief Medical Officer Terminal</h1>", unsafe_allow_html=True)
    ecg_divider()

    # ---------------- NEW MESSAGE NOTIFICATION ----------------
    if has_unread_messages(db, st.session_state.username):
        count = unread_message_count(db, st.session_state.username)
        plural = "message" if count == 1 else "messages"
        st.markdown(
            f"<div class='announce-banner'>💬 {count} new {plural} in Chat & Security — open that "
            f"tab to read {'it' if count == 1 else 'them'}.</div>",
            unsafe_allow_html=True,
        )

    tab_quiz, tab_chat, tab_poll, tab_announce, tab_leaders, tab_library = st.tabs(
        ["📝 Medical Quiz", "💬 Chat & Security", "📊 Smart Polls", "📢 Broadcasts", "🏆 Performance Tracking", "📚 Library"]
    )

    # ---------------- CHAT ----------------
    with tab_chat:
        # Admin is actively viewing chat now, so clear the unread badge.
        mark_chat_seen(db, st.session_state.username)

        col_c1, col_c2 = st.columns([3, 1])
        with col_c1:
            st.subheader("Live Class Chat")
            chat_container = st.container(height=460, border=True)
            with chat_container:
                render_chat_messages(db["chat"], st.session_state.username)
            render_chat_composer(db, st.session_state.username, is_blocked=False, key_prefix="admin", is_admin=True)

        with col_c2:
            st.subheader("Security & Mod")
            with st.container(border=True):
                chat_is_on = db.get("chat_enabled", True)
                status_label = "🟢 Chat is ON for students" if chat_is_on else "🔒 Chat is OFF for students"
                st.markdown(f"**{status_label}**")
                toggle_label = "🔒 Turn Chat OFF" if chat_is_on else "🟢 Turn Chat ON"
                if st.button(toggle_label, type="secondary" if chat_is_on else "primary"):
                    db["chat_enabled"] = not chat_is_on
                    save_db(db)
                    st.rerun()
                st.caption("Admin can always post, even when chat is off for students.")
                st.divider()

                if st.button("🗑️ Purge ALL Chat", type="primary"):
                    db["chat"] = []
                    save_db(db)
                    st.rerun()
                st.divider()

                all_students = [u for u, info in db["users"].items() if info["role"] == "student"]
                if all_students:
                    target_user = st.selectbox("Select Student:", all_students)
                    if st.button(f"🗑️ Delete {target_user}'s Chat"):
                        db["chat"] = [msg for msg in db["chat"] if msg["sender"] != target_user]
                        save_db(db)
                        st.success(f"Purged messages from {target_user}")

                    is_blocked = db["users"][target_user].get("blocked", False)
                    btn_txt = f"🔓 Unblock {target_user}" if is_blocked else f"🚫 Block {target_user}"
                    if st.button(btn_txt):
                        db["users"][target_user]["blocked"] = not is_blocked
                        save_db(db)
                        st.rerun()
                else:
                    st.caption("No students registered yet.")

    # ---------------- ANNOUNCEMENTS ----------------
    with tab_announce:
        st.subheader("Broadcast a Live Message")
        ann_text = st.text_input("Type your announcement here:")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🚨 Broadcast to Class", type="primary"):
                db["announcement"] = ann_text
                db["announcement_time"] = time.time()
                save_db(db)
                st.rerun()
        with col_b:
            if st.button("🗑️ Clear Announcement"):
                db["announcement"] = ""
                save_db(db)
                st.rerun()

    # ---------------- QUIZ ----------------
    with tab_quiz:
        col1, col2 = st.columns([2, 1])
        with col1:
            if not db["quiz_state"]["active"]:
                with st.container(border=True):
                    st.subheader("🧬 Generate Exam Case Study")
                    quiz_mode = st.radio(
                        "Quiz mode",
                        ["Single Question", "Auto Quiz (AI, multiple, timed)", "My Question Bank"],
                        horizontal=True,
                    )

                    # ---------------- SINGLE QUESTION (AI) ----------------
                    if quiz_mode == "Single Question":
                        subject = st.selectbox("Choose Specialty", SUBJECTS, key="single_subject")
                        topic = st.selectbox("Choose Chapter", get_chapters(subject), key="single_topic")

                        use_timer = st.checkbox("⏱️ Add a countdown timer to this question")
                        timer_secs = 0
                        if use_timer:
                            timer_secs = st.slider("Seconds per question", 10, 120, 30, step=5)

                        st.caption("Each question is independently fact-checked by a second AI pass before it's sent out.")
                        if st.button("🚀 Generate & Dispatch to Residents", type="primary"):
                            with st.spinner("Analyzing medical databanks and verifying accuracy..."):
                                q_data = generate_question(subject, topic)
                                start_quiz(db, q_data, timer_seconds=timer_secs)
                                st.session_state.balloon_shown = False
                                st.rerun()

                    # ---------------- AUTO QUIZ (AI) ----------------
                    elif quiz_mode == "Auto Quiz (AI, multiple, timed)":
                        subject = st.selectbox("Choose Specialty", SUBJECTS, key="auto_subject")
                        topic = st.selectbox("Choose Chapter", get_chapters(subject), key="auto_topic")

                        num_questions = st.slider("Number of questions", 2, 20, 5)
                        timer_secs = st.slider("Seconds per question", 10, 120, 30, step=5)
                        st.caption(f"This will run {num_questions} questions back-to-back, {timer_secs}s each, auto-revealing and advancing on its own. Each question is independently fact-checked before being shown.")

                        if st.button("🚀 Start Auto Quiz", type="primary"):
                            with st.spinner("Generating and verifying question 1..."):
                                start_auto_quiz(db, subject, topic, num_questions, timer_secs)
                                st.session_state.balloon_shown = False
                                st.rerun()

                    # ---------------- MY QUESTION BANK ----------------
                    else:
                        st.caption(
                            "Paste 20-30 questions below. One-time use - not saved permanently, "
                            "just used for this quiz. Format per question (blank line between each):"
                        )
                        st.code(
                            "Q: What is the powerhouse of the cell?\n"
                            "A) Nucleus\n"
                            "B) Mitochondria\n"
                            "C) Ribosome\n"
                            "D) Golgi body\n"
                            "Answer: B\n"
                            "Explanation: Mitochondria generate ATP via oxidative phosphorylation.",
                            language=None,
                        )
                        raw_bank_text = st.text_area(
                            "Paste your questions here",
                            height=220,
                            key="bank_paste_area",
                        )

                        if st.button("🔍 Parse & Preview"):
                            parsed, errors = parse_pasted_questions(raw_bank_text)
                            st.session_state.question_bank = parsed
                            st.session_state.question_bank_errors = errors

                        if "question_bank" in st.session_state:
                            parsed = st.session_state.question_bank
                            errors = st.session_state.get("question_bank_errors", [])

                            if parsed:
                                st.success(f"✅ {len(parsed)} question(s) parsed successfully.")
                                with st.expander("Preview parsed questions"):
                                    for i, q in enumerate(parsed, start=1):
                                        st.markdown(f"**{i}. {q['question']}**")
                                        for opt in q["options"]:
                                            mark = "✅" if opt == q["answer"] else "•"
                                            st.write(f"{mark} {opt}")
                                        st.divider()
                            if errors:
                                st.warning(f"⚠️ {len(errors)} block(s) skipped due to formatting issues:")
                                for e in errors:
                                    st.caption(f"• {e}")

                            if parsed:
                                bank_timer = st.slider("Seconds per question", 10, 120, 30, step=5, key="bank_timer")
                                bank_count = st.slider(
                                    "Number of questions to use this quiz",
                                    1, len(parsed), len(parsed), key="bank_count",
                                )
                                if st.button("🚀 Start Quiz from My Question Bank", type="primary"):
                                    start_bank_quiz(db, parsed, bank_timer, bank_count)
                                    st.session_state.balloon_shown = False
                                    st.rerun()
            else:
                qs = db["quiz_state"]
                q_data = qs["question_data"]

                if qs.get("auto_mode"):
                    source_tag = "📚 My Question Bank" if qs.get("question_source") == "bank" else "🤖 AI Generated"
                    st.warning(f"⚠️ Auto Quiz live ({source_tag})")
                else:
                    st.warning("⚠️ Case study is currently active on student screens!")

                if q_data.get("_correction_made"):
                    st.info("ℹ️ Note: the fact-check pass corrected this question's answer before it was sent out.")

                # ---- Header row: question text on the left, progress + timer badges on the right ----
                badges_html = ""
                if qs.get("auto_mode"):
                    badges_html += (
                        f"<div class='progress-badge'><div class='t-val'>{qs['current_index']}/{qs['total_questions']}</div>"
                        f"<div class='t-lbl'>Question</div></div>"
                    )
                if qs.get("timer_seconds") and not qs["revealed"]:
                    remaining = time_left(db)
                    urgent = remaining is not None and remaining <= 10
                    badge_class = "timer-badge urgent" if urgent else "timer-badge"
                    badges_html += (
                        f"<div class='{badge_class}'><div class='t-val'>{int(remaining)}s</div>"
                        f"<div class='t-lbl'>Remaining</div></div>"
                    )
                safe_question = html_lib.escape(str(q_data['question']))
                st.markdown(
                    f"<div class='quiz-header-row'>"
                    f"<div class='quiz-heading'><strong>Q:</strong> {safe_question}</div>"
                    f"<div class='quiz-badges'>{badges_html}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                if not qs["revealed"]:
                    # Auto-reveal if the timer expired (checked each autorefresh tick)
                    if qs.get("timer_seconds") and is_time_up(db):
                        lock_and_reveal(db)
                        st.rerun()

                    st.info(f"Diagnoses received: {len(qs['answers'])} students")
                    if st.button("🚨 Lock Time & Reveal Answers", type="primary"):
                        lock_and_reveal(db)
                        st.rerun()
                else:
                    st.success(f"**Correct Diagnosis:** {q_data['answer']}")
                    _render_results_table(qs, q_data, db)

                    if qs.get("auto_mode"):
                        st.caption("Advancing to the next question automatically...")
                        time.sleep(2.5)
                        advance_auto_quiz(db)
                        st.rerun()
                    else:
                        if st.button("Clear Board for Next Case"):
                            clear_quiz(db)
                            st.rerun()

    # ---------------- POLLS ----------------
    with tab_poll:
        if not db["polls"]["active"]:
            st.subheader("Create a Poll")
            poll_mode = st.radio(
                "Poll type",
                ["🧠 Tracking Poll (Yes / No / Partially)", "✏️ Custom Poll"],
                horizontal=True,
            )

            if poll_mode.startswith("🧠"):
                track_metric = st.selectbox(
                    "Which metric should this poll track?",
                    ["Revision", "Tests", "DPPs"],
                    key="tracking_metric_select",
                )
                default_q = f"Did you complete today's {track_metric.lower()}?"
                poll_q = st.text_input("Poll Question", value=default_q, key="tracking_poll_q")
                st.caption(f"Options are fixed: {', '.join(TRACKING_OPTIONS)}. Any vote increases '{track_metric}' by 1 for that student, regardless of which option they pick.")

                if st.button("Start Tracking Poll", type="primary"):
                    if poll_q.strip():
                        start_tracking_poll(db, track_metric, poll_q.strip())
                        st.rerun()
                    else:
                        st.warning("Add a poll question.")

            else:
                poll_q = st.text_input("Poll Question", key="custom_poll_q")

                if "custom_poll_options" not in st.session_state:
                    st.session_state.custom_poll_options = ["", ""]

                st.write("**Options**")
                for i in range(len(st.session_state.custom_poll_options)):
                    col_opt, col_del = st.columns([5, 1])
                    with col_opt:
                        st.session_state.custom_poll_options[i] = st.text_input(
                            f"Option {i + 1}",
                            value=st.session_state.custom_poll_options[i],
                            key=f"custom_opt_{i}",
                            label_visibility="collapsed",
                            placeholder=f"Option {i + 1}",
                        )
                    with col_del:
                        if len(st.session_state.custom_poll_options) > 2:
                            if st.button("🗑️", key=f"custom_opt_del_{i}"):
                                st.session_state.custom_poll_options.pop(i)
                                st.rerun()

                if st.button("➕ Add option"):
                    st.session_state.custom_poll_options.append("")
                    st.rerun()

                st.divider()
                is_smart = st.checkbox("🧠 Also track a student metric on this custom poll")
                track_metric = None
                if is_smart:
                    track_metric = st.selectbox("Which metric should answering this poll increase?", ["Revision", "Tests", "DPPs"], key="custom_smart_metric")
                    st.info(f"When a student votes, their '{track_metric}' score increases by 1.")

                if st.button("Start Custom Poll", type="primary"):
                    valid_opts = [o for o in st.session_state.custom_poll_options if o.strip()]
                    if poll_q.strip() and len(valid_opts) >= 2:
                        start_poll(db, poll_q.strip(), valid_opts, is_smart, track_metric)
                        st.session_state.custom_poll_options = ["", ""]
                        st.rerun()
                    else:
                        st.warning("Add a question and at least 2 non-empty options.")
        else:
            st.info(f"**Active Poll:** {db['polls']['question']}")
            if db["polls"].get("is_smart"):
                st.success(f"🧠 Smart tracking active: +1 {db['polls']['track_metric']} per vote.")

            for opt in db["polls"]["options"]:
                votes = list(db["polls"]["votes"].values()).count(opt)
                st.write(f"{opt}: {votes} votes")
            if st.button("End Poll"):
                end_poll(db)
                st.rerun()

    # ---------------- LEADERBOARD ----------------
    with tab_leaders:
        st.subheader("Comprehensive Medical Charts")
        if st.button("Start New Shift (zeros session scores only)"):
            db["current_session_scores"] = {u: 0 for u in db["users"] if db["users"][u]["role"] == "student"}
            save_db(db)
            st.success("Session scores reset!")

        students = {k: v for k, v in db["users"].items() if v["role"] == "student"}
        if not students:
            st.caption("No students registered yet.")
        for s_name, data in sorted(students.items(), key=lambda kv: -kv[1].get("lifetime_score", 0)):
            with st.container(border=True):
                st.markdown(f"#### 🩺 {s_name.capitalize()}")
                m = data.get("metrics", {})
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(f"<div class='metric-tile'><div class='val'>{data.get('lifetime_score', 0)}</div><div class='lbl'>Quiz Pts</div></div>", unsafe_allow_html=True)
                c2.markdown(f"<div class='metric-tile'><div class='val'>{m.get('Revision',0)}</div><div class='lbl'>Revision</div></div>", unsafe_allow_html=True)
                c3.markdown(f"<div class='metric-tile'><div class='val'>{m.get('Tests',0)}</div><div class='lbl'>Tests</div></div>", unsafe_allow_html=True)
                c4.markdown(f"<div class='metric-tile'><div class='val'>{m.get('DPPs',0)}</div><div class='lbl'>DPPs</div></div>", unsafe_allow_html=True)

    # ---------------- LIBRARY ----------------
    with tab_library:
        lib_upload, lib_browse = st.tabs(["📤 Upload", "📂 Browse"])
        with lib_upload:
            st.subheader("Add a Document to the Library")
            with st.container(border=True):
                render_library_uploader(db, st.session_state.username)
        with lib_browse:
            st.subheader("Library Contents")
            render_library_browser(db, st.session_state.username, allow_delete=True)


def _render_results_table(qs, q_data, db):
    """Shared results table: who answered what, correct/wrong, and time taken."""
    st.write("**Results — who chose what, and how fast:**")
    answers = qs.get("answers", {})
    answer_times = qs.get("answer_times", {})

    all_students = [u for u, info in db["users"].items() if info["role"] == "student"]
    rows = []
    for student in all_students:
        chosen = answers.get(student)
        if chosen is None:
            rows.append({"Student": student.capitalize(), "Answer": "— no answer —", "Result": "⏱️ Timed out", "Time": "—"})
        else:
            correct = chosen == q_data["answer"]
            t = answer_times.get(student)
            rows.append({
                "Student": student.capitalize(),
                "Answer": chosen,
                "Result": "✅ Correct" if correct else "❌ Wrong",
                "Time": f"{t}s" if t is not None else "—",
            })

    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No students have answered yet.")
