-- Migration: Simplify community_role to 3 types
-- Description: Remove volunteer, driver, dispatcher roles - keep only donor, recipient, organizer
-- Date: 2026-06-28
-- Author: System Admin

-- Step 1: Migrate existing volunteer/driver users to organizer
-- This preserves their helper/organizer intent without deprecated role types
UPDATE users
SET community_role = 'organizer'
WHERE community_role IN ('volunteer', 'driver', 'dispatcher')
  AND community_role IS NOT NULL;

-- Step 2: Drop the old CHECK constraint
ALTER TABLE users
DROP CONSTRAINT IF EXISTS users_community_role_check;

-- Step 3: Add new CHECK constraint with only 3 allowed roles
ALTER TABLE users
ADD CONSTRAINT users_community_role_check
CHECK (
    community_role IS NULL OR 
    community_role IN ('donor', 'recipient', 'organizer')
);

COMMENT ON COLUMN users.community_role IS 
'User-selected role in the food-sharing community: donor (shares food), recipient (receives food), organizer (coordinates distributions). NOT a security role (see users.role for auth).';
