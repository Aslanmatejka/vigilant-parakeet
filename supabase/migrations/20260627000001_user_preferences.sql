-- Migration: Create user_preferences table for preference learning
-- Description: Stores learned user preferences (food types, search radius, etc.)
-- Date: 2026-06-27

CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    preferences JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);

-- RLS Policies
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- Users can read their own preferences
CREATE POLICY "Users can view own preferences"
    ON user_preferences FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own preferences
CREATE POLICY "Users can insert own preferences"
    ON user_preferences FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own preferences
CREATE POLICY "Users can update own preferences"
    ON user_preferences FOR UPDATE
    USING (auth.uid() = user_id);

-- Service role can do everything
CREATE POLICY "Service role full access to preferences"
    ON user_preferences FOR ALL
    USING (auth.jwt()->>'role' = 'service_role');

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_user_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_user_preferences_updated_at();

COMMENT ON TABLE user_preferences IS 'Stores learned user preferences for AI agent personalization';
COMMENT ON COLUMN user_preferences.preferences IS 'JSONB object with food_types, search_radius, communities, typical_quantities, etc.';
