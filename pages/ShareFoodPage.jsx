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

                // Trigger custom event for other components
                window.dispatchEvent(new CustomEvent('foodShared'));

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
