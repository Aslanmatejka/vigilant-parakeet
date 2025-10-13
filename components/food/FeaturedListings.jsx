import React from 'react';
import PropTypes from 'prop-types';
import FoodCard from './FoodCard';
import { reportError } from '../../utils/helpers';

function FeaturedListings({ 
    listings = [], 
    onClaim, 

    loading = false 
}) {
    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6" aria-busy="true">
                {[1, 2, 3].map((i) => (
                    <div key={i} className="animate-pulse">
                        <div className="bg-gray-200 h-64 rounded-lg"></div>
                        <div className="mt-4 space-y-3">
                            <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    if (!listings.length) {
        return (
            <div 
                className="text-center py-8 bg-gray-50 rounded-lg"
                role="status"
                aria-label="No featured listings available"
            >
                <i className="fas fa-box-open text-gray-400 text-4xl mb-3"></i>
                <p className="text-gray-500">No featured listings available at the moment</p>
            </div>
        );
    }

    return (
        <div 
            className="grid grid-cols-1 md:grid-cols-3 gap-6"
            role="feed"
            aria-label="Featured food listings"
        >
            {listings.map((listing) => (
                <FoodCard
                    key={listing.id}
                    food={listing}
                    onClaim={onClaim}
                    onTrade={onTrade}
                    showReturnButton={true}
                />
            ))}
        </div>
    );
}

FeaturedListings.propTypes = {
    listings: PropTypes.arrayOf(
        PropTypes.shape({
            id: PropTypes.string.isRequired,
            // Additional food item properties will be validated by FoodCard component
        })
    ),
    onClaim: PropTypes.func,
    onTrade: PropTypes.func,
    loading: PropTypes.bool
};

export default FeaturedListings;
