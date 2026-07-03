"""
database.py
All persistence logic lives here.

Backend: Supabase (Postgres), accessed via the supabase-py client. The
entire app database is stored as ONE JSON blob in a single row (id=1) of
the 'app_state' table's 'data' jsonb column — same shape as the old
database.json file, just persisted remotely instead of on Streamlit
Cloud's ephemeral local disk (which is why accounts kept disappearing).

Requires SUPABASE_URL and SUPABASE_KEY in .streamlit/secrets.toml (locally)
or in Streamlit Cloud's Settings -> Secrets (when deployed). See README.md
for the one-time Supabase project + table setup.

NOTE: uploaded files (library PDFs) are handled separately by storage.py,
which persists them in Supabase Storage — also survives Streamlit Cloud
restarts, same as this JSON data does.
"""

import time
import streamlit as st
from supabase import create_client

TABLE = "app_state"
ROW_ID = 1

DEFAULT_ADMIN_PASSWORD = "212020"  # change this after first login if possible


@st.cache_resource
def _get_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def _default_db():
    return {
        "quiz_state": {
            "active": False,
            "question_data": None,
            "answers": {},
            "answer_times": {},
            "revealed": False,
            "timer_seconds": 0,
            "question_start_time": 0,
            "auto_mode": False,
            "subject": None,
            "topic": None,
            "total_questions": 0,
            "current_index": 0,
            "question_source": "ai",
            "bank_order": [],
        },
        "polls": {"active": False, "question": "", "options": [], "votes": {}},
        "current_session_scores": {},
        "announcement": "",
        "announcement_time": 0,
        "library": [],
        "users": {
            "admin": {
                "password": DEFAULT_ADMIN_PASSWORD,
                "role": "admin",
                "lifetime_score": 0,
                "last_seen": time.time(),
                "blocked": False,
                "avatar_color": "#6366f1",
            }
        },
        "scores": {},
    }


def upgrade_db(data: dict) -> dict:
    """Ensure older saved states gain new fields without losing data."""
    defaults = _default_db()

    for key, value in defaults.items():
        if key not in data:
            data[key] = value

    # nested quiz_state
    for k, v in defaults["quiz_state"].items():
        data["quiz_state"].setdefault(k, v)

    # nested polls
    for k, v in defaults["polls"].items():
        data["polls"].setdefault(k, v)

    # per-user upgrades
    for uname, uinfo in data.get("users", {}).items():
        uinfo.setdefault("lifetime_score", data.get("scores", {}).get(uname, 0))
        uinfo.setdefault("last_seen", time.time())
        uinfo.setdefault("blocked", False)
        uinfo.setdefault("avatar_color", "#6366f1")

    return data


class DatabaseUnavailableError(Exception):
    """Raised when Supabase can't be reached. Callers MUST NOT fall back to
    treating this as 'no data' and saving a fresh empty database over it —
    that was the #1 cause of accounts/scores/chat vanishing. A temporary
    network hiccup should show an error and stop, never wipe real data."""
    pass


def load_db() -> dict:
    client = _get_client()
    try:
        result = client.table(TABLE).select("data").eq("id", ROW_ID).execute()
    except Exception as e:
        # Do NOT return a fresh default here. Returning an empty DB looks
        # identical to "this is a brand new install" to every caller, and
        # app.py calls save_db() on every page load — so a single flaky
        # connection would silently overwrite the real database with an
        # empty one seconds later. Fail loudly instead.
        raise DatabaseUnavailableError(str(e))

    if result.data:
        return upgrade_db(result.data[0]["data"])

    # This case means the row genuinely doesn't exist yet in Supabase
    # (true first-ever run, not a fetch failure) — safe to seed defaults.
    fresh = upgrade_db(_default_db())
    save_db(fresh)
    return fresh


def save_db(data: dict):
    client = _get_client()
    client.table(TABLE).update({"data": data, "updated_at": "now()"}).eq("id", ROW_ID).execute()


def register_user(username: str, user_data: dict) -> str:
    """Atomically adds a new user via a Postgres function (register_user
    SQL RPC — see README setup notes), instead of load_db() -> add to dict
    -> save_db(). That old pattern is exactly what caused students to lose
    freshly-created accounts and have to register repeatedly: if two
    students register within the same few seconds (very common right when
    a session starts), both load the same snapshot, both add themselves in
    Python, and whichever save_db() finishes last overwrites the other's
    new account entirely. Doing the add-if-not-exists check AND the write
    in one atomic database step makes concurrent registrations safe
    regardless of timing.

    Returns "ok", "taken" (username already exists), or "error".
    """
    client = _get_client()
    try:
        result = client.rpc(
            "register_user", {"p_username": username, "p_user_data": user_data}
        ).execute()
        return result.data if isinstance(result.data, str) else "ok"
    except Exception:
        return "error"


def touch_user_last_seen(username: str):
    """Atomically updates one user's last_seen timestamp via a Postgres
    function (touch_last_seen SQL RPC), instead of the old pattern of
    loading the whole database, mutating one field in Python, and saving
    the whole thing back. This runs on every single page load for every
    logged-in user (app.py), so with several students autorefreshing every
    few seconds, the old pattern was a constant source of overlapping
    load-modify-save cycles — exactly the kind of race that can silently
    drop other changes (chat messages, quiz answers, new registrations)
    made in the same narrow window. Touching just one field atomically
    removes that whole class of collision."""
    client = _get_client()
    try:
        client.rpc("touch_last_seen", {"p_username": username}).execute()
    except Exception:
        pass  # Non-critical (presence indicator only) — never crash the page over this.
