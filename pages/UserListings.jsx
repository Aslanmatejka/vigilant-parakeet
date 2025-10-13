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
    const { user: authUser, isAuthenticated } = useAuth();
    const { listings, loading, error, createListing, updateListing, deleteListing } = useFoodListings({ user_id: authUser?.id });
    
    const [activeTab, setActiveTab] = React.useState('individual');
    const [initialData, setInitialData] = React.useState(null);
    const [isEditing, setIsEditing] = React.useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(null);
    const [successMessage, setSuccessMessage] = React.useState(null);

    React.useEffect(() => {
        if (!isAuthenticated) {
            window.location.href = '/login';
            return;
        }
    }, [isAuthenticated]);

    const handleSubmit = async (formData) => {
        try {
            const listingData = {
                ...formData,
                user_id: authUser.id,
                status: 'active'
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
        } catch (error) {
            console.error('Download template error:', error);
        }
    };

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
        <div className="max-w-7xl mx-auto py-8 px-4">
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-gray-900 mb-4">My Listings</h1>
                <p className="text-gray-600">Manage your food listings and track their status</p>
            </div>

            {error && (
                <div className="mb-4 p-4 rounded-lg bg-red-50 text-red-800" role="alert">
                    <i className="fas fa-exclamation-circle mr-2" aria-hidden="true"></i>
                    {error}
                </div>
            )}
            {successMessage && (
                <div className="mb-4 p-4 rounded-lg bg-green-50 text-green-800" role="alert">
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
                                    ? 'border-green-500 text-green-600'
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
                                    ? 'border-green-500 text-green-600'
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
                                                                ? 'bg-green-100 text-green-800' 
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
    );
}

export default UserListings;
