import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import Card from '../common/Card';
import Input from '../common/Input';
import Button from '../common/Button';
import { formatDate } from '../../utils/helpers';

function ListingsTab({ 
    listings = [], 
    onEdit, 
    onDelete,
    loading = false 
}) {
    const [activeTab, setActiveTab] = useState('active');
    const [searchTerm, setSearchTerm] = useState('');
    const navigate = useNavigate();

    const filteredListings = listings.filter(listing => {
        const matchesSearch = listing.title.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesStatus = activeTab === 'all' || listing.status === activeTab;
        return matchesSearch && matchesStatus;
    });

    const handleImageError = (e) => {
        e.target.src = '/images/placeholder-food.png'; // Fallback image
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
                                ? 'bg-green-600 text-white' 
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                    >
                        Active
                    </button>
                    <button
                        role="tab"
                        aria-selected={activeTab === 'completed'}
                        aria-controls="completed-listings"
                        onClick={() => setActiveTab('completed')}
                        className={`px-4 py-2 rounded-lg ${
                            activeTab === 'completed' 
                                ? 'bg-green-600 text-white' 
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
                                ? 'bg-green-600 text-white' 
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
                {filteredListings.map(listing => (
                    <Card key={listing.id} className="overflow-hidden">
                        <div className="aspect-w-16 aspect-h-9">
                            <img 
                                src={listing.image_url || '/images/placeholder-food.png'} 
                                alt={listing.title}
                                className="w-full h-48 object-cover"
                                onError={handleImageError}
                            />
                        </div>
                        <div className="p-4">
                            <div className="flex justify-between items-start mb-2">
                                <h3 className="text-lg font-semibold">{listing.title}</h3>
                                <span 
                                    className={`px-2 py-1 text-xs rounded-full ${
                                        listing.status === 'active' 
                                            ? 'bg-green-100 text-green-800' 
                                            : 'bg-gray-100 text-gray-800'
                                    }`}
                                    role="status"
                                >
                                    {listing.status}
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
                ))}
            </div>

            {filteredListings.length === 0 && (
                <div 
                    className="text-center py-12"
                    role="status"
                    aria-label="No listings found"
                >
                    <i className="fas fa-box-open text-gray-400 text-4xl mb-4" aria-hidden="true"></i>
                    <p className="text-gray-600">No listings found</p>
                    <Button
                        variant="primary"
                        className="mt-4"
                        onClick={() => navigate('/share')}
                        aria-label="Create new listing"
                    >
                        Create Listing
                    </Button>
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
            status: PropTypes.oneOf(['active', 'completed']).isRequired,
            createdAt: PropTypes.string.isRequired
        })
    ),
    onEdit: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
    loading: PropTypes.bool
};

export default ListingsTab;
