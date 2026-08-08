"""
question_parser.py
Parses admin-pasted questions into the {question, options, answer,
explanation} shape database.add_questions() expects directly, with no
reshaping needed at the call site.

This is a self-contained port of the same parsing logic already proven
out in the Telegram bot's question_engine.py — duplicated here rather
than imported cross-repo, since the website and the bot are separate
codebases/deployments with no shared package between them. If you fix a
parsing edge case in one, mirror the fix in the other.

FORMAT FLEXIBILITY — this parser is deliberately permissive about
*labeling* punctuation (Q1. vs Q: vs Question 1) because admins paste
from wildly different sources (books, other test banks, PDFs) that
each pick their own convention. It is NOT permissive about *content* —
every line's actual text (including any math/physics/chemistry
notation: H₂O, x², Δ, →, ⇌, °C, mol/L, √, ±, μ, subscripts/
superscripts, etc.) is passed through completely untouched. Only the
handful of characters that are the recognized LABEL punctuation itself
(a leading "Q1.", "A)", "Answer:", ...) are ever stripped, via
anchored ^-prefix regexes that only look at the start of a line — so a
chemistry option like "A) Ka = [H+][A-]/[HA]" only ever loses the
leading "A) ", never anything inside the option text itself, even
though that text also contains a "-" and other symbols identical in
shape to option-prefix punctuation.
"""

import re

# ---- Question-start line, e.g. "Q:", "Q.", "Q1.", "Q1)", "Q 1.",
# "Question 1:", "Question:" — optional number, optional space before
# the number, then one of . ) : as the closing punctuation.
_QUESTION_START_RE = re.compile(
    r"^(q(?:uestion)?\s*\d*\s*[.):]|\d+\s*[.)])\s*", re.IGNORECASE
)

# Stricter than _QUESTION_START_RE: only the "Q"/"Question"-prefixed
# forms, never a bare number. Used specifically for detecting NEW-
# QUESTION BOUNDARIES inside an already-fused multi-question block (see
# _split_fused_questions) — a bare "1." or "2." there is far more
# likely to be a match-the-following/numbered-sub-point line INSIDE one
# question (confirmed real case: "Match the following: 1. Mitochondria
# - Powerhouse") than an actual second question starting with no blank
# line at all. A "Q"/"Question" prefix is a much stronger, safer signal
# of a genuine new question and won't misfire on that pattern.
_QUESTION_BOUNDARY_RE = re.compile(
    r"^q(?:uestion)?\s*\d*\s*[.):]\s*", re.IGNORECASE
)

# ---- Option line, e.g. "A)", "A.", "A-", "(A)", "a)" — letter may be
# bare or wrapped in parentheses.
_OPTION_PREFIX_RE = re.compile(r"^\(?([A-Da-d])[).\-]\s*")

# ---- Answer line, e.g. "Answer: B", "Ans: B", "Correct Answer: B",
# "Correct option: B", "Answer - B". Captures the whole remainder so a
# non-letter answer (books that write out the full option text instead
# of a letter) can be matched against the option texts as a fallback.
_ANSWER_LINE_RE = re.compile(
    r"^(?:correct\s+)?(?:answer|ans|option)\s*[:\-]\s*", re.IGNORECASE
)
_ANSWER_LETTER_RE = re.compile(r"^\(?([A-Da-d])\)?\b")

_EXPLANATION_LINE_RE = re.compile(r"^(?:explanation|solution)\s*[:\-]\s*", re.IGNORECASE)


def _strip_option_prefix(line: str) -> str:
    return _OPTION_PREFIX_RE.sub("", line).strip()


def _normalize(raw_text: str) -> str:
    """Books/other test banks are frequently pasted with Windows CRLF
    line endings (confirmed on real uploaded files) — leaving a stray
    \\r on every line doesn't break the regexes above (they don't
    anchor on $), but it DOES survive into stored question/option text
    and shows up as an invisible corrupted-looking character later.
    Normalizing here, once, up front, is simpler than guarding every
    downstream string operation against it."""
    return raw_text.replace("\r\n", "\n").replace("\r", "\n")


def _split_fused_questions(block: str) -> list:
    """Blank-line splitting (the caller's first pass) assumes every
    question is separated from the next by an empty line. Pasted
    sources don't always add that blank line — an Explanation: line can
    run straight into the next question start with zero gap, which would
    otherwise show up as "found 8 options, need exactly 4" and silently
    drop BOTH questions instead of just the malformed one. This
    re-splits at every line that starts a new question, so a fused
    block becomes clean sub-blocks each parsed normally. A block with
    only one such line (the normal case) is returned unchanged."""
    lines = block.splitlines()
    starts = [i for i, l in enumerate(lines) if _QUESTION_BOUNDARY_RE.match(l.strip())]
    if len(starts) <= 1:
        return [block]
    sub_blocks = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        sub_blocks.append("\n".join(lines[start:end]))
    return sub_blocks


