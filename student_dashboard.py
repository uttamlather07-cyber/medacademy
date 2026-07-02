"""
student_dashboard.py
The student-facing view: live quiz/poll, staff room chat, personal chart.
"""

import streamlit as st

from database import save_db
from chat import render_chat_messages, render_chat_composer, has_unread_messages, unread_message_count, mark_chat_seen
from quiz import submit_answer, time_left
from polls import cast_vote
from styles import ecg_divider
from library import render_library_browser


def render_student_dashboard(db):
    uname = st.session_state.username
    st.markdown("<div class='hero-eyebrow'><span class='pulse-dot'></span> ON DUTY</div>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='margin-top:4px;'>Welcome, {uname.capitalize()}</h1>", unsafe_allow_html=True)
    ecg_divider()

    # ---------------- NEW MESSAGE NOTIFICATION ----------------
    if has_unread_messages(db, uname):
        count = unread_message_count(db, uname)
        plural = "message" if count == 1 else "messages"
        st.markdown(
            f"<div class='announce-banner'>💬 {count} new {plural} in the Staff Room — open the "
            f"'Staff Room' tab to read {'it' if count == 1 else 'them'}.</div>",
            unsafe_allow_html=True,
        )

    tab_class, tab_chat, tab_stats, tab_library = st.tabs(["📝 Live Operating Room", "💬 Staff Room", "📊 My Medical Chart", "📚 Library"])

    # ---------------- CHAT ----------------
    with tab_chat:
        # User is actively viewing chat now, so clear their unread badge.
        mark_chat_seen(db, uname)

        st.subheader("Live Class Chat")
        chat_container = st.container(height=460, border=True)
        with chat_container:
            render_chat_messages(db["chat"], uname)

        is_blocked = db["users"][uname].get("blocked", False)
        render_chat_composer(db, uname, is_blocked=is_blocked, key_prefix="student")

    # ---------------- LIVE CLASS ----------------
    with tab_class:
        if db["polls"]["active"]:
            with st.container(border=True):
                st.markdown("### 📊 Active CMO Poll")
                st.write(db["polls"]["question"])
                my_vote = db["polls"]["votes"].get(uname)
                if not my_vote:
                    for opt in db["polls"]["options"]:
                        if st.button(f"Vote: {opt}", key=f"vote_{opt}"):
                            cast_vote(db, uname, opt)
                            st.rerun()
                else:
                    st.success(f"You voted: {my_vote}. Waiting for CMO to close poll...")
                    if db["polls"].get("is_smart"):
                        st.info(f"✅ Your {db['polls']['track_metric']} tracker was updated!")

        if db["quiz_state"]["active"]:
            qs = db["quiz_state"]
            q_data = qs["question_data"]
            revealed = qs["revealed"]
            my_answer = qs["answers"].get(uname)

            with st.container(border=True):
                heading = (
                    f"📋 Question {qs['current_index']}"
                    if qs.get("auto_mode") else "📋 Question"
                )

                # ---- Header row: short question title on the left, progress + timer badges on the right ----
                badges_html = ""
                if qs.get("auto_mode"):
                    badges_html += (
                        f"<div class='progress-badge'><div class='t-val'>{qs['current_index']}/{qs['total_questions']}</div>"
                        f"<div class='t-lbl'>Question</div></div>"
                    )
                if qs.get("timer_seconds") and not revealed:
                    remaining = time_left(db)
                    urgent = remaining is not None and remaining <= 10
                    badge_class = "timer-badge urgent" if urgent else "timer-badge"
                    badges_html += (
                        f"<div class='{badge_class}'><div class='t-val'>{int(remaining)}s</div>"
                        f"<div class='t-lbl'>Remaining</div></div>"
                    )
                st.markdown(
                    f"<div class='quiz-header-row'>"
                    f"<div class='quiz-heading'><h3>{heading}</h3></div>"
                    f"<div class='quiz-badges'>{badges_html}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.write(q_data["question"])

                if not revealed:
                    if not my_answer:
                        choice = st.radio("Select your diagnosis:", q_data["options"], index=None)
                        if st.button("Lock Diagnosis", type="primary"):
                            if choice:
                                submit_answer(db, uname, choice)
                                st.rerun()
                            else:
                                st.warning("Please select a diagnosis first.")
                    else:
                        my_time = qs.get("answer_times", {}).get(uname)
                        time_note = f" in {my_time}s" if my_time is not None else ""
                        st.info(f"You locked in: **{my_answer}**{time_note}. Waiting for results...")
                else:
                    is_correct = my_answer == q_data["answer"]
                    box_class = "reveal-box" if is_correct else "reveal-box wrong"
                    st.markdown(f"<div class='{box_class}'>", unsafe_allow_html=True)

                    my_time = qs.get("answer_times", {}).get(uname)
                    time_note = f" (in {my_time}s)" if my_time is not None else ""

                    if is_correct:
                        st.success(f"✅ Excellent diagnosis! (+4 points) You chose {my_answer}{time_note}")
                        if not st.session_state.get("balloon_shown"):
                            st.balloons()
                            st.session_state.balloon_shown = True
                    elif my_answer:
                        st.error(f"❌ Incorrect diagnosis! (-1 point) You chose {my_answer}{time_note}")
                    else:
                        st.warning("⏱️ Patient transferred! You didn't answer in time.")

                    st.info(f"**The correct diagnosis was:** {q_data['answer']}")
                    st.markdown(f"**Medical explanation:** {q_data['explanation']}")
                    st.markdown("</div>", unsafe_allow_html=True)

                    st.divider()
                    st.write("### How the ward voted")
                    for opt in q_data["options"]:
                        voters = [s for s, a in qs["answers"].items() if a == opt]
                        if voters:
                            st.write(f"**{opt}**: {', '.join(v.capitalize() for v in voters)}")

                    if qs.get("auto_mode"):
                        st.caption("⏭️ Next question is on its way...")
        else:
            st.info("🏥 Waiting for the Chief Medical Officer to post the next case...")
            st.session_state.balloon_shown = False

    # ---------------- STATS ----------------
    with tab_stats:
        my_session = db["current_session_scores"].get(uname, 0)
        my_lifetime = db["users"][uname].get("lifetime_score", 0)
        m = db["users"][uname].get("metrics", {})

        st.markdown("### 🏆 Quiz Performance")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"<div class='metric-tile'><div class='val'>{my_session}</div><div class='lbl'>Today's Shift Score</div></div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='metric-tile'><div class='val'>{my_lifetime}</div><div class='lbl'>Lifetime Points</div></div>", unsafe_allow_html=True)

        st.markdown("### 📈 Consistent Effort Tracking")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div class='metric-tile'><div class='val'>{m.get('Revision',0)}</div><div class='lbl'>Revisions Completed</div></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-tile'><div class='val'>{m.get('Tests',0)}</div><div class='lbl'>Tests Attempted</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-tile'><div class='val'>{m.get('DPPs',0)}</div><div class='lbl'>DPPs Solved</div></div>", unsafe_allow_html=True)

    # ---------------- LIBRARY ----------------
    with tab_library:
        st.subheader("📚 Study Materials")
        render_library_browser(db, uname, allow_delete=False)
