-- Migration: Add food_claims table for claim requests

CREATE TYPE claim_status AS ENUM ('pending', 'approved', 'declined');

CREATE TABLE food_claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    food_id UUID REFERENCES food_listings(id) ON DELETE CASCADE,
    claimer_id UUID REFERENCES users(id) ON DELETE CASCADE,
    requester_name VARCHAR(255) NOT NULL,
    requester_email VARCHAR(255),
    requester_phone VARCHAR(20),
    school_district VARCHAR(100),
    school VARCHAR(100),
    school_contact VARCHAR(100),
    school_contact_email VARCHAR(100),
    school_contact_phone VARCHAR(20),
    category VARCHAR(50),
    dietary_restrictions VARCHAR(200),
    members_count INTEGER,
    pickup_time TIME,
    pickup_place VARCHAR(100),
    pickup_contact VARCHAR(100),
    dropoff_time TIME,
    dropoff_place VARCHAR(100),
    dropoff_contact VARCHAR(100),
    status claim_status DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add trigger to send notification on claim status change
CREATE OR REPLACE FUNCTION notify_claim_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'approved' AND OLD.status <> 'approved' THEN
        INSERT INTO notifications (user_id, title, message, type, data)
        VALUES (
            NEW.claimer_id,
            'Food Claim Approved',
            'Your claim for food has been approved! Please check your email for pickup details.',
            'claim_approved',
            jsonb_build_object('claim_id', NEW.id, 'food_id', NEW.food_id)
        );
    ELSIF NEW.status = 'declined' AND OLD.status <> 'declined' THEN
        INSERT INTO notifications (user_id, title, message, type, data)
        VALUES (
            NEW.claimer_id,
            'Food Claim Not Approved',
            'Your claim for food was not approved. Please try again or contact support for more info.',
            'claim_declined',
            jsonb_build_object('claim_id', NEW.id, 'food_id', NEW.food_id)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_notify_claim_status_change ON food_claims;
CREATE TRIGGER trigger_notify_claim_status_change
AFTER UPDATE ON food_claims
FOR EACH ROW
EXECUTE FUNCTION notify_claim_status_change();
