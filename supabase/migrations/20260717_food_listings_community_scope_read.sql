-- Scope published food listings by viewer community at the database layer.
-- Recipients only SELECT approved/active donations from their community
-- plus the shared warehouse (id = 1). Admins and listing owners keep
-- existing broader policies.

DROP POLICY IF EXISTS "Anyone can view published food listings" ON food_listings;

CREATE POLICY "Anyone can view published food listings" ON food_listings
  FOR SELECT TO authenticated
  USING (
    status IN ('approved', 'active')
    AND (
      community_id = 1
      OR (
        community_id IS NOT NULL
        AND community_id = (
          SELECT u.community_id
          FROM users u
          WHERE u.id = (SELECT auth.uid())
        )
      )
    )
  );
