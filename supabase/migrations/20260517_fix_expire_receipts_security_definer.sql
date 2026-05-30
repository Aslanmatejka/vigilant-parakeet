-- Fix: expire_unclaimed_receipts must run with elevated privileges so it can
-- update food_listings rows it does not own (RLS otherwise blocks the inventory
-- restore silently, leaving receipts stuck in 'pending' even after the deadline).
--
-- Also grants EXECUTE to authenticated + anon so any logged-in client triggering
-- the client-side fallback can run it. The function only touches expired rows,
-- so this is safe.

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

        -- Return food items to inventory (food_listings uses 'active' enum value)
        UPDATE food_listings
        SET status = 'active'
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

REVOKE ALL ON FUNCTION expire_unclaimed_receipts() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expire_unclaimed_receipts() TO authenticated;
GRANT EXECUTE ON FUNCTION expire_unclaimed_receipts() TO anon;
GRANT EXECUTE ON FUNCTION expire_unclaimed_receipts() TO service_role;

COMMENT ON FUNCTION expire_unclaimed_receipts() IS
    'Marks pending receipts whose pickup_by has passed as expired, returns items to inventory, and marks claims as expired. SECURITY DEFINER so RLS does not block inventory restore.';
