"""
quiz.py
AI-powered NEET question generation, scoring, live timed quizzes, and
full-length timed tests (mock/PYQ-style exams).

QUESTION SOURCES:
Live quiz (single question or auto-quiz series) can pull questions from:
  - "ai"   : generated live via the multi-provider AI pool (ai_providers.py)
  - "bank" : drawn from an admin-pasted question bank
             (st.session_state.question_bank, NOT saved to the database -
             one-time-use, per-session set as requested)
Full-length tests are always pre-generated in full BEFORE the test opens
(see create_full_test) - nothing is generated live while students are
sitting the test, so a slow/flaky AI call never blocks or times out a
student mid-exam.

ACCURACY SAFEGUARDS FOR AI-GENERATED QUESTIONS:
1. POSITIONAL BIAS: options are shuffled in code after generation (with the
   answer relocated to match), so a model's tendency to place the correct
   answer in the same slot every time never reaches students.
2. FACTUAL ACCURACY: a second, independent AI completion re-derives the
   answer from scratch and checks/corrects the first pass before anything
   is shown to students.
Neither fix makes AI questions as trustworthy as a human-verified question
bank. For high-stakes tests, prefer "My Question Bank" as the source.

MULTI-PROVIDER RELIABILITY:
Generation and verification both go through ai_providers.complete_with_rotation,
which rotates across every configured Groq + Gemini key. A single
exhausted/rate-limited/dead key never blocks generation - see
ai_providers.py for the full rationale.

CONCURRENCY / "WHO IS ALLOWED TO ADVANCE THE QUIZ" - THE CRITICAL FIX:
The single biggest bug in the previous version: EVERY connected browser
(every student's session, not just the admin's) independently executed the
"reveal happened, now advance to the next question" code on its own
autorefresh tick. With N students connected, that meant N browsers each
sleeping, each calling generate_question (2-6 blocking AI calls), and each
overwriting the database with their own "next question" - simultaneously.
That's what crashed the app at question 2 with just 6 users: it was never
really a "concurrency at scale" problem, it would happen with 2 users too.

THE FIX: quiz-state-mutating functions in this file (advance_auto_quiz,
lock_and_reveal, generate_question-triggering starts) must ONLY ever be
called from the admin's own dashboard code path - student_dashboard.py
must be strictly read-only with respect to quiz_state, only ever calling
submit_answer() for its own user. This file doesn't enforce that by itself
(it can't know who's calling it) - it's enforced by which functions
admin_dashboard.py vs student_dashboard.py import and call. See both
files' module docstrings.
"""

import random
import re
import time
import uuid

import streamlit as st

from database import save_db, DatabaseUnavailableError
from ai_providers import complete_with_rotation, AllProvidersExhaustedError


def _safe_save(db) -> bool:
    """save_db() now retries internally (see database.py) but can still
    raise DatabaseUnavailableError if every retry fails - e.g. a real
    outage, not just a blip. Every write in this file goes through this
    wrapper instead of calling save_db directly, so a bad moment for
    Supabase shows the student/admin a normal warning ("try again") rather
    than an unhandled exception crashing their page mid-quiz/mid-test."""
    try:
        save_db(db)
        return True
    except DatabaseUnavailableError:
        st.warning("Couldn't save just now - connection hiccup. Please try that action again in a few seconds.")
        return False


# ----------------------------------------------------------------------
# AI GENERATION - shuffle-bias fix + independent verification pass
# ----------------------------------------------------------------------

def _shuffle_options(q_data: dict) -> dict:
    """Re-orders options randomly and relocates the answer to match, so the
    model's own positional bias can never reach the student."""
    options = list(q_data["options"])
    correct_text = q_data["answer"]

    if correct_text not in options:
        return q_data  # caller's validation will catch this

    shuffled = options[:]
    random.shuffle(shuffled)

    q_data = dict(q_data)
    q_data["options"] = shuffled
    q_data["answer"] = correct_text
    return q_data


