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
    const [locationStatus, setLocationStatus] = useState(null);

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

    const InfoIcon = ({ text }) => (
        <span
            title={text}
            aria-label={text}
            className="ml-1 inline-flex items-center justify-center w-4 h-4 rounded-full bg-gray-200 text-gray-700 text-[10px] font-bold cursor-help select-none"
        >
            ?
        </span>
    );

    return (
        <div className="filter-panel p-4 bg-white rounded-lg shadow-md">
            <p className="text-sm text-gray-500 mb-4">
                Use these filters to narrow your search. Changes apply automatically.
            </p>

            <div className="mb-4">
                <h3 className="text-lg font-semibold mb-1 flex items-center">
                    Location
                    <InfoIcon text="Turn on location so we can sort listings by distance. Use the radius field to set how far you’ll travel (in miles)." />
                </h3>
                <p className="text-xs text-gray-500 mb-2">Set how far you’re willing to travel.</p>
                <div className="flex items-center gap-2">
                    <Button 
                        onClick={enableLocation}
                        disabled={locationStatus === 'denied'}
                        className={`${filters.locationEnabled ? 'bg-primary-500' : 'bg-gray-500'}`}
                        title="Share your current location with this page"
                    >
                        {filters.locationEnabled ? 'Location Enabled' : 'Enable Location'}
                    </Button>
                    {filters.locationEnabled && (
                        <Input
                            type="number"
                            value={filters.radius}
                            onChange={(e) => handleRadiusChange(e.target.value)}
                            placeholder="Radius (mi)"
                            min="1"
                            max="50"
                            className="w-24"
                            title="Maximum distance in miles"
                        />
                    )}
                </div>
            </div>

            <div className="mb-4">
                <h3 className="text-lg font-semibold mb-1 flex items-center">
                    Food Type
                    <InfoIcon text="Pick a category to only see one kind of food. Tap again to clear." />
                </h3>
                <p className="text-xs text-gray-500 mb-2">Choose what kind of food you’re looking for.</p>
                <div className="flex flex-wrap gap-2">
                    {foodTypes.map(type => (
                        <Button
                            key={type}
                            onClick={() => handleFoodTypeChange(filters.foodType === type ? '' : type)}
                            className={`${filters.foodType === type ? 'bg-blue-500' : 'bg-gray-200'}`}
                            title={`Show only ${type}`}
                        >
                            {type}
                        </Button>
                    ))}
                </div>
            </div>

            <div className="mb-4">
                <h3 className="text-lg font-semibold mb-1 flex items-center">
                    Dietary Preferences
                    <InfoIcon text="Select one or more diets. Only listings tagged with all of your selections will be shown." />
                </h3>
                <p className="text-xs text-gray-500 mb-2">Filter by your dietary needs. Select as many as apply.</p>
                <div className="flex flex-wrap gap-2">
                    {dietaryOptions.map(preference => (
                        <Button
                            key={preference}
                            onClick={() => handleDietaryChange(preference)}
                            className={`${filters.dietaryPreferences.includes(preference) ? 'bg-blue-500' : 'bg-gray-200'}`}
                            title={`Only show ${preference} options`}
                        >
                            {preference}
                        </Button>
                    ))}
                </div>
            </div>

            <div className="mb-4">
                <h3 className="text-lg font-semibold mb-1 flex items-center">
                    Pickup Time
                    <InfoIcon text="Filter to listings available around the time you can pick them up. Leave blank to see everything." />
                </h3>
                <p className="text-xs text-gray-500 mb-2">When can you pick the food up?</p>
                <Input
                    type="datetime-local"
                    value={filters.pickupTime}
                    onChange={(e) => {
                        setFilters(prev => ({ ...prev, pickupTime: e.target.value }));
                        onFilterChange({ ...filters, pickupTime: e.target.value });
                    }}
                    className="w-full"
                    title="Pick the date and time you can collect the food"
                />
            </div>
        </div>
    );
};
