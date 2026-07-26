-- ============================================================
-- Migration 002: persistent login sessions
--
-- Fixes "students have to log in every time they close and reopen the
-- browser." Streamlit's own session state lives only in server memory
-- and is wiped the moment a browser tab/window closes — there is no
-- built-in way around this (confirmed: even Streamlit's own official
-- st.login() has had real bugs where its auth cookie stopped
-- persisting across browser closes). The fix is a browser cookie
-- holding an opaque session token, checked against this table on every
-- page load before showing the login screen.
--
-- Deliberately NOT storing username/password in the cookie itself —
-- only a random, meaningless token that maps to a username here. This
-- means a leaked or stolen cookie can be revoked by deleting its row
-- (or waiting for expires_at), without the student's actual password
-- ever being exposed to or stored in the browser at all.
--
-- Safe to re-run — uses IF NOT EXISTS throughout.
-- ============================================================

create table if not exists auth_sessions (
    token       text primary key,
    username    text not null references app_users(username) on delete cascade,
    created_at  timestamptz not null default now(),
    expires_at  timestamptz not null
);
create index if not exists idx_auth_sessions_username on auth_sessions(username);
create index if not exists idx_auth_sessions_expires on auth_sessions(expires_at);

alter table auth_sessions enable row level security;
drop policy if exists "allow all" on auth_sessions;
create policy "allow all" on auth_sessions for all using (true) with check (true);
grant all on auth_sessions to anon, authenticated;

-- Atomic session creation — same reasoning as register_app_user/
-- start_or_resume_attempt elsewhere in this schema: wraps the insert
-- in a function so the token-generation and expiry-setting happen as
-- one clean, reviewable unit rather than raw client-side inserts.
create or replace function create_session(
    p_token text,
    p_username text,
    p_days_valid integer
) returns void as $$
begin
    insert into auth_sessions (token, username, expires_at)
    values (p_token, p_username, now() + (p_days_valid || ' days')::interval);
end;
$$ language plpgsql;

-- Looks up a token and returns the username IF the session is still
-- valid (exists AND not expired) — a single round trip instead of a
-- separate exists-check then expiry-check from Python.
create or replace function validate_session(p_token text) returns text as $$
declare
    v_username text;
begin
    select username into v_username from auth_sessions
        where token = p_token and expires_at > now();
    return v_username;  -- NULL if not found or expired
end;
$$ language plpgsql;

-- Housekeeping — deletes rows past their expiry so this table doesn't
-- grow forever with dead sessions. Not scheduled automatically (no pg_cron
-- assumed available on every Supabase tier); call this occasionally from
-- the app, or run it manually now and then. Harmless to skip entirely —
-- validate_session already ignores expired rows regardless, this only
-- affects table size, not correctness.
create or replace function cleanup_expired_sessions() returns void as $$
begin
    delete from auth_sessions where expires_at < now();
end;
$$ language plpgsql;
