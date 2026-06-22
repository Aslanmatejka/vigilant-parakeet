import { useState, useEffect, useMemo } from "react";
import { useNavigate, useLocation as useRouterLocation, Link } from 'react-router-dom';
import Button from "../components/common/Button";
import Input from "../components/common/Input";
import FoodCard from "../components/food/FoodCard";
import FoodMap from "../components/common/FoodMap";
import { useFoodListings } from "../utils/hooks/useSupabase";
import { useEffectiveLocation } from "../utils/hooks/useLocation";
import { useAuthContext } from "../utils/AuthContext";
import UrgencyService from "../utils/urgencyService";
import supabase from "../utils/supabaseClient";

// Category mapping for URL parameters
const CATEGORY_MAPPING = {
    fruits: 'produce',
    vegetables: 'produce'
};

// Human labels used by the active-filter chip row.
const CATEGORY_LABELS = {
    produce: 'Produce',
    dairy: 'Dairy',
    bakery: 'Bakery',
    pantry: 'Pantry',
    meat: 'Meat',
    seafood: 'Seafood',
    frozen: 'Frozen',
    snacks: 'Snacks',
    beverages: 'Beverages',
    prepared: 'Prepared',
    other: 'Other',
};

const RADIUS_OPTIONS = [
    { value: '5', label: '5 km' },
    { value: '10', label: '10 km' },
    { value: '25', label: '25 km' },
    { value: '50', label: '50 km' },
    { value: '100', label: '100 km' },
];

const SORT_OPTIONS = [
    { value: 'urgency', label: 'Expiring soon' },
    { value: 'distance', label: 'Nearest', requiresGps: true },
    { value: 'newest', label: 'Newest' },
];

// Small debounce hook so typing into the search input filters the list
// locally without firing on every keystroke.
function useDebouncedValue(value, delay = 250) {
    const [debounced, setDebounced] = useState(value);
    useEffect(() => {
        const t = setTimeout(() => setDebounced(value), delay);
        return () => clearTimeout(t);
    }, [value, delay]);
    return debounced;
}

// Shimmer placeholder shown while the initial fetch is in flight so the
// grid and map don't both hide behind a single spinner.
const FoodCardSkeleton = () => (
    <div className="rounded-xl bg-white border border-gray-100 shadow-sm overflow-hidden animate-pulse">
        <div className="h-28 sm:h-32 bg-gray-200" />
        <div className="p-2.5 sm:p-4 space-y-2">
            <div className="h-4 bg-gray-200 rounded w-3/4" />
            <div className="h-3 bg-gray-100 rounded w-1/2" />
            <div className="h-3 bg-gray-100 rounded w-2/3" />
            <div className="h-9 bg-gray-100 rounded-full mt-2" />
        </div>
    </div>
);

// Calculate distance between two points using Haversine formula
const calculateDistance = (lat1, lon1, lat2, lon2) => {
    const R = 6371; // Earth's radius in kilometers
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = 
        Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
        Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
};

