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
                <div className="border-t border-gray-200 mt-8 pt-8 bg-gradient-to-r from-green-50 to-green-100 rounded-b-2xl">
                    <h2 className="text-2xl font-bold text-green-700 mb-4 text-center">Community Impact</h2>
                    {impactLoading ? (
                        <div className="flex justify-center items-center py-8">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-700"></div>
                            <span className="ml-2 text-green-700">Loading impact data...</span>
                        </div>
                    ) : (
                        <>
                            {/* Food Sharing Impact */}
                            <div className="mb-6">
                                <h3 className="text-xl font-semibold text-green-700 mb-3 text-center">Food Sharing Impact</h3>
                                <div className="flex flex-col md:flex-row justify-center items-center gap-4 p-4">
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.totalFoodShared} lb</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Total Food Shared</span>
                                    </div>
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.foodWasteReduced} lb</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Food Waste Reduced</span>
                                    </div>
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.sharingCount}</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Food Donations</span>
                                    </div>
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.donorsCount}</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Donors</span>
                                    </div>
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.activeListings}</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Active Listings</span>
                                    </div>
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-amber-600">{impact.pendingListings}</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Pending Listings</span>
                                    </div>
                                </div>
                            </div>
                            
                            {/* Environmental Impact */}
                            <div className="mb-6">
                                <h3 className="text-xl font-semibold text-green-700 mb-3 text-center">Environmental Impact</h3>
                                <div className="flex flex-col md:flex-row justify-center items-center gap-4 p-4">
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.co2Reduction.toFixed(1)} lb</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">CO₂ Emissions Avoided</span>
                                    </div>
                                </div>
                            </div>
                            
                            {/* People Impact */}
                            <div>
                                <h3 className="text-xl font-semibold text-green-700 mb-3 text-center">People Impact</h3>
                                <div className="flex flex-col md:flex-row justify-center items-center gap-4 p-4">
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.livesImpacted}</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Lives Impacted</span>
                                    </div>
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.neighborsHelped}</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Neighbors Helped</span>
                                    </div>
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.students}</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">Students</span>
                                    </div>
                                    <div className="flex flex-col items-center bg-white rounded-lg shadow-sm p-4 min-w-[120px]">
                                        <span className="text-3xl font-extrabold text-green-600">{impact.schoolStaff}</span>
                                        <span className="text-md text-gray-700 mt-2 text-center">School Staff</span>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}
                    <div className="text-center mt-4 text-sm text-gray-600 pb-4">
                        <p>Real-time impact data based on all food shared and approved claims</p>
                        {impact.lastUpdated && (
                            <>
                                <p className="mt-2">
                                    <span className="inline-block px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs font-semibold">
                                        <span className="inline-block w-2 h-2 bg-green-500 rounded-full mr-1 animate-pulse"></span>
                                        Auto-updating • Last updated: {new Date(impact.lastUpdated).toLocaleTimeString()}
                                    </span>
                                </p>
                                <p className="mt-2 text-xs text-gray-500">
                                    Note: Newly shared food items appear immediately in "Pending Listings" 
                                    and will move to "Active Listings" after admin approval.
                                </p>
                            </>
                        )}
                    </div>
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
