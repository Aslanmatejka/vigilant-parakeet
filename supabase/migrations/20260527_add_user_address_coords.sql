-- Persist geocoded coordinates of each user's profile address so that
-- map/AI/distance features can use the profile address as a fallback origin
-- when live GPS is unavailable or denied.

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS latitude numeric(9,6),
  ADD COLUMN IF NOT EXISTS longitude numeric(9,6),
  ADD COLUMN IF NOT EXISTS address_geocoded_at timestamptz;

COMMENT ON COLUMN public.users.latitude IS 'Geocoded latitude of profile address; used as fallback origin for distance/route features.';
COMMENT ON COLUMN public.users.longitude IS 'Geocoded longitude of profile address.';
COMMENT ON COLUMN public.users.address_geocoded_at IS 'When the address was last geocoded.';

CREATE INDEX IF NOT EXISTS idx_users_latlng ON public.users (latitude, longitude);