_DANGLING_STEM_RE = re.compile(
    r"(given\s+below\s+are|consider\s+the\s+following|read\s+the\s+following|"
    r"read\s+the\s+assertion|assertion\s*\(a\)|two\s+statements|three\s+statements)"
    r"[^.]{0,15}[:\-]?\s*$",
    re.IGNORECASE,
)


def _has_dangling_statement_stem(question_text: str) -> bool:
    return bool(_DANGLING_STEM_RE.search(question_text.strip()))


def _validate_question_shape(q_data: dict) -> bool:
    """Structural check: 4 options, answer text exactly matches one of
    them, and statement/assertion stems actually contain their content."""
    if not isinstance(q_data, dict):
        return False
    required = ("question", "options", "answer", "explanation")
    if not all(k in q_data for k in required):
        return False
    if not isinstance(q_data["options"], list) or len(q_data["options"]) != 4:
        return False
    if q_data["answer"] not in q_data["options"]:
        return False
    question_text = str(q_data["question"]).strip()
    if not question_text:
        return False
    if _has_dangling_statement_stem(question_text):
        return False
    return True


DIFFICULTY_INSTRUCTIONS = {
    "Easy": "EASY difficulty: direct recall of a single fact or definition, the kind "
            "of question that rewards a student who read the NCERT textbook carefully. "
            "No multi-step reasoning.",
    "Medium": "MEDIUM difficulty: standard NEET difficulty - requires connecting two "
              "related facts or applying a concept to a slightly unfamiliar example.",
    "Hard": "HARD difficulty: a tough, discriminating NEET question - multi-step "
            "reasoning, easily-confused options, or combining concepts from more than "
            "one part of the chapter.",
}


def _generate_raw(subject: str, topic: str, difficulty: str = "Medium", pyq_style: bool = False) -> tuple:
    """Returns (q_data, provider_used)."""
    difficulty_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["Medium"])
    pyq_block = (
        "\nWrite this in the STYLE of an actual NEET Previous Year Question - the exact "
        "phrasing conventions and answer-choice patterns real NEET papers use. This is "
        "AI-generated, INSPIRED BY that style, not a claim of being a real past paper "
        "question - never state or imply a specific year or session.\n"
        if pyq_style else ""
    )

    prompt = f"""Generate 1 tough NEET multiple choice question for {subject} on the chapter/topic "{topic}".
Be scientifically precise. Double check the correct answer is actually correct before responding.

DIFFICULTY: {difficulty_instruction}
{pyq_block}
You may use any standard NEET question style, including assertion-reason questions and
two/three-statement "which of the following is/are correct" questions. This is exactly why the
"question" field rule below matters.

CRITICAL RULE FOR THE "question" FIELD:
The "question" field must be a SINGLE, FULLY SELF-CONTAINED STRING that includes every piece of
text a student needs in order to answer - there is no separate field for statements, assertions,
or reasons, so nothing outside "question" and "options" is ever shown to the student.
- If this is a statement-based question, the "question" string MUST include the complete text of
  every statement, numbered (Statement I: ..., Statement II: ...).
- If this is an assertion-reason question, the "question" string MUST include the full text of both
  the Assertion (A) and the Reason (R) written out in full, not just the labels.
- NEVER write a stem like "Given below are two statements:" without immediately writing out the
  full statement text right after it, inside that same "question" string.
- The "options" array should then contain only the final answer choices, never the statements.

Output ONLY valid JSON in this exact shape, nothing else:
{{"question": "text (fully self-contained)", "options": ["option 1", "option 2", "option 3", "option 4"], "answer": "exact correct option text, copied verbatim from options", "explanation": "Why it is correct, and briefly why the other options are wrong"}}"""

    result, provider = complete_with_rotation(prompt)
    return result, provider


