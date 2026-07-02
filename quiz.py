"""
quiz.py
Groq-powered NEET question generation, scoring, and timed auto-quiz logic.

QUESTION SOURCES:
Auto quiz can pull questions from two places, controlled by
db["quiz_state"]["question_source"]:
  - "ai"   : generated live via Groq, one at a time (original behavior)
  - "bank" : drawn from an admin-pasted question bank
             (st.session_state.question_bank, NOT saved to database.json —
             it's a one-time-use, per-session set as requested)

ACCURACY SAFEGUARDS FOR AI-GENERATED QUESTIONS:
Two independent fixes, because "the AI got it wrong" for NEET quizzes
usually means one of two different bugs:

1. POSITIONAL BIAS: small/fast models often place the correct answer in
   the same option slot (commonly "A") far more often than random chance
   would predict. This is a known failure mode, not a content error - the
   question and answer can both be individually correct while still being
   predictable. Fix: after generation, we shuffle the options ourselves in
   code and move the answer along with them, so whatever bias the model has
   never reaches the student.

2. FACTUAL ACCURACY: the question/options/answer/explanation need to be
   scientifically correct. No amount of prompting makes a model incapable
   of error. What we CAN do: ask a second, independent completion to check
   the first one's work before anything is shown to students. This roughly
   doubles latency and API cost per question, which was a deliberate
   tradeoff (accuracy over speed) - see README for details.

Neither fix makes AI questions as trustworthy as a human-verified question
bank. If a quiz is high-stakes, use "My Question Bank" mode instead.

TIMER PRECISION NOTE:
The timer is derived from a shared `question_start_time` timestamp stored in
the database, not a client-side JS countdown. Every connected browser (admin
and all students) computes `time_left` the same way on each autorefresh tick,
so everyone sees the same countdown without needing a separate sync system.
The tradeoff: because the app only refreshes every few seconds (see
AUTOREFRESH_MS in config.py), the auto-reveal can fire up to ~3 seconds late,
and a student's "time to answer" is accurate to the second but the on-screen
countdown updates in ~3-second steps rather than smoothly. This is normal
for a Streamlit app (it doesn't have a persistent live connection like a
game server would) and doesn't affect scoring fairness, since everyone is
bound by the same shared clock.
"""

import json
import random
import re
import time
import streamlit as st
from groq import Groq

from database import save_db


def get_groq_client():
    """
    Reads the API key from Streamlit secrets (.streamlit/secrets.toml),
    NEVER hardcode the key in source — see README.md for setup.
    """
    api_key = st.secrets.get("GROQ_API_KEY")
    if not api_key:
        st.error(
            "⚠️ GROQ_API_KEY is not configured. Add it to `.streamlit/secrets.toml` "
            "(locally) or in your Streamlit Cloud app's Secrets settings."
        )
        st.stop()
    return Groq(api_key=api_key)


# ----------------------------------------------------------------------
# AI GENERATION — with shuffle-bias fix + independent verification pass
# ----------------------------------------------------------------------

def _shuffle_options(q_data: dict) -> dict:
    """
    Re-orders the options randomly and relocates the answer to match, so
    the model's own positional bias (e.g. "answer is always A") can never
    reach the student. Does nothing to the question/explanation text.
    """
    options = list(q_data["options"])
    correct_text = q_data["answer"]

    if correct_text not in options:
        # Model returned an answer that doesn't match any option verbatim.
        # Don't silently guess — let the caller's validation catch this.
        return q_data

    shuffled = options[:]
    random.shuffle(shuffled)

    q_data = dict(q_data)
    q_data["options"] = shuffled
    q_data["answer"] = correct_text  # still the same text, just now at a new index
    return q_data


# Stems that promise statement/assertion content is coming ("Given below are
# two statements:", "Read the assertion and reason below:", etc.). If the
# question text ends right after one of these phrases (allowing only a
# trailing colon/whitespace), the model dropped the actual statement text —
# a known small-model failure mode. Caught here so it's retried instead of
# ever reaching a student as an unanswerable question.
_DANGLING_STEM_RE = re.compile(
    r"(given\s+below\s+are|consider\s+the\s+following|read\s+the\s+following|"
    r"read\s+the\s+assertion|assertion\s*\(a\)|two\s+statements|three\s+statements)"
    r"[^.]{0,15}[:\-]?\s*$",
    re.IGNORECASE,
)


def _has_dangling_statement_stem(question_text: str) -> bool:
    return bool(_DANGLING_STEM_RE.search(question_text.strip()))


def _validate_question_shape(q_data: dict) -> bool:
    """Structural check: 4 options, answer text exactly matches one of them,
    and (for statement/assertion-style stems) the actual statement text is
    present rather than dropped."""
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


