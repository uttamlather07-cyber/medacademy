# MedAcademy — NEET Live Classroom Platform (v3)

A live classroom platform for NEET prep: AI-generated and admin-curated
quizzes, live diagnosis polls, a real-time staff room chat with file
sharing, and a subject/chapter-organized study material library.

## File structure

```
neet-academy/
├── app.py                   # Entry point — run this with `streamlit run app.py`
├── config.py                 # Theme colors, constants, page setup
├── styles.py                  # All CSS + the ECG "signature" animation
├── database.py               # JSON database load/save/upgrade
├── auth.py                    # Landing page, login, signup
├── chat.py                     # Chat rendering + image/file upload
├── quiz.py                     # Quiz generation (AI + question bank), scoring
├── chapters.py                # Standard NEET syllabus chapter list per subject
├── library.py                  # PDF/document library (subject → chapter)
├── polls.py                    # Smart poll logic
├── admin_dashboard.py         # Admin (CMO) terminal
├── student_dashboard.py       # Student view
├── sidebar.py                  # On-duty roster
├── requirements.txt
├── .gitignore
└── .streamlit/
    └── secrets.toml.example   # Copy to secrets.toml and fill in your key
```

## ⚠️ Required one-time Supabase setup (fixes crashes + data loss)

Run this SQL once in your Supabase project's **SQL Editor** (same place you
set up `append_chat_message`, if you already had that). It adds two more
atomic database functions that fix the "students had to register 3 times"
and app-restart data-loss issues:

```sql
-- Atomically registers a new user. Returns 'ok' or 'taken'.
-- Doing the "does this username exist?" check AND the insert as one
-- database step means two students registering at the same moment can
-- never overwrite each other, which is what was silently deleting
-- freshly-created accounts before.
create or replace function register_user(p_username text, p_user_data jsonb)
returns text
language plpgsql
as $$
declare
  existing jsonb;
begin
  select data->'users'->p_username into existing from app_state where id = 1;
  if existing is not null then
    return 'taken';
  end if;

  update app_state
  set data = jsonb_set(data, array['users', p_username], p_user_data),
      updated_at = now()
  where id = 1;

  return 'ok';
end;
$$;

-- Atomically updates one user's last_seen timestamp without touching
-- anything else in the database, so the "who's online" refresh that runs
-- every few seconds for every logged-in user can never collide with or
-- overwrite a chat message, quiz answer, or new registration happening in
-- the same instant.
create or replace function touch_last_seen(p_username text)
returns void
language plpgsql
as $$
begin
  update app_state
  set data = jsonb_set(
        data,
        array['users', p_username, 'last_seen'],
        to_jsonb(extract(epoch from now()))
      ),
      updated_at = now()
  where id = 1
    and data->'users' ? p_username;
end;
$$;
```

If you don't already have `append_chat_message` set up, add it too:

```sql
create or replace function append_chat_message(new_msg jsonb)
returns void
language plpgsql
as $$
begin
  update app_state
  set data = jsonb_set(
        data,
        array['chat'],
        coalesce(data->'chat', '[]'::jsonb) || jsonb_build_array(new_msg)
      ),
      updated_at = now()
  where id = 1;
end;
$$;
```

**Why this matters:** the app previously loaded the *entire* database,
changed one small thing in Python, and saved the *entire* thing back. With
several people's browsers auto-refreshing every 3 seconds, two of these
load-change-save cycles could overlap, and whichever one finished saving
last would silently erase whatever the other one had just added — a new
account, a chat message, a quiz answer. These SQL functions make each of
those specific changes happen as one atomic step inside the database
itself, so overlapping requests can no longer erase each other.

There was also a separate bug where a temporary Supabase connection hiccup
made the app quietly treat the database as brand new and empty, and then
save that emptiness right over your real data. That's fixed in code (see
`database.py`) — a connection problem now shows a "please wait, retrying"
message instead of ever touching your real data.

## Local setup

```bash
pip install -r requirements.txt

# Set up your API key
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then open .streamlit/secrets.toml and paste your real Groq key

streamlit run app.py
```

## Keeping your API key safe

Your Groq API key lives in **one place only**: `.streamlit/secrets.toml`.
It is never hardcoded in any `.py` file, and `.gitignore` already excludes
`.streamlit/secrets.toml` from git — as long as you don't force-add it,
it will never reach GitHub.

