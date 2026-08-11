-- Align expire_unclaimed_receipts with canonical go-live status (approved).
-- Previously restored inventory as 'active', which reintroduced dual live statuses.

CREATE OR REPLACE FUNCTION expire_unclaimed_receipts()
RETURNS TABLE(expired_count INT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    expired_receipt RECORD;
    total_expired INT := 0;
BEGIN
    FOR expired_receipt IN
        SELECT id FROM receipts
        WHERE status = 'pending'
          AND pickup_by < NOW()
    LOOP
        UPDATE receipts
        SET status = 'expired',
            expired_at = NOW()
        WHERE id = expired_receipt.id;

        -- Restore inventory as approved (canonical go-live status)
        UPDATE food_listings
        SET status = 'approved'
        WHERE id IN (
            SELECT food_id FROM food_claims
            WHERE receipt_id = expired_receipt.id
        );

        UPDATE food_claims
        SET status = 'expired'
        WHERE receipt_id = expired_receipt.id;

        total_expired := total_expired + 1;
    END LOOP;

    RETURN QUERY SELECT total_expired;
END;
$$;

COMMENT ON FUNCTION expire_unclaimed_receipts() IS
    'Marks pending receipts whose pickup_by has passed as expired, returns items to inventory as approved, and marks claims as expired. SECURITY DEFINER so RLS does not block inventory restore.';
