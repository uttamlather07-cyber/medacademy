"""
database.py
All persistence logic lives here.

Backend: Supabase (Postgres), via real per-row tables — see schema.sql.
This REPLACES the old single-JSON-blob "app_state" design entirely. The
old design stored the whole database as one JSON row; every read fetched
everything, every write rewrote everything. With 20-30 students in a live
test all answering questions at once, that meant 20-30 full-database
read-modify-write cycles racing to overwrite the same one row — that
was the actual cause of the lag, not the AI features that have since
been removed.

Every function below reads or writes EXACTLY the rows it needs. The one
that matters most under load is submit_answer(), which is a single
targeted upsert via the submit_answer() Postgres RPC (see schema.sql) —
completely independent of what any other student is doing at the same
moment. No shared blob, no lock contention, no reason concurrent load
should slow anything down.

Requires SUPABASE_URL and SUPABASE_KEY in .streamlit/secrets.toml
(locally) or Streamlit Cloud's Settings -> Secrets (deployed).
"""

import streamlit as st
from supabase import create_client


@st.cache_resource
def _get_client():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


class DatabaseUnavailableError(Exception):
    """Raised when Supabase can't be reached. Callers should show a
    friendly retry message and stop, not treat this as 'no data' —
    same principle as the old database.py, just now applying to
    individual targeted queries instead of one big blob fetch."""
    pass


def _run(fn, *args, **kwargs):
    """Every public function below routes its actual Supabase call
    through this, so 'Supabase is unreachable' always surfaces as the
    same DatabaseUnavailableError regardless of which function hit it,
    rather than each function needing its own try/except."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        raise DatabaseUnavailableError(str(e))


# ============================================================
# USERS / AUTH
# ============================================================

def register_user(username: str, password: str, role: str) -> str:
    """Atomic insert-if-not-taken via the register_app_user RPC (see
    schema.sql) — two students racing to register the same username at
    the same instant can't both succeed; the DB's own unique constraint
    on app_users.username is the actual guarantee, this RPC just makes
    the check-and-insert one atomic round trip instead of two separate
    ones a Python-level 'does it exist? then insert' could race on.
    Returns 'ok', 'taken', or 'error'."""
    client = _get_client()

    def _do():
        result = client.rpc(
            "register_app_user",
            {"p_username": username, "p_password": password, "p_role": role},
        ).execute()
        return result.data
    return _run(_do)


def get_user(username: str) -> dict | None:
    client = _get_client()

    def _do():
        result = client.table("app_users").select("*").eq("username", username).execute()
        return result.data[0] if result.data else None
    return _run(_do)


def verify_login(username: str, password: str) -> dict | None:
    """Returns the user row on success, None on bad credentials or a
    blocked account. Plaintext password comparison — matches the old
    system's DEFAULT_ADMIN_PASSWORD approach exactly; hashing passwords
    properly is a real, worthwhile upgrade but a separate piece of work
    from this lag-focused rebuild, flagged here rather than silently
    fixed so it doesn't get lost."""
    user = get_user(username)
    if not user or user["password"] != password or user.get("blocked"):
        return None
    return user


def touch_last_seen(username: str):
    """Fire-and-forget presence update via the touch_last_seen RPC —
    same atomic-single-field pattern as the old system, kept because it
    was already correct: a presence dot doesn't need sub-second
    freshness, but it does need to never collide with anything else."""
    client = _get_client()
    try:
        client.rpc("touch_last_seen", {"p_username": username}).execute()
    except Exception:
        pass  # non-critical — never crash the page over a presence ping


def get_all_users() -> list[dict]:
    client = _get_client()

    def _do():
        result = client.table("app_users").select("*").order("username").execute()
        return result.data
    return _run(_do)


def set_user_blocked(username: str, blocked: bool):
    client = _get_client()

    def _do():
        client.table("app_users").update({"blocked": blocked}).eq("username", username).execute()
    return _run(_do)


# ============================================================
# TESTS (admin side)
# ============================================================

