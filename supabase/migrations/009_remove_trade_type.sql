ALTER TYPE listing_type RENAME TO listing_type_old;
CREATE TYPE listing_type AS ENUM ('donation');
-- This file has been archived and renamed to 009_remove_trade_type.sql.bak
-- Update existing columns to use new type
ALTER TABLE food_listings 
  ALTER COLUMN listing_type TYPE listing_type 
  USING (CASE WHEN listing_type::text = 'trade' THEN 'donation'::listing_type ELSE listing_type::text::listing_type END);

-- Drop old type
DROP TYPE listing_type_old;
