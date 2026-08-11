-- Default claim moderation on (matches Nouri "wait for admin approval" copy).
INSERT INTO platform_settings (key, value, updated_at)
VALUES ('require_claim_approval', 'true'::jsonb, now())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = now();
