import React, { useState, useEffect, useMemo } from 'react';
import FoodList from '../components/food/FoodList';
import { FilterPanel } from '../components/food/FilterPanel';
import { useEffectiveLocation } from '../utils/hooks/useLocation';
import Button from '../components/common/Button';
import dataService from '../utils/dataService';
import { useAuthContext } from '../utils/AuthContext';
import { browseCommunityIdsForUser, listingVisibleToCommunityScope } from '../utils/communityScope';

function distanceKm(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lng2 - lng1) * Math.PI / 180;
    const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) *
        Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

function NearMePage() {
    const { user, isAdmin } = useAuthContext();
    const allowedCommunityIds = useMemo(
        () => browseCommunityIdsForUser(user, { isAdmin }),
        [user?.community_id, isAdmin]
    );

    const [filters, setFilters] = useState({
        foodType: '',
        dietaryPreferences: [],
        pickupTime: ''
    });

    const {
        location,
        loading: locationLoading,
        error: locationError,
        enableLocation
    } = useEffectiveLocation();

    const [nearbyListings, setNearbyListings] = useState([]);
    const [loading, setLoading] = useState(true);

    // Fetch listings on mount AND when location/filters change.
    // Depend on primitive values to avoid an infinite loop — `location` and
    // `filters` get new object references on every render even when the
    // underlying coordinates/values are unchanged.
    const lat = location?.latitude;
    const lng = location?.longitude;
    const dietaryKey = (filters.dietaryPreferences || []).join(',');
    const communityKey = allowedCommunityIds == null ? 'all' : allowedCommunityIds.join(',');
    useEffect(() => {
        fetchNearbyListings();
    }, [lat, lng, filters.foodType, dietaryKey, filters.pickupTime, communityKey, user?.id]);

    const fetchNearbyListings = async () => {
        setLoading(true);
        try {
            const rawListings = await dataService.getFoodListings({
                status: ['approved', 'active'],
                listing_type: 'donation',
                ...(user?.id ? { exclude_user_id: user.id } : {}),
                ...(allowedCommunityIds != null ? { community_ids: allowedCommunityIds } : {}),
            });
            // Defensive dedupe by id in case the query returns duplicates
            // (e.g. via joins or realtime echo).
            const seen = new Set();
            const allListings = [];
            for (const l of rawListings || []) {
                if (!l?.id || seen.has(l.id)) continue;
                seen.add(l.id);
                allListings.push(l);
            }

            let result = allListings.filter(listing =>
                listingVisibleToCommunityScope(listing, allowedCommunityIds)
            );

            // Sort by distance when location is available — no radius cutoff.
            if (location && location.latitude && location.longitude) {
                const withCoords = [];
                const withoutCoords = [];
                result.forEach(listing => {
                    if (listing.latitude != null && listing.longitude != null) {
                        listing._distance = distanceKm(
                            location.latitude,
                            location.longitude,
                            listing.latitude,
                            listing.longitude
                        );
                        withCoords.push(listing);
                    } else {
                        withoutCoords.push(listing);
                    }
                });
                result = [
                    ...withCoords.sort((a, b) => (a._distance || 0) - (b._distance || 0)),
                    ...withoutCoords,
                ];
            }

            if (filters.foodType) {
                result = result.filter(listing => listing.category === filters.foodType);
            }

            if (filters.dietaryPreferences && filters.dietaryPreferences.length > 0) {
                result = result.filter(listing => {
                    if (!listing.dietary_tags) return false;
                    return filters.dietaryPreferences.some(pref =>
                        listing.dietary_tags.includes(pref.toLowerCase())
                    );
                });
            }

            setNearbyListings(result);
        } catch (error) {
            const msg = error?.message || '';
            if (error?.name === 'AbortError' || error?.code === '20' || msg.includes('aborted')) {
                // Request was superseded or timed out — ignore silently.
                return;
            }
            console.error('Error fetching nearby listings:', error);
            setNearbyListings([]);
        } finally {
            setLoading(false);
        }
    };

    const handleFilterChange = (newFilters) => {
        setFilters(newFilters);
    };

    return (
        <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
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
                            Local Food Map
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            Food{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                Near Me
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Find free food shared by neighbors and local organizations in your community.
                        </p>
                    </div>
                </div>
            </header>

            <div className="container mx-auto px-4 pb-8">
                <div className="mb-8">

                    {/* Step-by-step guide */}
                    <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                        <h2 className="text-lg font-semibold text-green-800 mb-3 flex items-center">
                            <span className="mr-2">ℹ️</span> How it works — 3 quick steps
                        </h2>
                        <ol className="space-y-2 text-sm text-gray-700">
                            <li>
                                <span className="font-semibold text-green-700">1. Enable location</span> —
                                click <em>Enable Location</em> below so we can sort food by distance. We never store your exact location.
                            </li>
                            <li>
                                <span className="font-semibold text-green-700">2. Filter (optional)</span> —
                                narrow results by food type, dietary needs, or pickup time.
                            </li>
                            <li>
                                <span className="font-semibold text-green-700">3. Claim & pick up</span> —
                                tap a listing to see details, then claim it and coordinate pickup with the donor.
                            </li>
                        </ol>
                    </div>

                    {!location && !locationLoading && (
                        <div className="flex flex-col sm:flex-row sm:items-center gap-3 bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                            <p className="text-sm text-gray-700 flex-1">
                                Ready to start? Share your location and we'll sort food by distance.
                                Your coordinates stay on your device.
                            </p>
                            <Button
                                onClick={enableLocation}
                                className="bg-primary-500 hover:bg-primary-600 text-white"
                                title="Click to share your current location with this page only"
                            >
                                Enable Location
                            </Button>
                        </div>
                    )}

                    {locationError && (
                        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                            <p className="text-red-600">
                                {locationError}. Please enable location services in your browser settings.
                            </p>
                        </div>
                    )}
                </div>

                {/* Always show listings — with filters when location available, all listings otherwise */}
                {location && (
                    <FilterPanel onFilterChange={handleFilterChange} />
                )}
                <div className={location ? "mt-6" : ""}>
                    {location && !loading && nearbyListings.length > 0 && (
                        <p
                            className="text-sm text-gray-600 mb-3"
                            title="Listings are sorted by distance from you. Tap any listing to view details and claim it."
                        >
                            Showing <span className="font-semibold">{nearbyListings.length}</span> listing{nearbyListings.length === 1 ? '' : 's'}
                            {location ? ', nearest first' : ''}.
                            Tap a listing to view details and claim it.
                        </p>
                    )}
                    {location && !loading && nearbyListings.length === 0 && (
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 text-sm text-gray-700">
                            No listings found right now. Try clearing filters or check back later.
                        </div>
                    )}
                    <FoodList
                        foods={nearbyListings}
                        loading={loading}
                        showDistance={!!location}
                        showFilters={false}
                    />
                </div>
            </div>
        </div>
    );
}

export default NearMePage;
