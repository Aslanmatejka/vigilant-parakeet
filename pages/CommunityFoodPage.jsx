import React, { useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import FoodCard from '../components/food/FoodCard';
import { useFoodListings } from '../utils/hooks/useSupabase';
import communities from '../utils/communities';

export default function CommunityFoodPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const communityId = parseInt(id, 10);

    const community = communities.find(c => c.id === communityId);

    const { listings: foods, loading, error, fetchListings } = useFoodListings({ status: 'approved' });

    // Filter foods by community - assume food.location or donor_city contains community name or id
    // We'll use a simple heuristic: check listing.donor_city or listing.location.address for community name
    const communityFoods = useMemo(() => {
        if (!foods) return [];
        if (!community) return [];
        const nameLower = community.name.toLowerCase();
        return foods.filter(f => {
            const city = (f.donor_city || '') + ' ' + (f.donor_state || '');
            const loc = f.location && f.location.address ? f.location.address : '';
            return (city.toLowerCase().includes(nameLower) || loc.toLowerCase().includes(nameLower) || (f.community_id && f.community_id === communityId));
        });
    }, [foods, community, communityId]);

    if (!community) {
        return (
            <div className="max-w-4xl mx-auto py-10 px-4">
                <Card>
                    <div className="p-6 text-center">
                        <h2 className="text-xl font-bold">Community Not Found</h2>
                        <p className="text-gray-600 mt-2">We couldn't find the community you're looking for.</p>
                        <div className="mt-4">
                            <Button onClick={() => navigate('/')} variant="secondary">Back to Home</Button>
                        </div>
                    </div>
                </Card>
            </div>
        );
    }

    return (
        <div className="max-w-6xl mx-auto py-10 px-4">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold">{community.name}</h1>
                    <p className="text-sm text-gray-600">{community.location}</p>
                </div>
                <div>
                    <Button variant="secondary" onClick={() => navigate('/find')}>View All Listings</Button>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {loading ? (
                    <div className="text-center py-12">Loading...</div>
                ) : error ? (
                    <div className="text-center py-12 text-red-600">Error loading listings</div>
                ) : communityFoods.length === 0 ? (
                    <Card>
                        <div className="p-6 text-center">
                            <h3 className="text-lg font-semibold">No food available right now</h3>
                            <p className="text-gray-600 mt-2">Check back later or view all listings.</p>
                        </div>
                    </Card>
                ) : (
                    communityFoods.map(food => (
                        <FoodCard key={food.id || food.objectId} food={food} onClaim={() => navigate('/claim', { state: { food } })} />
                    ))
                )}
            </div>
        </div>
    );
}
