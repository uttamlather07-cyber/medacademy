"""
auth.py
Login/signup screen. Talks to app_users via database.py's targeted
functions (verify_login, register_user) — never a blob load/save.
"""

import streamlit as st
from database import verify_login, register_user, DatabaseUnavailableError

DEFAULT_ADMIN_PASSWORD = "212020"  # change this after first login


def render_login_signup():
    st.markdown(
        "<div style='text-align:center;padding:48px 0 24px;'>"
        "<h1>NEET Test Console</h1>"
        "<p style='color:#9aa4b6;'>Sign in to continue</p></div>",
        unsafe_allow_html=True,
    )

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        tab_login, tab_signup = st.tabs(["Log In", "Sign Up"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log In", type="primary", use_container_width=True)
            if submitted:
                _handle_login(username.strip(), password)

        with tab_signup:
            with st.form("signup_form"):
                new_username = st.text_input("Choose a username")
                new_password = st.text_input("Choose a password", type="password")
                submitted = st.form_submit_button("Sign Up", type="primary", use_container_width=True)
            if submitted:
                _handle_signup(new_username.strip(), new_password)

    st.stop()


def _handle_login(username: str, password: str):
    if not username or not password:
        st.error("Enter both a username and password.")
        return
    try:
        user = verify_login(username, password)
    except DatabaseUnavailableError:
        st.error("Lost connection to the database. Please try again in a moment.")
        return
    if not user:
        st.error("Incorrect username/password, or this account is blocked.")
        return
    st.session_state.logged_in = True
    st.session_state.username = user["username"]
    st.session_state.role = user["role"]
    st.rerun()


def _handle_signup(username: str, password: str):
    if not username or not password:
        st.error("Choose both a username and password.")
        return
    if len(password) < 4:
        st.error("Password should be at least 4 characters.")
        return
    try:
        result = register_user(username, password, role="student")
    except DatabaseUnavailableError:
        st.error("Lost connection to the database. Please try again in a moment.")
        return
    if result == "taken":
        st.error("That username is already taken.")
        return
    if result != "ok":
        st.error("Something went wrong creating your account. Please try again.")
        return
    st.success("Account created — you can log in now.")
