import React from "react";
import { useNavigate } from "react-router-dom";
import Button from "../components/common/Button";
import Avatar from "../components/common/Avatar";
import Card from "../components/common/Card";
import { useAuth, useFoodListings, useNotifications } from "../utils/hooks/useSupabase";
import { useImpact } from "../utils/hooks/useImpact";

// Helper function for date formatting
const formatDate = (date) => {
    if (!date) return '';
    return new Date(date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
};

function UserDashboard() {
    const navigate = useNavigate();
    const { user: authUser, isAuthenticated } = useAuth();
    const { listings: userListings, loading: listingsLoading, error: listingsError } = useFoodListings({ user_id: authUser?.id });

    const { notifications, loading: notificationsLoading, error: notificationsError } = useNotifications(authUser?.id);
    const { impact } = useImpact();

    const loading = listingsLoading || notificationsLoading;
    const error = listingsError || notificationsError;
    const user = authUser;

    // Calculate stats from Supabase data
    const stats = React.useMemo(() => {
        if (!userListings) return {
            listings: 0,
            donations: 0,
            foodSaved: 0,
            peopleHelped: 0
        };

        return {
            listings: userListings.length,
            donations: userListings.length,
            foodSaved: Math.round(impact.foodSavedKg),
            peopleHelped: impact.peopleHelped
        };
    }, [userListings, impact]);
    const recentActivity = React.useMemo(() => {
        if (!userListings) return [];
        
        const activities = userListings.map(listing => ({
            type: 'listing_created',
            title: 'New Listing Created',
            description: `You listed "${listing.title}" for sharing`,
            time: formatDate(listing.created_at),
            icon: 'fa-plus-circle',
            iconColor: 'text-green-500'
        })).sort((a, b) => new Date(b.time) - new Date(a.time)).slice(0, 5);

        return activities;
    }, [userListings]);

    // Quick actions
    const quickActions = [
        {
            title: 'Share Food',
            description: 'Share your surplus food',
            icon: 'fa-plus',
            path: '/share',
            color: 'bg-green-500'
        },
        {
            title: 'Find Food',
            description: 'Browse available items',
            icon: 'fa-search',
            path: '/find',
            color: 'bg-blue-500'
        }
    ];

    // Calculate notifications from Supabase data
    const dashboardNotifications = React.useMemo(() => {
        if (!userListings) return [];
        
        return userListings
            .filter(listing => {
                const daysUntilExpiry = Math.ceil(
                    (new Date(listing.expiry_date) - new Date()) / (1000 * 60 * 60 * 24)
                );
                return daysUntilExpiry <= 3 && daysUntilExpiry > 0;
            })
            .map(listing => ({
                title: 'Listing Expiring Soon',
                message: `Your listing "${listing.title}" expires in ${Math.ceil(
                    (new Date(listing.expiry_date) - new Date()) / (1000 * 60 * 60 * 24)
                )} days`,
                time: formatDate(new Date()),
                read: false,
                type: 'warning'
            }));
    }, [userListings]);

    if (loading) {
        return (
            <div className="max-w-7xl mx-auto py-8 px-4" role="status" aria-busy="true">
                <div className="sr-only">Loading dashboard data...</div>
                <div className="animate-pulse space-y-8">
                    <div className="h-32 bg-gray-200 rounded-lg"></div>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        {[1, 2, 3, 4].map(i => (
                            <div key={i} className="h-24 bg-gray-200 rounded-lg"></div>
                        ))}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div className="h-64 bg-gray-200 rounded-lg"></div>
                        <div className="h-64 bg-gray-200 rounded-lg"></div>
                    </div>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="max-w-7xl mx-auto py-8 px-4 text-center" role="alert">
                <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4" aria-hidden="true"></i>
                <p className="text-gray-600 mb-4">{error.message || 'An unexpected error occurred.'}</p>
                <Button
                    variant="secondary"
                    onClick={() => window.location.reload()}
                    aria-label="Retry loading dashboard data"
                >
                    Try Again
                </Button>
            </div>
        );
    }

    const handleQuickAction = (path) => {
        navigate(path);
    };

    return (
        <div className="max-w-7xl mx-auto py-8 px-4">
            {/* Welcome Section */}
            <div className="bg-white rounded-lg shadow-sm p-6 mb-8" role="banner">
                <div className="flex items-center">
                    <Avatar 
                        src={user?.avatar} 
                        size="xl" 
                        alt={`${user?.name}'s avatar`}
                    />
                    <div className="ml-6">
                        <h1 className="text-2xl font-bold text-gray-900">
                            Welcome back, {user?.name}!
                        </h1>
                        <p className="text-gray-600">
                            Here's what's happening with your food sharing activities
                        </p>
                    </div>
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8" role="region" aria-label="Activity Statistics">
                {[
                    { label: 'Active Listings', value: stats.listings, icon: 'fa-list' },
                    { label: 'Food Saved', value: `${stats.foodSaved}kg`, icon: 'fa-apple-whole' },
                    { label: 'People Helped', value: stats.peopleHelped, icon: 'fa-users' }
                ].map((stat, index) => (
                    <div key={index} className="bg-white rounded-lg shadow-sm p-6" role="article">
                        <div className="flex items-center">
                            <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                                <i className={`fas ${stat.icon} text-green-600 text-xl`} aria-hidden="true"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm text-gray-500">{stat.label}</p>
                                <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Quick Actions */}
                <div className="space-y-6">
                    <h2 className="text-lg font-semibold text-gray-900">Quick Actions</h2>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4" role="navigation">
                        {quickActions.map((action, index) => (
                            <button
                                key={index}
                                onClick={() => handleQuickAction(action.path)}
                                className="bg-white rounded-lg shadow-sm p-4 hover:shadow-md transition-shadow"
                                aria-label={`${action.title}: ${action.description}`}
                            >
                                <div className="flex items-center">
                                    <div className={`w-10 h-10 rounded-full ${action.color} flex items-center justify-center`}>
                                        <i className={`fas ${action.icon} text-white`} aria-hidden="true"></i>
                                    </div>
                                    <div className="ml-4 text-left">
                                        <h3 className="font-medium text-gray-900">{action.title}</h3>
                                        <p className="text-sm text-gray-500">{action.description}</p>
                                    </div>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Recent Activities */}
                <div className="space-y-6">
                    <h2 className="text-lg font-semibold text-gray-900">Recent Activities</h2>
                    <Card>
                        <div className="divide-y divide-gray-200" role="feed" aria-label="Recent activities">
                            {recentActivity.length > 0 ? (
                                recentActivity.map((activity, index) => (
                                    <div key={index} className="p-4" role="article">
                                        <div className="flex items-start">
                                            <div className={`mt-1 ${activity.iconColor}`}>
                                                <i className={`fas ${activity.icon}`} aria-hidden="true"></i>
                                            </div>
                                            <div className="ml-3">
                                                <p className="text-sm font-medium text-gray-900">
                                                    {activity.title}
                                                </p>
                                                <p className="text-sm text-gray-500">
                                                    {activity.description}
                                                </p>
                                                <p className="text-xs text-gray-400 mt-1">
                                                    {activity.time}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className="p-4 text-center text-gray-500" role="status">
                                    No recent activities
                                </div>
                            )}
                        </div>
                    </Card>
                </div>
            </div>

            {/* Notifications */}
            {notifications.length > 0 && (
                <div className="mt-8" role="complementary" aria-label="Notifications">
                    <h2 className="text-lg font-semibold text-gray-900 mb-6">Notifications</h2>
                    <div className="space-y-4">
                        {notifications.map((notification, index) => (
                            <Card key={index}>
                                <div className="p-4" role="alert">
                                    <div className="flex items-start">
                                        <div className="flex-shrink-0">
                                            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                                                notification.type === 'warning' ? 'bg-yellow-100' : 'bg-blue-100'
                                            }`}>
                                                <i className={`fas ${
                                                    notification.type === 'warning' ? 'fa-exclamation-triangle text-yellow-600' : 'fa-handshake text-blue-600'
                                                }`} aria-hidden="true"></i>
                                            </div>
                                        </div>
                                        <div className="ml-3 flex-1">
                                            <p className="text-sm font-medium text-gray-900">
                                                {notification.title}
                                            </p>
                                            <p className="mt-1 text-sm text-gray-500">
                                                {notification.message}
                                            </p>
                                            <p className="mt-1 text-xs text-gray-400">
                                                {notification.time}
                                            </p>
                                        </div>
                                        {!notification.read && (
                                            <div className="ml-3">
                                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                                    New
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </Card>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

export default UserDashboard;