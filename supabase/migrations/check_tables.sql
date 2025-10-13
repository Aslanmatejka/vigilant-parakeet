-- Comprehensive database check script
-- Run this in the Supabase SQL Editor to diagnose table issues

-- Get table information
SELECT 
  table_name, 
  table_schema,
  rls_enabled
FROM 
  information_schema.tables t
JOIN
  pg_tables pt ON t.table_name = pt.tablename
WHERE 
  table_schema = 'public'
ORDER BY 
  table_name;

-- Get policy information
SELECT
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual
FROM
  pg_policies
WHERE
  schemaname = 'public'
ORDER BY
  tablename, policyname;

-- Check your admin user
SELECT 
  id, 
  email, 
  is_admin
FROM 
  users
WHERE 
  id = 'c4dcbd93-081e-4160-87eb-1d51d444413a';

-- Check food_claims table structure
SELECT 
  column_name, 
  data_type
FROM 
  information_schema.columns
WHERE 
  table_name = 'food_claims'
  AND table_schema = 'public'
ORDER BY 
  ordinal_position;

-- Check for claimant_id in food_claims (this needs to exist for the policies)
SELECT 
  COUNT(*) AS has_claimant_id
FROM 
  information_schema.columns
WHERE 
  table_name = 'food_claims'
  AND column_name = 'claimant_id'
  AND table_schema = 'public';

-- Check count of pending food claims (for testing)
SELECT 
  COUNT(*) AS pending_claim_count
FROM 
  food_claims
WHERE 
  status = 'pending';