def create_test(title: str, duration_minutes: int, marks_correct: float, marks_wrong: float,
                 created_by: str, window_start: str = None, window_end: str = None) -> int:
    """Creates a test in 'draft' status — not visible to students until
    open_test() is called. Returns the new test's id."""
    client = _get_client()

    def _do():
        result = client.table("tests").insert({
            "title": title, "duration_minutes": duration_minutes,
            "marks_correct": marks_correct, "marks_wrong": marks_wrong,
            "created_by": created_by, "window_start": window_start, "window_end": window_end,
            "status": "draft",
        }).execute()
        return result.data[0]["id"]
    return _run(_do)


def add_questions(test_id: int, questions: list[dict], subject: str = "General") -> int:
    """questions: list of {question, options, answer, explanation}
    dicts, exactly the shape parse_pasted_questions already produces —
    no reshaping needed at the call site. order_index is assigned here
    sequentially starting from whatever's already in the test FOR THIS
    SUBJECT specifically (not globally across the whole test) — so
    pasting Physics then Chemistry gives each subject its own clean
    1, 2, 3... numbering, matching how the student-side palette numbers
    questions within a subject tab, same as the Telegram bot."""
    if not questions:
        return 0
    client = _get_client()

    def _do():
        existing = (
            client.table("test_questions").select("order_index")
            .eq("test_id", test_id).eq("subject", subject)
            .order("order_index", desc=True).limit(1).execute()
        )
        start_index = (existing.data[0]["order_index"] + 1) if existing.data else 0
        rows = [
            {
                "test_id": test_id, "subject": subject, "order_index": start_index + i,
                "question": q["question"], "options": q["options"],
                "correct_answer": q["answer"], "explanation": q.get("explanation", ""),
            }
            for i, q in enumerate(questions)
        ]
        client.table("test_questions").insert(rows).execute()
        return len(rows)
    return _run(_do)


def get_test(test_id: int) -> dict | None:
    client = _get_client()

    def _do():
        result = client.table("tests").select("*").eq("id", test_id).execute()
        return result.data[0] if result.data else None
    return _run(_do)


def get_all_tests() -> list[dict]:
    """Admin's full test list, newest first — used by the Manage Tests
    screen. Deliberately does NOT also fetch every test's questions or
    attempts here (that would turn one list-screen render back into a
    disguised full-database fetch); those are loaded separately, on
    demand, only for the one test an admin actually expands."""
    client = _get_client()

    def _do():
        result = client.table("tests").select("*").order("created_at", desc=True).execute()
        return result.data
    return _run(_do)


def open_test(test_id: int):
    client = _get_client()

    def _do():
        client.table("tests").update({"status": "open", "opened_at": "now()"}).eq("id", test_id).execute()
    return _run(_do)


def close_test(test_id: int):
    """Flips to 'closed' and freezes the #1 leaderboard position into
    topper_snapshot in the same call, so 'who won' survives forever
    even if attempts/answers are later queried differently."""
    leaderboard = get_test_leaderboard(test_id, limit=1)
    snapshot = leaderboard[0] if leaderboard else None
    client = _get_client()

    def _do():
        client.table("tests").update({
            "status": "closed", "closed_at": "now()", "topper_snapshot": snapshot,
        }).eq("id", test_id).execute()
    return _run(_do)


def delete_test(test_id: int) -> bool:
    """Genuinely one line here, unlike the Telegram bot's db_tests.py
    equivalent — SQLite there has no foreign-key enforcement at all, so
    that version had to manually delete from six tables in dependency
    order inside one transaction. Postgres's `on delete cascade` (see
    every child table's FK in schema.sql) means deleting the tests row
    automatically and atomically removes every test_questions,
    test_attempts, and test_answers row that references it — the
    database itself guarantees no orphaned rows, not application code."""
    client = _get_client()

    def _do():
        result = client.table("tests").delete().eq("id", test_id).execute()
        return len(result.data) > 0
    return _run(_do)


# ============================================================
# TESTS (student side)
# ============================================================