def _generate_raw(client, subject: str, topic: str) -> dict:
    prompt = f"""Generate 1 tough NEET multiple choice question for {subject} on the chapter/topic "{topic}".
Be scientifically precise. Double check the correct answer is actually correct before responding.

You may use any standard NEET question style, including assertion-reason questions and
two/three-statement "which of the following is/are correct" questions. This is exactly why the
"question" field rule below matters.

CRITICAL RULE FOR THE "question" FIELD:
The "question" field must be a SINGLE, FULLY SELF-CONTAINED STRING that includes every piece of
text a student needs in order to answer — there is no separate field for statements, assertions,
or reasons, so nothing outside "question" and "options" is ever shown to the student.
- If this is a statement-based question ("Given below are two/three statements..."), the "question"
  string MUST include the complete text of every statement, numbered (Statement I: ..., Statement II: ...).
- If this is an assertion-reason question, the "question" string MUST include the full text of both
  the Assertion (A) and the Reason (R) written out in full, not just the labels "Assertion" and "Reason".
- NEVER write a stem like "Given below are two statements:" or "Read the assertion and reason
  below:" without immediately writing out the full statement/assertion/reason text right after it,
  inside that same "question" string. A stem with no content after it is an invalid question.
- The "options" array should then contain only the final answer choices (e.g. "Both I and II are
  correct", "A is true but R is false"), never the statements themselves.

Output ONLY valid JSON in this exact shape, nothing else:
{{"question": "text (fully self-contained, including any statements/assertion/reason spelled out in full)", "options": ["option 1", "option 2", "option 3", "option 4"], "answer": "exact correct option text, copied verbatim from options", "explanation": "Why it is correct, and briefly why the other options are wrong"}}"""

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def _verify_question(client, q_data: dict) -> dict:
    """
    Independent second pass: shows the model the question + options + the
    first pass's proposed answer, and asks it to verify or correct it -
    it's asked to re-derive the answer itself from scratch, not just agree.

    Returns a (possibly corrected) q_data dict. If the verifier's answer
    doesn't match any option (malformed response), q_data["_verified"] is
    set to False so callers can retry rather than trust an unclear result.
    """
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

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        response_format={"type": "json_object"},
    )
    verified = json.loads(response.choices[0].message.content)

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


def generate_question(subject: str, topic: str, max_attempts: int = 3) -> dict:
    """
    Full pipeline: generate -> shuffle (bias fix) -> verify (accuracy pass).
    Retries up to max_attempts times if the structural shape is ever invalid,
    since a malformed response should never be shown to a student rather
    than silently guessing at a fix.
    """
    client = get_groq_client()
    last_error = None

    for attempt in range(max_attempts):
        try:
            q_data = _generate_raw(client, subject, topic)
            q_data = _shuffle_options(q_data)

            if not _validate_question_shape(q_data):
                last_error = "Malformed question shape from generation step"
                continue

            q_data = _verify_question(client, q_data)

            if not _validate_question_shape(q_data):
                last_error = "Malformed question shape from verification step"
                continue

            return q_data
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            last_error = str(e)
            continue

    st.error(f"⚠️ Could not generate a reliable question after {max_attempts} attempts ({last_error}). Try again or use your own question bank.")
    st.stop()


# ----------------------------------------------------------------------
# QUESTION BANK — admin-pasted, plain-text parsing
# ----------------------------------------------------------------------

_OPTION_PREFIX_RE = re.compile(r"^\s*[\(\[]?([A-Da-d])[\)\].:\-]\s*")
_ANSWER_LETTER_RE = re.compile(r"^\s*([A-Da-d])\b")


def _strip_option_prefix(line: str) -> str:
    """Strips leading 'A)', 'A.', '(A)', 'A -' style prefixes from an option line."""
    return _OPTION_PREFIX_RE.sub("", line).strip()


