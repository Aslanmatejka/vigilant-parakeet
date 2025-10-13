-- Migration: Add pending/approved/declined status to food_listings and notification logic

-- Update listing_status type to include pending, approved, declined
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'listing_status') THEN
        CREATE TYPE listing_status AS ENUM ('pending', 'approved', 'declined', 'active', 'completed', 'expired', 'cancelled');
    ELSE
        -- Add new values if not present
        ALTER TYPE listing_status ADD VALUE IF NOT EXISTS 'pending';
        ALTER TYPE listing_status ADD VALUE IF NOT EXISTS 'approved';
        ALTER TYPE listing_status ADD VALUE IF NOT EXISTS 'declined';
    END IF;
END $$;

-- Update food_listings table default status to 'pending'
ALTER TABLE food_listings ALTER COLUMN status SET DEFAULT 'pending';

-- Add trigger to send notification on status change to declined
CREATE OR REPLACE FUNCTION notify_declined_submission()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'declined' AND OLD.status <> 'declined' THEN
        INSERT INTO notifications (user_id, title, message, type, data)
        VALUES (
            NEW.user_id,
            'Food Submission Not Approved',
            'Your food submission was not approved by the admin. Please review the guidelines and try again.',
            'submission_declined',
            jsonb_build_object('listing_id', NEW.id)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_notify_declined_submission ON food_listings;
CREATE TRIGGER trigger_notify_declined_submission
AFTER UPDATE ON food_listings
FOR EACH ROW
EXECUTE FUNCTION notify_declined_submission();
