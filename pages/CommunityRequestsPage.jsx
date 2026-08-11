import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import ErrorBoundary from '../components/common/ErrorBoundary';
import Button from '../components/common/Button';
import dataService from '../utils/dataService';
import { useAuth } from '../utils/hooks/useSupabase';
import { useCommunityRole } from '../utils/hooks/useCommunityRole';
import { browseCommunityIdsForUser } from '../utils/communityScope';
import supabase from '../utils/supabaseClient';

function formatDate(value) {
  if (!value) return null;
  try {
    const raw = String(value).slice(0, 10);
    const [y, m, d] = raw.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return String(value).slice(0, 10);
  }
}

/**
 * Browse open food requests in the viewer's community (donors / organizers /
 * recipients). Requests are food_listings with listing_type=request.
 */
function CommunityRequestsPageContent() {
  const navigate = useNavigate();
  const { user, loading: authLoading, isAdmin } = useAuth();
  const communityRole = useCommunityRole();
  const [freshCommunityId, setFreshCommunityId] = React.useState(undefined);
  const [requests, setRequests] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const loadSeqRef = React.useRef(0);
  const hasLoadedRef = React.useRef(false);

  // Auth cache can lag behind DB (4s profile timeout). Resolve community_id
  // before scoping so the first fetch doesn't use an empty community filter.
  React.useEffect(() => {
    let cancelled = false;

    if (authLoading) return undefined;

    if (!user?.id || isAdmin) {
      setFreshCommunityId(null);
      return undefined;
    }

    const cached = user.community_id;
    if (cached != null && cached !== '') {
      setFreshCommunityId(cached);
      return undefined;
    }

    (async () => {
      try {
        const { data, error: profileError } = await supabase
          .from('users')
          .select('community_id')
          .eq('id', user.id)
          .maybeSingle();
        if (cancelled) return;
        if (profileError) throw profileError;
        setFreshCommunityId(data?.community_id ?? null);
      } catch (err) {
        console.warn('Community requests: could not resolve community_id', err);
        if (!cancelled) setFreshCommunityId(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authLoading, user?.id, user?.community_id, isAdmin]);

  const scopeUser = React.useMemo(() => {
    if (!user) return null;
    const communityId = freshCommunityId !== undefined ? freshCommunityId : user.community_id;
    return { ...user, community_id: communityId ?? null };
  }, [user, freshCommunityId]);

  const scopeReady = !authLoading && (isAdmin || !user?.id || freshCommunityId !== undefined);

  const allowedCommunityIds = React.useMemo(
    () => browseCommunityIdsForUser(scopeUser, { isAdmin }),
    [scopeUser?.community_id, isAdmin, scopeUser]
  );

  const buildListingFilters = React.useCallback(() => {
    const listingFilters = {
      listing_type: 'request',
      status: ['approved', 'active'],
      includeExpired: false,
      skipCommunityScope: false,
    };
    if (Array.isArray(allowedCommunityIds)) {
      listingFilters.community_ids = allowedCommunityIds;
    } else if (allowedCommunityIds != null) {
      listingFilters.community_id = allowedCommunityIds;
    }
    return listingFilters;
  }, [allowedCommunityIds]);

  const load = React.useCallback(async ({ background = false, retry = 0 } = {}) => {
    if (!scopeReady) return;

    const seq = ++loadSeqRef.current;
    if (!background && !hasLoadedRef.current) {
      setLoading(true);
    }

    try {
      const rows = await dataService.getFoodListings(buildListingFilters());

      let mine = [];
      if (user?.id) {
        try {
          mine = await dataService.getFoodListings({
            listing_type: 'request',
            status: 'pending',
            user_id: user.id,
            includeExpired: true,
            skipCommunityScope: true,
          });
        } catch {
          mine = [];
        }
      }

      if (seq !== loadSeqRef.current) return;

      const byId = new Map();
      for (const row of [...(Array.isArray(rows) ? rows : []), ...(Array.isArray(mine) ? mine : [])]) {
        if (row?.id) byId.set(row.id, row);
      }
      const list = Array.from(byId.values()).sort(
        (a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)
      );
      setRequests(list);
      setError(null);
      hasLoadedRef.current = true;
    } catch (err) {
      if (seq !== loadSeqRef.current) return;

      const msg = err?.message || '';
      const isAbort =
        err?.name === 'AbortError'
        || err?.code === '20'
        || msg.includes('aborted');
      if (isAbort) return;

      if (retry < 1) {
        await new Promise((resolve) => setTimeout(resolve, 600));
        if (seq === loadSeqRef.current) {
          return load({ background, retry: retry + 1 });
        }
        return;
      }

      console.error('Community requests load failed:', err);
      if (!hasLoadedRef.current) {
        setRequests([]);
        setError('Could not load community requests. Please try again.');
      }
    } finally {
      if (seq === loadSeqRef.current) {
        setLoading(false);
      }
    }
  }, [scopeReady, buildListingFilters, user?.id]);

  React.useEffect(() => {
    if (!scopeReady) return undefined;
    load();
    return () => {
      loadSeqRef.current += 1;
    };
  }, [scopeReady, load]);

  React.useEffect(() => {
    if (!scopeReady) return undefined;

    let refetchTimer = null;
    const schedule = () => {
      if (refetchTimer) clearTimeout(refetchTimer);
      refetchTimer = setTimeout(() => {
        refetchTimer = null;
        load({ background: true });
      }, 800);
    };

    const channel = supabase
      .channel(`community-food-requests-${user?.id || 'guest'}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'food_listings' },
        (payload) => {
          const row = payload.new || payload.old;
          if (row && String(row.listing_type || '').toLowerCase() !== 'request') {
            return;
          }
          schedule();
        }
      )
      .subscribe();

    return () => {
      if (refetchTimer) clearTimeout(refetchTimer);
      supabase.removeChannel(channel);
    };
  }, [scopeReady, load, user?.id]);

  const isDonor = communityRole === 'donor';
  const canFulfillRequests = isDonor || communityRole === 'organizer';
  const missingCommunity =
    scopeReady
    && !isAdmin
    && user?.id
    && Array.isArray(allowedCommunityIds)
    && allowedCommunityIds.length === 0;

  return (
    <div
      data-name="community-requests-page"
      className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40"
      role="main"
    >
      <header className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10" aria-hidden="true">
          <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
          <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
        </div>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
          <div className="text-center">
            <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
              <i className="fas fa-inbox mr-2" aria-hidden="true" />
              Food Near You
            </span>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
              Community{' '}
              <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                Requests
              </span>
            </h1>
            <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
              {canFulfillRequests
                ? 'Neighbors asked for food that isn’t on Find Food yet. Share a matching donation when you can.'
                : 'See what others in your community are asking for — or post your own request.'}
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {isDonor ? (
                <Button variant="primary" onClick={() => navigate('/share')}>
                  Share food
                </Button>
              ) : (
                <>
                  <Button variant="secondary" onClick={() => navigate('/find')}>
                    Find Food
                  </Button>
                  <Button variant="primary" onClick={() => navigate('/request')}>
                    Request food
                  </Button>
                  {canFulfillRequests && (
                    <Button variant="secondary" onClick={() => navigate('/share')}>
                      Share food
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pb-12 sm:pb-16">
        {loading && requests.length === 0 && !error ? (
          <div className="rounded-2xl border border-gray-200 bg-white p-12 text-center text-gray-500">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#2CABE3] mx-auto" />
            <p className="mt-3 text-sm">Loading requests…</p>
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-12 text-center">
            <i className="fas fa-exclamation-circle text-3xl text-red-400 mb-3" aria-hidden="true" />
            <p className="text-lg font-semibold text-gray-900">Couldn&apos;t load requests</p>
            <p className="mt-1 text-sm text-gray-600">{error}</p>
            <Button
              variant="primary"
              className="mt-5"
              onClick={() => load({ background: false })}
            >
              Try again
            </Button>
          </div>
        ) : missingCommunity ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-12 text-center">
            <i className="fas fa-school text-3xl text-amber-500 mb-3" aria-hidden="true" />
            <p className="text-lg font-semibold text-gray-900">Community not set</p>
            <p className="mt-1 text-sm text-gray-600 max-w-md mx-auto">
              Add your school or community in Settings so we can show requests for your area.
            </p>
            <Button
              variant="primary"
              className="mt-5"
              onClick={() => navigate('/settings')}
            >
              Open Settings
            </Button>
          </div>
        ) : requests.length === 0 ? (
          <div className="rounded-2xl border border-gray-200 bg-white p-12 text-center">
            <i className="fas fa-inbox text-4xl text-gray-300 mb-3" aria-hidden="true" />
            <p className="text-lg font-semibold text-gray-900">No open requests right now</p>
            <p className="mt-1 text-sm text-gray-500">
              {isDonor
                ? 'When neighbors post needs, they’ll show up here for you to share matching food.'
                : 'Check Find Food first — or post a request if you still need something.'}
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {isDonor ? (
                <Link
                  to="/share"
                  className="inline-flex items-center gap-1.5 rounded-full bg-[#2CABE3] text-white px-4 py-2 text-sm font-semibold hover:bg-[#2596c7]"
                >
                  Share food
                </Link>
              ) : (
                <>
                  <Link
                    to="/find"
                    className="inline-flex items-center gap-1.5 rounded-full bg-white border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Browse Find Food
                  </Link>
                  <Link
                    to="/request"
                    className="inline-flex items-center gap-1.5 rounded-full bg-[#2CABE3] text-white px-4 py-2 text-sm font-semibold hover:bg-[#2596c7]"
                  >
                    Request food
                  </Link>
                </>
              )}
            </div>
          </div>
        ) : (
          <ul className="space-y-4">
            {requests.map((req) => {
              const community = req.communities;
              const communityName = Array.isArray(community)
                ? community[0]?.name
                : community?.name || req.community_name;
              const qty = [req.quantity, req.unit].filter((v) => v != null && v !== '').join(' ');
              const needed = formatDate(req.expiry_date || req.pickup_by);
              const isMine = user?.id && String(req.user_id) === String(user.id);
              const pending = String(req.status || '').toLowerCase() === 'pending';

              return (
                <li
                  key={req.id}
                  className="rounded-2xl border border-[#2CABE3]/15 bg-white shadow-sm p-5 sm:p-6"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold text-gray-900">{req.title}</h2>
                        <span className="inline-flex items-center rounded-full bg-emerald-50 text-emerald-800 px-2 py-0.5 text-[11px] font-semibold capitalize">
                          {req.category || 'other'}
                        </span>
                        {pending && (
                          <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 px-2 py-0.5 text-[11px] font-semibold">
                            Pending approval
                          </span>
                        )}
                        {isMine && (
                          <span className="inline-flex items-center rounded-full bg-[#2CABE3]/15 text-[#1a7a9e] px-2 py-0.5 text-[11px] font-semibold">
                            Your request
                          </span>
                        )}
                      </div>
                      {req.description && (
                        <p className="mt-2 text-sm text-gray-600 whitespace-pre-wrap">{req.description}</p>
                      )}
                      <dl className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm text-gray-700">
                        {qty && (
                          <div>
                            <dt className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">Amount</dt>
                            <dd>{qty}</dd>
                          </div>
                        )}
                        {communityName && (
                          <div>
                            <dt className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">Community</dt>
                            <dd>{communityName}</dd>
                          </div>
                        )}
                        {needed && (
                          <div>
                            <dt className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold">Needed by</dt>
                            <dd>{needed}</dd>
                          </div>
                        )}
                      </dl>
                    </div>
                    {canFulfillRequests && !isMine && !pending && (
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => {
                          const params = new URLSearchParams();
                          if (req.title) params.set('request', req.title);
                          if (req.category) params.set('category', req.category);
                          if (req.description) {
                            const desc = String(req.description).trim();
                            if (desc) params.set('description', desc.slice(0, 240));
                          }
                          if (req.quantity != null && req.quantity !== '') {
                            params.set('quantity', String(req.quantity));
                          }
                          if (req.unit) params.set('unit', req.unit);
                          // Pin the donation to the request's community (id preferred).
                          const reqCommunityId =
                            req.community_id
                            || (Array.isArray(community) ? community[0]?.id : community?.id)
                            || null;
                          if (reqCommunityId) params.set('community_id', String(reqCommunityId));
                          if (communityName) params.set('community', communityName);
                          if (req.id) params.set('fulfilling_request_id', String(req.id));
                          const neededBy = req.expiry_date || req.pickup_by;
                          if (neededBy) params.set('needed_by', String(neededBy).slice(0, 10));
                          navigate(`/share?${params.toString()}`);
                        }}
                      >
                        Share matching food
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function CommunityRequestsPage() {
  return (
    <ErrorBoundary>
      <CommunityRequestsPageContent />
    </ErrorBoundary>
  );
}

export default CommunityRequestsPage;
