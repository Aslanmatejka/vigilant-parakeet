-- Migration: Agent action framework tables (AGENT_V2 + destructive intercept)
-- Description: Creates agent_pending_actions, agent_audit_log, agent_user_facts.
--              These back the confirm-or-commit envelope (POST /api/ai/confirm),
--              the audit log for every WRITE the agent performs, and the
--              long-term per-user memory ("forget about me" target).
-- Date: 2026-07-01

-- ============================================================================
-- agent_pending_actions
-- ============================================================================
-- Rows inserted by backend.agent.actions.plan_action when a tool call is
-- flagged requires_confirmation=True. Resolved by POST /api/ai/confirm which
-- calls commit_pending_action or cancel_pending_action.

CREATE TABLE IF NOT EXISTS agent_pending_actions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID,
    turn_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    args JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary TEXT,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'cancelled', 'failed', 'expired')),
    result JSONB,
    audit_id UUID,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '10 minutes'),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enforce one live pending row per (user, tool+args hash). Retries of the
-- same request short-circuit to the existing row instead of creating a
-- second confirmation prompt.
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_pending_idem_pending
    ON agent_pending_actions (user_id, idempotency_key)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_agent_pending_user
    ON agent_pending_actions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_pending_status_expires
    ON agent_pending_actions (status, expires_at)
    WHERE status = 'pending';

ALTER TABLE agent_pending_actions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access to pending actions"
    ON agent_pending_actions FOR ALL
    USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Users can view their own pending actions"
    ON agent_pending_actions FOR SELECT
    USING (user_id = auth.uid());

COMMENT ON TABLE agent_pending_actions IS 'Queued write actions awaiting user confirmation via /api/ai/confirm';


-- ============================================================================
-- agent_audit_log
-- ============================================================================
-- One row per attempted WRITE. Populated by commit_action (v2 planner) and
-- by _audit_v1_writes (legacy tool loop). Used for rollback + activity log.

CREATE TABLE IF NOT EXISTS agent_audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    actor_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    turn_id TEXT,
    conversation_id UUID,
    tool_name TEXT NOT NULL,
    args_redacted JSONB NOT NULL DEFAULT '{}'::jsonb,
    before_state JSONB,
    after_state JSONB,
    target_table TEXT,
    target_id TEXT,
    status TEXT NOT NULL DEFAULT 'committed'
        CHECK (status IN ('committed', 'failed', 'rolled_back')),
    rollback_token TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_audit_actor
    ON agent_audit_log (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_audit_tool
    ON agent_audit_log (tool_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_audit_status
    ON agent_audit_log (status) WHERE status = 'failed';

ALTER TABLE agent_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access to audit log"
    ON agent_audit_log FOR ALL
    USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Users can view their own audit rows"
    ON agent_audit_log FOR SELECT
    USING (actor_user_id = auth.uid());

CREATE POLICY "Admins can view all audit rows"
    ON agent_audit_log FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE users.id = auth.uid() AND users.is_admin = TRUE
        )
    );

COMMENT ON TABLE agent_audit_log IS 'Audit trail of every write the AI agent has attempted';


-- ============================================================================
-- agent_user_facts
-- ============================================================================
-- Long-term per-user memory harvested by backend.agent.memory. Wiped by
-- the forget_about_me tool. Optional embedding column can be added later
-- via a separate migration when AGENT_V2_MEMORY_EMBEDDINGS is turned on.

CREATE TABLE IF NOT EXISTS agent_user_facts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'other'
        CHECK (kind IN ('preference', 'dietary', 'style', 'relationship', 'other')),
    content TEXT NOT NULL,
    importance NUMERIC(4, 3) NOT NULL DEFAULT 0.500
        CHECK (importance >= 0 AND importance <= 1),
    confirmed_by_user BOOLEAN NOT NULL DEFAULT FALSE,
    source_turn_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_user_facts_user
    ON agent_user_facts (user_id, kind, created_at DESC);

-- Cheap de-dupe guard so the extractor doesn't insert the same phrase twice
-- for the same user. Case-insensitive match on the first 200 chars.
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_user_facts_user_content
    ON agent_user_facts (user_id, kind, LOWER(LEFT(content, 200)));

ALTER TABLE agent_user_facts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access to user facts"
    ON agent_user_facts FOR ALL
    USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Users can view their own facts"
    ON agent_user_facts FOR SELECT
    USING (user_id = auth.uid());

-- Self-serve wipe path if the AI is unreachable.
CREATE POLICY "Users can delete their own facts"
    ON agent_user_facts FOR DELETE
    USING (user_id = auth.uid());

COMMENT ON TABLE agent_user_facts IS 'Long-term per-user memory (preferences, dietary, style, relationships)';