def parse_pasted_questions(raw_text: str):
    """Accepts a wide range of per-question label formats, mixed
    freely in the same paste — e.g. all of these start a question:
        Q: What is the powerhouse of the cell?
        Q. What is the powerhouse of the cell?
        Q1. What is the powerhouse of the cell?
        Q1) What is the powerhouse of the cell?
        Question 1: What is the powerhouse of the cell?
        1. What is the powerhouse of the cell?
    ...followed by 4 options in any of these forms (mixing forms
    within one question is fine too):
        A) Nucleus       A. Nucleus       (A) Nucleus       a) Nucleus
    ...then an answer line in any of these forms:
        Answer: B        Ans: B        Correct Answer: B        Answer: Mitochondria
    ...then an optional explanation:
        Explanation: Mitochondria generate ATP via oxidative phosphorylation.
        Solution: ...

    Multi-line question text (statements, assertion-reason, match-the-
    following) is handled — every line between the question start and
    the first option line is kept as part of the question, not
    discarded. Math/physics/chemistry notation (H₂O, x², Δ, →, ⇌, °C,
    mol/L, √, ±, μ, sub/superscripts, etc.) is preserved exactly as
    pasted — this parser only ever strips recognized LABEL punctuation
    from the start of a line, never touches characters inside the
    question/option/explanation text itself.

    Returns (parsed_questions, errors) — malformed blocks are skipped and
    reported by number/preview text, never guessed at or silently
    dropped without explanation."""
    raw_text = _normalize(raw_text)
    raw_blocks = re.split(r"\n\s*\n", raw_text.strip())
    blocks = []
    for raw_block in raw_blocks:
        blocks.extend(_split_fused_questions(raw_block))
    parsed = []
    errors = []

    for block_num, block in enumerate(blocks, start=1):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue

        question_lines = []
        options = []
        answer_letter = None
        answer_raw = None  # remainder of the Answer: line, for the full-text fallback
        explanation_lines = []
        collecting_question = False
        collecting_explanation = False

        for line in lines:
            is_option_line = _OPTION_PREFIX_RE.match(line)
            is_question_start = _QUESTION_START_RE.match(line)
            is_answer_line = _ANSWER_LINE_RE.match(line)
            is_explanation_line = _EXPLANATION_LINE_RE.match(line)

            if is_question_start and not question_lines:
                # Only treat this as THE question-start line the first
                # time — a later line that happens to also look like
                # "1. ..." (e.g. a numbered sub-point inside the
                # question itself) should just fall through to being
                # ordinary question text instead of resetting things.
                first_piece = _QUESTION_START_RE.sub("", line).strip()
                if first_piece:
                    question_lines.append(first_piece)
                collecting_question = True
                collecting_explanation = False
            elif is_answer_line:
                remainder = _ANSWER_LINE_RE.sub("", line).strip()
                answer_raw = remainder
                m = _ANSWER_LETTER_RE.match(remainder)
                if m:
                    answer_letter = m.group(1).upper()
                collecting_question = False
                collecting_explanation = False
            elif is_explanation_line:
                piece = _EXPLANATION_LINE_RE.sub("", line).strip()
                if piece:
                    explanation_lines.append(piece)
                collecting_explanation = True
                collecting_question = False
            elif is_option_line:
                options.append(_strip_option_prefix(line))
                collecting_question = False
                collecting_explanation = False
            elif collecting_explanation:
                explanation_lines.append(line)
            elif collecting_question or (question_lines and not options):
                question_lines.append(line)
            # else: stray text outside any recognized section — ignored.

        question_text = "\n".join(question_lines).strip() if question_lines else None
        explanation = "\n".join(explanation_lines).strip()

        if question_text is None:
            preview = block.strip().splitlines()[0][:40] if block.strip() else ""
            errors.append(f"Block {block_num} (\"{preview}...\"): no recognizable question-start line found (expected something like 'Q:', 'Q1.', or 'Question 1:') — skipped.")
            continue
        if len(options) != 4:
            errors.append(f"Block {block_num} (\"{question_text[:40]}...\"): found {len(options)} options, need exactly 4 — skipped.")
            continue

        if answer_letter is not None:
            letter_index = {"A": 0, "B": 1, "C": 2, "D": 3}[answer_letter]
            answer_text = options[letter_index]
        elif answer_raw:
            # Fallback for books/banks that write the answer out in full
            # instead of a letter, e.g. "Answer: Mitochondria" — matched
            # against the option texts themselves, case-insensitively,
            # since exact case can vary between the answer line and the
            # option line even within the same source.
            match = next((opt for opt in options if opt.strip().lower() == answer_raw.strip().lower()), None)
            if match is None:
                errors.append(f"Block {block_num} (\"{question_text[:40]}...\"): Answer line (\"{answer_raw[:40]}\") is neither an A/B/C/D letter nor an exact match for any of the 4 options — skipped.")
                continue
            answer_text = match
        else:
            errors.append(f"Block {block_num} (\"{question_text[:40]}...\"): no valid 'Answer: A/B/C/D' line found — skipped.")
            continue

        parsed.append({
            "question": question_text,
            "options": options,
            "answer": answer_text,
            "explanation": explanation or "No explanation provided.",
        })

    return parsed, errors

