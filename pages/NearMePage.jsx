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
            const allListings = await dataService.getFoodListings({ status: ['approved', 'active'] });
            
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
                    <h1 className="text-3xl font-bold mb-4">Food Near Me</h1>
                    {!location && !locationLoading && (
                        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                            <h2 className="text-lg font-semibold mb-2">Enable Location Services</h2>
                            <p className="text-gray-600 mb-4">
                                Allow ShareFoods to access your location to see available food listings near you.
                            </p>
                            <Button
                                onClick={enableLocation}
                                className="bg-primary-500 hover:bg-primary-600 text-white"
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
