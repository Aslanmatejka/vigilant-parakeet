import React from 'react';
import PropTypes from 'prop-types';

function formatNumber(num) {
    if (num >= 1000) {
        return `${(num / 1000).toFixed(1)}k`;
    }
    return Math.round(num).toString();
}

function ProfileStats({
    impact = null,
    loading = false
}) {
    if (loading) {
        return (
            <div className="bg-gradient-to-r from-green-50 to-blue-50 rounded-2xl p-6 shadow-sm">
                <h2 className="text-2xl font-bold text-gray-900 mb-6 text-center">Your Impact</h2>
                <div
                    className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
                    role="status"
                    aria-busy="true"
                    aria-label="Loading impact statistics"
                >
                    {[1, 2, 3, 4].map((i) => (
                        <div key={i} className="bg-white p-6 rounded-xl shadow-sm animate-pulse">
                            <div className="h-8 bg-gray-200 rounded w-16 mb-2"></div>
                            <div className="h-4 bg-gray-200 rounded w-24"></div>
                        </div>
                    ))}
                    <div className="sr-only">Loading statistics...</div>
                </div>
            </div>
        );
    }

    if (!impact) {
        return null;
    }

    const statCards = [
        {
            value: impact.totalFoodShared,
            label: 'Total Food Shared',
            unit: 'lb',
            icon: 'fa-utensils',
            color: 'green',
            bgGradient: 'from-green-50 to-green-100',
            iconColor: 'text-green-600'
        },
        {
            value: impact.foodClaimed,
            label: 'Food Claimed',
            unit: 'lb',
            icon: 'fa-check-circle',
            color: 'blue',
            bgGradient: 'from-blue-50 to-blue-100',
            iconColor: 'text-blue-600'
        },
        {
            value: impact.livesImpacted,
            label: 'Lives Impacted',
            unit: '',
            icon: 'fa-heart',
            color: 'red',
            bgGradient: 'from-red-50 to-red-100',
            iconColor: 'text-red-600'
        },
        {
            value: impact.co2Reduced,
            label: 'CO₂ Reduced',
            unit: 'lb',
            icon: 'fa-leaf',
            color: 'emerald',
            bgGradient: 'from-emerald-50 to-emerald-100',
            iconColor: 'text-emerald-600'
        }
    ];

    const progressCards = [
        {
            label: 'Active Listings',
            value: impact.activeListings,
            total: impact.totalListings,
            icon: 'fa-list-check',
            color: 'green'
        },
        {
            label: 'Claimed Listings',
            value: impact.claimedListings,
            total: impact.totalListings,
            icon: 'fa-handshake',
            color: 'blue'
        },
        {
            label: 'Pending Approval',
            value: impact.pendingListings,
            total: impact.totalListings,
            icon: 'fa-clock',
            color: 'amber'
        }
    ];

    return (
        <div
            className="bg-gradient-to-r from-green-50 to-blue-50 rounded-2xl p-6 shadow-sm"
            role="region"
            aria-label="Your impact statistics"
        >
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-gray-900">Your Impact</h2>
                {impact.lastUpdated && (
                    <span className="inline-flex items-center px-3 py-1 bg-green-100 text-green-800 rounded-full text-xs font-semibold">
                        <span className="inline-block w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></span>
                        Live Updates
                    </span>
                )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                {statCards.map((item, index) => (
                    <div
                        key={index}
                        className={`bg-gradient-to-br ${item.bgGradient} p-6 rounded-xl shadow-md hover:shadow-lg transition-all duration-300 transform hover:-translate-y-1`}
                        role="status"
                        aria-label={item.label}
                    >
                        <div className="flex items-start justify-between mb-3">
                            <i className={`fas ${item.icon} text-3xl ${item.iconColor}`} aria-hidden="true"></i>
                        </div>
                        <div className="text-4xl font-extrabold text-gray-900 mb-1">
                            {formatNumber(item.value)}
                            {item.unit && (
                                <span className="text-xl ml-1 text-gray-600">{item.unit}</span>
                            )}
                        </div>
                        <div className="text-sm font-medium text-gray-700">
                            {item.label}
                        </div>
                    </div>
                ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {progressCards.map((item, index) => {
                    const percentage = item.total > 0 ? (item.value / item.total) * 100 : 0;
                    const colorClasses = {
                        green: 'bg-green-500',
                        blue: 'bg-blue-500',
                        amber: 'bg-amber-500'
                    };

                    return (
                        <div
                            key={index}
                            className="bg-white p-5 rounded-xl shadow-sm hover:shadow-md transition-shadow"
                        >
                            <div className="flex items-center justify-between mb-3">
                                <div className="flex items-center">
                                    <i className={`fas ${item.icon} text-xl text-${item.color}-600 mr-3`} aria-hidden="true"></i>
                                    <span className="text-sm font-semibold text-gray-700">{item.label}</span>
                                </div>
                                <span className="text-2xl font-bold text-gray-900">{item.value}</span>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                                <div
                                    className={`h-2.5 rounded-full ${colorClasses[item.color]} transition-all duration-700 ease-out`}
                                    style={{ width: `${Math.min(percentage, 100)}%` }}
                                    role="progressbar"
                                    aria-valuenow={percentage}
                                    aria-valuemin="0"
                                    aria-valuemax="100"
                                ></div>
                            </div>
                            <div className="text-xs text-gray-500 mt-2">
                                {item.value} of {item.total} total
                            </div>
                        </div>
                    );
                })}
            </div>

            {impact.lastUpdated && (
                <div className="text-center mt-4">
                    <p className="text-xs text-gray-600">
                        Last updated: {new Date(impact.lastUpdated).toLocaleTimeString()}
                    </p>
                </div>
            )}
        </div>
    );
}

ProfileStats.propTypes = {
    impact: PropTypes.shape({
        totalListings: PropTypes.number,
        activeListings: PropTypes.number,
        pendingListings: PropTypes.number,
        claimedListings: PropTypes.number,
        totalFoodShared: PropTypes.number,
        foodClaimed: PropTypes.number,
        peopleHelped: PropTypes.number,
        studentsHelped: PropTypes.number,
        staffHelped: PropTypes.number,
        livesImpacted: PropTypes.number,
        co2Reduced: PropTypes.number,
        lastUpdated: PropTypes.string
    }),
    loading: PropTypes.bool
};

export default ProfileStats;
