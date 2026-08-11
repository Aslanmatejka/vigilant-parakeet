/**
 * Community scope helpers (Jest)
 */
import {
  browseCommunityIdsForUser,
  listingVisibleToCommunityScope,
  WAREHOUSE_COMMUNITY_ID,
} from '../utils/communityScope.js';

describe('browseCommunityIdsForUser', () => {
  it('returns null for admins (unrestricted)', () => {
    expect(browseCommunityIdsForUser({ community_id: 8 }, { isAdmin: true })).toBeNull();
  });

  it('scopes school users to their community only (not warehouse)', () => {
    expect(browseCommunityIdsForUser({ community_id: 8 }, { isAdmin: false }))
      .toEqual([8]);
  });

  it('warehouse members only see warehouse', () => {
    expect(browseCommunityIdsForUser({ community_id: WAREHOUSE_COMMUNITY_ID }, { isAdmin: false }))
      .toEqual([WAREHOUSE_COMMUNITY_ID]);
  });

  it('returns null for guests (public browse)', () => {
    expect(browseCommunityIdsForUser(null)).toBeNull();
    expect(browseCommunityIdsForUser(undefined)).toBeNull();
  });

  it('empty when user has no community', () => {
    expect(browseCommunityIdsForUser({}, { isAdmin: false }))
      .toEqual([]);
  });
});

describe('listingVisibleToCommunityScope', () => {
  it('allows all when unrestricted', () => {
    expect(listingVisibleToCommunityScope({ community_id: 99 }, null)).toBe(true);
  });

  it('hides other schools and warehouse from school users', () => {
    expect(listingVisibleToCommunityScope({ community_id: 12 }, [8])).toBe(false);
    expect(listingVisibleToCommunityScope({ community_id: 8 }, [8])).toBe(true);
    expect(listingVisibleToCommunityScope({ community_id: 1 }, [8])).toBe(false);
  });

  it('hides listings with no community when scoped', () => {
    expect(listingVisibleToCommunityScope({ community_id: null }, [8])).toBe(false);
  });

  it('hides everything when allowed set is empty', () => {
    expect(listingVisibleToCommunityScope({ community_id: 1 }, [])).toBe(false);
  });
});
