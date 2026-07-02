"""
auth.py
The landing page (hero + vitals strip) and login/signup forms.
"""

import time
import streamlit as st

from database import load_db, register_user, DatabaseUnavailableError
from styles import ecg_divider


def render_hero(db):
    total_students = len([u for u, i in db["users"].items() if i["role"] == "student"])
    online_now = len([
        u for u, i in db["users"].items()
        if time.time() - i.get("last_seen", 0) < 15
    ])
    questions_asked = 1 if db.get("quiz_state", {}).get("question_data") else 0
    messages_sent = len(db.get("chat", []))

    st.markdown(
        f"""
        <div class="hero-wrap">
            <div class="hero-eyebrow anim-in">
                <span class="pulse-dot"></span> LIVE CLASSROOM · SESSION ACTIVE
            </div>
            <div class="hero-title anim-in-delay-1">Precision prep for <em>NEET</em>, run like rounds.</div>
            <p class="hero-sub anim-in-delay-2">
                Case-study quizzes, live diagnosis polls, and a real-time staff room —
                built for students who treat every practice question like a patient chart.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ecg_divider()
    st.markdown(
        f"""
        <div class="vitals-strip anim-in-delay-3">
            <div class="vital-stat"><div class="num mono-num">{total_students}</div><div class="label">Residents Enrolled</div></div>
            <div class="vital-stat"><div class="num mono-num">{online_now}</div><div class="label">On Duty Now</div></div>
            <div class="vital-stat"><div class="num mono-num">{messages_sent}</div><div class="label">Ward Messages</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login_signup():
    try:
        db = load_db()
    except DatabaseUnavailableError:
        st.error("⚠️ Can't reach the database right now. Please wait a few seconds and refresh the page.")
        st.stop()
    render_hero(db)

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        portal_student, portal_admin = st.tabs(["🩺 Student Portal", "👨‍⚕️ Admin Portal"])

        with portal_student:
            with st.container(border=True):
                sub_log, sub_reg = st.tabs(["Login", "Create Account"])
                with sub_log:
                    login_username = st.text_input("Username", key="log_u").strip().lower()
                    login_password = st.text_input("Password", type="password", key="log_p")
                    if st.button("Access Academy", key="btn_login"):
                        try:
                            db = load_db()
                        except DatabaseUnavailableError:
                            st.error("⚠️ Can't reach the database right now. Please try again in a few seconds.")
                            st.stop()
                        user = db["users"].get(login_username)
                        if user and user["password"] == login_password and user["role"] == "student":
                            st.session_state.logged_in = True
                            st.session_state.username = login_username
                            st.session_state.role = "student"
                            st.rerun()
                        else:
                            st.error("❌ Incorrect username or password.")
                with sub_reg:
                    new_username = st.text_input("Choose Username", key="reg_u").strip().lower()
                    new_password = st.text_input("Choose Password", type="password", key="reg_p")
                    if st.button("Register as Student", key="btn_register"):
                        if not new_username or not new_password:
                            st.error("Please fill in both fields.")
                        elif new_username == "admin":
                            st.error("Username taken!")
                        elif len(new_username) < 3:
                            st.error("Username too short (min 3 characters).")
                        else:
                            new_user_data = {
                                "password": new_password,
                                "role": "student",
                                "lifetime_score": 0,
                                "last_seen": time.time(),
                                "blocked": False,
                                "metrics": {"Revision": 0, "Tests": 0, "DPPs": 0},
                                "avatar_color": "#5b8def",
                                "last_seen_chat_count": 0,
                            }
                            # Atomic: the database itself checks "does this
                            # username already exist?" and inserts it in one
                            # step, so two students registering within the
                            # same second can never overwrite each other —
                            # this is what was causing repeated "register
                            # again" loops during busy session starts.
                            try:
                                result = register_user(new_username, new_user_data)
                            except DatabaseUnavailableError:
                                result = "error"

                            if result == "taken":
                                st.error("Username taken!")
                            elif result == "error":
                                st.error("⚠️ Could not reach the database. Please try again in a moment — your account was NOT created, so it's safe to retry.")
                            else:
                                st.success("✅ Registration successful! Switch to the Login tab.")

        with portal_admin:
            with st.container(border=True):
                st.markdown("##### 🔐 Chief Medical Officer Access")
                admin_password = st.text_input("Master Password", type="password", key="admin_log_p")
                if st.button("Unlock Command Center", type="primary", key="btn_admin_login"):
                    try:
                        db = load_db()
                    except DatabaseUnavailableError:
                        st.error("⚠️ Can't reach the database right now. Please try again in a few seconds.")
                        st.stop()
                    if db["users"]["admin"]["password"] == admin_password:
                        st.session_state.logged_in = True
                        st.session_state.username = "admin"
                        st.session_state.role = "admin"
                        st.rerun()
                    else:
                        st.error("❌ Access Denied.")
    st.stop()