def _verify_question(q_data: dict) -> dict:
    """Independent second pass: re-derives the answer from scratch and
    compares it to the first pass's proposed answer."""
    options_list = "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(q_data["options"]))
    prompt = f"""You are fact-checking a NEET exam question. Solve it yourself from scratch first,
then compare to the proposed answer below.

Question: {q_data['question']}
Options:
{options_list}

Proposed answer: {q_data['answer']}
Proposed explanation: {q_data['explanation']}

Independently determine the correct option. If the proposed answer is correct, confirm it.
If it is wrong, correct it.
Output ONLY valid JSON in this exact shape, nothing else:
{{"answer": "exact correct option text, copied verbatim from the options list above", "explanation": "correct, accurate explanation", "was_correct": true or false}}"""

    verified, _provider = complete_with_rotation(prompt)

    if verified.get("answer") not in q_data["options"]:
        q_data = dict(q_data)
        q_data["_verified"] = False
        return q_data

    q_data = dict(q_data)
    q_data["answer"] = verified["answer"]
    q_data["explanation"] = verified.get("explanation", q_data["explanation"])
    q_data["_verified"] = True
    q_data["_correction_made"] = not verified.get("was_correct", True)
    return q_data


def generate_question(subject: str, topic: str, max_attempts: int = 3,
                       difficulty: str = "Medium", pyq_style: bool = False) -> dict:
    """
    Full pipeline: generate -> shuffle (bias fix) -> verify (accuracy pass).
    Retries up to max_attempts times if the structural shape is ever
    invalid. Raises AllProvidersExhaustedError (from ai_providers) if every
    configured key fails - callers should catch this and show a specific
    "check your API keys" message rather than a generic crash.
    """
    last_error = None

    for attempt in range(max_attempts):
        try:
            q_data, _provider = _generate_raw(subject, topic, difficulty=difficulty, pyq_style=pyq_style)
            q_data = _shuffle_options(q_data)

            if not _validate_question_shape(q_data):
                last_error = "Malformed question shape from generation step"
                continue

            q_data = _verify_question(q_data)

            if not _validate_question_shape(q_data):
                last_error = "Malformed question shape from verification step"
                continue

            return q_data
        except AllProvidersExhaustedError:
            raise
        except (ValueError, KeyError, TypeError) as e:
            last_error = str(e)
            continue

    raise RuntimeError(f"Could not generate a reliable question after {max_attempts} attempts. Last error: {last_error}")


# ----------------------------------------------------------------------
# QUESTION BANK - admin-pasted, plain-text parsing
# ----------------------------------------------------------------------

_OPTION_PREFIX_RE = re.compile(r"^\s*[\(\[]?([A-Da-d])[\)\].:\-]\s*")
_ANSWER_LETTER_RE = re.compile(r"^\s*([A-Da-d])\b")


def _strip_option_prefix(line: str) -> str:
    return _OPTION_PREFIX_RE.sub("", line).strip()


def parse_pasted_questions(raw_text: str) -> tuple:
    """
    Parses a plain-text block of NEET-style questions into
    {question, options, answer, explanation} dicts.

    Expected per-question format (blank line separates questions):
        Q: What is the powerhouse of the cell?
        A) Nucleus
        B) Mitochondria
        C) Ribosome
        D) Golgi body
        Answer: B
        Explanation: Mitochondria generate ATP via oxidative phosphorylation.

    Returns (parsed_questions, errors).
    """
    blocks = re.split(r"\n\s*\n", raw_text.strip())
    parsed = []
    errors = []

    for block_num, block in enumerate(blocks, start=1):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue

        question_text = None
        options = []
        answer_letter = None
        explanation = ""

        for line in lines:
            low = line.lower()
            if low.startswith("q:") or low.startswith("q.") or low.startswith("question:"):
                question_text = line.split(":", 1)[-1].strip()
            elif low.startswith("answer:") or low.startswith("ans:"):
                m = _ANSWER_LETTER_RE.match(line.split(":", 1)[-1].strip())
                if m:
                    answer_letter = m.group(1).upper()
            elif low.startswith("explanation:") or low.startswith("solution:"):
                explanation = line.split(":", 1)[-1].strip()
            elif _OPTION_PREFIX_RE.match(line):
                options.append(_strip_option_prefix(line))

        if question_text is None:
            errors.append(f"Block {block_num}: no line starting with 'Q:' found - skipped.")
            continue
        if len(options) != 4:
            errors.append(f"Block {block_num} (\"{question_text[:40]}...\"): found {len(options)} options, need exactly 4 - skipped.")
            continue
        if answer_letter is None:
            errors.append(f"Block {block_num} (\"{question_text[:40]}...\"): no valid 'Answer: A/B/C/D' line found - skipped.")
            continue

        letter_index = {"A": 0, "B": 1, "C": 2, "D": 3}[answer_letter]
        answer_text = options[letter_index]

        parsed.append({
            "question": question_text,
            "options": options,
            "answer": answer_text,
            "explanation": explanation or "No explanation provided.",
        })

    return parsed, errors


