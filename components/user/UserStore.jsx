import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import { Button } from '../common/Button';
import { FoodCard } from '../food/FoodCard';
import { reportError } from '../../utils/helpers';


// Tab configuration
const TABS = [
    { id: 'active', label: 'Active', status: 'available' },
    { id: 'completed', label: 'Completed', status: 'completed' },
    { id: 'expired', label: 'Expired', status: 'expired' }
];

function UserStore({
    
    listings,
    onEdit,
    onDelete,
    loading = false,
    error = null
}) {
    const navigate = useNavigate();
    const [activeTab, setActiveTab] = useState('active');

    const filteredListings = listings?.filter(listing => {
        const tab = TABS.find(tab => tab.id === activeTab);
        return listing.status === tab?.status;
    });

    const handleNewListing = () => {
                    navigate('/share');
    };

    const handleRetry = () => {
        window.location.reload();
    };

    return (
        <div 
            data-name="user-store" 
            className="bg-white rounded-lg shadow-sm"
            role="region"
            aria-label="User Store"
        >
            <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-2xl font-bold text-gray-900">My Store</h2>
                    <Button
                        variant="primary"
                        onClick={handleNewListing}
                        aria-label="Create new listing"
                    >
                        <i className="fas fa-plus" aria-hidden="true"></i>
                        New Listing
                    </Button>
                </div>

                <div className="border-b mb-6">
                    <nav className="flex space-x-8" role="tablist" aria-label="Store listings">
                        {TABS.map((tab) => (
                            <button
                                key={tab.id}
                                role="tab"
                                aria-selected={activeTab === tab.id}
                                aria-controls={`${tab.id}-panel`}
                                className={`
                                    py-4 px-1 border-b-2 font-medium text-sm
                                    ${activeTab === tab.id ?
                                        'border-green-500 text-green-600' :
                                        'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                    }
                                `}
                                onClick={() => setActiveTab(tab.id)}
                            >
                                {tab.label}
                            </button>
                        ))}
                    </nav>
                </div>

                {loading ? (
                    <div className="space-y-4" role="status" aria-label="Loading listings">
                        {[1, 2, 3].map((i) => (
                            <div
                                key={i}
                                className="animate-pulse bg-gray-200 rounded-lg h-48"
                                aria-hidden="true"
                            />
                        ))}
                    </div>
                ) : error ? (
                    <div className="text-center py-8" role="alert">
                        <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4" aria-hidden="true"></i>
                        <p className="text-gray-600">{error}</p>
                        <Button
                            variant="secondary"
                            className="mt-4"
                            onClick={handleRetry}
                        >
                            Try Again
                        </Button>
                    </div>
                ) : !filteredListings?.length ? (
                    <div className="text-center py-8" role="status">
                        <i className="fas fa-store text-gray-400 text-4xl mb-4" aria-hidden="true"></i>
                        <p className="text-gray-600">No {activeTab} listings found</p>
                    </div>
                ) : (
                    <div 
                        id={`${activeTab}-panel`}
                        role="tabpanel"
                        aria-labelledby={`${activeTab}-tab`}
                        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                    >
                        {filteredListings.map((listing) => (
                            <FoodCard
                                key={listing.objectId}
                                food={listing}
                                footer={
                                    <div className="flex justify-end space-x-2">
                                        <Button
                                            variant="secondary"
                                            size="sm"
                                            onClick={() => onEdit(listing)}
                                            aria-label={`Edit ${listing.title}`}
                                        >
                                            <i className="fas fa-edit" aria-hidden="true"></i>
                                            Edit
                                        </Button>
                                        <Button
                                            variant="danger"
                                            size="sm"
                                            onClick={() => onDelete(listing)}
                                            aria-label={`Delete ${listing.title}`}
                                        >
                                            <i className="fas fa-trash" aria-hidden="true"></i>
                                            Delete
                                        </Button>
                                    </div>
                                }
                            />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

UserStore.propTypes = {
    user: PropTypes.shape({
        id: PropTypes.string.isRequired,
        name: PropTypes.string.isRequired
    }).isRequired,
    listings: PropTypes.arrayOf(PropTypes.shape({
        objectId: PropTypes.string.isRequired,
        title: PropTypes.string.isRequired,
        status: PropTypes.oneOf(['available', 'completed', 'expired']).isRequired
    })),
    onEdit: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
    loading: PropTypes.bool,
    error: PropTypes.string
};

export default UserStore;
