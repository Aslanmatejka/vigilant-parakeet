/*
  # Add Impact Tracking Columns to Food Claims

  1. Changes
    - Add `people` column to food_claims table (number of general people impacted)
    - Add `students` column to food_claims table (number of students impacted)
    - Add `school_staff` column to food_claims table (number of school staff impacted)

  2. Purpose
    - Enable detailed impact tracking for food sharing
    - Support community impact metrics calculations
    - Track different beneficiary categories

  3. Notes
    - Columns default to 0 to avoid null issues in calculations
    - All columns are optional (not required) in forms
*/

-- Add impact tracking columns to food_claims table
DO $$
BEGIN
  -- Add people column if it doesn't exist
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'food_claims' AND column_name = 'people'
  ) THEN
    ALTER TABLE food_claims ADD COLUMN people INTEGER DEFAULT 0;
  END IF;

  -- Add students column if it doesn't exist
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'food_claims' AND column_name = 'students'
  ) THEN
    ALTER TABLE food_claims ADD COLUMN students INTEGER DEFAULT 0;
  END IF;

  -- Add school_staff column if it doesn't exist
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'food_claims' AND column_name = 'school_staff'
  ) THEN
    ALTER TABLE food_claims ADD COLUMN school_staff INTEGER DEFAULT 0;
  END IF;
END $$;

-- Update existing rows to have 0 instead of NULL
UPDATE food_claims
SET people = 0
WHERE people IS NULL;

UPDATE food_claims
SET students = 0
WHERE students IS NULL;

UPDATE food_claims
SET school_staff = 0
WHERE school_staff IS NULL;