def get_open_tests() -> list[dict]:
    client = _get_client()

    def _do():
        result = client.table("tests").select("*").eq("status", "open").order("created_at", desc=True).execute()
        return result.data
    return _run(_do)


def get_test_questions(test_id: int) -> list[dict]:
    """Ordered by subject first, then order_index within that subject —
    so consuming this as one flat list still naturally groups every
    subject's questions together (Physics 1-15, then Chemistry 1-15,
    etc.) rather than interleaving them. student_dashboard.py's palette
    groups explicitly by the 'subject' field regardless, but this
    ordering keeps a plain flat rendering sane too."""
    client = _get_client()

    def _do():
        result = client.table("test_questions").select("*").eq("test_id", test_id).order("subject").order("order_index").execute()
        return result.data
    return _run(_do)


def get_test_subjects(test_id: int) -> list[str]:
    """Distinct subject names for a test, in first-added order (not
    alphabetical) — matches the order the admin pasted them in, since
    that's usually a deliberate sequencing (e.g. Physics, Chemistry,
    Botany, Zoology) worth preserving on the student-side subject tabs."""
    client = _get_client()

    def _do():
        result = client.table("test_questions").select("subject, created_at").eq("test_id", test_id).order("created_at").execute()
        seen = []
        for row in result.data:
            if row["subject"] not in seen:
                seen.append(row["subject"])
        return seen
    return _run(_do)


# ============================================================
# ATTEMPTS
# ============================================================

def start_or_resume_attempt(test_id: int, username: str) -> int:
    """Wraps the start_or_resume_attempt RPC (see schema.sql) — atomic
    'return the existing in-progress attempt if there is one, otherwise
    create one' in a single database round trip, so two tabs or a
    double-click can never create two in-progress attempts for the same
    student on the same test (the partial unique index in schema.sql is
    the actual backstop even if this RPC somehow raced anyway)."""
    client = _get_client()

    def _do():
        result = client.rpc("start_or_resume_attempt", {"p_test_id": test_id, "p_username": username}).execute()
        return result.data
    return _run(_do)


def get_attempt(attempt_id: int) -> dict | None:
    client = _get_client()

    def _do():
        result = client.table("test_attempts").select("*").eq("id", attempt_id).execute()
        return result.data[0] if result.data else None
    return _run(_do)


def get_active_attempt(test_id: int, username: str) -> dict | None:
    client = _get_client()

    def _do():
        result = (
            client.table("test_attempts").select("*")
            .eq("test_id", test_id).eq("username", username).eq("status", "in_progress")
            .execute()
        )
        return result.data[0] if result.data else None
    return _run(_do)


def set_current_question(attempt_id: int, question_id: int):
    client = _get_client()

    def _do():
        client.table("test_attempts").update({"current_question_id": question_id}).eq("id", attempt_id).execute()
    return _run(_do)


def submit_answer(attempt_id: int, question_id: int, selected_option: str | None, is_skipped: bool):
    """THE per-click write during a live test. Routes through the
    submit_answer RPC (see schema.sql) — a single atomic upsert on
    exactly this (attempt_id, question_id) row. Two different students
    answering at the exact same instant touch completely different
    rows and never contend with each other; this is the whole fix for
    the original lag."""
    client = _get_client()

    def _do():
        client.rpc("submit_answer", {
            "p_attempt_id": attempt_id, "p_question_id": question_id,
            "p_selected_option": selected_option, "p_is_skipped": is_skipped,
        }).execute()
    return _run(_do)


def get_attempt_answers(attempt_id: int) -> dict:
    """Returns {question_id: answer_row} for one attempt — a small,
    targeted fetch scoped to a single student's single attempt, never
    every answer ever submitted."""
    client = _get_client()

    def _do():
        result = client.table("test_answers").select("*").eq("attempt_id", attempt_id).execute()
        return {row["question_id"]: row for row in result.data}
    return _run(_do)