def parse_pasted_questions(raw_text: str) -> tuple:
    """
    Parses a plain-text block of NEET-style questions into the same
    {question, options, answer, explanation} shape used everywhere else.

    Expected per-question format (blank line separates questions):
        Q: What is the powerhouse of the cell?
        A) Nucleus
        B) Mitochondria
        C) Ribosome
        D) Golgi body
        Answer: B
        Explanation: Mitochondria generate ATP via oxidative phosphorylation.

    The "Answer:" line is resolved by POSITION (A = 1st option line, B = 2nd,
    etc.), never by re-matching text - this keeps behavior correct even if
    two options happen to have similar wording, and keeps shuffling safe
    later since we always operate on the resolved option TEXT after parsing.

    Returns (parsed_questions, errors):
      parsed_questions: list of valid {question, options, answer, explanation} dicts
      errors: list of human-readable strings describing any block that
              failed to parse, including which block number and why -
              malformed blocks are skipped, never guessed at.
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
            # lines matching nothing above are ignored (e.g. stray blank text)

        if question_text is None:
            errors.append(f"Block {block_num}: no line starting with 'Q:' found — skipped.")
            continue
        if len(options) != 4:
            errors.append(f"Block {block_num} (\"{question_text[:40]}...\"): found {len(options)} options, need exactly 4 — skipped.")
            continue
        if answer_letter is None:
            errors.append(f"Block {block_num} (\"{question_text[:40]}...\"): no valid 'Answer: A/B/C/D' line found — skipped.")
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
# MANUAL (single question, admin reveals manually) — original behavior
# ----------------------------------------------------------------------

def start_quiz(db, q_data: dict, timer_seconds: int = 0):
    db["quiz_state"] = {
        "active": True,
        "question_data": q_data,
        "answers": {},
        "answer_times": {},
        "revealed": False,
        "timer_seconds": timer_seconds,
        "question_start_time": time.time() if timer_seconds else 0,
        "auto_mode": False,
        "subject": None,
        "topic": None,
        "total_questions": 0,
        "current_index": 0,
        "question_source": "ai",
    }
    save_db(db)


def clear_quiz(db):
    db["quiz_state"] = {
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
    }
    save_db(db)


# ----------------------------------------------------------------------
# AUTO QUIZ (N questions, one at a time, shared countdown timer)
# ----------------------------------------------------------------------

def start_auto_quiz(db, subject: str, topic: str, total_questions: int, timer_seconds: int):
    """Kicks off an AI-generated auto quiz set and generates the first question."""
    q_data = generate_question(subject, topic)
    db["quiz_state"] = {
        "active": True,
        "question_data": q_data,
        "answers": {},
        "answer_times": {},
        "revealed": False,
        "timer_seconds": timer_seconds,
        "question_start_time": time.time(),
        "auto_mode": True,
        "subject": subject,
        "topic": topic,
        "total_questions": total_questions,
        "current_index": 1,
        "question_source": "ai",
    }
    save_db(db)


def start_bank_quiz(db, bank_questions: list, timer_seconds: int, num_questions: int = None):
    """
    Kicks off an auto quiz set drawn from an admin-pasted question bank.
    bank_questions is NOT stored in db/database.json (one-time-use, per
    the "used for that quiz only, then discarded" requirement) - only the
    draw order (a shuffled list of indices) is tracked in db["quiz_state"]
    so the running quiz can survive autorefresh reruns within the session.
    The actual question bank stays in st.session_state.question_bank.
    """
    count = len(bank_questions) if num_questions is None else min(num_questions, len(bank_questions))
    order = list(range(len(bank_questions)))
    random.shuffle(order)
    order = order[:count]

    first_q = bank_questions[order[0]]
    db["quiz_state"] = {
        "active": True,
        "question_data": first_q,
        "answers": {},
        "answer_times": {},
        "revealed": False,
        "timer_seconds": timer_seconds,
        "question_start_time": time.time(),
        "auto_mode": True,
        "subject": None,
        "topic": None,
        "total_questions": count,
        "current_index": 1,
        "question_source": "bank",
        "bank_order": order,
    }
    save_db(db)


def advance_auto_quiz(db):
    """Generates/loads the next question in the set, or ends the set if finished."""
    qs = db["quiz_state"]
    if qs["current_index"] >= qs["total_questions"]:
        clear_quiz(db)
        return

    if qs.get("question_source") == "bank":
        bank = st.session_state.get("question_bank", [])
        order = qs.get("bank_order", [])
        next_pos = qs["current_index"]  # 0-indexed into order for the NEXT question
        if next_pos >= len(order) or not bank:
            clear_quiz(db)
            return
        q_data = bank[order[next_pos]]
    else:
        q_data = generate_question(qs["subject"], qs["topic"])

    qs["question_data"] = q_data
    qs["answers"] = {}
    qs["answer_times"] = {}
    qs["revealed"] = False
    qs["question_start_time"] = time.time()
    qs["current_index"] += 1
    save_db(db)


def time_left(db) -> float:
    """Seconds remaining on the current question's timer. 0 if untimed."""
    qs = db["quiz_state"]
    if not qs.get("timer_seconds"):
        return None
    elapsed = time.time() - qs.get("question_start_time", time.time())
    remaining = qs["timer_seconds"] - elapsed
    return max(0, remaining)


def is_time_up(db) -> bool:
    tl = time_left(db)
    return tl is not None and tl <= 0


# ----------------------------------------------------------------------
# SHARED: answering + scoring
# ----------------------------------------------------------------------

def submit_answer(db, username: str, choice: str):
    qs = db["quiz_state"]
    qs["answers"][username] = choice
    if qs.get("timer_seconds"):
        elapsed = time.time() - qs.get("question_start_time", time.time())
        qs["answer_times"][username] = round(max(0, elapsed), 1)
    save_db(db)


def lock_and_reveal(db):
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
    save_db(db)
