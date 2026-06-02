import React, { useState, useEffect } from 'react';
import FoodList from '../components/food/FoodList';
import { FilterPanel } from '../components/food/FilterPanel';
import { useEffectiveLocation } from '../utils/hooks/useLocation';
import Button from '../components/common/Button';
import dataService from '../utils/dataService';

function NearMePage() {
    const [filters, setFilters] = useState({
        radius: 10,
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
    useEffect(() => {
        fetchNearbyListings();
    }, [lat, lng, filters.radius, filters.foodType, dietaryKey, filters.pickupTime]);

    const fetchNearbyListings = async () => {
        setLoading(true);
        try {
            // Fetch all approved and active listings
            const rawListings = await dataService.getFoodListings({ status: ['approved', 'active'] });
            // Defensive dedupe by id in case the query returns duplicates
            // (e.g. via joins or realtime echo).
            const seen = new Set();
            const allListings = [];
            for (const l of rawListings || []) {
                if (!l?.id || seen.has(l.id)) continue;
                seen.add(l.id);
                allListings.push(l);
            }
            
            // Filter by distance if location is available
            if (location && location.latitude && location.longitude) {
                // Separate listings with coordinates (can be distance-filtered) from those without
                const withCoords = [];
                const withoutCoords = [];
                allListings.forEach(listing => {
                    if (listing.latitude && listing.longitude) {
                        withCoords.push(listing);
                    } else {
                        withoutCoords.push(listing);
                    }
                });

                const filtered = withCoords.filter(listing => {
                    // Calculate distance using Haversine formula
                    const R = 6371; // Earth's radius in km
                    const dLat = (listing.latitude - location.latitude) * Math.PI / 180;
                    const dLon = (listing.longitude - location.longitude) * Math.PI / 180;
                    const a = 
                        Math.sin(dLat/2) * Math.sin(dLat/2) +
                        Math.cos(location.latitude * Math.PI / 180) * 
                        Math.cos(listing.latitude * Math.PI / 180) *
                        Math.sin(dLon/2) * Math.sin(dLon/2);
                    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                    const distance = R * c;
                    listing._distance = distance;
                    
                    // Convert radius from miles to km (1 mile = 1.60934 km)
                    const radiusKm = filters.radius * 1.60934;
                    return distance <= radiusKm;
                });
                
                // Combine: nearby items first (sorted by distance), then items without coords
                let result = [...filtered.sort((a, b) => (a._distance || 0) - (b._distance || 0)), ...withoutCoords];
                
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
            } else {
                setNearbyListings(allListings);
            }
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
        <>
            <div className="container mx-auto px-4 py-8">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold mb-2">Food Near Me</h1>
                    <p className="text-gray-600 mb-4">
                        Find free food shared by neighbors and local organizations within a distance you choose.
                    </p>

                    {/* Step-by-step guide */}
                    <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                        <h2 className="text-lg font-semibold text-green-800 mb-3 flex items-center">
                            <span className="mr-2">ℹ️</span> How it works — 4 quick steps
                        </h2>
                        <ol className="space-y-2 text-sm text-gray-700">
                            <li>
                                <span className="font-semibold text-green-700">1. Enable location</span> —
                                click <em>Enable Location</em> below so we can show food near you. We never store your exact location.
                            </li>
                            <li>
                                <span className="font-semibold text-green-700">2. Set your distance</span> —
                                use the radius (in miles) to control how far you’re willing to travel.
                            </li>
                            <li>
                                <span className="font-semibold text-green-700">3. Filter (optional)</span> —
                                narrow results by food type, dietary needs, or pickup time.
                            </li>
                            <li>
                                <span className="font-semibold text-green-700">4. Claim & pick up</span> —
                                tap a listing to see details, then claim it and coordinate pickup with the donor.
                            </li>
                        </ol>
                    </div>

                    {!location && !locationLoading && (
                        <div className="flex flex-col sm:flex-row sm:items-center gap-3 bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                            <p className="text-sm text-gray-700 flex-1">
                                Ready to start? Share your location and we'll show food nearby.
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
                    <FilterPanel
                        onFilterChange={handleFilterChange}
                        initialRadius={filters.radius}
                    />
                )}
                <div className={location ? "mt-6" : ""}>
                    {location && !loading && nearbyListings.length > 0 && (
                        <p
                            className="text-sm text-gray-600 mb-3"
                            title="Listings are sorted by distance from you. Tap any listing to view details and claim it."
                        >
                            Showing <span className="font-semibold">{nearbyListings.length}</span> listing{nearbyListings.length === 1 ? '' : 's'} within {filters.radius} mile{filters.radius === 1 ? '' : 's'}.
                            Tap a listing to view details and claim it.
                        </p>
                    )}
                    {location && !loading && nearbyListings.length === 0 && (
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 text-sm text-gray-700">
                            No listings found in this area. Try widening the radius or clearing filters.
                        </div>
                    )}
                    <FoodList
                        foods={nearbyListings}
                        loading={loading}
                        showDistance={!!location}
                    />
                </div>
            </div>
        </>
    );
}

export default NearMePage;
