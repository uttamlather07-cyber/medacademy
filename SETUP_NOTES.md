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
