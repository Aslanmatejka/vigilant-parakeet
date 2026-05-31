-- =============================================================================
-- DoGoods AI — Persistent Long-Term Memory
-- Migration: 20260530_create_ai_user_memory.sql
-- Creates: ai_user_memory (stable per-user facts the assistant remembers)
-- =============================================================================
--
-- This table powers Nouri's "concierge memory" — durable facts about a user
-- that survive across sessions and are injected into every chat turn so the
-- assistant doesn't re-ask the same questions ("how big is your household?",
-- "are you vegan?", "do you drive?").
--
-- Memories are extracted in two ways:
--   1. Explicitly: the assistant calls `remember_user_fact(key, value)` when
--      the user says "remember that I'm allergic to peanuts".
--   2. Implicitly: a background extractor runs after each chat turn and saves
--      stable preferences/facts it finds in the user's message.
--
-- The user owns and can delete any memory at any time via Settings.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_user_memory (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    key          TEXT NOT NULL CHECK (char_length(key) BETWEEN 1 AND 80),
    value        TEXT NOT NULL CHECK (char_length(value) BETWEEN 1 AND 500),
    confidence   REAL NOT NULL DEFAULT 0.8 CHECK (confidence BETWEEN 0 AND 1),
    source       TEXT NOT NULL DEFAULT 'extracted'
                 CHECK (source IN ('extracted', 'explicit', 'profile', 'system')),
    last_seen    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_ai_user_memory_user
    ON ai_user_memory (user_id, last_seen DESC);

-- =============================================
-- Row-Level Security
-- =============================================

ALTER TABLE ai_user_memory ENABLE ROW LEVEL SECURITY;

-- Owner can read their own memories
CREATE POLICY "Users can view own AI memories" ON ai_user_memory FOR
SELECT TO authenticated USING (
    (select auth.uid()) = user_id
);

-- Owner can write / overwrite their own memories
CREATE POLICY "Users can insert own AI memories" ON ai_user_memory FOR
INSERT TO authenticated WITH CHECK (
    (select auth.uid()) = user_id
);

CREATE POLICY "Users can update own AI memories" ON ai_user_memory FOR
UPDATE TO authenticated USING (
    (select auth.uid()) = user_id
);

-- Owner can delete any of their own memories at any time
CREATE POLICY "Users can delete own AI memories" ON ai_user_memory FOR
DELETE TO authenticated USING (
    (select auth.uid()) = user_id
);

-- Admins can read all memories for moderation / debugging
CREATE POLICY "Admins can view all AI memories" ON ai_user_memory FOR
SELECT TO authenticated USING (
    EXISTS (
        SELECT 1 FROM users
        WHERE users.id = (select auth.uid())
          AND users.is_admin = true
    )
);

-- Service role (backend) can manage memories on the user's behalf
CREATE POLICY "Service can manage AI memories" ON ai_user_memory FOR
ALL TO service_role USING (true) WITH CHECK (true);
