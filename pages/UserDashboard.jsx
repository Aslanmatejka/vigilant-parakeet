import React from "react";
import { useNavigate } from "react-router-dom";
import Button from "../components/common/Button";
import Avatar from "../components/common/Avatar";
import Card from "../components/common/Card";
import Receipt from "../components/common/Receipt";
import RoleInsightsPanel from "../components/assistant/RoleInsightsPanel";
import AIQueryPanel from "../components/assistant/AIQueryPanel";
import PickupRouteOptimizer from "../components/donations/PickupRouteOptimizer";
import { useAuth, useFoodListings, useNotifications } from "../utils/hooks/useSupabase";
import supabase from "../utils/supabaseClient";

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

    const [receipts, setReceipts] = React.useState([]);
    const [receiptsLoading, setReceiptsLoading] = React.useState(true);
    // Always trust the DB for community_role — auth cache can lag after a save.
    const [freshRole, setFreshRole] = React.useState(null);

    const loading = listingsLoading || notificationsLoading || receiptsLoading;
    const error = listingsError || notificationsError;
    const user = React.useMemo(
        () => ({ ...(authUser || {}), community_role: freshRole ?? authUser?.community_role ?? null }),
        [authUser, freshRole]
    );

    React.useEffect(() => {
        let cancelled = false;
        if (!authUser?.id) { setFreshRole(null); return; }
        (async () => {
            try {
                const { data } = await supabase
                    .from('users')
                    .select('community_role')
                    .eq('id', authUser.id)
                    .single();
                if (!cancelled && data) setFreshRole(data.community_role || null);
            } catch (_) { /* keep cached value */ }
        })();
        const onRoleChanged = (e) => {
            // Only react when the event explicitly targets this user.
            if (e?.detail && e.detail.userId === authUser.id) {
                setFreshRole(e.detail.role ?? null);
            }
        };
        window.addEventListener('dogoods:community-role-changed', onRoleChanged);
        return () => {
            cancelled = true;
            window.removeEventListener('dogoods:community-role-changed', onRoleChanged);
        };
    }, [authUser?.id]);

    React.useEffect(() => {
        let isMounted = true;
        if (authUser?.id) {
            fetchReceipts(() => isMounted);
        }
        return () => { isMounted = false; };
    }, [authUser?.id]);

    const fetchReceipts = async (isStillMounted = () => true) => {
        try {
            setReceiptsLoading(true);

            // Fetch all receipts for the user
            const { data: userReceipts, error: receiptsError } = await supabase
                .from('receipts')
                .select('*')
                .eq('user_id', authUser.id)
                .order('claimed_at', { ascending: false });

            if (receiptsError) throw receiptsError;
            if (!isStillMounted()) return;

            // For each receipt, fetch the associated food claims and items
            const receiptsWithItems = await Promise.all(
                (userReceipts || []).map(async (receipt) => {
                    const { data: claims, error: claimsError } = await supabase
                        .from('food_claims')
                        .select(`
                            *,
                            food_listings (
                                id,
                                title,
                                description,
                                quantity,
                                unit
                            )
                        `)
                        .eq('receipt_id', receipt.id);

                    if (claimsError) {
                        console.error('Error fetching claims for receipt:', claimsError);
                        return { ...receipt, items: [] };
                    }

                    // Transform claims into receipt items format
                    const items = (claims || []).map(claim => ({
                        food_id: claim.food_id,
                        food_name: claim.food_listings?.title || 'Unknown Item',
                        quantity: `${claim.quantity ?? 1} ${claim.food_listings?.unit || ''}`.trim() || 'N/A'
                    }));

                    return { ...receipt, items };
                })
            );

            if (isStillMounted()) setReceipts(receiptsWithItems);
        } catch (err) {
            console.error('Error fetching receipts:', err);
        } finally {
            if (isStillMounted()) setReceiptsLoading(false);
        }
    };
    const recentActivity = React.useMemo(() => {
        if (!userListings) return [];
        
        const activities = userListings.map(listing => ({
            type: 'listing_created',
            title: 'New Listing Created',
            description: `You listed "${listing.title}" for sharing`,
            time: formatDate(listing.created_at),
            icon: 'fa-plus-circle',
            iconColor: 'text-[#2CABE3]'
        })).sort((a, b) => new Date(b.time) - new Date(a.time)).slice(0, 5);

        return activities;
    }, [userListings]);

    // Quick actions tailored to community_role so the dashboard actually
    // changes when the user switches between donor / recipient / volunteer.
    const role = String(user?.community_role || '').toLowerCase();
    const isDonor = role === 'donor';
    const isRecipient = role === 'recipient';
    const isVolunteer = role === 'volunteer' || role === 'driver' || role === 'dispatcher';

    const quickActions = isDonor
        ? [
            { title: 'Share Food', description: 'Post surplus food for the community', icon: 'fa-plus', path: '/share', color: 'bg-[#2CABE3]' },
            { title: 'My Listings', description: 'Manage what you’ve posted', icon: 'fa-list', path: '/listings', color: 'bg-emerald-500' },
            { title: 'Donation Schedules', description: 'Set up recurring donations', icon: 'fa-calendar', path: '/donations', color: 'bg-purple-500' },
        ]
        : isRecipient
        ? [
            { title: 'Find Food', description: 'Browse available items near you', icon: 'fa-search', path: '/find', color: 'bg-blue-500' },
            { title: 'Near Me', description: 'See pickups on the map', icon: 'fa-location-dot', path: '/near-me', color: 'bg-emerald-500' },
            { title: 'My Receipts', description: 'View claims and pickups', icon: 'fa-receipt', path: '/receipts', color: 'bg-purple-500' },
        ]
        : isVolunteer
        ? [
            { title: 'Pickup Routes', description: 'Plan your delivery run', icon: 'fa-route', path: '/donations', color: 'bg-[#2CABE3]' },
            { title: 'Find Food', description: 'See what needs delivering', icon: 'fa-search', path: '/find', color: 'bg-blue-500' },
            { title: 'Near Me', description: 'Pickups on the map', icon: 'fa-location-dot', path: '/near-me', color: 'bg-emerald-500' },
        ]
        : [
            { title: 'Find Food', description: 'Browse available items', icon: 'fa-search', path: '/find', color: 'bg-blue-500' },
            { title: 'Donation Schedules', description: 'Set up recurring donations', icon: 'fa-calendar', path: '/donations', color: 'bg-purple-500' },
        ];

    // Calculate notifications from Supabase data
    const dashboardNotifications = React.useMemo(() => {
        if (!userListings) return [];
        
        // Compare dates as local-timezone strings to avoid the UTC-midnight
        // off-by-one: new Date('YYYY-MM-DD') parses as UTC so in Pacific time
        // a listing expiring "tomorrow" evaluates as 0 days away after 5 PM.
        const now = new Date();
        const msPerDay = 1000 * 60 * 60 * 24;

        return userListings
            .filter(listing => {
                if (!listing.expiry_date) return false;
                const expiryLocal = new Date(listing.expiry_date + 'T00:00:00');
                const daysUntilExpiry = Math.ceil((expiryLocal - now) / msPerDay);
                return daysUntilExpiry <= 3 && daysUntilExpiry > 0;
            })
            .map(listing => {
                const expiryLocal = new Date(listing.expiry_date + 'T00:00:00');
                const daysUntilExpiry = Math.ceil((expiryLocal - now) / msPerDay);
                return {
                    title: 'Listing Expiring Soon',
                    message: `Your listing "${listing.title}" expires in ${daysUntilExpiry} day${daysUntilExpiry === 1 ? '' : 's'}`,
                    time: formatDate(new Date()),
                    read: false,
                    type: 'warning'
                };
            });
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
                        <div className="flex items-center gap-3">
                            <h1 className="text-2xl font-bold text-gray-900">
                                Welcome back, {user?.name}!
                            </h1>
                        </div>
                        <p className="text-gray-600">
                            Here's what's happening with your food sharing activities
                        </p>
                    </div>
                </div>
            </div>

            {/* AI Role-Specific Insights */}
            <RoleInsightsPanel className="mb-8" />

            {/* Smart Pickup Route Optimizer — donor/volunteer only */}
            {(isDonor || isVolunteer) && <PickupRouteOptimizer className="mb-8" />}

            {/* Natural-language Query Panel */}
            <AIQueryPanel className="mb-8" />

            {/* Food Receipts Section — recipient/volunteer/default; hidden for donors */}
            {!isDonor && (
            <div className="mb-8" role="region" aria-label="Food Claim Receipts">
                <h2 className="text-2xl font-bold text-gray-900 mb-6">Your Food Receipts</h2>
                
                {receiptsLoading ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="animate-pulse bg-gray-200 rounded-lg h-96"></div>
                        ))}
                    </div>
                ) : receipts.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {receipts.map((receipt) => (
                            <Receipt 
                                key={receipt.id}
                                receipt={receipt}
                                items={receipt.items || []}
                                onUpdate={fetchReceipts}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="bg-white rounded-lg shadow-sm p-12 text-center">
                        <i className="fas fa-receipt text-gray-400 text-5xl mb-4" aria-hidden="true"></i>
                        <h3 className="text-xl font-semibold text-gray-900 mb-2">No Receipts Yet</h3>
                        <p className="text-gray-600 mb-6">
                            Start claiming food from your community to see your receipts here. Multiple items claimed on the same day will be grouped into one receipt.
                        </p>
                        <Button
                            variant="primary"
                            onClick={() => navigate('/find')}
                            aria-label="Find available food"
                        >
                            <i className="fas fa-search mr-2" aria-hidden="true"></i>
                            Find Food
                        </Button>
                    </div>
                )}
            </div>
            )}

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

                {/* Recent Activities — these are listings YOU posted, only meaningful for donors */}
                {isDonor ? (
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
                ) : null}
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
                                                {notification.created_at ? new Date(notification.created_at).toLocaleString() : ''}
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