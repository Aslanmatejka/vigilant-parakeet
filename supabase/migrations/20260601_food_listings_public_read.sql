-- Allow authenticated users (recipients, donors, volunteers) to browse
-- published food listings created by other users. Without this policy only
-- the listing owner and admins could SELECT rows, so AI photo listings and
-- approved donations never appeared on Find Food for recipients.

DROP POLICY IF EXISTS "Anyone can view published food listings" ON food_listings;

CREATE POLICY "Anyone can view published food listings" ON food_listings
  FOR SELECT TO authenticated
  USING (status IN ('approved', 'active'));