# ----------------------------------------------------------------------
# LIVE QUIZ - single question (admin reveals manually)
# ----------------------------------------------------------------------

def _empty_quiz_state() -> dict:
    return {
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
    }


def start_quiz(db, q_data: dict, timer_seconds: int = 0):
    """ADMIN-ONLY - see module docstring."""
    db["quiz_state"] = _empty_quiz_state()
    db["quiz_state"].update({
        "active": True,
        "question_data": q_data,
        "timer_seconds": timer_seconds,
        "question_start_time": time.time() if timer_seconds else 0,
    })
    _safe_save(db)


def clear_quiz(db):
    """ADMIN-ONLY - see module docstring."""
    db["quiz_state"] = _empty_quiz_state()
    _safe_save(db)


# ----------------------------------------------------------------------
# LIVE QUIZ - auto series (N questions, one at a time, shared countdown)
# ----------------------------------------------------------------------

def start_auto_quiz(db, subject: str, topic: str, total_questions: int, timer_seconds: int,
                     difficulty: str = "Medium", pyq_style: bool = False):
    """ADMIN-ONLY - see module docstring. Generates question 1 and starts
    the series; subsequent questions are generated by advance_auto_quiz,
    which must ALSO only ever be called from the admin's own session."""
    q_data = generate_question(subject, topic, difficulty=difficulty, pyq_style=pyq_style)
    db["quiz_state"] = _empty_quiz_state()
    db["quiz_state"].update({
        "active": True,
        "question_data": q_data,
        "timer_seconds": timer_seconds,
        "question_start_time": time.time(),
        "auto_mode": True,
        "subject": subject,
        "topic": topic,
        "difficulty": difficulty,
        "pyq_style": pyq_style,
        "total_questions": total_questions,
        "current_index": 1,
        "question_source": "ai",
    })
    _safe_save(db)


def start_bank_quiz(db, bank_questions: list, timer_seconds: int, num_questions: int = None):
    """ADMIN-ONLY - see module docstring. bank_questions is NOT persisted
    to the database (one-time-use, per-session) - only the shuffled draw
    order is tracked in quiz_state so the running quiz survives reruns."""
    count = len(bank_questions) if num_questions is None else min(num_questions, len(bank_questions))
    order = list(range(len(bank_questions)))
    random.shuffle(order)
    order = order[:count]

    first_q = bank_questions[order[0]]
    db["quiz_state"] = _empty_quiz_state()
    db["quiz_state"].update({
        "active": True,
        "question_data": first_q,
        "timer_seconds": timer_seconds,
        "question_start_time": time.time(),
        "auto_mode": True,
        "total_questions": count,
        "current_index": 1,
        "question_source": "bank",
        "bank_order": order,
    })
    _safe_save(db)


