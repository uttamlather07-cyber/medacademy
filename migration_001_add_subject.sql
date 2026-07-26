-- ============================================================
-- Migration 001: add subject support to test_questions
--
-- Run this in Supabase's SQL Editor if you already ran the original
-- schema.sql and have live data (accounts, tests) you don't want to
-- lose. This is purely ADDITIVE — it does not drop or modify any
-- existing table, row, or column; every existing question row gets
-- subject = 'General' automatically via the DEFAULT, so nothing you
-- already created breaks or needs re-entering.
--
-- Safe to re-run — uses IF NOT EXISTS throughout.
-- ============================================================

alter table test_questions
    add column if not exists subject text not null default 'General';

-- Replaces the old (test_id, order_index) index with one that also
-- covers subject, since the student-side palette now groups/tabs by
-- subject and queries will filter on it constantly.
drop index if exists idx_test_questions_test;
create index if not exists idx_test_questions_test on test_questions(test_id, subject, order_index);
