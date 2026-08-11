-- Recipients may only SELECT published donations for THEIR community.
-- DoGoods Warehouse (id = 1) is no longer visible to every school.

DROP POLICY IF EXISTS "Anyone can view published food listings" ON food_listings;

CREATE POLICY "Anyone can view published food listings" ON food_listings
  FOR SELECT TO authenticated
  USING (
    status IN ('approved', 'active')
    AND community_id IS NOT NULL
    AND community_id = (
      SELECT u.community_id
      FROM users u
      WHERE u.id = (SELECT auth.uid())
    )
  );
