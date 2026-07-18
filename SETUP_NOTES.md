# Setup notes for this rebuild

## 1. New secrets format (.streamlit/secrets.toml)

Add your Supabase credentials (unchanged) plus AI provider keys as **lists**,
so you can add as many as you want:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-supabase-key"

GROQ_API_KEYS = ["gsk_key_one", "gsk_key_two", "gsk_key_three"]
GEMINI_API_KEYS = ["AIza_key_one", "AIza_key_two"]
```

A single key as a plain string also still works (`GROQ_API_KEY = "gsk_..."`),
for backward compatibility — it just gets wrapped into a one-item list.

You need **at least one** Groq or Gemini key for question generation to work.
More keys = more headroom before you'd ever see a failure — the app rotates
through all of them automatically and only shows an error if every single
configured key fails.

## 2. Files removed

`storage.py` is gone — it was only used for the chat/library file uploads,
which have been dropped per your "just tests and practice" direction. If you
had a `chat.py` or `library.py` in your repo, you can delete those too;
nothing in the rebuilt code imports them anymore.

## 3. What changed structurally

- **The crash fix**: `student_dashboard.py` no longer touches shared quiz
  state at all — it only submits the logged-in student's own answer. Only
  `admin_dashboard.py` can advance quizzes, reveal answers, or open/close
  tests. See the big docstring at the top of both files and of `quiz.py` for
  the full explanation.
- **New**: `ai_providers.py` — multi-key, multi-provider (Groq + Gemini)
  rotation. Every question generation call goes through this instead of a
  single hardcoded client.
- **New**: full-length timed test system in `quiz.py` (the
  `create_full_test` / `open_full_test` / ... functions), with a real
  exam-taking UI in `student_dashboard.py` — question palette, mark for
  review, free navigation, one shared countdown clock, no per-question timer.
- **Dropped**: chat, announcements, polls, roster file library. Kept and
  polished: auth, live practice quiz (single question / auto-quiz series /
  question bank), the new full-length test mode, and the leaderboard.
- **New theme**: `styles.py` was rewritten from the clinical/ECG theme to a
  minimal, professional dark theme (indigo accent, monospace numbers) in the
  PW/Unacademy register, per your direction.

## 4. Recommended before going live with a real class

- Add at least 3-4 keys total across Groq + Gemini if you can — that's the
  real insurance policy against the kind of failure you saw before.
- Test the full-length test flow yourself end-to-end once (create a small
  5-question test, open it, take it as a second browser/incognito student
  account, submit, check the leaderboard) before your first real class.

## 5. Permanent archive + unlimited reattempts + DPPs (latest update)

**Nothing is ever deleted.** Every test and DPP you create stays in the
database forever. Students can revisit and retake any of them — open or
closed — as many times as they want. Only their single **best-scoring**
attempt counts for the leaderboard and "Past Tests/DPPs" — older, worse
attempts aren't individually kept (this app tracks best score, not a full
attempt log), but retaking never loses the score they already banked.

**DPPs are a new, separate type** alongside full-length Tests, created from
the same "Create New" form (pick "DPP" instead of "Full-Length Timed
Test"). The only functional difference: Tests run on one shared timed
clock for the whole class; DPPs are untimed, so students can do them
whenever, at their own pace. Everything else — permanent archive,
unlimited best-score reattempts, review, leaderboard — works identically
for both.

**"Close"** on a test/DPP now only ends the shared live session (and
auto-submits anyone still mid-test on a timed Test) — it does **not**
delete or lock the test. Students can keep retaking it afterward,
untimed, exactly like a DPP.

**Existing tests you already created before this update** are migrated
automatically the next time the app loads the database — no action
needed. Each old submission's single score becomes its "best" attempt,
and it becomes retakeable going forward.

### Load / crash hardening that came with this update

- `save_db()` now retries a couple of times with a short backoff before
  giving up, instead of failing on the first blip. Every write in
  `quiz.py` goes through a wrapper that catches a real (post-retry)
  failure and shows a normal "try again" warning instead of crashing
  the page.
- **Answer-save batching**: while a student is taking a test/DPP, their
  answers and marks are kept in the browser session and only written to
  the database when they move to another question, mark for review, or
  submit — plus a background autosave roughly every 20 seconds. Previously
  every single option click wrote to Supabase immediately, which was the
  single biggest source of database load with a full class answering
  concurrently.
- Fixed a real crash: the exam UI assumed there was always a countdown
  clock running, which broke (`TypeError`) the moment a student retook a
  closed test or attempted an untimed DPP. It now shows "Untimed"
  correctly instead of crashing.
- Closing a test/DPP no longer lets one corrupted student submission stop
  the rest of the class from being graded.
