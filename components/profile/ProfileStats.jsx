import React from 'react';
import PropTypes from 'prop-types';

function formatNumber(num) {
    if (num >= 1000) {
        return `${(num / 1000).toFixed(1)}k`;
    }
    return num.toString();
}

function ProfileStats({ 
    stats = null,
    loading = false 
}) {
    if (loading) {
        return (
            <div 
                className="grid grid-cols-2 md:grid-cols-4 gap-4"
                role="status"
                aria-busy="true"
                aria-label="Loading profile statistics"
            >
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="bg-white p-4 rounded-lg shadow-sm animate-pulse">
                        <div className="h-8 bg-gray-200 rounded w-16 mb-2"></div>
                        <div className="h-4 bg-gray-200 rounded w-24"></div>
                    </div>
                ))}
                <div className="sr-only">Loading statistics...</div>
            </div>
        );
    }

    if (!stats) {
        return null;
    }

    const statItems = [
        { value: stats.donations, label: 'Donations Made', unit: '' },
        { value: stats.foodSaved, label: 'Food Saved', unit: 'kg' },
        { value: stats.impact, label: 'CO2 Reduced', unit: 'kg' }
    ];

    return (
        <div 
            className="grid grid-cols-2 md:grid-cols-4 gap-4"
            role="region"
            aria-label="Profile statistics"
        >
            {statItems.map((item, index) => (
                <div 
                    key={index} 
                    className="bg-white p-4 rounded-lg shadow-sm"
                    role="status"
                    aria-label={item.label}
                >
                    <div className="text-3xl font-bold text-green-600">
                        {formatNumber(item.value)}
                        {item.unit && (
                            <span className="text-xl ml-1">{item.unit}</span>
                        )}
                    </div>
                    <div 
                        className="text-sm text-gray-500"
                        aria-label={`${item.label}: ${item.value}${item.unit}`}
                    >
                        {item.label}
                    </div>
                </div>
            ))}
        </div>
    );
}

ProfileStats.propTypes = {
    stats: PropTypes.shape({
        donations: PropTypes.number.isRequired,
        foodSaved: PropTypes.number.isRequired,
        impact: PropTypes.number.isRequired
    }),
    loading: PropTypes.bool
};

export default ProfileStats;