def advance_auto_quiz(db):
    """ADMIN-ONLY - see module docstring for why this is critical. Calling
    this from more than one session concurrently is exactly what crashed
    the app previously (every connected student's browser independently
    generating + overwriting 'question 2' at once)."""
    qs = db["quiz_state"]
    if qs["current_index"] >= qs["total_questions"]:
        clear_quiz(db)
        return

    if qs.get("question_source") == "bank":
        bank = st.session_state.get("question_bank", [])
        order = qs.get("bank_order", [])
        next_pos = qs["current_index"]
        if next_pos >= len(order) or not bank:
            clear_quiz(db)
            return
        q_data = bank[order[next_pos]]
    else:
        q_data = generate_question(
            qs["subject"], qs["topic"],
            difficulty=qs.get("difficulty", "Medium"),
            pyq_style=qs.get("pyq_style", False),
        )

    qs["question_data"] = q_data
    qs["answers"] = {}
    qs["answer_times"] = {}
    qs["revealed"] = False
    qs["question_start_time"] = time.time()
    qs["current_index"] += 1
    _safe_save(db)


def time_left(db) -> float:
    """Seconds remaining on the current question's timer. None if untimed."""
    qs = db["quiz_state"]
    if not qs.get("timer_seconds"):
        return None
    elapsed = time.time() - qs.get("question_start_time", time.time())
    remaining = qs["timer_seconds"] - elapsed
    return max(0, remaining)


def is_time_up(db) -> bool:
    tl = time_left(db)
    return tl is not None and tl <= 0


def submit_answer(db, username: str, choice: str):
    """Safe to call from ANY session - this is the one quiz.py function
    every student's browser is expected to call, for themselves only."""
    qs = db["quiz_state"]
    qs["answers"][username] = choice
    if qs.get("timer_seconds"):
        elapsed = time.time() - qs.get("question_start_time", time.time())
        qs["answer_times"][username] = round(max(0, elapsed), 1)
    _safe_save(db)


def lock_and_reveal(db):
    """ADMIN-ONLY - see module docstring."""
    q_data = db["quiz_state"]["question_data"]
    for student, answer in db["quiz_state"]["answers"].items():
        if student not in db["users"]:
            continue
        if answer == q_data["answer"]:
            db["current_session_scores"][student] = db["current_session_scores"].get(student, 0) + 4
            db["users"][student]["lifetime_score"] += 4
        else:
            db["current_session_scores"][student] = db["current_session_scores"].get(student, 0) - 1
            db["users"][student]["lifetime_score"] -= 1
    db["quiz_state"]["revealed"] = True
    _safe_save(db)


# ----------------------------------------------------------------------
# FULL-LENGTH TIMED TESTS + DPPs (mock exams / daily practice - professional
# exam UX, PERMANENT ARCHIVE, unlimited reattempts)
# ----------------------------------------------------------------------
# Fundamentally different model from the live quiz above:
#   - The ENTIRE question set is generated up front, before the test opens
#     to students - nothing is generated live while a student is sitting
#     the test, so a slow AI call can never block or time out a student
#     mid-exam.
#   - One shared clock (opened_at + duration_minutes) for full-length
#     Tests. DPPs (test_type="dpp") are untimed by design - no shared
#     clock, no per-question timer - so a student can practice a DPP at
#     3am on their own schedule, not just during a live window.
#   - Each student's answers/navigation state are tracked PER-STUDENT
#     (test["submissions"][username]), never shared - unlike the live
#     quiz's single shared question_data, because every student works
#     through the same fixed paper independently and asynchronously.
#   - PERMANENT ARCHIVE + UNLIMITED REATTEMPTS: nothing in full_tests is
#     ever deleted, so every test/DPP ever run stays available forever for
#     students to revisit. A student can retake the same test/DPP as many
#     times as they want - each finished attempt is graded, but only the
#     BEST-SCORING attempt is kept as sub["best"] (shown on leaderboards
#     and in "Past Tests"). Older attempts are not individually retained
#     (this app tracks best score, not a full attempt-by-attempt log) -
#     the in-progress attempt fields (answers/marked_for_review/started_at)
#     reset cleanly on every new attempt so retaking never corrupts the
#     best score already banked.