def finalize_attempt(attempt_id: int, expired: bool = False) -> dict:
    """Scores server-side by re-reading test_answers + test_questions
    directly from the database — never trusts a client-computed score,
    same principle the Telegram bot's Mini App integration notes call
    out explicitly. Returns the computed result dict AND persists it
    onto the test_attempts row in the same call."""
    attempt = get_attempt(attempt_id)
    if not attempt or attempt["status"] != "in_progress":
        return attempt  # already finalized, or doesn't exist — no-op

    test = get_test(attempt["test_id"])
    questions = get_test_questions(attempt["test_id"])
    answers = get_attempt_answers(attempt_id)

    correct = wrong = unanswered = 0
    for q in questions:
        entry = answers.get(q["id"])
        if not entry or entry["is_skipped"] or entry["selected_option"] is None:
            unanswered += 1
        elif entry["selected_option"] == q["correct_answer"]:
            correct += 1
        else:
            wrong += 1

    score = correct * test["marks_correct"] + wrong * test["marks_wrong"]
    new_status = "expired" if expired else "submitted"

    client = _get_client()

    def _do():
        client.table("test_attempts").update({
            "status": new_status, "submitted_at": "now()",
            "score": score, "correct_count": correct, "wrong_count": wrong, "unanswered_count": unanswered,
        }).eq("id", attempt_id).execute()
    _run(_do)

    return {
        **attempt, "status": new_status, "score": score,
        "correct_count": correct, "wrong_count": wrong, "unanswered_count": unanswered,
    }


# ============================================================
# LEADERBOARD
# ============================================================

def get_test_leaderboard(test_id: int, limit: int = 10) -> list[dict]:
    """Ranked by score, best attempt per student only (a student who
    reattempted for practice shouldn't appear twice or have a later,
    worse practice score bump their best live result). Only considers
    'submitted'/'expired' attempts — an 'in_progress' one has no score
    yet and is correctly excluded rather than sorting as a 0."""
    client = _get_client()

    def _do():
        result = (
            client.table("test_attempts").select("*")
            .eq("test_id", test_id).in_("status", ["submitted", "expired"])
            .order("score", desc=True)
            .execute()
        )
        best_per_student = {}
        for row in result.data:
            u = row["username"]
            if u not in best_per_student or row["score"] > best_per_student[u]["score"]:
                best_per_student[u] = row
        ranked = sorted(best_per_student.values(), key=lambda r: r["score"], reverse=True)
        return ranked[:limit]
    return _run(_do)


def get_lifetime_leaderboard(limit: int = 20) -> list[dict]:
    """Lifetime standings across EVERY test combined — sums each
    student's BEST score per test (mirroring get_test_leaderboard's own
    'best attempt only' rule), so a student who reattempted a test
    several times for practice can't inflate their lifetime total just
    by retaking the same test repeatedly; each test contributes at most
    once, at its best result.

    Deliberately NOT surfaced anywhere in student_dashboard.py — per-
    test leaderboards stay automatic and visible to everyone, but
    lifetime standings are something the admin posts themselves, on
    their own schedule, not something the system reveals on its own.
    This function only computes the numbers; showing them to anyone is
    entirely up to what admin_dashboard.py does with the result."""
    client = _get_client()

    def _do():
        result = (
            client.table("test_attempts").select("username, test_id, score")
            .in_("status", ["submitted", "expired"])
            .execute()
        )
        # best score per (student, test) pair first...
        best_per_student_per_test = {}
        for row in result.data:
            key = (row["username"], row["test_id"])
            if key not in best_per_student_per_test or row["score"] > best_per_student_per_test[key]:
                best_per_student_per_test[key] = row["score"]

        # ...then summed per student across every test they've taken.
        totals = {}
        test_counts = {}
        for (username, _test_id), score in best_per_student_per_test.items():
            totals[username] = totals.get(username, 0) + score
            test_counts[username] = test_counts.get(username, 0) + 1

        ranked = sorted(
            ({"username": u, "total_score": totals[u], "tests_taken": test_counts[u]} for u in totals),
            key=lambda r: r["total_score"], reverse=True,
        )
        return ranked[:limit]
    return _run(_do)
