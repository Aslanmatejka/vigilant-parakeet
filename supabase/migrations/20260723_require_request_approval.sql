-- Dedicated moderation toggle for food requests (listing_type = request).
-- Donations continue to use require_listing_approval.

INSERT INTO public.platform_settings (key, value)
VALUES ('require_request_approval', 'true'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- Prefer require_request_approval for requests; fall back to listing approval
-- when the new key is absent so older environments stay moderated.
CREATE OR REPLACE FUNCTION public.enforce_listing_approval_on_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  approval_required boolean := true;
  setting_key text := 'require_listing_approval';
  is_admin boolean := false;
BEGIN
  IF NEW.status IS NULL OR NEW.status NOT IN ('approved', 'active') THEN
    RETURN NEW;
  END IF;

  IF lower(coalesce(NEW.listing_type, 'donation')) = 'request' THEN
    setting_key := 'require_request_approval';
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
  WHERE ps.key = setting_key
  LIMIT 1;

  -- If request setting missing, fall back to donation listing approval.
  IF NOT FOUND AND setting_key = 'require_request_approval' THEN
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
  END IF;

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
