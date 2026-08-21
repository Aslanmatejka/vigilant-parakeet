-- Documents accessibility profile storage in user_preferences.preferences JSONB.
-- No schema change required — the frontend stores under key "accessibility".

COMMENT ON COLUMN user_preferences.preferences IS
  'JSONB object: food_types, search_radius, accessibility (a11y profile v1), etc.';
