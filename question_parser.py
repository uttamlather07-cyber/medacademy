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
"""

import re

_OPTION_PREFIX_RE = re.compile(r"^[A-Da-d][).\-]\s*")
_ANSWER_LETTER_RE = re.compile(r"^([A-Da-d])\b")
_QUESTION_START_RE = re.compile(r"^(q[:.]|question:)", re.IGNORECASE)


def _strip_option_prefix(line: str) -> str:
    return _OPTION_PREFIX_RE.sub("", line).strip()


def _split_fused_questions(block: str) -> list:
    """Blank-line splitting (the caller's first pass) assumes every
    question is separated from the next by an empty line. Pasted
    sources don't always add that blank line — an Explanation: line can
    run straight into the next "Q:" with zero gap, which would
    otherwise show up as "found 8 options, need exactly 4" and silently
    drop BOTH questions instead of just the malformed one. This
    re-splits at every line that starts a new question, so a fused
    block becomes clean sub-blocks each parsed normally. A block with
    only one such line (the normal case) is returned unchanged."""
    lines = block.splitlines()
    starts = [i for i, l in enumerate(lines) if _QUESTION_START_RE.match(l.strip())]
    if len(starts) <= 1:
        return [block]
    sub_blocks = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        sub_blocks.append("\n".join(lines[start:end]))
    return sub_blocks


def parse_pasted_questions(raw_text: str):
    """Expected format per question, blank line between each:
        Q: What is the powerhouse of the cell?
        A) Nucleus
        B) Mitochondria
        C) Ribosome
        D) Golgi body
        Answer: B
        Explanation: Mitochondria generate ATP via oxidative phosphorylation.

    Multi-line question text (statements, assertion-reason) is handled —
    every line between "Q:" and the first option line is kept as part of
    the question, not discarded.

    Returns (parsed_questions, errors) — malformed blocks are skipped and
    reported by number/preview text, never guessed at or silently
    dropped without explanation."""
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
        explanation_lines = []
        collecting_question = False
        collecting_explanation = False

        for line in lines:
            low = line.lower()
            is_option_line = _OPTION_PREFIX_RE.match(line)

            if low.startswith("q:") or low.startswith("q.") or low.startswith("question:"):
                first_piece = line.split(":", 1)[-1].strip()
                if first_piece:
                    question_lines.append(first_piece)
                collecting_question = True
                collecting_explanation = False
            elif low.startswith("answer:") or low.startswith("ans:"):
                m = _ANSWER_LETTER_RE.match(line.split(":", 1)[-1].strip())
                if m:
                    answer_letter = m.group(1).upper()
                collecting_question = False
                collecting_explanation = False
            elif low.startswith("explanation:") or low.startswith("solution:"):
                piece = line.split(":", 1)[-1].strip()
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
