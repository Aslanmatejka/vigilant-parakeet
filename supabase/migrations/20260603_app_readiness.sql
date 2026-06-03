-- App readiness pass: missing column referenced by dataService, perf indexes
-- used by AI nearby search and dashboard, and storage buckets the app
-- uploads to (avatars, food-images). All statements are idempotent.

-- 1. Verification status column on food_claims (read by dataService selects)
ALTER TABLE IF EXISTS food_claims
    ADD COLUMN IF NOT EXISTS verification_status TEXT DEFAULT 'pending';

-- 2. Geo index for AI bounding-box search (skips NULL coords)
CREATE INDEX IF NOT EXISTS idx_food_listings_geo
    ON food_listings (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- 3. Hot path index: active/approved listings ordered by expiry
CREATE INDEX IF NOT EXISTS idx_food_listings_status_expiry
    ON food_listings (status, expiry_date DESC);

-- 4. Public storage buckets the app expects to exist
INSERT INTO storage.buckets (id, name, public)
VALUES ('avatars', 'avatars', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public)
VALUES ('food-images', 'food-images', true)
ON CONFLICT (id) DO NOTHING;
