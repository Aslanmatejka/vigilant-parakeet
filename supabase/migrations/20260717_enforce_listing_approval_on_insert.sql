-- Force community donor inserts to pending when admin approval is required.
-- Backend (service role) and admin users may still insert approved listings.

CREATE OR REPLACE FUNCTION public.enforce_listing_approval_on_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  approval_required boolean := true;
  is_admin boolean := false;
BEGIN
  IF NEW.status IS NULL OR NEW.status NOT IN ('approved', 'active') THEN
    RETURN NEW;
  END IF;

  SELECT COALESCE(
    CASE
      WHEN ps.value = 'true'::jsonb THEN true
      WHEN ps.value = 'false'::jsonb THEN false
      WHEN jsonb_typeof(ps.value) = 'string' AND lower(trim(both '"' from ps.value::text)) IN ('true', '1', 'yes', 'on') THEN true
      WHEN jsonb_typeof(ps.value) = 'string' AND lower(trim(both '"' from ps.value::text)) IN ('false', '0', 'no', 'off') THEN false
      ELSE true
    END,
    true
  )
  INTO approval_required
  FROM public.platform_settings ps
  WHERE ps.key = 'require_listing_approval'
  LIMIT 1;

  IF NOT approval_required THEN
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

  NEW.status := 'pending';
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_listing_approval_on_insert ON public.food_listings;
CREATE TRIGGER trg_enforce_listing_approval_on_insert
  BEFORE INSERT ON public.food_listings
  FOR EACH ROW
  EXECUTE FUNCTION public.enforce_listing_approval_on_insert();