def create_full_test(db, title: str, questions: list, duration_minutes: int,
                      marks_correct: float = 4, marks_wrong: float = -1,
                      test_type: str = "test") -> str:
    """ADMIN-ONLY. Registers a new full-length test or DPP (questions
    already generated/collected by the caller). Created in "draft" status
    so the admin can review before students can see it - open_full_test
    activates it.

    test_type: "test" (full-length, shared timed clock) or "dpp" (Daily
    Practice Problem - untimed, no shared clock, students work through it
    at their own pace whenever it's open). Both types share every other
    mechanic below: permanent archive, unlimited best-score reattempts,
    leaderboard, review."""
    test_id = uuid.uuid4().hex[:10]
    db.setdefault("full_tests", {})
    db["full_tests"][test_id] = {
        "id": test_id,
        "title": title,
        "test_type": test_type,  # "test" or "dpp"
        "questions": questions,  # [{question, options, answer, explanation}, ...]
        "duration_minutes": duration_minutes,  # DPPs: still stored, just not clocked against students
        "marks_correct": marks_correct,
        "marks_wrong": marks_wrong,
        "status": "draft",  # draft -> open -> closed
        "opened_at": None,
        "created_at": time.time(),
        "submissions": {},  # username -> {answers, marked_for_review, started_at, submitted_at, best: {...} or None}
    }
    _safe_save(db)
    return test_id


def open_full_test(db, test_id: str):
    """ADMIN-ONLY. Makes the test/DPP visible/attemptable to students. For
    a timed Test this also starts the shared countdown clock; DPPs ignore
    the clock entirely (untimed by design) so they stay attemptable
    indefinitely once opened - and since nothing is ever deleted, closing
    one later just stops NEW attempts, past results and the archive stay
    intact forever either way."""
    test = db["full_tests"][test_id]
    test["status"] = "open"
    test["opened_at"] = time.time()
    _safe_save(db)


def close_full_test(db, test_id: str):
    """ADMIN-ONLY. Stops new attempts. For a timed Test, any student still
    mid-attempt is auto-submitted with whatever they had filled in so far.
    A single malformed/corrupt submission can no longer abort grading for
    everyone else - each student's finalize is isolated so one bad record
    doesn't block the rest.

    The test/DPP itself is NEVER deleted - closing only stops new
    attempts. Students can still browse it forever under Past
    Tests/DPPs, and it stays fully reviewable (own answers + explanations)."""
    test = db["full_tests"][test_id]
    for username, sub in test["submissions"].items():
        if sub.get("submitted_at") is None:
            try:
                _grade_and_finalize_submission(test, sub)
            except Exception:
                # Don't let one corrupt submission stop the rest of the
                # class from being graded and the test from closing.
                continue
    test["status"] = "closed"
    _safe_save(db)


def full_test_time_left(db, test_id: str) -> float:
    """Seconds remaining on the shared test clock. None if not open, or if
    this is an untimed DPP (DPPs never have a countdown)."""
    test = db["full_tests"][test_id]
    if test.get("test_type") == "dpp":
        return None
    if test["status"] != "open" or not test.get("opened_at"):
        return None
    elapsed = time.time() - test["opened_at"]
    remaining = test["duration_minutes"] * 60 - elapsed
    return max(0, remaining)


def _fresh_attempt_fields() -> dict:
    return {
        "answers": {},            # question_index (str) -> chosen option text
        "marked_for_review": [],  # list of question_index (int)
        "started_at": time.time(),
        "submitted_at": None,
    }


def start_full_test_attempt(db, test_id: str, username: str):
    """Safe to call from a student's own session. Creates that student's
    per-user submission record the first time they open the test/DPP.

    UNLIMITED REATTEMPTS: if the student already has a finished attempt
    (submitted_at is set), this starts a brand new attempt - the previous
    finished attempt's score has already been folded into sub["best"] (see
    submit_full_test), so nothing is lost by resetting the working fields.
    If they have an attempt already IN PROGRESS, this is a no-op so a
    stray rerun never wipes their unsaved progress."""
    test = db["full_tests"][test_id]
    sub = test["submissions"].get(username)

    if sub is not None and sub.get("submitted_at") is None:
        return  # already mid-attempt - don't wipe progress

    fresh = _fresh_attempt_fields()
    if sub is not None:
        fresh["best"] = sub.get("best")  # carry the best score forward across reattempts
        fresh["attempt_count"] = sub.get("attempt_count", 0)
    else:
        fresh["best"] = None
        fresh["attempt_count"] = 0
    test["submissions"][username] = fresh
    _safe_save(db)