If you're not sure whether an old version of this repo ever had a key
hardcoded in source and pushed publicly, check your GitHub commit history
(search the repo, including old commits, for `GROQ_API_KEY` or a string
starting with `gsk_`). If you find one, treat it as compromised: go to
[console.groq.com](https://console.groq.com) → API Keys → revoke it →
create a new one → put the new one in `secrets.toml` only. Deleting a file
today does not remove a key from earlier commits — only revoking the key
itself makes it safe.

## Deploying on Streamlit Community Cloud

1. Push all files **except** `.streamlit/secrets.toml`, `database.json`,
   `uploads/`, and `library_files/` (already handled by `.gitignore`).
2. In your app's dashboard → **Settings → Secrets**, paste:
   ```toml
   GROQ_API_KEY = "your-real-key"
   ```
3. Deploy. If you push new commits later and the live app doesn't seem to
   reflect them, use **Manage app → Reboot** from the Streamlit Cloud
   dashboard to force a fresh deploy.

### Important limitation on free hosting

Streamlit Community Cloud's free tier uses a filesystem that resets on every
restart/redeploy. That means `database.json` (all your users, scores, chat
history) **and** any images/files students upload in chat, **and** any
files uploaded to the Library, will be wiped periodically.

If you want data (accounts, scores, chat, library files) to survive
restarts, you have two options:
- Move to a host with a persistent disk (a small VPS, Railway, Render with
  a volume, etc.)
- Swap the JSON-file database for a real database (SQLite file on a
  persistent disk, or a hosted one like Supabase/Postgres)

## What's in this version

### Quiz — three modes
The Medical Quiz tab now has three modes, selected via radio button:

- **Single Question** — one AI-generated question, optionally timed,
  admin reveals manually.
- **Auto Quiz (AI, multiple, timed)** — a set of AI-generated questions
  run back-to-back on a shared timer, auto-revealing and advancing.
- **My Question Bank** — paste 20–30 of your own questions in as plain
  text and the app draws random questions from them for a timed auto
  quiz. Not saved permanently — used for that one quiz, then discarded.

  Paste format (blank line between questions):
  ```
  Q: What is the powerhouse of the cell?
  A) Nucleus
  B) Mitochondria
  C) Ribosome
  D) Golgi body
  Answer: B
  Explanation: Mitochondria generate ATP via oxidative phosphorylation.
  ```
  Before starting the quiz, click "Parse & Preview" — it shows exactly
  how many questions were understood, flags any block that didn't parse
  (wrong number of options, missing answer line, etc.) with the reason,
  and never guesses at a fix for a malformed entry.

### AI question accuracy safeguards
AI-generated questions (Single Question and Auto Quiz AI modes) go
through two fixes on every question, automatically, using your existing
Groq API key:

1. **Shuffle fix** — the model's raw response is re-ordered in code after
   generation, so any tendency the model has to put the correct answer in
   the same option slot every time never reaches students.
2. **Verification pass** — a second, independent API call re-derives the
   answer from scratch and checks it against the first pass before the
   question is ever shown. If it disagrees, the corrected version is used
   and the admin sees a small note that a correction was made.

This roughly doubles API calls (and therefore latency and Groq rate-limit
usage) per AI-generated question — a deliberate accuracy-over-speed
tradeoff. No AI safeguard makes questions error-free; for anything
high-stakes, use My Question Bank with questions you've already verified.

### Chapters
`chapters.py` contains the full standard NEET syllabus, split into four
subjects — **Physics, Chemistry, Botany, Zoology** (NEET treats Biology as
two separate papers) — used to populate dropdowns for both quiz topics and
the library, instead of free-typed topic names.

### Library
A new **📚 Library** tab, organized by Subject → Chapter:
- **Admin**: upload PDFs/DOCX/PPTX/TXT tagged with subject + chapter,
  delete any file.
- **Students**: browse and filter by subject/chapter, download any file,
  and **read PDF/TXT files directly on the site** via a "📖 Read" button
  that opens the file in a popup overlay — no download required. DOCX/PPTX
  don't have a reliable in-browser viewer, so those stay download-only
  (the Read button just doesn't appear for those types — Download always
  does).

Storage follows the same pattern as chat attachments — files live on disk,
only metadata is stored in `database.json` (see the hosting limitation
above).

Note: `st.dialog` (used for the inline reader popup) requires
**Streamlit 1.37+** — already reflected in `requirements.txt`. If you're
upgrading from an older version of this app, run
`pip install -r requirements.txt --upgrade` again.

### Chat
- Students and admin can upload and send images and files (PDF, DOCX,
  PPTX, XLSX, TXT, ZIP, CSV, and common image formats) directly in chat.
- Images render inline as previews; files show as downloadable chips with
  file name and size.
- Max file size is capped at 8 MB per file (edit `MAX_FILE_SIZE_MB` in
  `config.py` to change this).

### Code organization
- Split into focused files so future features are easy to add without
  touching everything else.
- API key lives only in Streamlit secrets, never in source.
- Atomic database writes (prevents corruption if the app crashes mid-save).

## Adding more features later

The pattern this codebase follows:
1. Create a new file, e.g. `notifications.py`.
2. Write functions there that take `db` as an argument and call `save_db(db)`
   when they change something (see `polls.py` for the simplest example).
3. Import those functions into `admin_dashboard.py` or `student_dashboard.py`
   and call them inside the relevant tab.

Send me the feature idea any time and I can write that file for you in the
same style.
