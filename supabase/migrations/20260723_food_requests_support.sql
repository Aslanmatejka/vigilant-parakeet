-- Food requests reuse food_listings.listing_type = 'request' (enum already exists).
-- Harden stats triggers, admin copy, browse indexes, and public read policies.

-- 1) Fast community-request lookups
CREATE INDEX IF NOT EXISTS idx_food_listings_requests_community
  ON public.food_listings (community_id, status, created_at DESC)
  WHERE listing_type = 'request';

CREATE INDEX IF NOT EXISTS idx_food_listings_listing_type_status
  ON public.food_listings (listing_type, status);

-- 2) Convenience view for Community Requests UI / reporting
CREATE OR REPLACE VIEW public.community_food_requests AS
SELECT
  fl.id,
  fl.title,
  fl.description,
  fl.quantity,
  fl.unit,
  fl.category,
  fl.status,
  fl.expiry_date,
  fl.pickup_by,
  fl.full_address,
  fl.location,
  fl.latitude,
  fl.longitude,
  fl.dietary_tags,
  fl.allergens,
  fl.user_id,
  fl.community_id,
  fl.donor_name AS requester_name,
  fl.donor_email AS requester_email,
  fl.donor_phone AS requester_phone,
  fl.created_at,
  fl.updated_at
FROM public.food_listings fl
WHERE fl.listing_type = 'request';

COMMENT ON VIEW public.community_food_requests IS
  'Open/closed food need requests (food_listings where listing_type = request).';

GRANT SELECT ON public.community_food_requests TO authenticated, anon, service_role;

-- 3) Do not count food requests as donations in impact/donor stats
CREATE OR REPLACE FUNCTION public.increment_impact_on_food_share()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $$
BEGIN
  IF NEW.listing_type IS DISTINCT FROM 'donation'::listing_type THEN
    RETURN NEW;
  END IF;
  UPDATE user_stats
  SET total_impact_score = total_impact_score + 1
  WHERE user_id = NEW.user_id;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_donor_stats()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  food_weight NUMERIC;
BEGIN
  IF NEW.listing_type IS DISTINCT FROM 'donation'::listing_type THEN
    RETURN NEW;
  END IF;

  IF NEW.status = 'approved' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'approved') THEN
    food_weight := NEW.quantity;

    INSERT INTO user_stats (user_id, total_donations, total_food_saved, total_impact_score)
    VALUES (NEW.user_id, 0, 0, 0)
    ON CONFLICT (user_id) DO NOTHING;

    UPDATE user_stats
    SET
      total_donations = total_donations + 1,
      total_food_saved = total_food_saved + food_weight,
      total_impact_score = ROUND((total_food_saved + food_weight) * 2.5),
      last_updated = NOW()
    WHERE user_id = NEW.user_id;
  END IF;

  RETURN NEW;
END;
$$;

-- 4) Admin notifications: distinguish food requests
CREATE OR REPLACE FUNCTION public.notify_admins_new_listing()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  headline text;
  body text;
  is_request boolean := (NEW.listing_type = 'request'::listing_type);
BEGIN
  IF is_request THEN
    IF NEW.status = 'pending' THEN
      headline := 'New food request awaiting approval';
      body := format('Request "%s" needs review. Open Admin to approve or decline.', coalesce(NEW.title, 'Food request'));
    ELSE
      headline := 'New food request published';
      body := format('Request "%s" is live for your community donors.', coalesce(NEW.title, 'Food request'));
    END IF;
  ELSE
    IF NEW.status = 'pending' THEN
      headline := 'New listing awaiting approval';
      body := format('"%s" needs review. Open Admin to approve or decline.', coalesce(NEW.title, 'Food listing'));
    ELSE
      headline := 'New food listing published';
      body := format('"%s" is live (%s). Admins can decline from the dashboard if needed.', coalesce(NEW.title, 'Food listing'), coalesce(NEW.status, 'approved'));
    END IF;
  END IF;

  INSERT INTO public.notifications (user_id, title, message, type, read, data)
  SELECT u.id, headline, body,
         CASE WHEN is_request THEN 'admin_new_food_request' ELSE 'admin_new_listing' END,
         false,
         jsonb_build_object(
           'listing_id', NEW.id,
           'status', NEW.status,
           'title', NEW.title,
           'listing_type', NEW.listing_type
         )
  FROM public.users u
  WHERE u.is_admin IS TRUE;

  RETURN NEW;
END;
$$;

-- 5) Public/anonymous browse feeds should only show donations
DROP POLICY IF EXISTS "All users can view approved food items" ON public.food_listings;
CREATE POLICY "All users can view approved food items" ON public.food_listings
  FOR SELECT TO public
  USING (
    status = 'approved'::listing_status
    AND listing_type = 'donation'::listing_type
  );

DROP POLICY IF EXISTS "Anyone can view active listings" ON public.food_listings;
CREATE POLICY "Anyone can view active listings" ON public.food_listings
  FOR SELECT TO public
  USING (
    status = 'active'::listing_status
    AND listing_type = 'donation'::listing_type
  );
