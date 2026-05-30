import React from 'react';
import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';

function formatNumber(num) {
    if (!num) return '0';
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
            <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <div className="mb-6">
                    <h2 className="text-xl sm:text-2xl font-bold text-gray-900">Your Impact</h2>
                    <p className="text-sm text-gray-500">A snapshot of the difference you're making.</p>
                </div>
                <div
                    className="grid grid-cols-1 sm:grid-cols-2 gap-3"
                    role="status"
                    aria-busy="true"
                    aria-label="Loading impact statistics"
                >
                    {[1, 2].map((i) => (
                        <div key={i} className="bg-gray-50 p-5 rounded-xl animate-pulse">
                            <div className="h-10 w-10 bg-gray-200 rounded-full mb-3"></div>
                            <div className="h-7 bg-gray-200 rounded w-20 mb-2"></div>
                            <div className="h-3 bg-gray-200 rounded w-24"></div>
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

    const heroStats = [
        {
            label: 'Food shared',
            value: impact.totalFoodShared || 0,
            unit: 'lb',
            icon: 'fa-utensils',
            bg: 'bg-emerald-50',
            iconColor: 'text-emerald-600'
        },
        {
            label: 'Food claimed',
            value: impact.foodClaimed || 0,
            unit: 'lb',
            icon: 'fa-hands-helping',
            bg: 'bg-blue-50',
            iconColor: 'text-[#2CABE3]'
        }
    ];

    const progressCards = [
        {
            label: 'Active listings',
            value: impact.activeListings || 0,
            total: impact.totalListings || 0,
            icon: 'fa-list-check',
            barColor: 'bg-emerald-500',
            iconColor: 'text-emerald-600'
        },
        {
            label: 'Claimed',
            value: impact.claimedListings || 0,
            total: impact.totalListings || 0,
            icon: 'fa-handshake',
            barColor: 'bg-[#2CABE3]',
            iconColor: 'text-[#2CABE3]'
        },
        {
            label: 'Pending approval',
            value: impact.pendingListings || 0,
            total: impact.totalListings || 0,
            icon: 'fa-clock',
            barColor: 'bg-amber-500',
            iconColor: 'text-amber-600'
        }
    ];

    const hasAnyActivity =
        (impact.totalListings || 0) > 0 ||
        (impact.totalFoodShared || 0) > 0 ||
        (impact.foodClaimed || 0) > 0;

    return (
        <div
            className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm"
            role="region"
            aria-label="Your impact statistics"
        >
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
                <div>
                    <h2 className="text-xl sm:text-2xl font-bold text-gray-900">Your Impact</h2>
                    <p className="text-sm text-gray-500">A snapshot of the difference you're making.</p>
                </div>
                {impact.lastUpdated && (
                    <span className="inline-flex items-center px-2.5 py-1 bg-emerald-50 text-emerald-700 rounded-full text-xs font-semibold">
                        <span className="inline-block w-2 h-2 bg-emerald-500 rounded-full mr-1.5 animate-pulse"></span>
                        Live
                    </span>
                )}
            </div>

            {!hasAnyActivity ? (
                <div className="bg-gradient-to-br from-[#2CABE3]/5 to-emerald-50 rounded-xl p-8 text-center">
                    <div className="h-14 w-14 mx-auto rounded-full bg-white shadow-sm flex items-center justify-center mb-3">
                        <i className="fas fa-seedling text-2xl text-emerald-500"></i>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-1">Your story starts here</h3>
                    <p className="text-sm text-gray-600 mb-4 max-w-md mx-auto">
                        Share or claim food on DoGoods to start tracking your personal impact on the community.
                    </p>
                    <div className="flex flex-wrap gap-2 justify-center">
                        <Link
                            to="/share"
                            className="inline-flex items-center px-4 py-2 rounded-lg bg-[#2CABE3] text-white text-sm font-medium hover:opacity-90"
                        >
                            <i className="fas fa-plus mr-2"></i>
                            Share food
                        </Link>
                        <Link
                            to="/find"
                            className="inline-flex items-center px-4 py-2 rounded-lg bg-white border border-gray-200 text-gray-700 text-sm font-medium hover:bg-gray-50"
                        >
                            <i className="fas fa-search mr-2"></i>
                            Find food
                        </Link>
                    </div>
                </div>
            ) : (
                <>
                    {/* Hero stat tiles */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
                        {heroStats.map((item) => (
                            <div
                                key={item.label}
                                className={`${item.bg} rounded-xl p-4 sm:p-5 hover:shadow-md transition-shadow`}
                                role="status"
                                aria-label={item.label}
                            >
                                <div className={`h-9 w-9 rounded-full bg-white flex items-center justify-center mb-3 ${item.iconColor}`}>
                                    <i className={`fas ${item.icon}`}></i>
                                </div>
                                <div className="text-2xl sm:text-3xl font-extrabold text-gray-900 leading-tight">
                                    {formatNumber(item.value)}
                                    {item.unit && (
                                        <span className="text-sm ml-1 font-medium text-gray-500">{item.unit}</span>
                                    )}
                                </div>
                                <div className="text-xs sm:text-sm font-medium text-gray-600 mt-1">
                                    {item.label}
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Listings overview */}
                    {(impact.totalListings || 0) > 0 && (
                        <div>
                            <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
                                Listings overview
                            </h3>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                {progressCards.map((item) => {
                                    const percentage = item.total > 0 ? (item.value / item.total) * 100 : 0;
                                    return (
                                        <div
                                            key={item.label}
                                            className="bg-gray-50 p-4 rounded-xl"
                                        >
                                            <div className="flex items-center justify-between mb-2">
                                                <div className="flex items-center">
                                                    <i className={`fas ${item.icon} ${item.iconColor} mr-2`} aria-hidden="true"></i>
                                                    <span className="text-sm font-medium text-gray-700">{item.label}</span>
                                                </div>
                                                <span className="text-lg font-bold text-gray-900">{item.value}</span>
                                            </div>
                                            <div className="w-full bg-white rounded-full h-2 overflow-hidden">
                                                <div
                                                    className={`h-2 rounded-full ${item.barColor} transition-all duration-700 ease-out`}
                                                    style={{ width: `${Math.min(percentage, 100)}%` }}
                                                    role="progressbar"
                                                    aria-valuenow={percentage}
                                                    aria-valuemin="0"
                                                    aria-valuemax="100"
                                                ></div>
                                            </div>
                                            <div className="text-[11px] text-gray-500 mt-1.5">
                                                {item.value} of {item.total} total
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </>
            )}

            {impact.lastUpdated && hasAnyActivity && (
                <p className="text-xs text-gray-400 text-right mt-4">
                    Updated {new Date(impact.lastUpdated).toLocaleTimeString()}
                </p>
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
