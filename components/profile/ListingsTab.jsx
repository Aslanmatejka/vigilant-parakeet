import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import Card from '../common/Card';
import Input from '../common/Input';
import Button from '../common/Button';
import { formatDate } from '../../utils/helpers';
import { useCommunityRole } from '../../utils/hooks/useCommunityRole';

function ListingsTab({ 
    listings = [], 
    onEdit, 
    onDelete,
    loading = false,
    initialFilter = 'active',
}) {
    const isDonor = useCommunityRole() === 'donor';
    const [activeTab, setActiveTab] = useState(
        initialFilter === 'requests' && isDonor ? 'active' : initialFilter
    );
    const [searchTerm, setSearchTerm] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        if (isDonor && activeTab === 'requests') {
            setActiveTab('active');
        }
    }, [isDonor, activeTab]);

    const filteredListings = listings.filter(listing => {
        const matchesSearch = listing.title.toLowerCase().includes(searchTerm.toLowerCase());
        const isRequest = String(listing.listing_type || '').toLowerCase() === 'request';
        if (activeTab === 'requests') {
            return matchesSearch && isRequest;
        }
        // Live tab: approved + active. Pending tab: awaiting admin review.
        const matchesStatus = activeTab === 'all'
            || (activeTab === 'active'
                ? listing.status === 'active' || listing.status === 'approved'
                : activeTab === 'pending'
                    ? listing.status === 'pending'
                    : activeTab === 'completed'
                        ? listing.status === 'completed' || listing.status === 'claimed'
                        : listing.status === activeTab);
        // Donations-only for status tabs so requests don't clutter Active/Pending
        // (they have their own Requests tab). "all" still shows everything.
        if (activeTab !== 'all' && isRequest) return false;
        return matchesSearch && matchesStatus;
    });

    const handleImageError = (e) => {
        e.target.onerror = null;
        e.target.src = 'data:image/svg+xml,' + encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300"><rect fill="#e5e7eb" width="400" height="300"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#9ca3af" font-family="sans-serif" font-size="18">No photo</text></svg>'
        );
    };

    if (loading) {
        return (
            <div 
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                role="status"
                aria-busy="true"
                aria-label="Loading listings"
            >
                {[1, 2, 3].map((i) => (
                    <div key={i} className="animate-pulse">
                        <div className="bg-gray-200 h-48 rounded-lg"></div>
                        <div className="mt-4 space-y-3">
                            <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div 
                    className="flex space-x-2" 
                    role="tablist" 
                    aria-label="Filter listings by status"
                >
                    <button
                        role="tab"
                        aria-selected={activeTab === 'active'}
                        aria-controls="active-listings"
                        onClick={() => setActiveTab('active')}
                        className={`px-4 py-2 rounded-lg ${
                            activeTab === 'active' 
                                ? 'bg-primary-600 text-white' 
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                    >
                        Active
                    </button>
                    <button
                        role="tab"
                        aria-selected={activeTab === 'pending'}
                        aria-controls="pending-listings"
                        onClick={() => setActiveTab('pending')}
                        className={`px-4 py-2 rounded-lg ${
                            activeTab === 'pending' 
                                ? 'bg-amber-500 text-white' 
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                    >
                        Pending
                    </button>
                    {!isDonor && (
                    <button
                        role="tab"
                        aria-selected={activeTab === 'requests'}
                        aria-controls="requests-listings"
                        onClick={() => setActiveTab('requests')}
                        className={`px-4 py-2 rounded-lg ${
                            activeTab === 'requests'
                                ? 'bg-emerald-600 text-white'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                    >
                        Requests
                    </button>
                    )}
                    <button
                        role="tab"
                        aria-selected={activeTab === 'completed'}
                        aria-controls="completed-listings"
                        onClick={() => setActiveTab('completed')}
                        className={`px-4 py-2 rounded-lg ${
                            activeTab === 'completed' 
                                ? 'bg-primary-600 text-white' 
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                    >
                        Completed
                    </button>
                    <button
                        role="tab"
                        aria-selected={activeTab === 'all'}
                        aria-controls="all-listings"
                        onClick={() => setActiveTab('all')}
                        className={`px-4 py-2 rounded-lg ${
                            activeTab === 'all' 
                                ? 'bg-primary-600 text-white' 
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                    >
                        All
                    </button>
                </div>
                <Input
                    placeholder="Search listings..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    icon={<i className="fas fa-search" aria-hidden="true"></i>}
                    className="md:w-64"
                    aria-label="Search listings"
                />
            </div>

            <div 
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                role="tabpanel"
                id={`${activeTab}-listings`}
                aria-label={`${activeTab} listings`}
            >
                {filteredListings.map(listing => {
                    const isRequest = String(listing.listing_type || '').toLowerCase() === 'request';
                    return (
                    <Card key={listing.id} className="overflow-hidden">
                        {!isRequest && (
                        <div className="aspect-w-16 aspect-h-9">
                            <img 
                                src={listing.image_url || '/images/placeholder-food.png'} 
                                alt={listing.title}
                                className="w-full h-48 object-cover"
                                onError={handleImageError}
                            />
                        </div>
                        )}
                        {isRequest && (
                        <div className="h-28 bg-emerald-50 border-b border-emerald-100 flex items-center justify-center text-emerald-700 gap-2">
                            <i className="fas fa-clipboard-list text-2xl" aria-hidden="true" />
                            <span className="text-sm font-semibold">Food request</span>
                        </div>
                        )}
                        <div className="p-4">
                            <div className="flex justify-between items-start mb-2 gap-2">
                                <div className="min-w-0">
                                    <h3 className="text-lg font-semibold">{listing.title}</h3>
                                    {isRequest && (
                                        <span className="inline-flex mt-1 px-2 py-0.5 text-[11px] font-semibold rounded-full bg-emerald-50 text-emerald-800">
                                            Food request
                                        </span>
                                    )}
                                </div>
                                <span 
                                    className={`px-2 py-1 text-xs rounded-full shrink-0 ${
                                        listing.status === 'active' || listing.status === 'approved'
                                            ? 'bg-primary-100 text-primary-800'
                                            : listing.status === 'pending'
                                                ? 'bg-amber-100 text-amber-800'
                                                : 'bg-gray-100 text-gray-800'
                                    }`}
                                    role="status"
                                >
                                    {listing.status === 'pending' ? 'Awaiting approval' : listing.status}
                                </span>
                            </div>
                            <p className="text-gray-600 text-sm mb-4">{listing.description}</p>
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-500">
                                    {listing.expiry_date ? formatDate(listing.expiry_date) : 'No expiry date'}
                                </span>
                                <div className="flex space-x-2">
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={() => onEdit(listing)}
                                        aria-label={`Edit ${listing.title}`}
                                    >
                                        <i className="fas fa-edit mr-1" aria-hidden="true"></i>
                                        Edit
                                    </Button>
                                    <Button
                                        variant="danger"
                                        size="sm"
                                        onClick={() => onDelete(listing)}
                                        aria-label={`Delete ${listing.title}`}
                                    >
                                        <i className="fas fa-trash mr-1" aria-hidden="true"></i>
                                        Delete
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </Card>
                    );
                })}
            </div>

            {filteredListings.length === 0 && (
                <div 
                    className="text-center py-12"
                    role="status"
                    aria-label="No listings found"
                >
                    <i className="fas fa-box-open text-gray-400 text-4xl mb-4" aria-hidden="true"></i>
                    <p className="text-gray-600">
                        {activeTab === 'requests'
                            ? 'No food requests yet'
                            : 'No listings found'}
                    </p>
                    {activeTab === 'requests' && !isDonor && (
                        <Button
                            variant="primary"
                            className="mt-4"
                            onClick={() => navigate('/request')}
                            aria-label="Request food"
                        >
                            Request Food
                        </Button>
                    )}
                    {activeTab === 'requests' && isDonor && (
                        <Button
                            variant="primary"
                            className="mt-4"
                            onClick={() => navigate('/community-requests')}
                            aria-label="View community requests"
                        >
                            Community Requests
                        </Button>
                    )}
                </div>
            )}
        </div>
    );
}

ListingsTab.propTypes = {
    listings: PropTypes.arrayOf(
        PropTypes.shape({
            id: PropTypes.string.isRequired,
            title: PropTypes.string.isRequired,
            description: PropTypes.string.isRequired,
            image: PropTypes.string.isRequired,
            status: PropTypes.oneOf([
                'pending', 'approved', 'active', 'claimed', 'completed', 'expired', 'declined', 'cancelled'
            ]).isRequired,
            createdAt: PropTypes.string.isRequired
        })
    ),
    onEdit: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
    loading: PropTypes.bool,
    initialFilter: PropTypes.oneOf(['active', 'pending', 'completed', 'all']),
};

export default ListingsTab;
