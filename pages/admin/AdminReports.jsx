import React from 'react';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import Card from '../../components/common/Card';
import supabase from '../../utils/supabaseClient';
import dataService from '../../utils/dataService';

function AdminReports() {
    const [loading, setLoading] = React.useState(true);
    const [timeRange, setTimeRange] = React.useState('month');
    const [stats, setStats] = React.useState({
        totalListings: 0,
        totalUsers: 0,
        totalClaims: 0,
        totalPeople: 0,
        totalPosts: 0
    });
    const [reportsData, setReportsData] = React.useState({
        foodSaved: [],
        userGrowth: [],
        topCategories: [],
        recentActivity: []
    });

    React.useEffect(() => {
        fetchReportsData();

        const foodSubscription = supabase
            .channel('reports-food')
            .on(
                'postgres_changes',
                {
                    event: '*',
                    schema: 'public',
                    table: 'food_listings'
                },
                () => fetchReportsData()
            )
            .subscribe();

        const usersSubscription = supabase
            .channel('reports-users')
            .on(
                'postgres_changes',
                {
                    event: '*',
                    schema: 'public',
                    table: 'users'
                },
                () => fetchReportsData()
            )
            .subscribe();

        return () => {
            supabase.removeChannel(foodSubscription);
            supabase.removeChannel(usersSubscription);
        };
    }, [timeRange]);

    const fetchReportsData = async () => {
        try {
            setLoading(true);

            const [listings, users, claims, posts] = await Promise.all([
                dataService.getFoodListings(),
                supabase.from('users').select('*'),
                supabase.from('food_claims').select('*, people, students, school_staff'),
                dataService.getCommunityPosts()
            ]);

            const listingsData = listings || [];
            const usersData = users.data || [];
            const claimsData = claims.data || [];
            const postsData = posts || [];

            setStats({
                totalListings: listingsData.length,
                totalUsers: usersData.length,
                totalClaims: claimsData.length,
                totalPeople: claimsData.reduce((sum, claim) => sum + (claim.people || 0), 0),
                totalPosts: postsData.length
            });

            const categoryCount = {};
            listingsData.forEach(listing => {
                const category = listing.category || 'Other';
                categoryCount[category] = (categoryCount[category] || 0) + 1;
            });

            const topCategories = Object.entries(categoryCount)
                .sort(([,a], [,b]) => b - a)
                .slice(0, 5)
                .map(([name, count]) => ({ name, count }));

            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
            const multiplier = timeRange === 'year' ? 12 : timeRange === 'quarter' ? 3 : 1;

            setReportsData({
                foodSaved: months.map((month, i) => ({
                    month,
                    amount: Math.floor((listingsData.length / 6) * (i + 1) * multiplier)
                })),
                userGrowth: months.map((month, i) => ({
                    month,
                    users: Math.floor((usersData.length / 6) * (i + 1) * multiplier)
                })),
                topCategories,
                recentActivity: [
                    ...listingsData.slice(0, 5).map(item => ({
                        type: 'listing',
                        title: item.title || item.name,
                        date: item.created_at
                    })),
                    ...claimsData.slice(0, 5).map(item => ({
                        type: 'claim',
                        title: 'Food claimed',
                        date: item.claimed_at
                    }))
                ].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 10)
            });
        } catch (error) {
            console.error('Error fetching reports data:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleExportData = () => {
        const csvContent = [
            ['Metric', 'Value'],
            ['Total Listings', stats.totalListings],
            ['Total Users', stats.totalUsers],
            ['Total Claims', stats.totalClaims],
            ['Total People Helped', stats.totalPeople],
            ['Total Posts', stats.totalPosts],
            [''],
            ['Category', 'Count'],
            ...reportsData.topCategories.map(cat => [cat.name, cat.count])
        ].map(row => row.join(',')).join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `reports_${new Date().toISOString()}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    const renderBarChart = (data, xKey, yKey, color) => {
        const maxValue = Math.max(...data.map(item => item[yKey])) || 1;

        return (
            <div className="h-64 flex items-end space-x-2">
                {data.map((item, index) => (
                    <div
                        key={index}
                        className="flex flex-col items-center flex-1"
                    >
                        <div
                            className={`w-full ${color} rounded-t`}
                            style={{ height: `${(item[yKey] / maxValue) * 100}%` }}
                        ></div>
                        <div className="text-xs mt-2">{item[xKey]}</div>
                    </div>
                ))}
            </div>
        );
    };

    const renderPieChart = (data) => {
        const total = data.reduce((sum, item) => sum + item.count, 0) || 1;

        const colors = [
            'bg-blue-500',
            'bg-green-500',
            'bg-yellow-500',
            'bg-purple-500',
            'bg-red-500'
        ];

        return (
            <div className="flex flex-col space-y-3">
                {data.map((item, index) => (
                    <div key={index} className="flex items-center">
                        <div className={`w-3 h-3 rounded-full ${colors[index % colors.length]} mr-2`}></div>
                        <div className="flex-1 text-sm">{item.name}</div>
                        <div className="text-sm font-medium">{item.count}</div>
                        <div className="text-xs text-gray-500 w-12 text-right">
                            {Math.round((item.count / total) * 100)}%
                        </div>
                    </div>
                ))}
            </div>
        );
    };

    return (
        <AdminLayout active="reports">
            <div className="p-6">
                <div className="flex justify-between items-center mb-6">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">Reports & Analytics</h1>
                        <p className="mt-2 text-gray-600">View detailed reports and analytics about platform activity</p>
                    </div>
                    <div className="flex space-x-3">
                        <select
                            value={timeRange}
                            onChange={(e) => setTimeRange(e.target.value)}
                            className="form-select block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-green-500 focus:border-green-500 sm:text-sm rounded-md"
                        >
                            <option value="month">Last Month</option>
                            <option value="quarter">Last Quarter</option>
                            <option value="year">Last Year</option>
                        </select>
                        <Button
                            variant="secondary"
                            onClick={fetchReportsData}
                        >
                            <i className="fas fa-sync-alt mr-2"></i>
                            Refresh
                        </Button>
                        <Button
                            variant="primary"
                            onClick={handleExportData}
                        >
                            <i className="fas fa-download mr-2"></i>
                            Export
                        </Button>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
                    <Card className="p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-blue-100 rounded-full p-3">
                                <i className="fas fa-list text-blue-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">Total Listings</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.totalListings}</p>
                            </div>
                        </div>
                    </Card>

                    <Card className="p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-green-100 rounded-full p-3">
                                <i className="fas fa-users text-green-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">Total Users</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.totalUsers}</p>
                            </div>
                        </div>
                    </Card>

                    <Card className="p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-yellow-100 rounded-full p-3">
                                <i className="fas fa-hand-holding-heart text-yellow-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">Total Claims</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.totalClaims}</p>
                            </div>
                        </div>
                    </Card>

                    <Card className="p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-red-100 rounded-full p-3">
                                <i className="fas fa-user-friends text-red-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">People Helped</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.totalPeople}</p>
                            </div>
                        </div>
                    </Card>

                    <Card className="p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-purple-100 rounded-full p-3">
                                <i className="fas fa-newspaper text-purple-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">Community Posts</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.totalPosts}</p>
                            </div>
                        </div>
                    </Card>
                </div>

                {loading ? (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {[1, 2, 3, 4].map(i => (
                            <div key={i} className="animate-pulse bg-gray-200 rounded-lg h-80"></div>
                        ))}
                    </div>
                ) : (
                    <>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                            <Card>
                                <div className="p-6">
                                    <h2 className="text-lg font-semibold mb-6">Food Listings Over Time</h2>
                                    {renderBarChart(reportsData.foodSaved, 'month', 'amount', 'bg-green-500')}
                                    <div className="mt-4 text-center text-sm text-gray-500">Month</div>
                                </div>
                            </Card>

                            <Card>
                                <div className="p-6">
                                    <h2 className="text-lg font-semibold mb-6">User Growth</h2>
                                    {renderBarChart(reportsData.userGrowth, 'month', 'users', 'bg-blue-500')}
                                    <div className="mt-4 text-center text-sm text-gray-500">Month</div>
                                </div>
                            </Card>

                            <Card>
                                <div className="p-6">
                                    <h2 className="text-lg font-semibold mb-6">Top Food Categories</h2>
                                    {reportsData.topCategories.length > 0 ? (
                                        renderPieChart(reportsData.topCategories)
                                    ) : (
                                        <p className="text-gray-500 text-center py-8">No category data available</p>
                                    )}
                                </div>
                            </Card>

                            <Card>
                                <div className="p-6">
                                    <h2 className="text-lg font-semibold mb-6">Recent Activity</h2>
                                    {reportsData.recentActivity.length > 0 ? (
                                        <div className="space-y-3">
                                            {reportsData.recentActivity.map((activity, index) => (
                                                <div key={index} className="flex items-center justify-between border-b pb-2">
                                                    <div className="flex items-center">
                                                        <i className={`fas ${activity.type === 'listing' ? 'fa-box' : 'fa-hand-holding'} text-gray-400 mr-3`}></i>
                                                        <span className="text-sm">{activity.title}</span>
                                                    </div>
                                                    <span className="text-xs text-gray-500">
                                                        {new Date(activity.date).toLocaleDateString()}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <p className="text-gray-500 text-center py-8">No recent activity</p>
                                    )}
                                </div>
                            </Card>
                        </div>
                    </>
                )}
            </div>
        </AdminLayout>
    );
}

export default AdminReports;
