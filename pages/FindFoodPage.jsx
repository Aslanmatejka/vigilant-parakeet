import { useState, useEffect, useMemo } from "react";
import useFormVoiceGuide from "../hooks/useFormVoiceGuide";
import { FIND_FOOD_WELCOME, FIND_FOOD_HINTS } from "../hooks/formGuideHints";
import { useNouriGuide } from "../utils/NouriGuideContext";
import { useNavigate, useLocation as useRouterLocation, Link } from 'react-router-dom';
import Button from "../components/common/Button";
import Input from "../components/common/Input";
import FoodCard from "../components/food/FoodCard";
import FoodMap from "../components/common/FoodMap";
import { useFoodListings } from "../utils/hooks/useSupabase";
import { useAuthContext } from "../utils/AuthContext";
import UrgencyService from "../utils/urgencyService";
import supabase from "../utils/supabaseClient";
import {
    browseCommunityIdsForUser,
    listingVisibleToCommunityScope,
} from "../utils/communityScope";

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

const SORT_OPTIONS = [
    { value: 'urgency', label: 'Expiring soon' },
    { value: 'distance', label: 'Nearest' },
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
    const { isAuthenticated, user, isAdmin } = useAuthContext();

    const { settings } = useNouriGuide();
    const { speakField } = useFormVoiceGuide({
        formId: 'find-food',
        welcomeMessage: FIND_FOOD_WELCOME,
        hints: FIND_FOOD_HINTS,
    });
    const [mapOpen, setMapOpen] = useState(false);

    useEffect(() => {
        if (!settings.listFirstFind) setMapOpen(true);
    }, [settings.listFirstFind]);

    const allowedCommunityIds = useMemo(
        () => browseCommunityIdsForUser(user, { isAdmin }),
        [user?.community_id, isAdmin]
    );

    const foodListFilters = useMemo(() => ({
        status: ['approved', 'active'],
        listing_type: 'donation',
        ...(user?.id ? { exclude_user_id: user.id } : {}),
        // Recipients only fetch their own community. Admins are unrestricted.
        ...(allowedCommunityIds != null ? { community_ids: allowedCommunityIds } : {}),
    }), [user?.id, allowedCommunityIds]);

    const { listings: foods, loading: foodsLoading, error: foodsError, fetchListings } = useFoodListings(foodListFilters);

    const profileLocation = useMemo(() => {
        const lat = user?.latitude;
        const lng = user?.longitude;
        if (lat == null || lng == null) return null;
        const nLat = Number(lat);
        const nLng = Number(lng);
        if (!Number.isFinite(nLat) || !Number.isFinite(nLng)) return null;
        return { latitude: nLat, longitude: nLng };
    }, [user?.latitude, user?.longitude]);
    
    const [searchTerm, setSearchTerm] = useState('');
    const debouncedSearch = useDebouncedValue(searchTerm, 250);
    const [visibleCount, setVisibleCount] = useState(12);
    const [hoveredFoodId, setHoveredFoodId] = useState(null);
    const [communityNames, setCommunityNames] = useState({});
    const [filters, setFilters] = useState({
        category: initialCategory || '',
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
            // Non-admins may only filter within their own community.
            const allowed = browseCommunityIdsForUser(user, { isAdmin });
            if (
                allowed == null ||
                allowed.map(String).includes(String(communityParam))
            ) {
                setFilters(prev => ({ ...prev, community: communityParam }));
            }
        }
    }, [routerLocation.search, user?.community_id, isAdmin]);

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

        // Hard scope: never show another school's food to a code-scoped user.
        result = result.filter(food =>
            listingVisibleToCommunityScope(food, allowedCommunityIds)
        );

        if (filters.community) {
            result = result.filter(food =>
                String(food.community_id) === String(filters.community) ||
                food.community === filters.community
            );
        }

        // Only show donations (food offers users can claim).
        // Requests have been removed from the platform.
        result = result.filter(food => food.listing_type === 'donation');

        // Apply sorting based on selected option
        if (filters.sortBy === 'urgency') {
            result = UrgencyService.sortByUrgency(result);
        } else if (filters.sortBy === 'distance' && profileLocation) {
            result = result.map(food => {
                const lat = food.latitude ?? food.location?.latitude;
                const lng = food.longitude ?? food.location?.longitude;
                if (lat == null || lng == null) return { ...food, distance: Infinity };
                const distance = calculateDistance(
                    profileLocation.latitude,
                    profileLocation.longitude,
                    Number(lat),
                    Number(lng)
                );
                return { ...food, distance };
            }).sort((a, b) => (a.distance || Infinity) - (b.distance || Infinity));
        } else if (filters.sortBy === 'newest') {
            result.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        }

        return result;
    }, [foods, debouncedSearch, filters, profileLocation, allowedCommunityIds]);

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
            className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40"
            role="main"
        >
            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-location-dot mr-2" aria-hidden="true"></i>
                            Food Near You
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Find Food{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                Assistance
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Browse nearby food listings and claim what you need. All requests are confidential.
                        </p>
                        <p className="mt-4">
                            <Link
                                to="/request"
                                className="inline-flex items-center gap-2 text-sm font-semibold text-amber-800 hover:text-amber-950 underline-offset-4 hover:underline"
                            >
                                <i className="fas fa-hand-holding-heart text-amber-600" aria-hidden="true" />
                                Can&apos;t find what you need? Request food
                            </Link>
                        </p>
                    </div>
                </div>
            </header>

            <div className="container mx-auto px-3 sm:px-4 pt-0 pb-6 sm:pb-10">

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
                                onFocus={() => speakField('search')}
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
                            onFocus={() => speakField('category')}
                            aria-label="Filter by category"
                            className="w-full sm:w-48 min-h-[44px] rounded-full bg-white border border-gray-200 px-4 py-2.5 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                        >
                            <option value="">All categories</option>
                            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                    </div>

                    {/* Sort pill row */}
                    <div className="flex flex-wrap items-center gap-2">
                        <label className="inline-flex items-center gap-1.5 text-xs text-gray-500 bg-white border border-gray-200 rounded-full pl-3 pr-1 py-1">
                            <i className="fas fa-sort-amount-down text-gray-400" aria-hidden="true" />
                            <span className="sr-only">Sort by</span>
                            <select
                                name="sortBy"
                                value={filters.sortBy}
                                onChange={handleFilterChange}
                                onFocus={() => speakField('sortBy')}
                                aria-label="Sort listings"
                                className="bg-transparent text-sm text-gray-700 focus:outline-none pr-1 py-1 cursor-pointer"
                            >
                                {SORT_OPTIONS.map(opt => (
                                    <option key={opt.value} value={opt.value}>
                                        {opt.label}
                                    </option>
                                ))}
                            </select>
                        </label>
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

                </div>
                <div className="mt-4 sm:mt-12">
                    {settings.listFirstFind && (
                        <div className="mb-4">
                            <button
                                type="button"
                                onClick={() => setMapOpen((o) => !o)}
                                className="inline-flex items-center gap-2 min-h-[44px] px-4 rounded-full border border-gray-200 bg-white text-sm font-medium text-gray-800 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2CABE3]"
                                aria-expanded={mapOpen}
                                aria-controls="find-food-map-panel"
                            >
                                <i className={`fas ${mapOpen ? 'fa-map-marked-alt' : 'fa-map'}`} aria-hidden="true" />
                                {mapOpen ? 'Hide map' : 'Show map (optional)'}
                            </button>
                        </div>
                    )}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                        <aside
                            id="find-food-map-panel"
                            aria-labelledby="food-map-heading"
                            className={`find-food-map-panel order-2 ${settings.listFirstFind && !mapOpen ? 'hidden' : ''}`}
                            data-collapsed={settings.listFirstFind && !mapOpen ? 'true' : 'false'}
                        >
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

                        <div className="order-1 find-food-list-panel">
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
                                            {debouncedSearch.trim() && (
                                                <button
                                                    type="button"
                                                    onClick={() => clearFilter('search')}
                                                    className="inline-flex items-center gap-1.5 rounded-full bg-white border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                                                >
                                                    Clear search
                                                </button>
                                            )}
                                            <Link
                                                to="/request"
                                                className="inline-flex items-center gap-1.5 rounded-full bg-amber-600 text-white px-3 py-1.5 text-xs font-semibold hover:bg-amber-700"
                                            >
                                                <i className="fas fa-hand-holding-heart text-[10px]" aria-hidden="true" />
                                                Request this food
                                            </Link>
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
