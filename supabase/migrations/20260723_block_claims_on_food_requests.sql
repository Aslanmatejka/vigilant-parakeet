-- Prevent claiming food_listings that are community requests (needs), not donations.
CREATE OR REPLACE FUNCTION public.block_claims_on_food_requests()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  lt listing_type;
BEGIN
  SELECT listing_type INTO lt
  FROM public.food_listings
  WHERE id = NEW.food_id;

  IF lt = 'request'::listing_type THEN
    RAISE EXCEPTION 'Cannot claim a food request listing'
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_block_claims_on_food_requests ON public.food_claims;
CREATE TRIGGER trg_block_claims_on_food_requests
  BEFORE INSERT ON public.food_claims
  FOR EACH ROW
  EXECUTE FUNCTION public.block_claims_on_food_requests();
