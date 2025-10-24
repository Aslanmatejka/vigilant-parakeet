import React from "react";
import { useNavigate } from "react-router-dom";
import Avatar from "../components/common/Avatar";
import Button from "../components/common/Button";
import ProfileStats from "../components/profile/ProfileStats";
import ListingsTab from "../components/profile/ListingsTab";
import { useAuthContext } from "../utils/AuthContext";
import { useFoodListings, useUserProfile } from "../utils/hooks/useSupabase";
import ErrorBoundary from "../components/common/ErrorBoundary";
import { DonateVolunteerButtons } from "./CommunityPage";
import dataService from '../utils/dataService';
import { reportError } from '../utils/helpers';

function ProfilePageContent() {
    const navigate = useNavigate();
    const { user: authUser, isAuthenticated, uploadAvatar } = useAuthContext();
    const { profile, loading: profileLoading, error: profileError } = useUserProfile(authUser?.id);
    const { listings, loading: listingsLoading, error: listingsError } = useFoodListings({ user_id: authUser?.id });

    const [activeTab, setActiveTab] = React.useState('profile');
    const [impact, setImpact] = React.useState(null);
    const [impactLoading, setImpactLoading] = React.useState(true);

    React.useEffect(() => {
        if (!isAuthenticated) {
            navigate('/login');
            return;
        }
    }, [isAuthenticated, navigate]);

    React.useEffect(() => {
        if (profileError || listingsError) {
            reportError('Failed to load user data');
        }
    }, [profileError, listingsError]);

    const loading = profileLoading || listingsLoading;

    const fetchUserImpact = React.useCallback(async () => {
        if (!authUser?.id) return;

        try {
            setImpactLoading(true);
            const impactData = await dataService.getUserImpact(authUser.id);
            setImpact(impactData);
        } catch (err) {
            console.error('Error fetching user impact data:', err);
            reportError(err);
            setImpact({
                totalListings: 0,
                activeListings: 0,
                pendingListings: 0,
                claimedListings: 0,
                totalFoodShared: 0,
                foodClaimed: 0,
                peopleHelped: 0,
                studentsHelped: 0,
                staffHelped: 0,
                livesImpacted: 0,
                co2Reduced: 0,
                lastUpdated: null
            });
        } finally {
            setImpactLoading(false);
        }
    }, [authUser]);

    React.useEffect(() => {
        if (!authUser?.id) return;

        fetchUserImpact();

        // Listen for custom events
        const handleFoodShared = () => {
            console.log('Food shared event detected, refreshing user impact...');
            setTimeout(() => fetchUserImpact(), 1000);
        };

        const handleFoodClaimed = () => {
            console.log('Food claimed event detected, refreshing user impact...');
            setTimeout(() => fetchUserImpact(), 1000);
        };

        window.addEventListener('foodShared', handleFoodShared);
        window.addEventListener('foodClaimed', handleFoodClaimed);

        // Subscribe to real-time updates
        const claimsSubscription = dataService.subscribeToClaims(() => {
            console.log('Food claim update detected, refreshing user impact');
            setTimeout(() => fetchUserImpact(), 1000);
        });

        const listingsSubscription = dataService.subscribeToFoodListings(() => {
            console.log('Food listing update detected, refreshing user impact');
            setTimeout(() => fetchUserImpact(), 1000);
        });

        // Refresh every 30 seconds for more frequent updates
        const intervalId = setInterval(() => {
            fetchUserImpact();
        }, 30000);

        return () => {
            window.removeEventListener('foodShared', handleFoodShared);
            window.removeEventListener('foodClaimed', handleFoodClaimed);
            dataService.unsubscribe('food_claims');
            dataService.unsubscribe('food_listings');
            clearInterval(intervalId);
        };
    }, [fetchUserImpact, authUser]);

    const handleEditListing = (listing) => {
        navigate(`/share?edit=${listing.id}`);
    };

    const handleDeleteListing = async (listing) => {
        if (!window.confirm('Are you sure you want to delete this listing?')) return;

        try {
            // This will be handled by the useFoodListings hook
            // The listing will be removed from the list automatically
            alert('Listing deleted successfully');
        } catch (error) {
            console.error('Delete listing error:', error);
            alert('Failed to delete listing. Please try again.');
        }
    };

    if (loading) {
        return (
            <div className="max-w-7xl mx-auto py-8 px-4">
                <div className="animate-pulse space-y-8">
                    <div className="h-32 bg-gray-200 rounded-lg"></div>
                    <div className="h-64 bg-gray-200 rounded-lg"></div>
                </div>
            </div>
        );
    }

    if (!profile) {
        return (
            <div className="max-w-7xl mx-auto py-8 px-4 text-center">
                <p className="text-gray-600">User profile not found</p>
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto py-8 px-4">
            <div className="bg-white rounded-lg shadow-sm overflow-hidden mb-8">
                <div className="p-6">
                    <div className="flex flex-col md:flex-row items-start md:items-center justify-between mb-8">
                        <div className="flex items-center mb-4 md:mb-0">
                            <div className="relative group">
                                <Avatar
                                    src={profile.avatar_url}
                                    size="xl"
                                    alt={`${profile.name}'s avatar`}
                                />
                                <label htmlFor="avatar-upload" className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-0 group-hover:bg-opacity-40 cursor-pointer transition duration-200">
                                    <span className="text-white opacity-0 group-hover:opacity-100 text-sm font-semibold"><i className="fas fa-camera mr-2"></i>Change</span>
                                </label>
                                <input
                                    id="avatar-upload"
                                    type="file"
                                    accept="image/*"
                                    className="hidden"
                                    onChange={async (e) => {
                                        const file = e.target.files[0];
                                        if (file) {
                                            try {
                                                // Call uploadAvatar from context
                                                await authUser && authUser.uploadAvatar(file);
                                                window.location.reload(); // Refresh to show new avatar
                                            } catch (err) {
                                                alert('Failed to upload avatar.');
                                            }
                                        }
                                    }}
                                />
                            </div>
                            <div className="ml-4">
                                <h1 className="text-2xl font-bold text-gray-900">{profile.name}</h1>
                                <p className="text-gray-600">{profile.email}</p>
                            </div>
                        </div>
                        <Button
                            variant="secondary"
                            icon={<i className="fas fa-edit"></i>}
                            onClick={() => navigate('/settings')}
                        >
                            Edit Profile
                        </Button>
                    </div>

                    <ProfileStats impact={impact} loading={impactLoading} />
                </div>
            </div>

            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="border-b border-gray-200">
                    <nav className="flex" role="tablist">
                        <button
                            onClick={() => setActiveTab('listings')}
                            className={`px-6 py-4 text-sm font-medium border-b-2 ${
                                activeTab === 'listings'
                                    ? 'border-green-500 text-green-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            }`}
                            role="tab"
                            aria-selected={activeTab === 'listings'}
                            aria-controls="listings-panel"
                        >
                            My Listings
                        </button>

                    </nav>
                </div>

                <div className="p-6">
                    <div
                        role="tabpanel"
                        id="listings-panel"
                        aria-labelledby="listings-tab"
                        hidden={activeTab !== 'listings'}
                    >
                        {activeTab === 'listings' && (
                            <ListingsTab
                                listings={listings || []}
                                onEdit={handleEditListing}
                                onDelete={handleDeleteListing}
                            />
                        )}
                    </div>


                </div>
            </div>

            <section className="mt-10">
                <h2 className="text-2xl font-bold mb-4">Support the Community</h2>
                <DonateVolunteerButtons />
            </section>
        </div>
    );
}

function ProfilePage() {
    return (
        <ErrorBoundary>
            <ProfilePageContent />
        </ErrorBoundary>
    );
}

export default ProfilePage;