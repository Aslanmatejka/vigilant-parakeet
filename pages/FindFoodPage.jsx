import { useState, useEffect, useMemo } from "react";
import { useNavigate, useLocation as useRouterLocation, Link } from 'react-router-dom';
import Button from "../components/common/Button";
import Input from "../components/common/Input";
import FoodCard from "../components/food/FoodCard";
import FoodMap from "../components/common/FoodMap";
import VoiceLocationSearch from "../components/food/VoiceLocationSearch";
import { toast } from "react-toastify";
import { useFoodListings, useSearch } from "../utils/hooks/useSupabase";
import { useEffectiveLocation } from "../utils/hooks/useLocation";
import { useAuthContext } from "../utils/AuthContext";
import UrgencyService from "../utils/urgencyService";
import { useMapContext } from "../utils/MapContext.jsx";
import aiChatService from "../utils/services/aiChatService";
import { isBayAreaCoord } from "../utils/mapBounds";
import supabase from "../utils/supabaseClient";

// Category mapping for URL parameters
const CATEGORY_MAPPING = {
    fruits: 'produce',
    vegetables: 'produce'
};

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
    const { search, results: searchResults, loading: searchLoading } = useSearch();
    const { 
        location: currentLocation, 
        loading: geoLoading, 
        error: geoError, 
        enableLocation: enableGeolocation,
        source: locationSource,
    } = useEffectiveLocation();
    const { setAIRoute, clearAIOverlays, centerOn } = useMapContext();
    
    const [searchTerm, setSearchTerm] = useState('');
    const [isSearchActive, setIsSearchActive] = useState(false);
    const [visibleCount, setVisibleCount] = useState(12);
    const [hoveredFoodId, setHoveredFoodId] = useState(null);
    const [voiceModalOpen, setVoiceModalOpen] = useState(false);
    const [communityNames, setCommunityNames] = useState({});
    const [filters, setFilters] = useState({
        category: initialCategory || '',
        radius: '100',
        sortBy: 'newest',
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
    const handleSearch = async () => {
        if (!searchTerm.trim()) {
            setIsSearchActive(false);
            return;
        }
        
        setIsSearchActive(true);
        try {
            await search(searchTerm, filters);
        } catch (error) {
            toast.error('Search failed. Please try again.');
            setIsSearchActive(false);
        }
    };

    const handleClearSearch = () => {
        setSearchTerm('');
        setIsSearchActive(false);
    };

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

    const filteredFoods = useMemo(() => {
        // Use search results if search is active, otherwise use all foods
        let result = isSearchActive ? [...searchResults] : [...foods];

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

        if (!isSearchActive && searchTerm) {
            const searchTermLower = searchTerm.toLowerCase();
            result = result.filter(food => 
                (food.title || '').toLowerCase().includes(searchTermLower) ||
                (food.description || '').toLowerCase().includes(searchTermLower) ||
                (typeof food.location === 'string' ? food.location : (food.location?.address || food.full_address || '')).toLowerCase().includes(searchTermLower)
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

        // If we have search results with scores, sort by them
        if (isSearchActive && searchResults.length > 0) {
            // Check if search results have scores
            const hasScores = searchResults.some(r => r.matchScore !== undefined);
            if (hasScores) {
                result.sort((a, b) => {
                    const resultA = searchResults.find(r => r.id === a.id);
                    const resultB = searchResults.find(r => r.id === b.id);
                    return (resultB?.matchScore || 0) - (resultA?.matchScore || 0);
                });
            }
        }

        return result;
    }, [foods, searchResults, isSearchActive, searchTerm, filters, currentLocation]);

    const LoadingSpinner = () => (
        <div className="text-center py-12" role="status">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#2CABE3] mx-auto" aria-hidden="true"></div>
            <p className="mt-4 text-gray-600">Loading food listings...</p>
            <span className="sr-only">Loading food listings</span>
        </div>
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
                    className="lg:hidden sticky top-[4.25rem] z-30 -mx-3 sm:-mx-4 px-3 sm:px-4 py-2 mb-4 bg-white/95 backdrop-blur-md border-y border-gray-100 shadow-sm"
                >
                    <div className="flex gap-2">
                        <a
                            href="#food-map-heading"
                            className="flex-1 inline-flex items-center justify-center gap-1.5 min-h-[44px] rounded-full bg-cyan-50 text-cyan-800 text-sm font-semibold border border-cyan-100 touch-manipulation"
                        >
                            <i className="fas fa-map-marked-alt text-xs" aria-hidden="true" />
                            Map
                        </a>
                        <a
                            href="#food-listings-heading"
                            className="flex-1 inline-flex items-center justify-center gap-1.5 min-h-[44px] rounded-full bg-white text-gray-700 text-sm font-semibold border border-gray-200 touch-manipulation"
                        >
                            <i className="fas fa-list text-xs" aria-hidden="true" />
                            Listings
                            {filteredFoods.length > 0 && (
                                <span className="ml-0.5 inline-flex min-w-[1.25rem] justify-center rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-bold text-gray-600">
                                    {filteredFoods.length}
                                </span>
                            )}
                        </a>
                    </div>
                </nav>

                <div className="mb-6 sm:mb-8 flex flex-col gap-3">
                    <div className="flex flex-col sm:flex-row gap-2 w-full sm:max-w-xl">
                        <div className="relative flex-1">
                            <i className="fas fa-search absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm pointer-events-none" aria-hidden="true"></i>
                            <input
                                type="text"
                                name="search"
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                onKeyDown={e => { if (e.key === 'Enter') handleSearch(); }}
                                placeholder="Search food..."
                                className="w-full min-h-[44px] pl-10 pr-3 py-2.5 rounded-full bg-white border border-gray-200 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                            />
                        </div>
                        <select
                            name="category"
                            value={filters.category}
                            onChange={handleFilterChange}
                            className="w-full sm:w-48 min-h-[44px] rounded-full bg-white border border-gray-200 px-4 py-2.5 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-[#2CABE3]"
                        >
                            <option value="">All categories</option>
                            <option value="produce">Produce</option>
                            <option value="dairy">Dairy</option>
                            <option value="bakery">Bakery</option>
                            <option value="pantry">Pantry</option>
                            <option value="meat">Meat</option>
                            <option value="seafood">Seafood</option>
                            <option value="frozen">Frozen</option>
                            <option value="snacks">Snacks</option>
                            <option value="beverages">Beverages</option>
                            <option value="prepared">Prepared</option>
                            <option value="other">Other</option>
                        </select>
                        {isSearchActive && (
                            <Button variant="secondary" className="min-h-[44px] w-full sm:w-auto" onClick={handleClearSearch}>Clear</Button>
                        )}
                    </div>

                    <button
                        type="button"
                        onClick={() => setVoiceModalOpen(true)}
                        className="w-full sm:w-auto sm:self-end inline-flex items-center justify-center gap-2 min-h-[44px] rounded-full bg-gradient-to-r from-[#2CABE3] to-[#1d8fbf] px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-[#2CABE3]/25 hover:shadow-lg hover:shadow-[#2CABE3]/30 transition touch-manipulation"
                    >
                        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-white/20">
                            <i className="fas fa-microphone text-xs" aria-hidden="true" />
                        </span>
                        Voice + GPS finder
                    </button>
                </div>
                <div className="mt-4 sm:mt-12">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                        {/* Map first on mobile for location-first discovery */}
                        <aside aria-labelledby="food-map-heading" className="order-1 lg:order-2">
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

                        <div className="order-2 lg:order-1">
                            <h2
                                id="food-listings-heading"
                                className="scroll-mt-28 text-lg sm:text-2xl font-bold text-gray-800 mb-3 sm:mb-4"
                            >
                                Available Food Listings
                                {filteredFoods.length > 0 && (
                                    <span className="ml-2 text-sm font-normal text-gray-500">({filteredFoods.length})</span>
                                )}
                            </h2>
                            <div className="grid grid-cols-2 gap-2 sm:gap-4 text-xs sm:text-sm [&_.h-48]:h-28 sm:[&_.h-48]:h-32 [&_#card-title]:text-sm [&_#card-title]:leading-snug [&_#card-title]:line-clamp-2 sm:[&_#card-title]:text-lg sm:[&_#card-title]:line-clamp-none [&_.p-4]:p-2.5 sm:[&_.p-4]:p-4">
                                {foodsLoading && foods.length === 0 ? (
                                    <div className="col-span-2"><LoadingSpinner /></div>
                                ) : foodsError ? (
                                    <div className="col-span-2"><ErrorDisplay /></div>
                                ) : filteredFoods.length === 0 ? (
                                    <div className="col-span-2 text-center py-12" role="status">
                                        <i className="fas fa-search text-gray-400 text-4xl mb-4" aria-hidden="true"></i>
                                        <p className="text-gray-600 mb-4">No food listings found</p>
                                        <Button
                                            variant="secondary"
                                            onClick={() => {
                                                setSearchTerm('');
                                                // Also exit search mode so the full
                                                // listings replace the search results.
                                                setIsSearchActive(false);
                                                setFilters({
                                                    category: '',
                                                    radius: '100',
                                                    sortBy: 'newest',
                                                    community: ''
                                                });
                                            }}
                                        >
                                            Clear Filters
                                        </Button>
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
                            {filteredFoods.length > visibleCount && (
                                <div className="flex justify-center mt-6">
                                    <button
                                        type="button"
                                        onClick={() => setVisibleCount(c => c + 4)}
                                        className="inline-flex items-center justify-center gap-2 min-h-[44px] w-full sm:w-auto px-5 py-2.5 rounded-full bg-white border border-gray-200 shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition touch-manipulation"
                                    >
                                        <i className="fas fa-ellipsis-h text-gray-400" aria-hidden="true"></i>
                                        {filteredFoods.length - visibleCount} More
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {voiceModalOpen && (
                <div
                    className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-slate-900/45 backdrop-blur-sm px-0 sm:px-4 py-0 sm:py-8"
                    role="dialog"
                    aria-modal="true"
                    aria-label="Voice and GPS food finder"
                    onClick={() => setVoiceModalOpen(false)}
                >
                    <div
                        className="relative w-full sm:max-w-2xl max-h-[92vh] sm:max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-white shadow-2xl ring-1 ring-black/5"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <button
                            type="button"
                            onClick={() => setVoiceModalOpen(false)}
                            aria-label="Close voice search"
                            className="absolute top-3 right-3 z-20 inline-flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-gray-600 shadow-sm ring-1 ring-gray-200 hover:bg-gray-50"
                        >
                            <i className="fas fa-times" aria-hidden="true" />
                        </button>
                        <div className="p-4 sm:p-6">
                            <VoiceLocationSearch
                                embedded
                                onResultSelect={(id, result) => {
                                    setHoveredFoodId(id);
                                    setVoiceModalOpen(false);

                                    // Resolve destination coords from voice result or local foods list
                                    const fallback = Array.isArray(foods) ? foods.find(f => f.id === id) : null;
                                    const destLat = Number(result?.latitude ?? fallback?.latitude);
                                    const destLng = Number(result?.longitude ?? fallback?.longitude);
                                    const originLat = Number(currentLocation?.latitude);
                                    const originLng = Number(currentLocation?.longitude);
                                    const haveCoords =
                                        Number.isFinite(destLat) && Number.isFinite(destLng) &&
                                        Number.isFinite(originLat) && Number.isFinite(originLng) &&
                                        isBayAreaCoord(destLat, destLng) &&
                                        isBayAreaCoord(originLat, originLng);

                                    if (haveCoords) {
                                        clearAIOverlays();
                                        aiChatService
                                            .getRoute({ originLat, originLng, destLat, destLng, profile: 'driving' })
                                            .then((route) => {
                                                if (!route || !route.geometry) return;
                                                setAIRoute({
                                                    geometry: route.geometry,
                                                    origin: { lat: originLat, lng: originLng },
                                                    destination: { lat: destLat, lng: destLng },
                                                    distance_km: route.distance_km,
                                                    duration_text: route.duration_text,
                                                    profile: route.profile || 'driving',
                                                });
                                            })
                                            .catch((err) => {
                                                console.warn('Could not draw route on map:', err);
                                                // Still center on the destination so user sees the marker.
                                                centerOn({ lat: destLat, lng: destLng, zoom: 14 });
                                            });
                                    } else if (Number.isFinite(destLat) && Number.isFinite(destLng) && isBayAreaCoord(destLat, destLng)) {
                                        // No user location available — at least center on the listing.
                                        centerOn({ lat: destLat, lng: destLng, zoom: 14 });
                                    }

                                    if (typeof window !== 'undefined') {
                                        // Scroll to the map so the user sees the highlighted marker and route
                                        setTimeout(() => {
                                            const el = document.getElementById('food-map-heading');
                                            el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                        }, 50);
                                    }
                                }}
                            />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default FindFoodPage;
