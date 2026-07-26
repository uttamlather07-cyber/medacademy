-- ============================================================
-- NEET Test Console — schema v2
-- Replaces the single-JSON-blob "app_state" table entirely.
-- Run this whole file once in Supabase's SQL Editor.
--
-- WHY THIS EXISTS (read before running):
-- The old app_state table stored the ENTIRE database — every test,
-- every student, every answer — as one JSON blob in one row. Answering
-- ONE question meant: fetch the whole blob, change one field in
-- Python, write the WHOLE blob back. With 20-30 students in a live
-- test all doing that at once, every single click was a full-database
-- read-modify-write racing against everyone else's. That's the actual
-- cause of the lag, not the AI features.
--
-- This schema instead gives every answer its own tiny row. A student
-- answering a question is now one small, targeted write that only
-- touches THAT student's THAT answer — completely independent of what
-- 29 other students are doing at the same moment. No shared blob, no
-- collision, no reason for concurrent load to slow anything down.
-- ============================================================

-- ---------- USERS ----------
-- Replaces the "users" key in the old blob. username is the natural
-- primary key since that's already how your login works (no separate
-- numeric id needed — every other table just references username
-- directly as a text foreign key, which keeps every query readable).
create table if not exists app_users (
    username        text primary key,
    password        text not null,
    role            text not null check (role in ('admin', 'student')),
    lifetime_score  numeric not null default 0,
    last_seen       timestamptz not null default now(),
    blocked         boolean not null default false,
    avatar_color    text not null default '#6366f1',
    created_at      timestamptz not null default now()
);

-- ---------- TESTS ----------
create table if not exists tests (
    id                  bigint generated always as identity primary key,
    title               text not null,
    status              text not null default 'draft' check (status in ('draft', 'open', 'closed')),
    duration_minutes    integer not null,
    marks_correct       numeric not null default 4,
    marks_wrong         numeric not null default -1,
    -- Optional scheduled window (e.g. 9am-6pm) — NULL/NULL means no
    -- schedule, the admin opens/closes it manually via status instead.
    -- Mirrors the Telegram bot's window_start/window_end exactly, so
    -- both systems share the same scheduling concept if you ever want
    -- them to interoperate.
    window_start        timestamptz,
    window_end          timestamptz,
    created_by          text references app_users(username),
    created_at          timestamptz not null default now(),
    opened_at           timestamptz,
    closed_at           timestamptz,
    -- Frozen #1-position snapshot, written once when the test closes —
    -- same idea as the bot's topper_snapshot, so "who won" survives
    -- forever even if the live leaderboard view later changes.
    topper_snapshot     jsonb
);

-- ---------- QUESTIONS ----------
-- One row per question. options as jsonb array of strings keeps this
-- flexible (3-6 options all work with no schema change) instead of
-- rigid option_a/option_b/option_c/option_d columns.
create table if not exists test_questions (
    id              bigint generated always as identity primary key,
    test_id         bigint not null references tests(id) on delete cascade,
    order_index     integer not null,
    question        text not null,
    options         jsonb not null,       -- e.g. ["5/12", "12/13", "5/13", "12/5"]
    correct_answer  text not null,        -- the OPTION TEXT that's correct, matching options[i] exactly
    explanation     text,
    created_at      timestamptz not null default now()
);
create index if not exists idx_test_questions_test on test_questions(test_id, order_index);

