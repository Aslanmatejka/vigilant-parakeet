-- Allow users to delete their own receipts.
-- Without this, the Reclaim flow in components/common/Receipt.jsx cannot
-- remove the old (expired) receipt after re-pointing its claims to the new
-- receipt — Postgres silently denies the DELETE under RLS, leaving an empty
-- expired card visible in the user's receipts list.

DROP POLICY IF EXISTS "receipts_delete_own" ON receipts;
CREATE POLICY "receipts_delete_own" ON receipts FOR DELETE TO public
  USING ((select auth.uid()) = user_id);
