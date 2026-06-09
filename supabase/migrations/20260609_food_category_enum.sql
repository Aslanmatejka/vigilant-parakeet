-- Add missing food_category enum values that are shown in FoodForm but were
-- absent from the DB enum, causing INSERT failures for those categories.
ALTER TYPE food_category ADD VALUE IF NOT EXISTS 'seafood';
ALTER TYPE food_category ADD VALUE IF NOT EXISTS 'frozen';
ALTER TYPE food_category ADD VALUE IF NOT EXISTS 'snacks';
ALTER TYPE food_category ADD VALUE IF NOT EXISTS 'beverages';
