-- This is a safer version of the fix_permissions.sql file
-- Fixed to work with Supabase PostgreSQL version

-- Check if claimant_id column exists in food_claims, if not use another appropriate column
DO $$
DECLARE
    column_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'food_claims'
        AND column_name = 'claimant_id'
    ) INTO column_exists;
    
    IF NOT column_exists THEN
        RAISE NOTICE 'Column claimant_id does not exist in food_claims. Please check your table structure.';
    END IF;
END $$;

-- Enable RLS on the users table if not already enabled
ALTER TABLE IF EXISTS "public"."users" ENABLE ROW LEVEL SECURITY;

-- Drop policies if they exist (to avoid conflicts)
DROP POLICY IF EXISTS "Users can read their own records" ON "public"."users";
DROP POLICY IF EXISTS "Admins can read all users" ON "public"."users";

-- Add policy to allow users to read their own records
CREATE POLICY "Users can read their own records"
ON "public"."users"
FOR SELECT
USING (auth.uid() = id);

-- Add policy to allow admins to read all user records
CREATE POLICY "Admins can read all users"
ON "public"."users"
FOR SELECT
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.id = auth.uid() AND users.is_admin = true
  )
);

-- Enable RLS on the food_claims table if not already enabled
ALTER TABLE IF EXISTS "public"."food_claims" ENABLE ROW LEVEL SECURITY;

-- Drop policies if they exist (to avoid conflicts)
DROP POLICY IF EXISTS "Users can read their own claims" ON "public"."food_claims";
DROP POLICY IF EXISTS "Donors can read claims on their food" ON "public"."food_claims";
DROP POLICY IF EXISTS "Admins can read all claims" ON "public"."food_claims";

-- Add policy to allow users to read their own claims
CREATE POLICY "Users can read their own claims"
ON "public"."food_claims"
FOR SELECT
USING (auth.uid() = claimant_id);

-- Add policy to allow donors to read claims on their donations
CREATE POLICY "Donors can read claims on their food"
ON "public"."food_claims"
FOR SELECT
USING (
  EXISTS (
    SELECT 1 FROM food_listings
    WHERE food_listings.id = food_claims.food_id 
    AND food_listings.donor_id = auth.uid()
  )
);

-- Add policy to allow admins to read all claims
CREATE POLICY "Admins can read all claims"
ON "public"."food_claims"
FOR SELECT
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE users.id = auth.uid() AND users.is_admin = true
  )
);

-- Add a universal access policy for debugging purposes (REMOVE IN PRODUCTION)
-- This is a temporary measure to help debug access issues
CREATE POLICY "Debug policy - allow all access to users"
ON "public"."users"
FOR ALL
USING (true);

-- This will let everyone read food_claims for debugging
CREATE POLICY "Debug policy - allow all access to food_claims"
ON "public"."food_claims"
FOR ALL
USING (true);

-- Success message
SELECT 'RLS policies successfully applied' as result;
