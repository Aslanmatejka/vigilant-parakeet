-- Migration: Create agent_telemetry table for observability
-- Description: Logs agent execution metrics (intent, tools, response time, tokens)
-- Date: 2026-06-27

CREATE TABLE IF NOT EXISTS agent_telemetry (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Intent classification
    detected_intent VARCHAR(50),
    intent_confidence FLOAT,
    detected_language VARCHAR(5) DEFAULT 'en',
    
    -- Tool execution
    tools_called TEXT[], -- Array of tool names
    tool_success_count INTEGER DEFAULT 0,
    tool_failure_count INTEGER DEFAULT 0,
    tool_execution_time_ms INTEGER,
    
    -- Response generation
    response_generated BOOLEAN DEFAULT TRUE,
    response_length INTEGER,
    
    -- Performance metrics
    total_execution_time_ms INTEGER,
    total_tokens_used INTEGER,
    model_name VARCHAR(50),
    
    -- Plan execution
    plan_created BOOLEAN DEFAULT FALSE,
    plan_steps_count INTEGER DEFAULT 0,
    plan_steps_completed INTEGER DEFAULT 0,
    
    -- Proactive suggestions
    suggestions_generated INTEGER DEFAULT 0,
    suggestions_shown BOOLEAN DEFAULT FALSE,
    
    -- Error tracking
    error_occurred BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    error_type VARCHAR(100),
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for analytics queries
CREATE INDEX IF NOT EXISTS idx_agent_telemetry_user_id ON agent_telemetry(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_telemetry_conversation_id ON agent_telemetry(conversation_id);
CREATE INDEX IF NOT EXISTS idx_agent_telemetry_created_at ON agent_telemetry(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_telemetry_intent ON agent_telemetry(detected_intent);
CREATE INDEX IF NOT EXISTS idx_agent_telemetry_error ON agent_telemetry(error_occurred) WHERE error_occurred = TRUE;

-- RLS Policies
ALTER TABLE agent_telemetry ENABLE ROW LEVEL SECURITY;

-- Service role can do everything (backend logs telemetry)
CREATE POLICY "Service role full access to telemetry"
    ON agent_telemetry FOR ALL
    USING (auth.jwt()->>'role' = 'service_role');

-- Admins can view all telemetry for analytics
CREATE POLICY "Admins can view all telemetry"
    ON agent_telemetry FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE users.id = auth.uid() AND users.is_admin = TRUE
        )
    );

COMMENT ON TABLE agent_telemetry IS 'Agent execution telemetry for observability and analytics';
COMMENT ON COLUMN agent_telemetry.tools_called IS 'Array of tool names executed during conversation turn';
COMMENT ON COLUMN agent_telemetry.total_execution_time_ms IS 'Total time from user message to response (milliseconds)';
