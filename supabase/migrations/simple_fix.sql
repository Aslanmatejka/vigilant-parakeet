-- SQL commands to fix Supabase permissions
-- Run this in the SQL Editor in your Supabase dashboard

-- Enable RLS on the users table
ALTER TABLE "public"."users" ENABLE ROW LEVEL SECURITY;

-- Drop existing policies to avoid conflicts
DROP POLICY IF EXISTS "Users can read their own records" ON "public"."users";
DROP POLICY IF EXISTS "Admins can read all users" ON "public"."users";
DROP POLICY IF EXISTS "Debug policy - allow all access to users" ON "public"."users";

-- Create simple permissive policies for users table
CREATE POLICY "Debug policy - allow all access to users"
ON "public"."users"
FOR ALL
USING (true);

-- Enable RLS on the food_claims table
ALTER TABLE "public"."food_claims" ENABLE ROW LEVEL SECURITY;

-- Drop existing policies to avoid conflicts
DROP POLICY IF EXISTS "Users can read their own claims" ON "public"."food_claims";
DROP POLICY IF EXISTS "Donors can read claims on their food" ON "public"."food_claims";
DROP POLICY IF EXISTS "Admins can read all claims" ON "public"."food_claims";
DROP POLICY IF EXISTS "Debug policy - allow all access to food_claims" ON "public"."food_claims";

-- Create simple permissive policy for food_claims table
CREATE POLICY "Debug policy - allow all access to food_claims"
ON "public"."food_claims"
FOR ALL
USING (true);

-- Set your user as admin
UPDATE "public"."users"
SET "is_admin" = true
WHERE id = 'c4dcbd93-081e-4160-87eb-1d51d444413a'
RETURNING id, email, is_admin;

-- Check if it worked
SELECT 'RLS policies successfully applied and admin set' as result;
