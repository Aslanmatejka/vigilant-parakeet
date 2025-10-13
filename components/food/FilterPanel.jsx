import React, { useState, useEffect } from 'react';
import Button from '../common/Button';
import { Input } from '../common/Input';
import { locationService } from '../../utils/locationService';

export const FilterPanel = ({ onFilterChange }) => {
    const [filters, setFilters] = useState({
        radius: 10,
        foodType: '',
        dietaryPreferences: [],
        pickupTime: '',
    });

    const dietaryOptions = [
        'Vegetarian',
        'Vegan',
        'Gluten-Free',
        'Halal',
        'Kosher',
        'Dairy-Free',
        'Nut-Free'
    ];

    const foodTypes = [
        'Fresh Produce',
        'Prepared Meals',
        'Canned Goods',
        'Baked Goods',
        'Dairy',
        'Beverages',
        'Packaged Foods',
        'Beverages',
        'Other'
    ];

    useEffect(() => {
        checkLocationPermission();
    }, []);

    const checkLocationPermission = async () => {
        try {
            const status = await locationService.requestLocationPermission();
            setLocationStatus(status);
            if (status === 'granted') {
                await enableLocation();
            }
        } catch (error) {
            setLocationStatus('denied');
            console.error('Location permission error:', error);
        }
    };

    const enableLocation = async () => {
        try {
            await locationService.getCurrentPosition();
            setFilters(prev => ({ ...prev, locationEnabled: true }));
            onFilterChange({ ...filters, locationEnabled: true });
        } catch (error) {
            console.error('Error getting location:', error);
            setFilters(prev => ({ ...prev, locationEnabled: false }));
        }
    };

    const handleRadiusChange = (value) => {
        const newRadius = parseInt(value) || 10;
        setFilters(prev => ({ ...prev, radius: newRadius }));
        onFilterChange({ ...filters, radius: newRadius });
    };

    const handleFoodTypeChange = (type) => {
        setFilters(prev => ({ ...prev, foodType: type }));
        onFilterChange({ ...filters, foodType: type });
    };

    const handleDietaryChange = (preference) => {
        setFilters(prev => {
            const newPreferences = prev.dietaryPreferences.includes(preference)
                ? prev.dietaryPreferences.filter(p => p !== preference)
                : [...prev.dietaryPreferences, preference];
            
            return { ...prev, dietaryPreferences: newPreferences };
        });
        onFilterChange({ ...filters, dietaryPreferences: filters.dietaryPreferences });
    };

    return (
        <div className="filter-panel p-4 bg-white rounded-lg shadow-md">
            <div className="mb-4">
                <h3 className="text-lg font-semibold mb-2">Location</h3>
                <div className="flex items-center gap-2">
                    <Button 
                        onClick={enableLocation}
                        disabled={locationStatus === 'denied'}
                        className={`${filters.locationEnabled ? 'bg-green-500' : 'bg-gray-500'}`}
                    >
                        {filters.locationEnabled ? 'Location Enabled' : 'Enable Location'}
                    </Button>
                    {filters.locationEnabled && (
                        <Input
                            type="number"
                            value={filters.radius}
                            onChange={(e) => handleRadiusChange(e.target.value)}
                            placeholder="Radius (km)"
                            min="1"
                            max="50"
                            className="w-24"
                        />
                    )}
                </div>
            </div>

            <div className="mb-4">
                <h3 className="text-lg font-semibold mb-2">Food Type</h3>
                <div className="flex flex-wrap gap-2">
                    {foodTypes.map(type => (
                        <Button
                            key={type}
                            onClick={() => handleFoodTypeChange(type)}
                            className={`${filters.foodType === type ? 'bg-blue-500' : 'bg-gray-200'}`}
                        >
                            {type}
                        </Button>
                    ))}
                </div>
            </div>

            <div className="mb-4">
                <h3 className="text-lg font-semibold mb-2">Dietary Preferences</h3>
                <div className="flex flex-wrap gap-2">
                    {dietaryOptions.map(preference => (
                        <Button
                            key={preference}
                            onClick={() => handleDietaryChange(preference)}
                            className={`${filters.dietaryPreferences.includes(preference) ? 'bg-blue-500' : 'bg-gray-200'}`}
                        >
                            {preference}
                        </Button>
                    ))}
                </div>
            </div>

            <div className="mb-4">
                <h3 className="text-lg font-semibold mb-2">Pickup Time</h3>
                <Input
                    type="datetime-local"
                    value={filters.pickupTime}
                    onChange={(e) => {
                        setFilters(prev => ({ ...prev, pickupTime: e.target.value }));
                        onFilterChange({ ...filters, pickupTime: e.target.value });
                    }}
                    className="w-full"
                />
            </div>
        </div>
    );
};