-- ---------- ATTEMPTS ----------
-- One row per student-attempt-at-a-test. A student CAN have multiple
-- rows here for the same test (reattempts) — what's enforced is that
-- at most ONE of them is 'in_progress' at a time per (test_id,
-- username), via the partial unique index below rather than a rigid
-- one-attempt-ever rule.
create table if not exists test_attempts (
    id                  bigint generated always as identity primary key,
    test_id             bigint not null references tests(id) on delete cascade,
    username            text not null references app_users(username),
    status              text not null default 'in_progress' check (status in ('in_progress', 'submitted', 'expired')),
    started_at          timestamptz not null default now(),
    submitted_at        timestamptz,
    score               numeric,
    correct_count       integer,
    wrong_count         integer,
    unanswered_count    integer,
    -- Which question is currently on screen — same reasoning as the
    -- Telegram bot's current_question_id: lets a background timer
    -- refresh (or a page reload) restore the exact right question
    -- instead of guessing "first unanswered."
    current_question_id bigint references test_questions(id)
);
create index if not exists idx_test_attempts_lookup on test_attempts(test_id, username);
-- At most one IN-PROGRESS attempt per student per test — this is what
-- "resume, don't duplicate" relies on. Submitted/expired attempts are
-- NOT covered by this constraint, so unlimited reattempts after
-- finishing are still fully allowed.
create unique index if not exists idx_one_active_attempt
    on test_attempts(test_id, username)
    where status = 'in_progress';

-- ---------- ANSWERS ----------
-- THE key table for the lag fix. One row per (attempt, question).
-- Primary key on that pair means every answer submission is a single
-- INSERT ... ON CONFLICT (attempt_id, question_id) DO UPDATE —
-- genuinely atomic per-answer, and completely independent of every
-- other student's rows. This is what makes 30 concurrent students
-- answering simultaneously a non-event instead of 30-way lock
-- contention on one shared blob.
create table if not exists test_answers (
    attempt_id      bigint not null references test_attempts(id) on delete cascade,
    question_id     bigint not null references test_questions(id) on delete cascade,
    selected_option text,           -- NULL if explicitly skipped
    is_skipped      boolean not null default false,
    answered_at     timestamptz not null default now(),
    primary key (attempt_id, question_id)
);

-- ============================================================
-- ATOMIC RPC FUNCTIONS
-- Mirrors database.py's existing register_user/touch_last_seen
-- pattern (atomic Postgres functions instead of read-modify-write in
-- Python) — extended here to cover the operations that happen DURING
-- a live test, which is exactly where 20-30 concurrent writers used
-- to collide under the old blob design.
-- ============================================================

-- Upsert one answer. This IS the per-click write during a live test —
-- see the test_answers table comment above for why this one function
-- is the actual fix for the lag.
create or replace function submit_answer(
    p_attempt_id bigint,
    p_question_id bigint,
    p_selected_option text,
    p_is_skipped boolean
) returns void as $$
begin
    insert into test_answers (attempt_id, question_id, selected_option, is_skipped, answered_at)
    values (p_attempt_id, p_question_id, p_selected_option, p_is_skipped, now())
    on conflict (attempt_id, question_id)
    do update set selected_option = excluded.selected_option,
                  is_skipped = excluded.is_skipped,
                  answered_at = excluded.answered_at;
end;
$$ language plpgsql;

-- Start-or-resume an attempt atomically. Two students (or one student
-- double-clicking / two open tabs) hitting "Begin Test" at the exact
-- same instant must NEVER both succeed in creating two 'in_progress'
-- rows — the unique index above would reject the second INSERT, but
-- without this function wrapping both the "does one already exist"
-- check AND the insert in one atomic call, a plain Python
-- check-then-insert has the same classic race the old register_user
-- fix was written to prevent (see database.py's existing comment on
-- that exact failure mode).
create or replace function start_or_resume_attempt(
    p_test_id bigint,
    p_username text
) returns bigint as $$
declare
    v_attempt_id bigint;
begin
    select id into v_attempt_id from test_attempts
        where test_id = p_test_id and username = p_username and status = 'in_progress';

    if v_attempt_id is not null then
        return v_attempt_id;
    end if;

    insert into test_attempts (test_id, username, status, started_at)
    values (p_test_id, p_username, 'in_progress', now())
    returning id into v_attempt_id;

    return v_attempt_id;
exception
    -- Genuinely concurrent double-click landed between the SELECT and
    -- INSERT above — the unique index catches it here; re-select
    -- rather than erroring out, so the second caller just gets back
    -- the same attempt_id the first one created.
    when unique_violation then
        select id into v_attempt_id from test_attempts
            where test_id = p_test_id and username = p_username and status = 'in_progress';
        return v_attempt_id;
