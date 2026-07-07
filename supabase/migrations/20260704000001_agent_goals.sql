-- Migration: Agent goal stack persistence (AGENT_V2 Phase 2)
-- Description: Persists open/in-progress/blocked goals across chat turns so
--              the agent can resume multi-step user intent.
-- Date: 2026-07-04

CREATE TABLE IF NOT EXISTS agent_goals (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    intent TEXT NOT NULL DEFAULT 'chitchat',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'blocked', 'done', 'abandoned')),
    priority TEXT NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    parent_goal_id UUID REFERENCES agent_goals(id) ON DELETE SET NULL,
    success_criteria TEXT,
    notes JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_turn_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_goals_user_active
    ON agent_goals (user_id, updated_at DESC)
    WHERE status IN ('open', 'in_progress', 'blocked');

CREATE INDEX IF NOT EXISTS idx_agent_goals_user_status
    ON agent_goals (user_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_goals_parent
    ON agent_goals (parent_goal_id)
    WHERE parent_goal_id IS NOT NULL;

ALTER TABLE agent_goals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access to agent goals"
    ON agent_goals FOR ALL
    USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Users can view their own agent goals"
    ON agent_goals FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can delete their own agent goals"
    ON agent_goals FOR DELETE
    USING (user_id = auth.uid());

COMMENT ON TABLE agent_goals IS 'Per-user goal stack for AGENT_V2 multi-turn intent tracking';
