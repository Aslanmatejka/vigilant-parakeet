import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import FoodCard from './FoodCard';
import Button from '../common/Button';
import { FilterPanel } from './FilterPanel';
import { locationService } from '../../utils/locationService';

function FoodList({
    foods = [],
    onClaim,
    loading = false,
    error = null
}) {
    const [filteredFoods, setFilteredFoods] = useState(foods);
    const [userLocation, setUserLocation] = useState(null);
    const [filters, setFilters] = useState({
        locationEnabled: false,
        radius: 10,
        foodType: '',
        dietaryPreferences: [],
        pickupTime: ''
    });

    useEffect(() => {
        if (filters.locationEnabled && userLocation) {
            updateFoodsWithDistance();
        }
    }, [userLocation, filters, foods]);

    const updateFoodsWithDistance = () => {
        const filtered = foods.filter(food => {
            let matchesFilters = true;

            // Location filter
            if (filters.locationEnabled && userLocation && food.location) {
                const isNearby = locationService.isWithinRadius(
                    userLocation,
                    food.location,
                    filters.radius
                );
                if (!isNearby) matchesFilters = false;
            }

            // Food type filter
            if (filters.foodType && food.type !== filters.foodType) {
                matchesFilters = false;
            }

            // Dietary preferences filter
            if (filters.dietaryPreferences.length > 0) {
                const hasMatchingPreference = filters.dietaryPreferences.every(pref =>
                    food.dietaryPreferences?.includes(pref)
                );
                if (!hasMatchingPreference) matchesFilters = false;
            }

            // Pickup time filter
            if (filters.pickupTime) {
                const pickupTime = new Date(filters.pickupTime);
                const foodTime = new Date(food.pickupTime);
                if (foodTime < pickupTime) matchesFilters = false;
            }

            return matchesFilters;
        });

        // Sort by distance if location is enabled
        if (filters.locationEnabled && userLocation) {
            filtered.sort((a, b) => {
                if (!a.location || !b.location) return 0;
                const distA = locationService.calculateDistance(
                    userLocation.latitude,
                    userLocation.longitude,
                    a.location.latitude,
                    a.location.longitude
                );
                const distB = locationService.calculateDistance(
                    userLocation.latitude,
                    userLocation.longitude,
                    b.location.latitude,
                    b.location.longitude
                );
                return distA - distB;
            });
        }

        setFilteredFoods(filtered);
    };

    const handleFilterChange = async (newFilters) => {
        setFilters(newFilters);
        
        if (newFilters.locationEnabled && !userLocation) {
            try {
                const position = await locationService.getCurrentPosition();
                setUserLocation(position);
            } catch (error) {
                console.error('Error getting location:', error);
            }
        }
    };

    if (loading) {
        return (
            <div 
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                role="status"
                aria-busy="true"
                aria-label="Loading food listings"
            >
                {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div
                        key={i}
                        className="animate-pulse bg-gray-200 rounded-lg h-96"
                        aria-hidden="true"
                    />
                ))}
                <div className="sr-only">Loading food listings...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div 
                className="text-center py-8"
                role="alert"
                aria-label="Error loading food listings"
            >
                <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4" aria-hidden="true"></i>
                <p className="text-gray-600">{error}</p>
                <Button
                    variant="secondary"
                    className="mt-4"
                    onClick={() => window.location.reload()}
                    aria-label="Reload page to try again"
                >
                    Try Again
                </Button>
            </div>
        );
    }

    if (!foods?.length) {
        return (
            <div 
                className="text-center py-8"
                role="status"
                aria-label="No food listings available"
            >
                <i className="fas fa-box-open text-gray-400 text-4xl mb-4" aria-hidden="true"></i>
                <p className="text-gray-600">No food listings available</p>
            </div>
        );
    }

    return (
        <div className="food-list-container">
            <FilterPanel onFilterChange={handleFilterChange} />
            
            <div 
                data-name="food-list" 
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-4"
                role="feed"
                aria-label="Food listings grid"
            >
                {filteredFoods.map((food) => (
                    <FoodCard
                        key={food.id || food.objectId}
                        food={food}
                        onClaim={onClaim}
                        distance={
                            userLocation && food.location
                                ? locationService.calculateDistance(
                                    userLocation.latitude,
                                    userLocation.longitude,
                                    food.location.latitude,
                                    food.location.longitude
                                )
                                : null
                        }
                    />
                ))}
            </div>
        </div>
    );
}

FoodList.propTypes = {
    foods: PropTypes.arrayOf(
        PropTypes.shape({
            id: PropTypes.string,
            objectId: PropTypes.string, // For backward compatibility
            title: PropTypes.string.isRequired,
            description: PropTypes.string.isRequired,
            image: PropTypes.string.isRequired,
            quantity: PropTypes.number.isRequired,
            unit: PropTypes.string.isRequired,
            expiryDate: PropTypes.string.isRequired,
            location: PropTypes.string.isRequired,
            type: PropTypes.oneOf(['donation']).isRequired,
            donor: PropTypes.shape({
                id: PropTypes.string.isRequired,
                name: PropTypes.string.isRequired,
                avatar: PropTypes.string.isRequired
            }).isRequired
        })
    ),
    onClaim: PropTypes.func,

    loading: PropTypes.bool,
    error: PropTypes.string
};

export default FoodList;
