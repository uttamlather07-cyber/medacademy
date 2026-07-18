"""
auth.py
The landing page (hero + stats strip) and login/signup forms.
"""

import time
import streamlit as st

from database import load_db, register_user, DatabaseUnavailableError


def render_hero(db):
    total_students = len([u for u, i in db["users"].items() if i["role"] == "student"])
    open_tests = len([t for t in db.get("full_tests", {}).values() if t["status"] == "open"])

    st.markdown(
        f"""
        <div class="hero-wrap">
            <div class="hero-eyebrow anim-in">
                <span class="pulse-dot"></span> LIVE SESSION
            </div>
            <div class="hero-title anim-in-delay-1">Practice like it's <em>results day</em>.</div>
            <p class="hero-sub anim-in-delay-2">
                Chapter-wise practice, full-length timed mock tests, and a leaderboard
                that actually tracks who's improving.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="vitals-strip anim-in-delay-2">
            <div class="vital-stat"><div class="num mono-num">{total_students}</div><div class="label">Students Enrolled</div></div>
            <div class="vital-stat"><div class="num mono-num">{open_tests}</div><div class="label">Tests Open Now</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login_signup():
    try:
        db = load_db()
    except DatabaseUnavailableError:
        st.error("Can't reach the database right now. Please wait a few seconds and refresh the page.")
        st.stop()
    render_hero(db)

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        portal_student, portal_admin = st.tabs(["Student Login", "Admin Login"])

        with portal_student:
            with st.container(border=True):
                sub_log, sub_reg = st.tabs(["Log In", "Create Account"])
                with sub_log:
                    login_username = st.text_input("Username", key="log_u").strip().lower()
                    login_password = st.text_input("Password", type="password", key="log_p")
                    if st.button("Log In", key="btn_login", type="primary"):
                        try:
                            db = load_db()
                        except DatabaseUnavailableError:
                            st.error("Can't reach the database right now. Please try again in a few seconds.")
                            st.stop()
                        user = db["users"].get(login_username)
                        if user and user["password"] == login_password and user["role"] == "student":
                            st.session_state.logged_in = True
                            st.session_state.username = login_username
                            st.session_state.role = "student"
                            st.rerun()
                        else:
                            st.error("Incorrect username or password.")
                with sub_reg:
                    new_username = st.text_input("Choose Username", key="reg_u").strip().lower()
                    new_password = st.text_input("Choose Password", type="password", key="reg_p")
                    if st.button("Create Account", key="btn_register"):
                        if not new_username or not new_password:
                            st.error("Please fill in both fields.")
                        elif new_username == "admin":
                            st.error("That username is reserved.")
                        elif len(new_username) < 3:
                            st.error("Username too short (minimum 3 characters).")
                        else:
                            new_user_data = {
                                "password": new_password,
                                "role": "student",
                                "lifetime_score": 0,
                                "last_seen": time.time(),
                                "blocked": False,
                                "avatar_color": "#5b5fef",
                            }
                            # Atomic: the database itself checks "does this
                            # username already exist?" and inserts it in one
                            # step, so two students registering within the
                            # same second can never overwrite each other.
                            try:
                                result = register_user(new_username, new_user_data)
                            except DatabaseUnavailableError:
                                result = "error"

                            if result == "taken":
                                st.error("That username is already taken.")
                            elif result == "error":
                                st.error("Could not reach the database. Please try again — your account was NOT created, so it's safe to retry.")
                            else:
                                st.success("Account created. Switch to the Log In tab.")

        with portal_admin:
            with st.container(border=True):
                st.markdown("##### Admin Access")
                admin_password = st.text_input("Password", type="password", key="admin_log_p")
                if st.button("Log In", type="primary", key="btn_admin_login"):
                    try:
                        db = load_db()
                    except DatabaseUnavailableError:
                        st.error("Can't reach the database right now. Please try again in a few seconds.")
                        st.stop()
                    if db["users"]["admin"]["password"] == admin_password:
                        st.session_state.logged_in = True
                        st.session_state.username = "admin"
                        st.session_state.role = "admin"
                        st.rerun()
                    else:
                        st.error("Incorrect password.")
    st.stop()