function FindFoodPage({ initialCategory }) {
    const navigate = useNavigate();
    const routerLocation = useRouterLocation();
    const { isAuthenticated, user } = useAuthContext();
    
    const { listings: foods, loading: foodsLoading, error: foodsError, fetchListings } = useFoodListings({ status: ['approved', 'active'] });
    const { 
        location: currentLocation, 
        loading: geoLoading, 
        error: geoError, 
        enableLocation: enableGeolocation,
        source: locationSource,
    } = useEffectiveLocation();
    
    const [searchTerm, setSearchTerm] = useState('');
    const debouncedSearch = useDebouncedValue(searchTerm, 250);
    const [visibleCount, setVisibleCount] = useState(12);
    const [hoveredFoodId, setHoveredFoodId] = useState(null);
    const [communityNames, setCommunityNames] = useState({});
    const [filters, setFilters] = useState({
        category: initialCategory || '',
        radius: '25',
        sortBy: 'urgency',
        community: ''
    });
    // Initial data load and category/community from URL
    useEffect(() => {
        // Scroll to top when page loads
        window.scrollTo(0, 0);

        const params = new URLSearchParams(routerLocation.search);
        const categoryParam = params.get('category');
        const communityParam = params.get('community');

        if (categoryParam) {
            const mappedCategory = CATEGORY_MAPPING[categoryParam.toLowerCase()] || categoryParam;
            setFilters(prev => ({ ...prev, category: mappedCategory }));
        }

        if (communityParam) {
            setFilters(prev => ({ ...prev, community: communityParam }));
        }
    }, [routerLocation.search]);

    // NOTE: intentionally NOT auto-filtering by the user's community —
    // users should see all available food, not just from their own community.

    useEffect(() => {
        let cancelled = false;
        (async () => {
            const { data } = await supabase.from('communities').select('id, name');
            if (cancelled || !data) return;
            const map = {};
            for (const c of data) map[String(c.id)] = c.name;
            setCommunityNames(map);
        })();
        return () => { cancelled = true; };
    }, []);

    // Refresh listings every 60s
    // Also refresh when the tab regains focus or a donor publishes via AI/Share Food.
    useEffect(() => {
        const interval = setInterval(() => {
            fetchListings();
        }, 60000);
        const onFocus = () => fetchListings();
        const onFoodShared = () => fetchListings();
        window.addEventListener('focus', onFocus);
        window.addEventListener('foodShared', onFoodShared);
        return () => {
            clearInterval(interval);
            window.removeEventListener('focus', onFocus);
            window.removeEventListener('foodShared', onFoodShared);
        };
    }, [fetchListings]);

    // Event handlers
    const handleClaim = (food) => {
        // Ensure food object has both id and objectId for compatibility
        const claimFood = {
            ...food,
            id: food.id || food.objectId,
            objectId: food.objectId || food.id
        };
        navigate(`/claim`, { state: { food: claimFood } });
    };


    const handleFilterChange = (e) => {
        const { name, value } = e.target;
        setFilters(prev => ({
            ...prev,
            [name]: value
        }));
        
        // Update URL when category changes
        if (name === 'category') {
            const newUrl = value 
                ? `${routerLocation.pathname}?category=${value}`
                : routerLocation.pathname;
            navigate(newUrl, { replace: true });
        }
    };

    const clearFilter = (name) => {
        if (name === 'search') {
            setSearchTerm('');
            return;
        }
        handleFilterChange({ target: { name, value: '' } });
    };

    const resetAllFilters = () => {
        setSearchTerm('');
        setFilters({
            category: '',
            radius: '25',
            sortBy: 'urgency',
            community: ''
        });
        navigate(routerLocation.pathname, { replace: true });
    };

    const filteredFoods = useMemo(() => {
        // Local-only filtering keeps the UX simple: one source of truth
        // (foods from useFoodListings), one debounced text filter, one
        // memo. No server search round-trip, no two-mode (active/idle)
        // state machine.
        let result = [...foods];

        // Client-side safety: hide any listing whose expiry_date is in the past
        // or whose status is 'expired'. This ensures stale cache never shows expired items.
        //
        // IMPORTANT: food.expiry_date is a YYYY-MM-DD string. new Date("YYYY-MM-DD")
        // parses as UTC midnight, so in US timezones (UTC-7/8) a listing expiring
        // "today" would evaluate as expired at 5pm the day before. Compare date
        // strings directly using local-timezone date to avoid this off-by-one.
        const now = new Date();
        const todayStr = [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, '0'),
            String(now.getDate()).padStart(2, '0'),
        ].join('-');
        result = result.filter(food => {
            if (food.status === 'expired') return false;
            if (!food.expiry_date) return true;
            // ISO date string comparison: "2026-06-08" >= "2026-06-08" → keep.
            return String(food.expiry_date).slice(0, 10) >= todayStr;
        });

        const term = debouncedSearch.trim().toLowerCase();
        if (term) {
            result = result.filter(food =>
                (food.title || '').toLowerCase().includes(term) ||
                (food.description || '').toLowerCase().includes(term) ||
                (typeof food.location === 'string' ? food.location : (food.location?.address || food.full_address || '')).toLowerCase().includes(term)
            );
        }

        if (filters.category) {
            result = result.filter(food => food.category === filters.category);
        }

        if (filters.community) {
            const WAREHOUSE_COMMUNITY_ID = '1';
            result = result.filter(food =>
                // Listings without a community are visible to everyone (e.g. AI photo uploads)
                food.community_id == null || food.community_id === '' ||
                String(food.community_id) === String(filters.community) ||
                food.community === filters.community ||
                String(food.community_id) === WAREHOUSE_COMMUNITY_ID
            );
        }

        // Only show donations (food offers users can claim).
        // Requests have been removed from the platform.
        result = result.filter(food => food.listing_type === 'donation');

        // Location-based filtering — ONLY apply when the user explicitly
        // granted GPS permission. Profile-coordinate fallback must NOT silently
        // filter listings, because users viewing from outside the Bay Area (or
        // whose profile address hasn't been geocoded) would see an almost-empty
        // list while the map still shows all 17+ pins.
        if (currentLocation && filters.radius && locationSource === 'gps') {
            const maxDistance = parseInt(filters.radius);
            // Separate items with and without coordinates
            const withCoords = [];
            const withoutCoords = [];
            result.forEach(food => {
                const lat = food.latitude ?? food.location?.latitude;
                const lng = food.longitude ?? food.location?.longitude;
                if (lat != null && lng != null && !Number.isNaN(Number(lat)) && !Number.isNaN(Number(lng))) {
                    withCoords.push({ ...food, _lat: lat, _lng: lng });
                } else {
                    withoutCoords.push(food);
                }
            });

            const nearby = withCoords.filter(food => {
                const distance = calculateDistance(
                    currentLocation.latitude,
                    currentLocation.longitude,
                    food._lat,
                    food._lng
                );
                food.distance = distance;
                return distance <= maxDistance;
            });

            // Sort nearby by distance, then append items without coordinates
            nearby.sort((a, b) => (a.distance || 0) - (b.distance || 0));
            const filtered = [...nearby, ...withoutCoords];

            // Safety fallback: if radius filtering removed ALL results but there
            // are listings available, show everything so users never see a blank
            // page due to being outside the default radius (e.g. testing from
            // outside the Bay Area, or listings clustered in one area).
            result = filtered.length > 0 ? filtered : result;
        }

        // Apply sorting based on selected option
        if (filters.sortBy === 'urgency') {
            // Sort by urgency (most urgent first)
            result = UrgencyService.sortByUrgency(result);
        } else if (filters.sortBy === 'distance' && currentLocation) {
            // Already sorted by distance above
        } else if (filters.sortBy === 'newest') {
            result.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        }

        return result;
    }, [foods, debouncedSearch, filters, currentLocation, locationSource]);

    // Count of listings whose urgency is critical or high — surfaced in the
    // listings header so the user sees "3 expiring soon" at a glance.
    const urgencyCount = useMemo(() => {
        return filteredFoods.reduce((acc, food) => {
            const level = UrgencyService.calculateUrgencyLevel(food);
            return level === 'critical' || level === 'high' ? acc + 1 : acc;
        }, 0);
    }, [filteredFoods]);

    const activeFilterCount = (
        (filters.category ? 1 : 0)
        + (filters.community ? 1 : 0)
        + (debouncedSearch.trim() ? 1 : 0)
    );

    const emptyReason = [
        filters.category && (CATEGORY_LABELS[filters.category] || filters.category),
        debouncedSearch.trim() && `matching "${debouncedSearch.trim()}"`,
        locationSource === 'gps' && currentLocation && `within ${filters.radius} km`,
    ].filter(Boolean).join(' · ');

    const skeletonGrid = (
        <>
            {Array.from({ length: 6 }).map((_, i) => (
                <FoodCardSkeleton key={`sk-${i}`} />
            ))}
        </>
    );

    const ErrorDisplay = () => (
        <div className="text-center py-12" role="alert">
            <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4" aria-hidden="true"></i>
            <p className="text-gray-600">{foodsError}</p>
            <Button
                variant="secondary"
                className="mt-4"
                onClick={fetchListings}
            >
                Try Again
            </Button>
        </div>
    );

    const FilterChip = ({ children, onRemove, ariaLabel }) => (
        <span className="inline-flex items-center gap-1 rounded-full bg-cyan-50 text-cyan-800 border border-cyan-100 pl-3 pr-1 py-1 text-xs font-medium">
            {children}
            <button
                type="button"
                onClick={onRemove}
                aria-label={ariaLabel}
                className="inline-flex h-6 w-6 items-center justify-center rounded-full hover:bg-cyan-100 text-cyan-700"
            >
                <i className="fas fa-times text-[10px]" aria-hidden="true" />
            </button>
        </span>
    );

    return (
        <div
            data-name="find-food-page"
            className="container mx-auto px-3 sm:px-4"
            role="main"
        >
            <div className="pt-0 pb-6 sm:pb-10">
                <div className="mb-3 sm:mb-4 text-center">
                    <h1 className="text-xl sm:text-2xl font-bold drop-shadow-sm mb-1" style={{ color: '#2CABE3' }}>Find Food Assistance</h1>
                    <p className="mt-1 text-xs sm:text-sm text-gray-600 max-w-lg mx-auto leading-relaxed">
                        Browse nearby food listings and claim what you need. All requests are confidential.
                    </p>
                </div>

                {/* Mobile: quick jump between map and listings */}
                <nav
                    aria-label="Page sections"
                    className="lg:hidden sticky top-14 sm:top-16 z-30 -mx-3 sm:-mx-4 px-3 sm:px-4 py-2 mb-4 bg-white/95 backdrop-blur-md border-y border-gray-100 shadow-sm"
                >
                    <div className="flex gap-2">
                        <a
                            href="#food-listings-heading"
                            className="flex-1 inline-flex items-center justify-center gap-1.5 min-h-[44px] rounded-full bg-cyan-50 text-cyan-800 text-sm font-semibold border border-cyan-100 touch-manipulation"
                        >
                            <i className="fas fa-list text-xs" aria-hidden="true" />
                            Listings
                            {filteredFoods.length > 0 && (
                                <span className="ml-0.5 inline-flex min-w-[1.25rem] justify-center rounded-full bg-white px-1.5 py-0.5 text-[10px] font-bold text-cyan-700">
                                    {filteredFoods.length}
                                </span>
                            )}
                        </a>
                        <a
                            href="#food-map-heading"
                            className="flex-1 inline-flex items-center justify-center gap-1.5 min-h-[44px] rounded-full bg-white text-gray-700 text-sm font-semibold border border-gray-200 touch-manipulation"
                        >
                            <i className="fas fa-map-marked-alt text-xs" aria-hidden="true" />
                            Map
                        </a>
                    </div>
                </nav>

                <div className="mb-6 sm:mb-8 flex flex-col gap-3">
                    <div className="flex flex-col sm:flex-row gap-2 w-full sm:max-w-xl">
                        <div className="relative flex-1">
                            <i className="fas fa-search absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm pointer-events-none" aria-hidden="true"></i>
                            <input
                                type="search"
                                name="search"
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                placeholder="Search food..."
                                aria-label="Search food listings"
                                className="w-full min-h-[44px] pl-10 pr-10 py-2.5 rounded-full bg-white border border-gray-200 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                            />
                            {searchTerm && (
                                <button
                                    type="button"
                                    onClick={() => setSearchTerm('')}
                                    aria-label="Clear search"
                                    title="Clear search"
                                    className="absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 inline-flex items-center justify-center rounded-full text-gray-400 hover:bg-gray-100"
                                >
                                    <i className="fas fa-times text-sm" aria-hidden="true" />
                                </button>
                            )}
                        </div>
                        <select
                            name="category"
                            value={filters.category}
                            onChange={handleFilterChange}
                            aria-label="Filter by category"
                            className="w-full sm:w-48 min-h-[44px] rounded-full bg-white border border-gray-200 px-4 py-2.5 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                        >
                            <option value="">All categories</option>
                            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                    </div>

                    {/* Sort + radius pill row — surfaces controls that were
                        previously locked into state with no UI. */}
                    <div className="flex flex-wrap items-center gap-2">
                        <label className="inline-flex items-center gap-1.5 text-xs text-gray-500 bg-white border border-gray-200 rounded-full pl-3 pr-1 py-1">
                            <i className="fas fa-sort-amount-down text-gray-400" aria-hidden="true" />
                            <span className="sr-only">Sort by</span>
                            <select
                                name="sortBy"
                                value={filters.sortBy}
                                onChange={handleFilterChange}
                                aria-label="Sort listings"
                                className="bg-transparent text-sm text-gray-700 focus:outline-none pr-1 py-1 cursor-pointer"
                            >
                                {SORT_OPTIONS.map(opt => (
                                    <option
                                        key={opt.value}
                                        value={opt.value}
                                        disabled={opt.requiresGps && locationSource !== 'gps'}
                                    >
                                        {opt.label}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className={`inline-flex items-center gap-1.5 text-xs text-gray-500 bg-white border border-gray-200 rounded-full pl-3 pr-1 py-1 ${locationSource !== 'gps' ? 'opacity-60' : ''}`}>
                            <i className="fas fa-location-crosshairs text-gray-400" aria-hidden="true" />
                            <span>Within</span>
                            <select
                                name="radius"
                                value={filters.radius}
                                onChange={handleFilterChange}
                                disabled={locationSource !== 'gps'}
                                aria-label="Distance radius"
                                className="bg-transparent text-sm text-gray-700 focus:outline-none pr-1 py-1 cursor-pointer disabled:cursor-not-allowed"
                            >
                                {RADIUS_OPTIONS.map(opt => (
                                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                            </select>
                        </label>
                        {locationSource === 'gps' && currentLocation && (
                            <span
                                className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-xs font-medium text-emerald-700"
                                title="Distance and 'Nearest' sort are using your current location"
                            >
                                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
                                Using your location
                            </span>
                        )}
                        {activeFilterCount > 0 && (
                            <button
                                type="button"
                                onClick={resetAllFilters}
                                className="text-xs text-gray-500 hover:text-gray-700 underline ml-auto"
                            >
                                Reset all
                            </button>
                        )}
                    </div>

                    {/* Active filter chips so the user can see and one-tap-
                        clear each filter individually. */}
                    {activeFilterCount > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5" aria-label="Active filters">
                            {debouncedSearch.trim() && (
                                <FilterChip
                                    onRemove={() => clearFilter('search')}
                                    ariaLabel={`Remove search filter "${debouncedSearch.trim()}"`}
                                >
                                    <i className="fas fa-search text-[10px] opacity-70" aria-hidden="true" />
                                    &ldquo;{debouncedSearch.trim()}&rdquo;
                                </FilterChip>
                            )}
                            {filters.category && (
                                <FilterChip
                                    onRemove={() => clearFilter('category')}
                                    ariaLabel={`Remove ${CATEGORY_LABELS[filters.category] || filters.category} filter`}
                                >
                                    {CATEGORY_LABELS[filters.category] || filters.category}
                                </FilterChip>
                            )}
                            {filters.community && (
                                <FilterChip
                                    onRemove={() => clearFilter('community')}
                                    ariaLabel="Remove community filter"
                                >
                                    {communityNames[String(filters.community)] || 'Community'}
                                </FilterChip>
                            )}
                        </div>
                    )}

                    {/* Soft prompt to enable GPS — only shown when the user
                        is not already on GPS. Keeps distance/radius controls
                        meaningful without nagging granted users. */}
                    {locationSource !== 'gps' && (
                        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs sm:text-sm text-amber-900 flex items-center gap-3">
                            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-600" aria-hidden="true">
                                <i className="fas fa-location-arrow" />
                            </span>
                            <div className="flex-1 leading-snug">
                                <span className="font-semibold">See food near you.</span>
                                <span className="ml-1 text-amber-800">
                                    {geoError
                                        ? 'Location access is blocked — re-enable it in your browser.'
                                        : 'Share your location to sort by nearest and filter by distance.'}
                                </span>
                            </div>
                            <button
                                type="button"
                                onClick={enableGeolocation}
                                disabled={geoLoading}
                                className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <i className="fas fa-location-crosshairs text-[10px]" aria-hidden="true" />
                                {geoLoading ? 'Locating…' : 'Use my location'}
                            </button>
                        </div>
                    )}
                </div>
                <div className="mt-4 sm:mt-12">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                        {/* Listings first on mobile so available food is the
                            primary above-the-fold content; map sits to the
                            right on desktop and just below on phones. */}
                        <aside aria-labelledby="food-map-heading" className="order-2">
                            <div className="lg:sticky lg:top-24 overflow-visible">
                                <h2
                                    id="food-map-heading"
                                    className="scroll-mt-28 text-lg sm:text-2xl font-bold text-gray-800 mb-3 sm:mb-4 flex items-center"
                                >
                                    <i className="fas fa-map-marked-alt text-cyan-600 mr-2" aria-hidden="true"></i>
                                    Food Locations Map
                                </h2>
                                <div className="relative isolate overflow-visible rounded-xl sm:rounded-2xl shadow-lg border border-gray-100 h-[min(52vh,420px)] sm:h-[480px] lg:h-[600px]">
                                    <FoodMap
                                        showSignupPrompt={!isAuthenticated}
                                        highlightedFoodId={hoveredFoodId}
                                        listings={filteredFoods}
                                    />
                                </div>
                            </div>
                        </aside>

                        <div className="order-1">
                            <h2
                                id="food-listings-heading"
                                className="scroll-mt-28 text-lg sm:text-2xl font-bold text-gray-800 mb-3 sm:mb-4"
                            >
                                Available Food Listings
                                {filteredFoods.length > 0 && (
                                    <span className="ml-2 text-sm font-normal text-gray-500">
                                        · {filteredFoods.length}
                                        {urgencyCount > 0 && (
                                            <span className="ml-1.5 text-rose-600 font-semibold">
                                                · {urgencyCount} expiring soon
                                            </span>
                                        )}
                                    </span>
                                )}
                            </h2>
                            <div className="grid grid-cols-2 gap-2 sm:gap-4 text-xs sm:text-sm [&_.h-48]:h-28 sm:[&_.h-48]:h-32 [&_#card-title]:text-sm [&_#card-title]:leading-snug [&_#card-title]:line-clamp-2 sm:[&_#card-title]:text-lg sm:[&_#card-title]:line-clamp-none [&_.p-4]:p-2.5 sm:[&_.p-4]:p-4">
                                {foodsLoading && foods.length === 0 ? (
                                    skeletonGrid
                                ) : foodsError ? (
                                    <div className="col-span-2"><ErrorDisplay /></div>
                                ) : filteredFoods.length === 0 ? (
                                    <div className="col-span-2 text-center py-12" role="status">
                                        <i className="fas fa-utensils text-gray-300 text-4xl mb-3" aria-hidden="true"></i>
                                        <p className="text-gray-700 font-medium">
                                            No food listings{emptyReason ? <span className="text-gray-500 font-normal"> ({emptyReason})</span> : null}
                                        </p>
                                        <p className="text-sm text-gray-500 mt-1">
                                            {activeFilterCount > 0 ? 'Try widening your filters.' : 'Check back soon — new listings appear every minute.'}
                                        </p>
                                        <div className="flex flex-wrap justify-center gap-2 mt-4">
                                            {filters.category && (
                                                <button
                                                    type="button"
                                                    onClick={() => clearFilter('category')}
                                                    className="inline-flex items-center gap-1.5 rounded-full bg-white border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                                                >
                                                    Show all categories
                                                </button>
                                            )}
                                            {locationSource === 'gps' && Number(filters.radius) < 100 && (
                                                <button
                                                    type="button"
                                                    onClick={() => setFilters(prev => ({ ...prev, radius: '100' }))}
                                                    className="inline-flex items-center gap-1.5 rounded-full bg-white border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                                                >
                                                    Widen to 100 km
                                                </button>
                                            )}
                                            {debouncedSearch.trim() && (
                                                <button
                                                    type="button"
                                                    onClick={() => clearFilter('search')}
                                                    className="inline-flex items-center gap-1.5 rounded-full bg-white border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                                                >
                                                    Clear search
                                                </button>
                                            )}
                                            {activeFilterCount === 0 && (
                                                <Link
                                                    to="/share"
                                                    className="inline-flex items-center gap-1.5 rounded-full bg-cyan-600 text-white px-3 py-1.5 text-xs font-semibold hover:bg-cyan-700"
                                                >
                                                    <i className="fas fa-heart text-[10px]" aria-hidden="true" />
                                                    Share food yourself
                                                </Link>
                                            )}
                                            {activeFilterCount > 1 && (
                                                <button
                                                    type="button"
                                                    onClick={resetAllFilters}
                                                    className="inline-flex items-center gap-1.5 rounded-full bg-gray-900 text-white px-3 py-1.5 text-xs font-semibold hover:bg-gray-800"
                                                >
                                                    Reset all filters
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                ) : (
                                    filteredFoods.slice(0, visibleCount).map((food) => (
                                        <div
                                            key={food.id || food.objectId}
                                            role="listitem"
                                            onMouseEnter={() => setHoveredFoodId(food.id)}
                                            onMouseLeave={() => setHoveredFoodId(null)}
                                            onFocus={() => setHoveredFoodId(food.id)}
                                            onBlur={() => setHoveredFoodId(null)}
                                        >
                                            <FoodCard
                                                food={food}
                                                onClaim={handleClaim}
                                                communityName={
                                                    food.community_name
                                                    || (food.community_id ? communityNames[String(food.community_id)] : null)
                                                }
                                            />
                                        </div>
                                    ))
                                )}
                            </div>
                            {filteredFoods.length > visibleCount && (() => {
                                const remaining = filteredFoods.length - visibleCount;
                                const showAll = remaining <= 12;
                                const increment = showAll ? remaining : 12;
                                return (
                                    <div className="flex justify-center mt-6">
                                        <button
                                            type="button"
                                            onClick={() => setVisibleCount(c => c + increment)}
                                            className="inline-flex items-center justify-center gap-2 min-h-[44px] w-full sm:w-auto px-5 py-2.5 rounded-full bg-white border border-gray-200 shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition touch-manipulation"
                                        >
                                            <i className="fas fa-plus text-gray-400 text-xs" aria-hidden="true"></i>
                                            {showAll
                                                ? `Show all ${remaining} more`
                                                : `Show 12 more · ${remaining} left`}
                                        </button>
                                    </div>
                                );
                            })()}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default FindFoodPage;
