"""
auth.py
Login/signup screen, PLUS persistent-login-across-browser-restarts.

THE PROBLEM THIS SOLVES: Streamlit's st.session_state lives only in
server memory, tied to one browser tab's connection — it's gone the
moment the tab/window closes.

STORAGE MECHANISM — st.query_params, NOT a cookie library. An earlier
version of this file used extra_streamlit_components' CookieManager.
That was a real mistake, caught before shipping: that package's cookies
are set inside a Streamlit custom-component iframe, and Streamlit
Cloud's own iframe sandboxing means a cookie set in that inner iframe's
context is NOT reliably visible to the outer app on a later page load
— multiple independent developers have hit and documented this exact
failure specifically on Streamlit Cloud (the deployment target here),
not just in an isolated bug report. On top of that, the package has its
own long-standing quirks independent of the sandboxing issue (calling
.get() twice in one script run throws, constructing it triggers an
internal rerun that can scramble unrelated button state elsewhere on
the page). st.query_params is a built-in Streamlit feature (since
1.30), reads synchronously on page load with no timing race to work
around, and has none of the iframe isolation risk since it's just the
page's own URL.

WHY A TOKEN, NOT THE PASSWORD: the URL parameter never contains the
student's actual username/password — only a random, meaningless string
that maps to a username in auth_sessions (see schema.sql). This means
the value sitting in the URL can't be reverse-engineered into real
credentials even if someone saw it over someone's shoulder or in
browser history, and a session can be revoked (logout, or a security
concern) by deleting one database row, without touching the student's
actual password at all.

TRADEOFF WORTH KNOWING: because the token lives in the URL rather than
an invisible cookie, it's visible in the address bar and in browser
history/bookmarks. Bookmarking or sharing that URL would hand someone
else that logged-in session until it's revoked or expires. This is a
real, deliberate tradeoff for reliability on Streamlit Cloud's
sandboxed deployment model — not an oversight. If a student is on a
shared/public computer, using Log Out (which deletes the session
server-side, not just locally) closes that specific exposure.
"""

import secrets
import base64
import streamlit as st

from database import (
    verify_login, register_user, create_session, validate_session,
    delete_session, DatabaseUnavailableError,
)

SESSION_DAYS_VALID = 30
QUERY_PARAM_NAME = "s"


def _encode_token(token: str) -> str:
    """Base64-encodes the token before putting it in the URL — not for
    secrecy (the underlying value is still just as revocable/opaque
    either way), but so the query param is a clean, single alphanumeric
    token Streamlit/browsers won't ever need to URL-escape oddly."""
    return base64.urlsafe_b64encode(token.encode()).decode()


def _decode_token(encoded: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(encoded.encode()).decode()
    except Exception:
        return None  # malformed/tampered value in the URL — treat as no session


def try_resume_session() -> bool:
    """Call this once, early in app.py, BEFORE deciding whether to show
    the login screen. Returns True and populates st.session_state if a
    valid, non-expired session token was found in the URL; False
    otherwise. Unlike the cookie-based version this replaced,
    st.query_params is available synchronously on the very first
    rerun — there's no 'give it one more rerun to be sure' quirk to
    work around here."""
    if st.session_state.get("logged_in"):
        return True  # already resumed (or freshly logged in) this session — skip re-checking

    encoded = st.query_params.get(QUERY_PARAM_NAME)
    if not encoded:
        return False

    token = _decode_token(encoded)
    if not token:
        return False

    try:
        username = validate_session(token)
    except DatabaseUnavailableError:
        return False  # can't verify right now — fall through to login screen rather than guessing

    if not username:
        return False  # token existed but expired, or was revoked

    try:
        from database import get_user
        user = get_user(username)
    except DatabaseUnavailableError:
        return False
    if not user or user.get("blocked"):
        return False

    st.session_state.logged_in = True
    st.session_state.username = user["username"]
    st.session_state.role = user["role"]
    st.session_state._session_token = token
    return True


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
                stay_logged_in = st.checkbox("Stay logged in on this browser", value=True)
                submitted = st.form_submit_button("Log In", type="primary", use_container_width=True)
            if submitted:
                _handle_login(username.strip(), password, stay_logged_in)

        with tab_signup:
            with st.form("signup_form"):
                new_username = st.text_input("Choose a username")
                new_password = st.text_input("Choose a password", type="password")
                submitted = st.form_submit_button("Sign Up", type="primary", use_container_width=True)
            if submitted:
                _handle_signup(new_username.strip(), new_password)

    st.stop()


def _handle_login(username: str, password: str, stay_logged_in: bool):
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

    if stay_logged_in:
        token = secrets.token_urlsafe(32)  # cryptographically random, not guessable
        try:
            create_session(token, user["username"], days_valid=SESSION_DAYS_VALID)
            st.query_params[QUERY_PARAM_NAME] = _encode_token(token)
            st.session_state._session_token = token
        except DatabaseUnavailableError:
            pass  # login itself still succeeded — persistence just won't stick this one time

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


def log_out():
    """Clears both the in-memory session state AND the persistent
    database session/URL token — called from sidebar.py's Log Out
    button. Without the second half, a student clicking Log Out would
    just get silently logged back in on their very next page load,
    since the token would still be sitting there in the URL, valid."""
    token = st.session_state.get("_session_token")
    if token:
        try:
            delete_session(token)
        except DatabaseUnavailableError:
            pass  # best-effort — clearing the URL param below still logs them out of THIS browser
    if QUERY_PARAM_NAME in st.query_params:
        del st.query_params[QUERY_PARAM_NAME]
    for key in ("logged_in", "username", "role", "active_attempt_id", "_session_token"):
        st.session_state.pop(key, None)
