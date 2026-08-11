/**
 * Community-scoped browse helpers.
 *
 * Recipients only see food posted to their own community. DoGoods Warehouse
 * (id = 1) is a normal community — not a global broadcast to every school.
 * Admins see everything.
 */

export const WAREHOUSE_COMMUNITY_ID = 1;

function normalizeCommunityId(value) {
  if (value == null || value === '') return null;
  const n = Number(value);
  if (Number.isFinite(n) && String(n) === String(value).trim()) return n;
  return value;
}

/**
 * Community IDs a browse/search request may include.
 * - null  → no restriction (admin / explicit bypass)
 * - []    → no communities allowed (empty results)
 * - [..]  → restrict to these IDs
 */
export function browseCommunityIdsForUser(user, { isAdmin = false } = {}) {
  if (isAdmin) return null;

  // Guests browse via RLS public policies — no client-side community filter.
  if (!user) return null;

  const own = normalizeCommunityId(user?.community_id);
  if (own == null) {
    // Authenticated but no school/warehouse affiliation → no community food.
    return [];
  }

  return [own];
}

/** True when a listing belongs to the viewer's allowed community set. */
export function listingVisibleToCommunityScope(listing, allowedIds) {
  if (allowedIds == null) return true;
  if (!Array.isArray(allowedIds) || allowedIds.length === 0) return false;
  const cid = listing?.community_id;
  if (cid == null || cid === '') return false;
  const allowed = new Set(allowedIds.map(String));
  return allowed.has(String(cid));
}
