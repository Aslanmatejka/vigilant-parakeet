import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import supabase from '../utils/supabaseClient';
import communitiesStatic from '../utils/communities';
import FoodCard from '../components/food/FoodCard';
import { useAuthContext } from '../utils/AuthContext';

function CommunityDetailPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { isAuthenticated, user } = useAuthContext();
    const [community, setCommunity] = useState(null);
    const [foodListings, setFoodListings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchCommunityData = async () => {
            try {
                setLoading(true);
                
                // Fetch community details
                const { data: communityData, error: communityError } = await supabase
                    .from('communities')
                    .select('*')
                    .eq('id', id)
                    .single();

                if (communityError) throw communityError;

                // Merge with static data
                const staticCommunity = communitiesStatic.find(c => c.name === communityData.name);
                const mergedCommunity = {
                    ...staticCommunity,
                    ...communityData
                };
                
                setCommunity(mergedCommunity);

                // Fetch food donation listings for this community (both approved and active).
                // Exclude expired items. All listings are donations (food offers users can claim).
                // Use local date to avoid dropping today's listings after 4 PM Pacific (UTC-8)
                // when toISOString() rolls to the next UTC day.
                const _t = new Date();
                const todayStr = [_t.getFullYear(), String(_t.getMonth() + 1).padStart(2, '0'), String(_t.getDate()).padStart(2, '0')].join('-');
                const { data: listings, error: listingsError } = await supabase
                    .from('food_listings')
                    .select('*')
                    .eq('community_id', id)
                    .eq('listing_type', 'donation')
                    .in('status', ['approved', 'active'])
                    .or(`expiry_date.is.null,expiry_date.gte.${todayStr}`)
                    .order('created_at', { ascending: false });

                if (listingsError) throw listingsError;

                setFoodListings(listings || []);
            } catch (err) {
                console.error('Error fetching community data:', err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        if (id) {
            fetchCommunityData();
        }
    }, [id]);

    const handleClaim = (food) => {
        if (!isAuthenticated) {
            navigate('/login', { state: { from: `/community/${id}`, returnToFood: food } });
            return;
        }
        const claimFood = {
            ...food,
            id: food.id || food.objectId,
            objectId: food.objectId || food.id
        };
        navigate('/claim', { state: { food: claimFood } });
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading community details...</p>
                </div>
            </div>
        );
    }

    if (error || !community) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                    <i className="fas fa-exclamation-circle text-6xl text-red-500 mb-4"></i>
                    <h2 className="text-2xl font-bold text-gray-800 mb-2">Community Not Found</h2>
                    <p className="text-gray-600 mb-4">{error || 'This community does not exist.'}</p>
                    <button
                        onClick={() => navigate('/')}
                        className="px-6 py-2 bg-[#2CABE3] text-white rounded-lg hover:bg-[#2398c7] transition-colors"
                    >
                        Back to Home
                    </button>
                </div>
            </div>
        );
    }

    const WAREHOUSE_COMMUNITY_ID = 1;
    const canViewListings = !isAuthenticated || 
        String(id) === String(WAREHOUSE_COMMUNITY_ID) || 
        String(user?.community_id) === String(id);

    const foodGivenValue = Math.round(parseFloat(community.food_given_lb) || 0);
    const familiesHelpedValue = parseInt(community.families_helped) || 0;
    const schoolStaffHelpedValue = parseInt(community.school_staff_helped) || 0;

    return (
        <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            {/* Header Section */}
            <div className="bg-white shadow-sm border-b">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                    <button
                        onClick={() => navigate('/')}
                        className="mb-4 text-[#2CABE3] hover:text-[#2398c7] flex items-center"
                    >
                        <i className="fas fa-arrow-left mr-2"></i>
                        Back to Communities
                    </button>
                    
                    <div className="grid md:grid-cols-3 gap-6">
                        {/* Community Image */}
                        <div className="md:col-span-1">
                            <img
                                src={community.image}
                                alt={community.name}
                                className="w-full h-64 object-cover rounded-lg shadow-md"
                            />
                        </div>

                        {/* Community Info */}
                        <div className="md:col-span-2">
                            <h1 className="text-3xl font-bold text-gray-800 mb-4">{community.name}</h1>
                            
                            {community.description && (
                                <p className="text-gray-600 mb-6 text-lg leading-relaxed">
                                    {community.description}
                                </p>
                            )}
                            
                            <div className="space-y-3 mb-6">
                                <div className="flex items-start text-gray-700">
                                    <i className="fas fa-map-marker-alt w-6 text-[#2CABE3] mt-1"></i>
                                    <span>{community.location}</span>
                                </div>
                                <div className="flex items-start text-gray-700">
                                    <i className="fas fa-user w-6 text-[#2CABE3] mt-1"></i>
                                    <span>Contact: {community.contact}</span>
                                </div>
                                <div className="flex items-start text-gray-700">
                                    <i className="fas fa-clock w-6 text-[#2CABE3] mt-1"></i>
                                    <span>Hours: {community.hours}</span>
                                </div>
                                <div className="flex items-start text-gray-700">
                                    <i className="fas fa-phone w-6 text-[#2CABE3] mt-1"></i>
                                    <a href={`tel:${community.phone}`} className="text-[#2CABE3] hover:underline">
                                        {community.phone}
                                    </a>
                                </div>
                            </div>

                            {/* Impact Metrics */}
                            <div className="grid grid-cols-3 gap-4 bg-cyan-50 p-4 rounded-lg">
                                <div className="text-center">
                                    <i className="fas fa-apple-alt text-3xl text-primary-600 mb-2"></i>
                                    <div className="text-2xl font-bold text-primary-700">{foodGivenValue.toLocaleString()}</div>
                                    <div className="text-sm text-gray-600">lbs Given</div>
                                </div>
                                <div className="text-center">
                                    <i className="fas fa-users text-3xl text-blue-600 mb-2"></i>
                                    <div className="text-2xl font-bold text-blue-700">{familiesHelpedValue.toLocaleString()}</div>
                                    <div className="text-sm text-gray-600">Families</div>
                                </div>
                                <div className="text-center">
                                    <i className="fas fa-chalkboard-teacher text-3xl text-purple-600 mb-2"></i>
                                    <div className="text-2xl font-bold text-purple-700">{schoolStaffHelpedValue.toLocaleString()}</div>
                                    <div className="text-sm text-gray-600">Staff</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Food Listings Section — only visible to members of this community or for the warehouse */}
            {canViewListings && (
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                <div className="mb-8">
                    <h2 className="text-2xl font-bold text-gray-800 mb-2">
                        Available Food at {community.name}
                    </h2>
                    <p className="text-gray-600">
                        {foodListings.length} {foodListings.length === 1 ? 'item' : 'items'} available
                    </p>
                </div>

                {foodListings.length === 0 ? (
                    <div className="bg-white rounded-lg shadow-sm p-12 text-center">
                        <i className="fas fa-box-open text-6xl text-gray-300 mb-4"></i>
                        <h3 className="text-xl font-semibold text-gray-700 mb-2">No Food Available</h3>
                        <p className="text-gray-500 mb-6">
                            There are currently no food items available at this community.
                        </p>
                        <button
                            onClick={() => navigate('/find')}
                            className="px-6 py-2 bg-[#2CABE3] text-white rounded-lg hover:bg-[#2398c7] transition-colors"
                        >
                            Browse All Food
                        </button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {foodListings.map((food) => (
                            <FoodCard
                                key={food.id}
                                food={food}
                                onClaim={() => handleClaim(food)}
                                showClaimButton={true}
                            />
                        ))}
                    </div>
                )}
            </div>
            )}
        </div>
    );
}

export default CommunityDetailPage;
