# NEET Test Console — setup guide

This is a full rebuild of the test-taking website, on real per-row
Supabase tables instead of the old single-JSON-blob design. See
`database.py`'s module docstring for the full explanation of why the old
design caused lag under concurrent load, and how this fixes it.

**Scope of this rebuild:** just the test system. The AI question
generation, live practice quiz, auto-quiz, and question bank features
from the old app are gone — this is intentional (per your request), not
an oversight. Admin pastes questions in; students take timed tests.

## 1. Set up the database

1. Open your Supabase project → **SQL Editor**.
2. Open `schema.sql` from this folder, copy the whole file, paste it into
   the SQL Editor, and run it. It's safe to re-run if you need to (every
   statement uses `IF NOT EXISTS` / `CREATE OR REPLACE`, or an explicit
   drop-first for the one thing that needs it).
3. **If you already ran an earlier version of schema.sql and have live
   data** (accounts, tests already created), also run
   `migration_001_add_subject.sql` — this adds subject-tab navigation
   (Physics/Chemistry/etc.) to the test-taking screen. It's purely
   additive: every existing question automatically gets subject =
   'General' and nothing you already built breaks or needs redoing.
   Also run `migration_002_persistent_login.sql` — this adds the
   `auth_sessions` table that keeps students logged in across browser
   restarts (see "Persistent login" section below).
4. **This creates a BRAND NEW set of tables** (`app_users`, `tests`,
   `test_questions`, `test_attempts`, `test_answers`) — it does **not**
   touch or delete your old `app_state` table. Your old data stays
   exactly where it is; it's just not read by this new code. If you want
   any of it migrated over (old user accounts, old test results), tell
   me and I'll write a one-time migration script — I didn't do this
   automatically since I don't know which parts of the old data you
   actually still want.

## 2. Check your Supabase key

In Supabase: **Settings → API**, note whether `SUPABASE_KEY` in your
`.streamlit/secrets.toml` is the `anon` key or the `service_role` key
(see `schema.sql`'s ROW LEVEL SECURITY section for why this matters).
Either works with this setup — the schema includes RLS policies that
work correctly with either key — but it's worth knowing which one you're
using.

Your `.streamlit/secrets.toml` needs only:
```toml
SUPABASE_URL = "https://yourproject.supabase.co"
SUPABASE_KEY = "your-key-here"
```
(The `GROQ_API_KEYS` / `GEMINI_API_KEYS` secrets from the old app are no
longer needed and can be removed.)

## 3. Install dependencies

```
pip install -r requirements.txt
```
Notably smaller than before — `groq`, `google-genai`, and
`streamlit-autorefresh` are all gone, since AI generation and the old
app-wide autorefresh model are both gone. See `app.py`'s module
docstring for what replaced the autorefresh approach.

## 4. Create your first admin account

The signup form (`auth.py`) only ever creates `student` role accounts —
there's no self-serve way to become an admin, deliberately. To create
your own admin account, run this once in Supabase's SQL Editor after
you've signed up normally through the app:

```sql
update app_users set role = 'admin' where username = 'your_username_here';
```

## 5. Run it

```
streamlit run app.py
```

## What changed vs. the old app, at a glance

- **No AI generation, no live quiz, no auto-quiz, no question bank** —
  removed per your request. Admin pastes questions using the same
  `Q: / A) / Answer: / Explanation:` format the old app already used.
- **Real database tables**, not one JSON blob — this is the actual lag
  fix. See `database.py`'s docstring.
- **Timer**: a real client-side ticking countdown (previously not
  possible in the old design), enforced server-side by a narrowly
  isolated background check that auto-submits when time runs out — see
  `student_dashboard.py`'s `_timer_watchdog_fragment` docstring for
  exactly how this avoids reintroducing the old "clicks need 2-3 tries"
  bug.
- **Free navigation**: jump to any question directly via the palette,
  AND jump to any subject via subject tabs — matches what you asked
  for. Creating a test is now two steps: set up the test shell (title/
  duration/marking), then add subjects one at a time (pick a subject
  name, paste that subject's questions, repeat) — same pattern as the
  Telegram bot's walkthrough. You can come back to a draft test later
  via **Manage Existing Tests → Add More Subjects** to keep adding.
- **Color-coded palette**: green = answered, orange = current question,
  grey = unanswered — matches your reference screenshot.
- **Answers/correct-answers only revealed after submit** — the review
  screen, never live during the test.

## Persistent login (students don't have to log in every time)

A student who checks "Stay logged in on this browser" won't need to
log in again the next time they open the site, even after fully
closing their browser — a random session token gets stored in the
page's URL (not their password) and checked against the `auth_sessions`
table on every visit.

**Worth knowing:** unlike a normal invisible cookie, this token is
visible in the browser's address bar and would show up in browser
history or if that URL got bookmarked/shared. This was a deliberate
choice, not an oversight — the more "invisible" cookie-based approach
was tried first and found to be unreliable specifically on Streamlit
Cloud's sandboxed deployment model (several independent developers have
hit and documented this exact failure). If a student uses a shared or
public computer, using the in-app **Log Out** button (not just closing
the tab) properly revokes that session in the database, not just on
that one device.

## Things I deliberately did NOT fix, flagged rather than silently left

- **Passwords are stored in plaintext** in `app_users.password` — this
  matches the old app's `DEFAULT_ADMIN_PASSWORD` approach exactly, so
  nothing got WORSE here, but proper hashing (e.g. bcrypt) is a real
  security upgrade worth doing separately from this lag-focused rebuild.
- **RLS policies are permissive** ("any request can read/write
  everything") — matches the old blob's actual security model (access
  control lived entirely in Streamlit's Python login gate, not the
  database). Tightening this to "a student can only see their own
  attempts at the database level" is a genuine additional layer of
  safety, but a separate piece of work.
- **Old `app_state` data is not migrated** — see step 1 above.

## If something breaks

I built and unit-tested the trickiest logic (leaderboard ranking,
server-side scoring, the timestamp parsing, the full render path for
both the test list and the test-taking screen) against mocked Supabase
responses — but I do not have a real Supabase project or a real
Streamlit server to run this against end-to-end. Please treat the first
real run as a genuine test: create one test, take it yourself with a
second (student) account, and confirm the whole flow works before
opening it up to actual students.
