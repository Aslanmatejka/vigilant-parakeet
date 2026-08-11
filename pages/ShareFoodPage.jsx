import React from "react";
import Button from "../components/common/Button";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth, useFoodListings } from "../utils/hooks/useSupabase";
import { useCommunityRole } from "../utils/hooks/useCommunityRole";
import { reportError } from "../utils/helpers";
import FoodForm from "../components/food/FoodForm";
import ShareBulkCsvPanel from "../components/food/ShareBulkCsvPanel";
import ErrorBoundary from "../components/common/ErrorBoundary";
import dataService from '../utils/dataService';
import supabase from '../utils/supabaseClient';
import { toast } from 'react-toastify';

function ShareFoodPageContent() {
    const navigate = useNavigate();
    const location = useLocation();
    const { user: authUser, isAuthenticated, isAdmin } = useAuth();
    const isDonor = useCommunityRole() === 'donor';
    const { createListing, updateListing, listings } = useFoodListings(
        authUser?.id ? { user_id: authUser.id } : {},
        100
    );
    const searchParams = React.useMemo(
        () => new URLSearchParams(location.search),
        [location.search]
    );
    const [activeTab, setActiveTab] = React.useState('individual');
    const [loading, setLoading] = React.useState(false);
    const [submitError, setSubmitError] = React.useState(null);
    const [editListing, setEditListing] = React.useState(null);

    const requestPrefill = React.useMemo(() => {
        const requestTitle = searchParams.get('request');
        const communityId = searchParams.get('community_id');
        const community = searchParams.get('community');
        // Allow community-only deep links from Nouri (no title yet).
        if (!requestTitle && !communityId && !community) return null;

        const prefill = {
            title: requestTitle || '',
            category: searchParams.get('category') || '',
            description: searchParams.get('description')
                || (requestTitle
                    ? `Shared in response to a community request for: ${requestTitle}`
                    : ''),
            // Keep donation in the same community as the food request.
            lockCommunity: true,
        };

        const quantity = searchParams.get('quantity');
        const unit = searchParams.get('unit');
        if (quantity) prefill.quantity = quantity;
        if (unit) prefill.unit = unit;

        if (communityId) prefill.community_id = communityId;
        if (community) prefill.school_district = community;

        const neededBy = searchParams.get('needed_by');
        if (neededBy) prefill.pickup_by = neededBy;

        const fulfillingId = searchParams.get('fulfilling_request_id');
        if (fulfillingId) prefill.fulfilling_request_id = fulfillingId;

        return prefill;
    }, [searchParams]);

    React.useEffect(() => {
        const editId = searchParams.get('edit');
        if (!editId) {
            setEditListing(null);
            return;
        }
        if (listings.length === 0) return;

        const listing = listings.find(
            (l) => l.id === parseInt(editId, 10) || String(l.id) === String(editId)
        );
        setEditListing(listing || null);
    }, [searchParams, listings]);

    const formInitialData = editListing || requestPrefill;
    const isEditing = Boolean(editListing);

    // Keep users on Individual when editing or fulfilling a single request.
    React.useEffect(() => {
        if (isEditing || requestPrefill) {
            setActiveTab('individual');
        }
    }, [isEditing, requestPrefill]);

    const preferredBulkLocation = React.useMemo(() => {
        const parts = [
            authUser?.full_address,
            authUser?.address,
            [authUser?.city, authUser?.state].filter(Boolean).join(', '),
            authUser?.zip_code,
            authUser?.zip,
        ].filter((p) => String(p || '').trim());
        return parts[0] ? String(parts[0]).trim() : '';
    }, [authUser]);

    const handleBulkSuccess = React.useCallback(({ awaitingApproval }) => {
        if (awaitingApproval) {
            navigate('/profile?tab=listings&filter=pending');
        } else {
            navigate('/profile?tab=listings');
        }
    }, [navigate]);

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

            // Prefer the request's community_id (Share matching food / Nouri),
            // then any id on the form, then look up by community name.
            let communityId =
                formData.community_id
                || searchParams.get('community_id')
                || null;
            if (!communityId && formData.school_district) {
                const { data: community } = await supabase
                    .from('communities')
                    .select('id')
                    .eq('name', formData.school_district)
                    .maybeSingle();
                if (community) {
                    communityId = community.id;
                }
            }

            const listingData = {
                ...formData,
                user_id: authUser.id,
                // Status resolved by dataService (pending when approval required).
                community_id: communityId,
                image_url: imageUrl,
                listing_type: 'donation',
            };
            delete listingData.lockCommunity;
            delete listingData.fulfilling_request_id;
            // Convert empty string date fields to null
            if (listingData.expiry_date === "") {
                listingData.expiry_date = null;
            }
            delete listingData.image; // Remove the file object

            try {
                if (isEditing && editListing) {
                    // Update existing listing
                    await updateListing(editListing.id, listingData);
                    toast.success('Listing updated.');
                    navigate('/profile?tab=listings');
                } else {
                    const created = await createListing(listingData);
                    const status = String(created?.status || listingData.status || '').toLowerCase();
                    if (status === 'pending') {
                        toast.success('Submitted for admin approval. You’ll see it under Pending on My Listings.');
                        navigate('/profile?tab=listings&filter=pending');
                    } else {
                        toast.success('Listing is live on Find Food.');
                        navigate('/profile?tab=listings');
                    }
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
        } catch (error) {
            setSubmitError(error.message || 'Failed to submit food listing.');
            console.error('Create/update listing error:', error);
            reportError(error);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div data-name="share-food-page" className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className={`fas ${isEditing ? 'fa-pen-to-square' : 'fa-hand-holding-heart'} mr-2`} aria-hidden="true"></i>
                            {isEditing ? 'Update Listing' : 'Donate Food'}
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            {isEditing ? 'Edit your ' : 'Share your '}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                {isEditing ? 'listing' : 'surplus food'}
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            {isEditing
                                ? 'Update your food listing information.'
                                : 'Share your surplus food with families and organizations in need. Your listing may wait for a quick admin review before it appears on Find Food.'}
                        </p>
                    </div>
                </div>
            </header>

            <div className="max-w-4xl mx-auto px-1 sm:px-4 pb-10">
                {!isDonor && (
                    <div className="mb-4 flex justify-end">
                        <Button onClick={() => navigate('/find')} variant="secondary" className="mr-2">Find Food</Button>
                    </div>
                )}

            <div className="bg-white rounded-2xl shadow-lg overflow-hidden border border-gray-100">
                    {submitError && (
                        <div className="text-red-600 text-center mb-4">{submitError}</div>
                    )}
                {!isEditing && !requestPrefill && (
                    <div className="border-b border-gray-200 bg-gradient-to-r from-primary-50 to-primary-100">
                        <nav className="flex justify-center" role="tablist">
                            <button
                                type="button"
                                id="individual-tab"
                                onClick={() => setActiveTab('individual')}
                                className={`px-4 sm:px-6 py-4 text-center w-1/2 font-semibold text-sm sm:text-base border-b-2 transition-colors duration-200 focus:outline-none ${
                                    activeTab === 'individual'
                                        ? 'border-primary-500 text-primary-700 bg-white shadow-sm'
                                        : 'border-transparent text-gray-500 hover:text-primary-600 hover:border-primary-300 bg-primary-50'
                                }`}
                                role="tab"
                                aria-selected={activeTab === 'individual'}
                                aria-controls="individual-panel"
                            >
                                <i className="fas fa-utensils mr-2" aria-hidden="true"></i>
                                Individual listing
                            </button>
                            <button
                                type="button"
                                id="bulk-tab"
                                onClick={() => setActiveTab('bulk')}
                                className={`px-4 sm:px-6 py-4 text-center w-1/2 font-semibold text-sm sm:text-base border-b-2 transition-colors duration-200 focus:outline-none ${
                                    activeTab === 'bulk'
                                        ? 'border-primary-500 text-primary-700 bg-white shadow-sm'
                                        : 'border-transparent text-gray-500 hover:text-primary-600 hover:border-primary-300 bg-primary-50'
                                }`}
                                role="tab"
                                aria-selected={activeTab === 'bulk'}
                                aria-controls="bulk-panel"
                            >
                                <i className="fas fa-file-csv mr-2" aria-hidden="true"></i>
                                Bulk CSV
                            </button>
                        </nav>
                    </div>
                )}

                <div className="p-8 md:p-10">
                    <div
                        role="tabpanel"
                        id="individual-panel"
                        aria-labelledby="individual-tab"
                        hidden={!isEditing && !requestPrefill && activeTab !== 'individual'}
                    >
                        {(isEditing || requestPrefill || activeTab === 'individual') && (
                            <FoodForm
                                key={
                                    searchParams.get('edit')
                                    || [
                                        searchParams.get('request'),
                                        searchParams.get('community_id'),
                                        searchParams.get('fulfilling_request_id'),
                                    ].filter(Boolean).join('|')
                                    || 'new-share'
                                }
                                initialData={formInitialData}
                                onSubmit={handleSubmit}
                                loading={loading}
                            />
                        )}
                    </div>

                    {!isEditing && !requestPrefill && (
                        <div
                            role="tabpanel"
                            id="bulk-panel"
                            aria-labelledby="bulk-tab"
                            hidden={activeTab !== 'bulk'}
                        >
                            {activeTab === 'bulk' && (
                                <ShareBulkCsvPanel
                                    userId={authUser?.id}
                                    preferredCommunityId={authUser?.community_id || null}
                                    preferredLocation={preferredBulkLocation}
                                    lockToUserCommunity={!isAdmin && !!authUser?.community_id}
                                    onSuccess={handleBulkSuccess}
                                />
                            )}
                        </div>
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
