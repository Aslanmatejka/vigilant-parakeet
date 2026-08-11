-- Prevent non-admins from self-approving listings via UPDATE (status bypass).

CREATE OR REPLACE FUNCTION public.enforce_listing_approval_on_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  is_admin boolean := false;
BEGIN
  IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
    RETURN NEW;
  END IF;

  IF auth.uid() IS NOT NULL THEN
    SELECT COALESCE(u.is_admin, false)
    INTO is_admin
    FROM public.users u
    WHERE u.id = auth.uid()
    LIMIT 1;
  END IF;

  IF is_admin THEN
    RETURN NEW;
  END IF;

  -- Non-admins may not promote their own listing to approved/active.
  IF NEW.status IN ('approved', 'active')
     AND OLD.status IS DISTINCT FROM NEW.status THEN
    NEW.status := OLD.status;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_listing_approval_on_update ON public.food_listings;
CREATE TRIGGER trg_enforce_listing_approval_on_update
  BEFORE UPDATE ON public.food_listings
  FOR EACH ROW
  EXECUTE FUNCTION public.enforce_listing_approval_on_update();
