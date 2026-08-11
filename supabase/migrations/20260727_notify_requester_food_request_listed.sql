-- Notify the recipient when their food request becomes listed (live).
-- Covers: form create (approval off), Nouri create, and admin approve.

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

  IF NEW.user_id IS NULL THEN
    RETURN NEW;
  END IF;

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

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_requester_food_request_listed ON public.food_listings;
CREATE TRIGGER trg_notify_requester_food_request_listed
  AFTER INSERT OR UPDATE OF status ON public.food_listings
  FOR EACH ROW
  EXECUTE FUNCTION public.notify_requester_food_request_listed();

COMMENT ON FUNCTION public.notify_requester_food_request_listed() IS
  'In-app notification to the requester when their food request goes live.';
