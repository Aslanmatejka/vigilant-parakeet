import React from "react";
import Button from "../components/common/Button";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth, useFoodListings } from "../utils/hooks/useSupabase";
import { reportError } from "../utils/helpers";
import FoodForm from "../components/food/FoodForm";
import ErrorBoundary from "../components/common/ErrorBoundary";
import dataService from '../utils/dataService';

function ShareFoodPageContent() {
    const navigate = useNavigate();
    const location = useLocation();
    const { user: authUser, isAuthenticated } = useAuth();
    const { createListing, updateListing, listings } = useFoodListings({}, 100); // Limit to 100 listings
    const searchParams = new URLSearchParams(location.search);
    const [activeTab, setActiveTab] = React.useState('individual');
    const [loading, setLoading] = React.useState(false);
    const [submitError, setSubmitError] = React.useState(null);
    const [initialData, setInitialData] = React.useState(null);
    const [isEditing, setIsEditing] = React.useState(false);

    React.useEffect(() => {
        // Check if we're editing an existing listing
        const editId = searchParams.get('edit');
        if (editId && listings.length > 0) {
            const listing = listings.find(l => l.id === parseInt(editId));
            if (listing) {
                setInitialData(listing);
                setIsEditing(true);
            }
        }
    }, [searchParams, listings]);

    const handleSubmit = async (formData) => {
        setLoading(true);
        setSubmitError(null);
        try {
            if (!authUser || !isAuthenticated) {
                setSubmitError('User not authenticated');
                setLoading(false);
                return;
            }

            let imageUrl = formData.image_url || null;

            // If there's a new image file, upload it first
            if (formData.image && typeof formData.image !== 'string') {
                const { success, url } = await dataService.uploadFile(formData.image, 'food-images');
                if (!success) {
                    setSubmitError('Failed to upload image');
                    setLoading(false);
                    return;
                }
                imageUrl = url;
            }

            const listingData = {
                ...formData,
                user_id: authUser.id,
                status: 'pending',
                image_url: imageUrl,
                listing_type: 'donation',
            };
            // Convert empty string date fields to null
            if (listingData.expiry_date === "") {
                listingData.expiry_date = null;
            }
            delete listingData.image; // Remove the file object

            try {
                if (isEditing && initialData) {
                    // Update existing listing
                    await updateListing(initialData.id, listingData);
                } else {
                    // Create new listing
                    await createListing(listingData);
                }
                
                // Immediately update the impact metrics
                console.log('Food listing submitted, updating impact metrics...');
                await fetchClaimImpact();
                
            } catch (apiError) {
                // Show specific error for missing donor_type column
                if (apiError.message && apiError.message.includes("donor_type")) {
                    setSubmitError("Submission failed: The 'donor_type' column is missing in the database. Please contact support or refresh your database schema.");
                } else {
                    setSubmitError(apiError.message || 'Failed to submit food listing.');
                }
                setLoading(false);
                return;
            }

            // Redirect to profile page
            navigate('/profile');
        } catch (error) {
            setSubmitError(error.message || 'Failed to submit food listing.');
            console.error('Create/update listing error:', error);
            reportError(error);
        } finally {
            setLoading(false);
        }
    }
    // ...existing code...

    // Impact based on claimed food
    const [impact, setImpact] = React.useState({
        foodWasteReduced: 0,
        totalFoodShared: 0,
        neighborsHelped: 0,
        donorsCount: 0,
        people: 0,
        schoolStaff: 0,
        students: 0,
        co2Reduction: 0,
        livesImpacted: 0,
        sharingCount: 0,
        activeListings: 0,
        pendingListings: 0,
        categoryDistribution: {},
        lastUpdated: null
    });
    const [impactLoading, setImpactLoading] = React.useState(true);

    const fetchClaimImpact = React.useCallback(async () => {
        try {
            setImpactLoading(true);
            const impactData = await dataService.getClaimImpact();
            setImpact(impactData);
        } catch (err) {
            console.error('Error fetching impact data:', err);
            setImpact({ 
                foodWasteReduced: 0, 
                totalFoodShared: 0,
                neighborsHelped: 0, 
                donorsCount: 0,
                people: 0, 
                schoolStaff: 0, 
                students: 0,
                co2Reduction: 0,
                livesImpacted: 0,
                sharingCount: 0,
                activeListings: 0,
                pendingListings: 0,
                categoryDistribution: {},
                lastUpdated: null
            });
        } finally {
            setImpactLoading(false);
        }
    }, []);

    React.useEffect(() => {
        fetchClaimImpact();
        
        // Subscribe to real-time claim updates
        const claimsSubscription = dataService.subscribeToClaims((payload) => {
            console.log('Food claim update detected:', payload.eventType);
            fetchClaimImpact();
        });
        
        // Subscribe to real-time food listing updates
        const listingsSubscription = dataService.subscribeToFoodListings((payload) => {
            console.log('Food listing update detected:', payload.eventType);
            fetchClaimImpact();
        });
        
        // Refresh impact data every minute as a fallback
        const intervalId = setInterval(() => {
            console.log('Auto-refreshing impact data...');
            fetchClaimImpact();
        }, 60000); // 60 seconds
        
        return () => {
            dataService.unsubscribe('food_claims');
            dataService.unsubscribe('food_listings');
            clearInterval(intervalId);
        };
    }, [fetchClaimImpact]);

    return (
        <div data-name="share-food-page" className="max-w-4xl mx-auto py-10 px-4">
            <div className="mb-4 flex justify-end">
                <Button onClick={() => navigate('/find')} variant="secondary" className="mr-2">Find Food</Button>
            </div>
            <div className="mb-8 text-center">
                <h1 className="text-4xl font-extrabold text-green-700 drop-shadow-sm mb-2">{isEditing ? 'Edit Listing' : 'Share Food'}</h1>
                <p className="mt-2 text-lg text-gray-600">
                    {isEditing
                        ? 'Update your food listing information.'
                        : 'Share your surplus food with families and organizations in need. All donations are reviewed and must be approved.'}
                </p>
            </div>

            <div className="bg-white rounded-2xl shadow-lg overflow-hidden border border-gray-100">
                    {submitError && (
                        <div className="text-red-600 text-center mb-4">{submitError}</div>
                    )}
                {!isEditing && (
                    <div className="border-b border-gray-200 bg-gradient-to-r from-green-50 to-green-100">
                        <nav className="flex justify-center" role="tablist">
                            <button
                                onClick={() => setActiveTab('individual')}
                                className={`px-6 py-4 text-center w-1/2 font-semibold text-base border-b-2 transition-colors duration-200 focus:outline-none ${
                                    activeTab === 'individual'
                                        ? 'border-green-500 text-green-700 bg-white shadow-sm'
                                        : 'border-transparent text-gray-500 hover:text-green-600 hover:border-green-300 bg-green-50'
                                }`}
                                role="tab"
                                aria-selected={activeTab === 'individual'}
                                aria-controls="individual-panel"
                            >
                                <i className="fas fa-utensils mr-2" aria-hidden="true"></i>
                                Individual/Organization Donation
                            </button>
                        </nav>
                    </div>
                )}

                <div className="p-8 md:p-10">
                    <div
                        role="tabpanel"
                        id="individual-panel"
                        aria-labelledby="individual-tab"
                        hidden={!isEditing && activeTab !== 'individual'}
                    >
                        {(isEditing || activeTab === 'individual') && (
                            <FoodForm
                                initialData={initialData}
                                onSubmit={handleSubmit}
                                loading={loading}
                            />
                        )}
                    </div>
                </div>
                {/* Impact Section */}
                <div className="border-t border-gray-200 mt-8 pt-8 bg-gradient-to-br from-green-50 via-blue-50 to-emerald-50 rounded-b-2xl p-6">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-3xl font-bold text-gray-900">Community Impact</h2>
                        {impact.lastUpdated && (
                            <span className="inline-flex items-center px-4 py-2 bg-green-100 text-green-800 rounded-full text-sm font-semibold shadow-sm">
                                <span className="inline-block w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></span>
                                Live Updates
                            </span>
                        )}
                    </div>

                    {impactLoading ? (
                        <div className="flex justify-center items-center py-12">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-green-600"></div>
                            <span className="ml-3 text-lg text-gray-700">Loading impact data...</span>
                        </div>
                    ) : (
                        <>
                            {/* Main Impact Cards */}
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                                <div className="bg-gradient-to-br from-green-50 to-green-100 p-6 rounded-2xl shadow-md hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1">
                                    <div className="flex items-start justify-between mb-4">
                                        <i className="fas fa-utensils text-4xl text-green-600" aria-hidden="true"></i>
                                    </div>
                                    <div className="text-5xl font-extrabold text-gray-900 mb-2">{Math.round(impact.totalFoodShared)}<span className="text-2xl ml-1 text-gray-600">lb</span></div>
                                    <div className="text-sm font-semibold text-gray-700">Total Food Shared</div>
                                </div>

                                <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-6 rounded-2xl shadow-md hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1">
                                    <div className="flex items-start justify-between mb-4">
                                        <i className="fas fa-recycle text-4xl text-blue-600" aria-hidden="true"></i>
                                    </div>
                                    <div className="text-5xl font-extrabold text-gray-900 mb-2">{Math.round(impact.foodWasteReduced)}<span className="text-2xl ml-1 text-gray-600">lb</span></div>
                                    <div className="text-sm font-semibold text-gray-700">Food Waste Reduced</div>
                                </div>

                                <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 p-6 rounded-2xl shadow-md hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1">
                                    <div className="flex items-start justify-between mb-4">
                                        <i className="fas fa-leaf text-4xl text-emerald-600" aria-hidden="true"></i>
                                    </div>
                                    <div className="text-5xl font-extrabold text-gray-900 mb-2">{impact.co2Reduction.toFixed(1)}<span className="text-2xl ml-1 text-gray-600">lb</span></div>
                                    <div className="text-sm font-semibold text-gray-700">CO₂ Avoided</div>
                                </div>

                                <div className="bg-gradient-to-br from-red-50 to-red-100 p-6 rounded-2xl shadow-md hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1">
                                    <div className="flex items-start justify-between mb-4">
                                        <i className="fas fa-heart text-4xl text-red-600" aria-hidden="true"></i>
                                    </div>
                                    <div className="text-5xl font-extrabold text-gray-900 mb-2">{impact.livesImpacted}</div>
                                    <div className="text-sm font-semibold text-gray-700">Lives Impacted</div>
                                </div>
                            </div>

                            {/* Secondary Stats Grid */}
                            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
                                <div className="bg-white p-5 rounded-xl shadow-sm hover:shadow-md transition-shadow">
                                    <div className="flex flex-col items-center text-center">
                                        <i className="fas fa-boxes text-2xl text-green-600 mb-2" aria-hidden="true"></i>
                                        <div className="text-3xl font-bold text-gray-900">{impact.sharingCount}</div>
                                        <div className="text-xs font-medium text-gray-600 mt-1">Donations</div>
                                    </div>
                                </div>

                                <div className="bg-white p-5 rounded-xl shadow-sm hover:shadow-md transition-shadow">
                                    <div className="flex flex-col items-center text-center">
                                        <i className="fas fa-users text-2xl text-blue-600 mb-2" aria-hidden="true"></i>
                                        <div className="text-3xl font-bold text-gray-900">{impact.donorsCount}</div>
                                        <div className="text-xs font-medium text-gray-600 mt-1">Donors</div>
                                    </div>
                                </div>

                                <div className="bg-white p-5 rounded-xl shadow-sm hover:shadow-md transition-shadow">
                                    <div className="flex flex-col items-center text-center">
                                        <i className="fas fa-check-circle text-2xl text-green-600 mb-2" aria-hidden="true"></i>
                                        <div className="text-3xl font-bold text-gray-900">{impact.activeListings}</div>
                                        <div className="text-xs font-medium text-gray-600 mt-1">Active</div>
                                    </div>
                                </div>

                                <div className="bg-white p-5 rounded-xl shadow-sm hover:shadow-md transition-shadow">
                                    <div className="flex flex-col items-center text-center">
                                        <i className="fas fa-clock text-2xl text-amber-600 mb-2" aria-hidden="true"></i>
                                        <div className="text-3xl font-bold text-gray-900">{impact.pendingListings}</div>
                                        <div className="text-xs font-medium text-gray-600 mt-1">Pending</div>
                                    </div>
                                </div>

                                <div className="bg-white p-5 rounded-xl shadow-sm hover:shadow-md transition-shadow">
                                    <div className="flex flex-col items-center text-center">
                                        <i className="fas fa-graduation-cap text-2xl text-purple-600 mb-2" aria-hidden="true"></i>
                                        <div className="text-3xl font-bold text-gray-900">{impact.students}</div>
                                        <div className="text-xs font-medium text-gray-600 mt-1">Students</div>
                                    </div>
                                </div>

                                <div className="bg-white p-5 rounded-xl shadow-sm hover:shadow-md transition-shadow">
                                    <div className="flex flex-col items-center text-center">
                                        <i className="fas fa-chalkboard-teacher text-2xl text-indigo-600 mb-2" aria-hidden="true"></i>
                                        <div className="text-3xl font-bold text-gray-900">{impact.schoolStaff}</div>
                                        <div className="text-xs font-medium text-gray-600 mt-1">Staff</div>
                                    </div>
                                </div>
                            </div>

                            {/* Info Banner */}
                            <div className="bg-white rounded-xl p-5 shadow-sm border-l-4 border-green-500">
                                <div className="flex items-start">
                                    <i className="fas fa-info-circle text-green-600 text-xl mr-3 mt-1" aria-hidden="true"></i>
                                    <div className="flex-1">
                                        <p className="text-sm text-gray-700 font-medium mb-1">Real-time community impact</p>
                                        <p className="text-xs text-gray-600">
                                            Data updates automatically when food is shared or claimed. Newly submitted items appear in "Pending" and move to "Active" after admin approval.
                                        </p>
                                        {impact.lastUpdated && (
                                            <p className="text-xs text-gray-500 mt-2">
                                                Last updated: {new Date(impact.lastUpdated).toLocaleString()}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

function ShareFoodPage() {
    return (
        <ErrorBoundary>
            <ShareFoodPageContent />
        </ErrorBoundary>
    );
}

export default ShareFoodPage;
