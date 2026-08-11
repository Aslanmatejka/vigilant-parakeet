-- When a food request goes live, also notify donors/organizers in that community.
-- Extends notify_requester_food_request_listed so form, Nouri, and admin approve
-- all fan out without relying on the admin JS path alone.

CREATE OR REPLACE FUNCTION public.notify_requester_food_request_listed()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
  IF NEW.listing_type IS DISTINCT FROM 'request'::listing_type THEN
    RETURN NEW;
  END IF;

  IF NEW.status IS DISTINCT FROM 'approved'::listing_status
     AND NEW.status IS DISTINCT FROM 'active'::listing_status THEN
    RETURN NEW;
  END IF;

  -- Fire only when the request newly becomes listed.
  IF TG_OP = 'UPDATE' THEN
    IF OLD.status IS NOT DISTINCT FROM NEW.status THEN
      RETURN NEW;
    END IF;
    IF OLD.status IN ('approved'::listing_status, 'active'::listing_status) THEN
      RETURN NEW;
    END IF;
  END IF;

  -- Requester confirmation
  IF NEW.user_id IS NOT NULL THEN
    INSERT INTO public.notifications (user_id, title, message, type, read, data)
    VALUES (
      NEW.user_id,
      'Food request listed',
      format(
        'Your request "%s" is live on Community Requests — donors in your community can share matching food.',
        coalesce(NEW.title, 'Food')
      ),
      'food_request_listed',
      false,
      jsonb_build_object(
        'listingId', NEW.id,
        'listing_type', 'request',
        'status', NEW.status,
        'path', '/profile?tab=listings&filter=requests'
      )
    );
  END IF;

  -- Donors / organizers in the same community
  IF NEW.community_id IS NOT NULL THEN
    INSERT INTO public.notifications (user_id, title, message, type, read, data)
    SELECT
      u.id,
      'New community food request',
      format(
        '"%s" was just posted — open Community Requests to share matching food.',
        coalesce(NEW.title, 'Food')
      ),
      'community_food_request',
      false,
      jsonb_build_object(
        'listingId', NEW.id,
        'listing_type', 'request',
        'community_id', NEW.community_id,
        'path', '/community-requests'
      )
    FROM public.users u
    WHERE u.community_id = NEW.community_id
      AND u.community_role IN ('donor', 'organizer')
      AND (NEW.user_id IS NULL OR u.id IS DISTINCT FROM NEW.user_id)
    LIMIT 200;
  END IF;

  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.notify_requester_food_request_listed() IS
  'Notify requester + community donors/organizers when a food request goes live.';
