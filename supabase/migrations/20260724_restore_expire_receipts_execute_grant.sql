-- CREATE OR REPLACE in 20260715_expire_receipts_restore_approved.sql left
-- expire_unclaimed_receipts without EXECUTE for authenticated clients, so
-- MainLayout / UserReceipts RPC calls return HTTP 403.
-- Re-grant for signed-in users only (housekeeping; not needed for anon).

REVOKE ALL ON FUNCTION public.expire_unclaimed_receipts() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.expire_unclaimed_receipts() TO authenticated;
GRANT EXECUTE ON FUNCTION public.expire_unclaimed_receipts() TO service_role;

COMMENT ON FUNCTION public.expire_unclaimed_receipts() IS
  'Marks pending receipts whose pickup_by has passed as expired, returns items to inventory as approved, and marks claims as expired. SECURITY DEFINER so RLS does not block inventory restore. Callable by authenticated users for best-effort client housekeeping.';