def save_full_test_answer(db, test_id: str, username: str, question_index: int, choice: str):
    """Safe to call from a student's own session - only ever touches that
    student's OWN submission dict, never anyone else's, so concurrent
    students answering simultaneously never collide.

    NOTE ON LOAD: prefer sync_full_test_progress() from the UI layer for
    normal answer-saving during a test - it batches many answer changes
    into one write instead of hitting the database on every click, which
    matters a lot once a whole class is answering concurrently. This
    function is still here for the immediate single-write case (e.g. the
    final flush on Submit)."""
    test = db["full_tests"][test_id]
    sub = test["submissions"].get(username)
    if not sub or sub.get("submitted_at") is not None:
        return
    sub["answers"][str(question_index)] = choice
    _safe_save(db)


def sync_full_test_progress(db, test_id: str, username: str, answers: dict, marked_for_review: list):
    """Batched write: overwrites this student's ENTIRE answers dict and
    marked-for-review list in one save, instead of one database write per
    option click. The UI layer keeps live edits in st.session_state and
    calls this only at natural checkpoints (moving to another question,
    submitting, or a periodic autosave) - cuts database writes from
    'every click' to a small handful per test attempt, which is the
    single biggest thing protecting the app from load-related slowdowns
    during a live class taking a test together."""
    test = db["full_tests"][test_id]
    sub = test["submissions"].get(username)
    if not sub or sub.get("submitted_at") is not None:
        return
    sub["answers"] = dict(answers)
    sub["marked_for_review"] = list(marked_for_review)
    _safe_save(db)


def toggle_mark_for_review(db, test_id: str, username: str, question_index: int):
    """Safe to call from a student's own session."""
    test = db["full_tests"][test_id]
    sub = test["submissions"].get(username)
    if not sub or sub.get("submitted_at") is not None:
        return
    marked = sub.setdefault("marked_for_review", [])
    if question_index in marked:
        marked.remove(question_index)
    else:
        marked.append(question_index)
    _safe_save(db)


def _grade_and_finalize_submission(test: dict, sub: dict):
    """Pure in-memory grading - caller is responsible for save_db().
    Grades the CURRENT working attempt, then folds it into sub["best"] if
    it beats (or is the first-ever) attempt - so sub["best"] always holds
    the single highest-scoring attempt this student has ever made on this
    test/DPP, no matter how many times they retake it."""
    questions = test["questions"]
    correct = wrong = unattempted = 0
    for i, q in enumerate(questions):
        chosen = sub["answers"].get(str(i))
        if chosen is None:
            unattempted += 1
        elif chosen == q["answer"]:
            correct += 1
        else:
            wrong += 1
    score = correct * test["marks_correct"] + wrong * test["marks_wrong"]
    submitted_at = time.time()

    this_attempt = {
        "answers": dict(sub["answers"]),
        "score": score,
        "correct_count": correct,
        "wrong_count": wrong,
        "unattempted_count": unattempted,
        "started_at": sub["started_at"],
        "submitted_at": submitted_at,
    }

    previous_best = sub.get("best")
    if previous_best is None or score > previous_best["score"]:
        sub["best"] = this_attempt

    sub["attempt_count"] = sub.get("attempt_count", 0) + 1
    sub["submitted_at"] = submitted_at  # marks the CURRENT attempt as finished


def submit_full_test(db, test_id: str, username: str):
    """Safe to call from a student's own session - grades and finalizes
    ONLY that student's own submission, updating their best score if this
    attempt beat it. Idempotent: calling twice (e.g. a double-click)
    doesn't re-grade or overwrite an already-submitted attempt."""
    test = db["full_tests"][test_id]
    sub = test["submissions"].get(username)
    if not sub or sub.get("submitted_at") is not None:
        return
    _grade_and_finalize_submission(test, sub)
    _safe_save(db)


