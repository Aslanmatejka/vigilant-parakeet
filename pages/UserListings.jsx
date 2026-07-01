import React from "react";
import Button from "../components/common/Button";
import Card from "../components/common/Card";
import FoodForm from "../components/food/FoodForm";
import { useAuth, useFoodListings } from "../utils/hooks/useSupabase";

const formatDate = (date) => {
    if (!date) return '';
    return new Date(date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
};

function UserListings() {
    const { user: authUser, isAuthenticated, loading: authLoading } = useAuth();
    const { listings, loading, error, createListing, updateListing, deleteListing } = useFoodListings({ user_id: authUser?.id });
    
    const [activeTab, setActiveTab] = React.useState('individual');
    const [initialData, setInitialData] = React.useState(null);
    const [isEditing, setIsEditing] = React.useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(null);
    const [successMessage, setSuccessMessage] = React.useState(null);

    // Auth redirect is handled by ProtectedRoute wrapper in app.jsx
    // No need for manual redirect here

    const handleSubmit = async (formData) => {
        try {
            const listingData = {
                ...formData,
                user_id: authUser.id,
            };

            if (isEditing && initialData) {
                await updateListing(initialData.id, listingData);
                setSuccessMessage('Listing updated successfully!');
            } else {
                await createListing(listingData);
                setSuccessMessage('Listing created successfully!');
            }

            setActiveTab('listings');
            setInitialData(null);
            setIsEditing(false);
        } catch (error) {
            console.error('Create/update listing error:', error);
        }
    };

    const handleEdit = (listing) => {
        setInitialData(listing);
        setIsEditing(true);
        setActiveTab('individual');
    };

    const handleDelete = async (listing) => {
        try {
            await deleteListing(listing.id);
            setSuccessMessage('Listing deleted successfully');
            setShowDeleteConfirm(null);
        } catch (error) {
            console.error('Delete listing error:', error);
        }
    };

    const downloadTemplate = () => {
        try {
            const csvContent = "title,description,quantity,unit,expiry_date,category\nOrganic Apples,Fresh locally grown apples,5,kg,2024-12-31,produce\nSourdough Bread,Freshly baked this morning,2,loaves,2024-12-25,bakery";
            const blob = new Blob([csvContent], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'food-listing-template.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Download template error:', error);
        }
    };

    // Show loading while checking authentication
    if (authLoading) {
        return (
            <div className="max-w-7xl mx-auto py-8 px-4" role="status" aria-busy="true">
                <div className="flex flex-col items-center justify-center min-h-[400px]">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mb-4"></div>
                    <p className="text-gray-600">Checking authentication...</p>
                </div>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="max-w-7xl mx-auto py-8 px-4" role="status" aria-busy="true">
                <div className="sr-only">Loading listings...</div>
                <div className="animate-pulse space-y-8">
                    <div className="h-12 bg-gray-200 rounded w-1/4"></div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="h-64 bg-gray-200 rounded-lg"></div>
                        ))}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
            {/* Hero */}
            <header className="relative overflow-hidden">
                <div className="absolute inset-0 -z-10" aria-hidden="true">
                    <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
                    <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
                </div>
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
                    <div className="text-center">
                        <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
                            <i className="fas fa-list-check mr-2" aria-hidden="true"></i>
                            Your Donations
                        </span>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
                            My{" "}
                            <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                                Listings
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
                            Manage your food listings and track their status.
                        </p>
                    </div>
                </div>
            </header>

            <div className="max-w-7xl mx-auto px-4 pb-8">

            {error && (
                <div className="mb-4 p-4 rounded-lg bg-red-50 text-red-800" role="alert">
                    <i className="fas fa-exclamation-circle mr-2" aria-hidden="true"></i>
                    {error}
                </div>
            )}
            {successMessage && (
                <div className="mb-4 p-4 rounded-lg bg-primary-50 text-primary-800" role="alert">
                    <i className="fas fa-check-circle mr-2" aria-hidden="true"></i>
                    {successMessage}
                </div>
            )}

            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="border-b border-gray-200">
                    <nav className="flex" role="tablist" aria-label="Listing options">
                        <button
                            onClick={() => setActiveTab('individual')}
                            aria-controls="individual-panel"
                            id="individual-tab"
                            className={`px-4 py-4 text-center w-1/2 font-medium text-sm border-b-2 ${
                                activeTab === 'individual'
                                    ? 'border-primary-500 text-primary-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            }`}
                        >
                            <i className="fas fa-plus mr-2" aria-hidden="true"></i>
                            Add Individual Listing
                        </button>
                        <button
                            onClick={() => setActiveTab('listings')}
                            aria-controls="listings-panel"
                            id="listings-tab"
                            className={`px-4 py-4 text-center w-1/2 font-medium text-sm border-b-2 ${
                                activeTab === 'listings'
                                    ? 'border-primary-500 text-primary-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                            }`}
                        >
                            <i className="fas fa-list mr-2" aria-hidden="true"></i>
                            My Listings
                        </button>
                    </nav>
                </div>

                <div className="p-6">
                    <div
                        role="tabpanel"
                        id={`${activeTab}-panel`}
                        aria-labelledby={`${activeTab}-tab`}
                    >
                        {activeTab === 'listings' && (
                            <div className="space-y-6">
                                {(!listings || listings.length === 0) ? (
                                    <div className="text-center py-12" role="status">
                                        <i className="fas fa-box-open text-gray-400 text-4xl mb-4" aria-hidden="true"></i>
                                        <p className="text-gray-600 mb-4">You haven't created any listings yet</p>
                                        <Button
                                            variant="primary"
                                            onClick={() => setActiveTab('individual')}
                                            aria-label="Create your first listing"
                                        >
                                            Create Your First Listing
                                        </Button>
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                        {listings.map(listing => (
                                            <Card key={listing.id} className="overflow-hidden">
                                                {listing.image_url && (
                                                    <img
                                                        src={listing.image_url}
                                                        alt={listing.title}
                                                        className="w-full h-48 object-cover"
                                                    />
                                                )}
                                                <div className="p-4">
                                                    <div className="flex justify-between items-start mb-2">
                                                        <h3 className="text-lg font-semibold">{listing.title}</h3>
                                                        <span className={`px-2 py-1 text-xs rounded-full ${
                                                            listing.status === 'active' 
                                                                ? 'bg-primary-100 text-primary-800' 
                                                                : 'bg-gray-100 text-gray-800'
                                                        }`}>
                                                            {listing.status}
                                                        </span>
                                                    </div>
                                                    <p className="text-gray-600 text-sm mb-4">{listing.description}</p>
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-sm text-gray-500">
                                                            {formatDate(listing.created_at)}
                                                        </span>
                                                        <div className="flex space-x-2">
                                                            <Button
                                                                variant="secondary"
                                                                size="sm"
                                                                onClick={() => handleEdit(listing)}
                                                                aria-label={`Edit ${listing.title}`}
                                                            >
                                                                Edit
                                                            </Button>
                                                            <Button
                                                                variant="danger"
                                                                size="sm"
                                                                onClick={() => setShowDeleteConfirm(listing.id)}
                                                                aria-label={`Delete ${listing.title}`}
                                                            >
                                                                Delete
                                                            </Button>
                                                        </div>
                                                    </div>
                                                </div>
                                                {showDeleteConfirm === listing.id && (
                                                    <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
                                                        <div className="bg-white rounded-lg p-6 max-w-sm w-full" role="alertdialog" aria-labelledby="delete-dialog-title">
                                                            <h4 id="delete-dialog-title" className="text-lg font-semibold mb-4">Confirm Delete</h4>
                                                            <p className="text-gray-600 mb-6">Are you sure you want to delete this listing? This action cannot be undone.</p>
                                                            <div className="flex justify-end space-x-4">
                                                                <Button
                                                                    variant="secondary"
                                                                    onClick={() => setShowDeleteConfirm(null)}
                                                                >
                                                                    Cancel
                                                                </Button>
                                                                <Button
                                                                    variant="danger"
                                                                    onClick={() => handleDelete(listing)}
                                                                >
                                                                    Delete
                                                                </Button>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                            </Card>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                        {activeTab === 'individual' && (
                            <FoodForm
                                initialData={initialData ? (() => { const { location, listing_type, defaultType, ...rest } = initialData; return rest; })() : null}
                                onSubmit={handleSubmit}
                                loading={loading}
                            />
                        )}
                    </div>
                </div>
            </div>
            </div>
        </div>
    );
}

export default UserListings;