end;
$$ language plpgsql;

-- Atomically registers a new user IF the username isn't taken. Same
-- shape as your existing register_user, kept here for completeness
-- since app_users is a new table in this schema.
create or replace function register_app_user(
    p_username text,
    p_password text,
    p_role text
) returns text as $$
begin
    insert into app_users (username, password, role)
    values (p_username, p_password, p_role);
    return 'ok';
exception
    when unique_violation then
        return 'taken';
    when others then
        return 'error';
end;
$$ language plpgsql;

create or replace function touch_last_seen(p_username text) returns void as $$
begin
    update app_users set last_seen = now() where username = p_username;
end;
$$ language plpgsql;

-- ============================================================
-- INDEXES for the read-heavy queries the UI runs constantly
-- ============================================================
create index if not exists idx_tests_status on tests(status);
create index if not exists idx_test_attempts_status on test_attempts(test_id, status);

-- ============================================================
-- ROW LEVEL SECURITY
--
-- IMPORTANT — check which Supabase key is in your
-- .streamlit/secrets.toml as SUPABASE_KEY before deciding whether you
-- even need the policies below:
--
--   service_role key ("secret", starts differently from anon in your
--   dashboard's Settings > API page) — BYPASSES RLS entirely,
--   policies below are inert either way, but RLS is still enabled so
--   the tables aren't wide open if that key ever leaked or a
--   different key gets used later.
--
--   anon/public key — RLS is what stands between "any request to
--   these tables" and "actually blocked" — the policies below are
--   REQUIRED for the app to work at all with this key, not just a
--   safety nicety.
--
-- Since Streamlit runs this Python server-side (the key never reaches
-- a student's browser directly, unlike a typical client-side web app),
-- the exposure is lower than usual either way — but enabling RLS with
-- permissive-but-real policies costs nothing and is what Supabase
-- itself recommends by default, so it's done here regardless of which
-- key you end up using.
-- ============================================================
alter table app_users enable row level security;
alter table tests enable row level security;
alter table test_questions enable row level security;
alter table test_attempts enable row level security;
alter table test_answers enable row level security;

-- Permissive policies: any request through Supabase's API can read/
-- write every table. This matches the OLD app_state table's actual
-- security model exactly (one shared blob, no per-user restriction at
-- the database level — access control was entirely handled by
-- Streamlit's own login gate in Python). Tightening this further
-- (e.g. a student can only see their OWN attempts/answers at the
-- database level, not just because the Streamlit UI happens to only
-- query for their username) is a real, worthwhile upgrade but a
-- separate piece of work from this lag-focused rebuild — flagged here
-- rather than silently included, since it changes how much you can
-- trust the database layer itself if the app layer ever has a bug.
-- DROP + CREATE rather than a bare CREATE — Postgres has no "CREATE
-- POLICY IF NOT EXISTS", and you'll likely re-run this whole file more
-- than once while we're setting this up. Every other statement above
-- already uses IF NOT EXISTS / CREATE OR REPLACE for the same reason;
-- this is the one place that needs the explicit drop-first instead.
drop policy if exists "allow all" on app_users;
drop policy if exists "allow all" on tests;
drop policy if exists "allow all" on test_questions;
drop policy if exists "allow all" on test_attempts;
drop policy if exists "allow all" on test_answers;
create policy "allow all" on app_users for all using (true) with check (true);
create policy "allow all" on tests for all using (true) with check (true);
create policy "allow all" on test_questions for all using (true) with check (true);
create policy "allow all" on test_attempts for all using (true) with check (true);
create policy "allow all" on test_answers for all using (true) with check (true);

-- Newer Supabase projects require explicit grants before the Data API
-- can reach a new table/function at all, separate from RLS policies
-- (see Supabase's "Securing your API" docs) — these are harmless
-- no-ops on older projects where the default grant already covers it.
grant usage on schema public to anon, authenticated;
grant all on all tables in schema public to anon, authenticated;
grant all on all sequences in schema public to anon, authenticated;
grant execute on all functions in schema public to anon, authenticated;
