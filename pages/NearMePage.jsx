import React, { useState, useEffect } from 'react';
import FoodList from '../components/food/FoodList';
import { FilterPanel } from '../components/food/FilterPanel';
import { useGeoLocation } from '../utils/hooks/useLocation';
import MainLayout from '../components/layout/MainLayout';
import Button from '../components/common/Button';

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
    } = useGeoLocation();

    const [nearbyListings, setNearbyListings] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (location) {
            fetchNearbyListings();
        }
    }, [location, filters]);

    const fetchNearbyListings = async () => {
        setLoading(true);
        try {
            // TODO: Replace with actual API call
            const listings = await fetch('/api/listings/nearby', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    latitude: location.latitude,
                    longitude: location.longitude,
                    radius: filters.radius,
                    foodType: filters.foodType,
                    dietaryPreferences: filters.dietaryPreferences,
                    pickupTime: filters.pickupTime
                })
            }).then(res => res.json());
            
            setNearbyListings(listings);
        } catch (error) {
            console.error('Error fetching nearby listings:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleFilterChange = (newFilters) => {
        setFilters(newFilters);
    };

    return (
        <MainLayout>
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
                                className="bg-green-500 hover:bg-green-600 text-white"
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

                {location && (
                    <>
                        <FilterPanel
                            onFilterChange={handleFilterChange}
                            initialRadius={filters.radius}
                        />
                        <div className="mt-6">
                            <FoodList
                                foods={nearbyListings}
                                loading={loading}
                                showDistance={true}
                            />
                        </div>
                    </>
                )}
            </div>
        </MainLayout>
    );
}

export default NearMePage;
