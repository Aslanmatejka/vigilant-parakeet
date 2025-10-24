export default FindFoodPage;
import { useState, useEffect, useMemo } from "react";
import { useNavigate, useLocation as useRouterLocation } from 'react-router-dom';
import Button from "../components/common/Button";
import Input from "../components/common/Input";
import FoodCard from "../components/food/FoodCard";
import { toast } from "react-toastify";
import { useFoodListings, useSearch } from "../utils/hooks/useSupabase";
import { useGeoLocation } from "../utils/hooks/useLocation";

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
    
    const { listings: foods, loading: foodsLoading, error: foodsError, fetchListings } = useFoodListings({ status: 'approved' });
    const { search, results: searchResults, loading: searchLoading } = useSearch();
    const { 
        location: currentLocation, 
        loading: geoLoading, 
        error: geoError, 
        enableLocation: enableGeolocation 
    } = useGeoLocation();
    
    const [searchTerm, setSearchTerm] = useState('');
    const [isSearchActive, setIsSearchActive] = useState(false);
    const [filters, setFilters] = useState({
        category: initialCategory || '',
        type: 'all',
        radius: '10'
    });
    const [formData, setFormData] = useState({
        requester_name: '',
        requester_email: '',
        requester_phone: '',
        school_district: '',
        school: '',
        school_contact: '',
        school_contact_email: '',
        school_contact_phone: '',
        category: '',
        dietary_restrictions: '',
        pickup_dropoff: ''
    });

    // Initial data load and category from URL
    useEffect(() => {
        fetchListings();
        
        const categoryParam = new URLSearchParams(location.search).get('category');
        if (categoryParam) {
            const mappedCategory = CATEGORY_MAPPING[categoryParam.toLowerCase()] || categoryParam;
            setFilters(prev => ({ ...prev, category: mappedCategory }));
        }
    }, [fetchListings, location.search]);

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
                ? `${location.pathname}?category=${value}`
                : location.pathname;
            navigate(newUrl, { replace: true });
        }
    };

    const handleFormChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));
    };

    const findSimilarItems = async (food) => {
        try {
            if (similarItems[food.objectId]) {
                return similarItems[food.objectId];
            }

            const request = {
                type: food.type,
                description: food.description,
                location: food.location,
                value: food.estimatedValue,
                urgency: food.urgency || 'normal',
                user: food.donor.objectId // Assuming food object has a donor property with objectId
            };

            const matches = await matchingEngine.findMatches(request, foods);
            const similar = matches
                .filter(match => 
                    match.offer.objectId !== food.objectId && 
                    match.scores.total > 0.6
                )
                .slice(0, 3)
                .map(match => ({
                    ...match.offer,
                    matchScore: Math.round(match.scores.total * 100)
                }));

            setSimilarItems(prev => ({
                ...prev,
                [food.objectId]: similar
            }));

            return similar;
        } catch (error) {
            console.error('Find similar items error:', error);
            return [];
        }
    };

    const handleViewItem = async (food) => {
        // Find similar items when viewing details
        await findSimilarItems(food);
    };

    const filteredFoods = useMemo(() => {
        // Use search results if search is active, otherwise use all foods
        let result = isSearchActive ? [...searchResults] : [...foods];

        if (!isSearchActive && searchTerm) {
            const searchTermLower = searchTerm.toLowerCase();
            result = result.filter(food => 
                food.title.toLowerCase().includes(searchTermLower) ||
                food.description.toLowerCase().includes(searchTermLower) ||
                food.location.toLowerCase().includes(searchTermLower)
            );
        }

        if (filters.category) {
            result = result.filter(food => food.category === filters.category);
        }

        if (filters.type !== 'all') {
            result = result.filter(food => food.type === filters.type);
        }

        // Location-based filtering
        if (currentLocation && filters.radius) {
            const maxDistance = parseInt(filters.radius);
            result = result.filter(food => {
                if (!food.location || !food.location.latitude || !food.location.longitude) {
                    return false;
                }
                const distance = calculateDistance(
                    currentLocation.latitude,
                    currentLocation.longitude,
                    food.location.latitude,
                    food.location.longitude
                );
                food.distance = distance; // Add distance to food object for display
                return distance <= maxDistance;
            });

            // Sort by distance when location is enabled
            result.sort((a, b) => (a.distance || 0) - (b.distance || 0));
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
    }, [foods, searchResults, isSearchActive, searchTerm, filters]);

    const LoadingSpinner = () => (
        <div className="text-center py-12" role="status">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-green-500 mx-auto" aria-hidden="true"></div>
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
            className="container mx-auto px-4"
            role="main"
        >
            <div className="py-10">
                <div className="mb-4 flex justify-end">
                    <Button onClick={() => navigate('/share')} variant="secondary" className="mr-2">Share Food</Button>
                </div>
                <div className="mb-8 text-center">
                    <h1 className="text-4xl font-extrabold text-green-700 drop-shadow-sm mb-2">Find Food Assistance</h1>
                    <p className="mt-2 text-lg text-gray-600">
                        Browse available food listings and claim what you need for your school, family, or organization. All requests are confidential and reviewed promptly.
                    </p>
                </div>
                {/* Search Bar and Category Filter */}
                <div className="flex flex-col md:flex-row items-center justify-between gap-4 mb-8">
                    <div className="flex-1 w-full md:w-auto">
                        <Input
                            type="text"
                            name="search"
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                            placeholder="Search for food..."
                            className="w-full md:w-64"
                        />
                    </div>
                    <div className="flex-1 w-full md:w-auto">
                        <select
                            name="category"
                            value={filters.category}
                            onChange={handleFilterChange}
                            className="border border-gray-300 rounded px-4 py-2 w-full md:w-48"
                        >
                            <option value="">All Categories</option>
                            <option value="produce">Fresh Produce</option>
                            <option value="dairy">Dairy</option>
                            <option value="bakery">Bakery</option>
                            <option value="pantry">Pantry Items</option>
                            <option value="meat">Meat & Poultry</option>
                            <option value="prepared">Prepared Foods</option>
                        </select>
                    </div>
                    <Button variant="primary" onClick={handleSearch} disabled={searchLoading}>Search</Button>
                    {isSearchActive && (
                        <Button variant="secondary" onClick={handleClearSearch}>Clear</Button>
                    )}
                </div>
                <div className="mt-12">
                    <h2 className="text-2xl font-bold text-gray-800 mb-4">Available Food Listings</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {foodsLoading ? (
                            <LoadingSpinner />
                        ) : foodsError ? (
                            <ErrorDisplay />
                        ) : filteredFoods.length === 0 ? (
                            <div className="text-center py-12" role="status">
                                <i className="fas fa-search text-gray-400 text-4xl mb-4" aria-hidden="true"></i>
                                <p className="text-gray-600 mb-4">No food listings found</p>
                                <Button
                                    variant="secondary"
                                    onClick={() => {
                                        setSearchTerm('');
                                        setFilters({
                                            category: '',
                                            type: 'all',
                                            distance: 10
                                        });
                                    }}
                                >
                                    Clear Filters
                                </Button>
                            </div>
                        ) : (
                            filteredFoods.map((food) => (
                                <div key={food.objectId} role="listitem">
                                    <FoodCard
                                        food={food}
                                        onClaim={handleClaim}
                                        onViewDetails={handleViewItem}
                                    />
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
