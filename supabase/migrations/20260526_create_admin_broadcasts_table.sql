-- Queue table for admin broadcast automation (processed by backend/run_forever.py)

CREATE TABLE IF NOT EXISTS admin_broadcasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'in_app' CHECK (channel IN ('in_app', 'sms', 'both')),
    target_role TEXT,
    community_id BIGINT,
    sent BOOLEAN NOT NULL DEFAULT false,
    sent_at TIMESTAMPTZ,
    delivered_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by UUID REFERENCES auth.users (id)
);

CREATE INDEX IF NOT EXISTS idx_admin_broadcasts_sent ON admin_broadcasts (sent, created_at);
CREATE INDEX IF NOT EXISTS idx_admin_broadcasts_community ON admin_broadcasts (community_id);

ALTER TABLE admin_broadcasts ENABLE ROW LEVEL SECURITY;

-- Admins can create and manage broadcasts.
DROP POLICY IF EXISTS "Admins can manage admin broadcasts" ON admin_broadcasts;
CREATE POLICY "Admins can manage admin broadcasts" ON admin_broadcasts
FOR ALL
USING (
    EXISTS (
        SELECT 1
        FROM users
        WHERE users.id = auth.uid()
          AND users.is_admin = true
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1
        FROM users
        WHERE users.id = auth.uid()
          AND users.is_admin = true
    )
);

-- Service role/automation can process sent status updates.
DROP POLICY IF EXISTS "Service can process admin broadcasts" ON admin_broadcasts;
CREATE POLICY "Service can process admin broadcasts" ON admin_broadcasts
FOR ALL
USING (auth.role() = 'service_role')
WITH CHECK (auth.role() = 'service_role');