def get_full_test_leaderboard(test: dict) -> list:
    """Ranked list of (username, score, correct, wrong, unattempted,
    time_taken_seconds) using each student's BEST-EVER attempt on this
    test/DPP - so retaking it to improve your score is reflected here,
    not just your latest attempt."""
    rows = []
    for username, sub in test["submissions"].items():
        best = sub.get("best")
        if best is None:
            continue
        time_taken = best["submitted_at"] - best["started_at"]
        rows.append((username, best["score"], best["correct_count"], best["wrong_count"], best["unattempted_count"], time_taken))
    rows.sort(key=lambda r: (-r[1], r[5]))  # highest score first, tie-break by faster time
    return rows


def render_full_test_leaderboard(test: dict, highlight_user: str = None):
    """Same visual styling as render_leaderboard, for a specific full-length
    test's results rather than the running session scores."""
    import html as html_lib

    rows = get_full_test_leaderboard(test)
    if not rows:
        st.caption("No submissions yet.")
        return

    rows_html = []
    for i, (username, score, correct, wrong, unattempted, time_taken) in enumerate(rows):
        rank = i + 1
        is_top3 = rank <= 3
        is_me = highlight_user is not None and username == highlight_user
        row_classes = "lb-row" + (" top3" if is_top3 else "") + (" me" if is_me else "")
        rank_classes = "lb-rank" + (" top3" if is_top3 else "")
        mins = int(time_taken // 60)
        display_name = html_lib.escape(username.capitalize()) + (" (You)" if is_me else "")

        rows_html.append(
            f"<div class='{row_classes}'>"
            f"<div class='{rank_classes}'>#{rank}</div>"
            f"<div class='lb-name'>{display_name}</div>"
            f"<div class='lb-meta'>{correct} correct - {wrong} wrong - {unattempted} skipped - {mins} min</div>"
            f"<div class='lb-score'>{score} pts</div>"
            f"</div>"
        )

    st.markdown("".join(rows_html), unsafe_allow_html=True)


# ----------------------------------------------------------------------
# LEADERBOARD (live-quiz session scores - see get_full_test_leaderboard
# above for the separate full-test leaderboard)
# ----------------------------------------------------------------------

def render_leaderboard(db, highlight_user: str = None):
    """Ranked leaderboard by current session score, with lifetime score
    shown alongside for context. Top 3 get a distinct rank style; the
    logged-in student's own row is highlighted."""
    import html as html_lib

    session_scores = db.get("current_session_scores", {})
    all_students = [u for u, info in db["users"].items() if info["role"] == "student"]

    if not all_students:
        st.caption("No students yet.")
        return

    ranked = sorted(all_students, key=lambda u: session_scores.get(u, 0), reverse=True)

    st.markdown("#### Today's Session")
    rows_html = []
    for i, student in enumerate(ranked):
        rank = i + 1
        is_top3 = rank <= 3
        is_me = highlight_user is not None and student == highlight_user
        row_classes = "lb-row" + (" top3" if is_top3 else "") + (" me" if is_me else "")
        rank_classes = "lb-rank" + (" top3" if is_top3 else "")

        session_pts = session_scores.get(student, 0)
        lifetime_pts = db["users"][student].get("lifetime_score", 0)
        display_name = html_lib.escape(student.capitalize()) + (" (You)" if is_me else "")

        rows_html.append(
            f"<div class='{row_classes}'>"
            f"<div class='{rank_classes}'>#{rank}</div>"
            f"<div class='lb-name'>{display_name}</div>"
            f"<div class='lb-meta'>{lifetime_pts} lifetime</div>"
            f"<div class='lb-score'>{session_pts} pts</div>"
            f"</div>"
        )

    st.markdown("".join(rows_html), unsafe_allow_html=True)
