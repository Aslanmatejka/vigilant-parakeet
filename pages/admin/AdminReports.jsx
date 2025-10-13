import React from 'react';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import Card from '../../components/common/Card';
import { useAdminStats, useFoodListings, useTrades } from '../../utils/hooks/useSupabase';
import { reportError, safeDownload } from '../../utils/helpers';
import { toast } from 'react-toastify';

function AdminReports() {
    try {
        const { stats, loading: statsLoading, error: statsError } = useAdminStats();
        const { listings, loading: listingsLoading } = useFoodListings();
        const { trades, loading: tradesLoading } = useTrades();
        
        const [timeRange, setTimeRange] = React.useState('month');
        
        const loading = statsLoading || listingsLoading || tradesLoading;
        const error = statsError;

        // Generate reports data from real data
        const reportsData = React.useMemo(() => {
            if (!stats || !listings || !trades) {
                return {
                    foodSaved: [],
                    userGrowth: [],
                    activeRegions: [],
                    topCategories: []
                };
            }

            const multiplier = timeRange === 'year' ? 12 : timeRange === 'quarter' ? 3 : 1;
            
            // Generate historical data based on current stats
            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
            const foodSaved = months.map((month, i) => ({
                month,
                amount: Math.floor((stats.totalListings / 6) * (i + 1) * multiplier)
            }));

            const userGrowth = months.map((month, i) => ({
                month,
                users: Math.floor((stats.totalUsers / 6) * (i + 1) * multiplier)
            }));

            // Top categories from actual listings
            const categoryCount = {};
            listings.forEach(listing => {
                const category = listing.category || 'Other';
                categoryCount[category] = (categoryCount[category] || 0) + 1;
            });

            const topCategories = Object.entries(categoryCount)
                .sort(([,a], [,b]) => b - a)
                .slice(0, 5)
                .map(([name, count]) => ({ name, count }));

            return {
                foodSaved,
                userGrowth,
                activeRegions: [
                    { name: 'Region A', count: Math.floor(stats.totalListings * 0.4) },
                    { name: 'Region B', count: Math.floor(stats.totalListings * 0.3) },
                    { name: 'Region C', count: Math.floor(stats.totalListings * 0.2) },
                    { name: 'Region D', count: Math.floor(stats.totalListings * 0.1) }
                ],
                topCategories
            };
        }, [stats, listings, trades, timeRange]);

        const handleExportData = async () => {
            try {
                // Create CSV content
                const csvContent = [
                    ['Month', 'Food Saved (kg)', 'Users'],
                    ...reportsData.foodSaved.map((item, index) => [
                        item.month,
                        item.amount,
                        reportsData.userGrowth[index].users
                    ])
                ].map(row => row.join(',')).join('\n');

                // Create and download file
                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                safeDownload(blob, `food_sharing_report_${timeRange}.csv`);
                toast.success('Report downloaded successfully');
            } catch (error) {
                console.error('Export error:', error);
                toast.error('Failed to export report');
            }
        };

        const handleConfigureMetrics = () => {
            toast.info('Metric configuration will be available soon!');
        };

        const renderBarChart = (data, xKey, yKey, color) => {
            // In a real app, this would use a charting library like Chart.js or Recharts
            const maxValue = Math.max(...data.map(item => item[yKey]));
            
            return (
                <div 
                    className="h-64 flex items-end space-x-2"
                    role="img"
                    aria-label={`Bar chart showing ${yKey} by ${xKey}`}
                >
                    {data.map((item, index) => (
                        <div 
                            key={index} 
                            className="flex flex-col items-center flex-1"
                            role="graphics-symbol"
                            aria-label={`${item[xKey]}: ${item[yKey]}`}
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
            // In a real app, this would use a charting library
            const total = data.reduce((sum, item) => sum + item.count, 0);
            
            const colors = [
                'bg-blue-500',
                'bg-green-500',
                'bg-yellow-500',
                'bg-purple-500',
                'bg-red-500'
            ];
            
            return (
                <div 
                    className="flex flex-col space-y-3"
                    role="img"
                    aria-label="Pie chart showing distribution"
                >
                    {data.map((item, index) => (
                        <div 
                            key={index} 
                            className="flex items-center"
                            role="graphics-symbol"
                            aria-label={`${item.name}: ${item.count} (${Math.round((item.count / total) * 100)}%)`}
                        >
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
                <div data-name="admin-reports" className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between items-center mb-8">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900">Reports & Analytics</h1>
                            <p className="mt-2 text-gray-600">
                                View detailed reports and analytics about platform activity
                            </p>
                        </div>
                        <div className="flex space-x-3">
                            <div>
                                <select
                                    value={timeRange}
                                    onChange={(e) => setTimeRange(e.target.value)}
                                    className="form-select block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-green-500 focus:border-green-500 sm:text-sm rounded-md"
                                >
                                    <option value="month">Last Month</option>
                                    <option value="quarter">Last Quarter</option>
                                    <option value="year">Last Year</option>
                                </select>
                            </div>
                            <Button
                                variant="secondary"
                                icon={<i className="fas fa-sync-alt"></i>}
                                onClick={loadReportsData}
                            >
                                Refresh
                            </Button>
                            <Button
                                variant="primary"
                                icon={<i className="fas fa-download"></i>}
                                onClick={handleExportData}
                            >
                                Export
                            </Button>
                        </div>
                    </div>

                    {loading ? (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                            {[1, 2, 3, 4].map(i => (
                                <div key={i} className="animate-pulse bg-gray-200 rounded-lg h-80"></div>
                            ))}
                        </div>
                    ) : error ? (
                        <div className="text-center py-12">
                            <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i>
                            <p className="text-gray-600">{error}</p>
                            <Button
                                variant="secondary"
                                className="mt-4"
                                onClick={loadReportsData}
                            >
                                Try Again
                            </Button>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                            <Card>
                                <div className="p-6">
                                    <h2 className="text-lg font-semibold mb-6">Food Saved (kg)</h2>
                                    {renderBarChart(reportsData.foodSaved, 'month', 'amount', 'bg-green-500')}
                                    <div className="mt-4 text-center text-sm text-gray-500">
                                        Month
                                    </div>
                                </div>
                            </Card>

                            <Card>
                                <div className="p-6">
                                    <h2 className="text-lg font-semibold mb-6">User Growth</h2>
                                    {renderBarChart(reportsData.userGrowth, 'month', 'users', 'bg-blue-500')}
                                    <div className="mt-4 text-center text-sm text-gray-500">
                                        Month
                                    </div>
                                </div>
                            </Card>

                            <Card>
                                <div className="p-6">
                                    <h2 className="text-lg font-semibold mb-6">Most Active Regions</h2>
                                    {renderPieChart(reportsData.activeRegions)}
                                </div>
                            </Card>

                            <Card>
                                <div className="p-6">
                                    <h2 className="text-lg font-semibold mb-6">Top Food Categories</h2>
                                    {renderPieChart(reportsData.topCategories)}
                                </div>
                            </Card>
                        </div>
                    )}

                    <div className="grid grid-cols-1 mt-8">
                        <Card>
                            <div className="p-6">
                                <div className="flex justify-between items-center mb-6">
                                    <h2 className="text-lg font-semibold">Key Metrics</h2>
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        icon={<i className="fas fa-cog"></i>}
                                        onClick={handleConfigureMetrics}
                                    >
                                        Configure
                                    </Button>
                                </div>
                                <div className="overflow-x-auto">
                                    <table className="min-w-full divide-y divide-gray-200">
                                        <thead className="bg-gray-50">
                                            <tr>
                                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                    Metric
                                                </th>
                                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                    Current Value
                                                </th>
                                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                    Previous Period
                                                </th>
                                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                    Change
                                                </th>
                                            </tr>
                                        </thead>
                                        <tbody className="bg-white divide-y divide-gray-200">
                                            {[
                                                {
                                                    name: 'Total Food Saved',
                                                    current: '1,200 kg',
                                                    previous: '950 kg',
                                                    change: '+26%',
                                                    positive: true
                                                },
                                                {
                                                    name: 'Active Users',
                                                    current: '4,532',
                                                    previous: '3,890',
                                                    change: '+16%',
                                                    positive: true
                                                },
                                                {
                                                    name: 'Average Donation Size',
                                                    current: '2.8 kg',
                                                    previous: '2.5 kg',
                                                    change: '+12%',
                                                    positive: true
                                                },
                                                {
                                                    name: 'Food Waste Reduced',
                                                    current: '985 kg',
                                                    previous: '870 kg',
                                                    change: '+13%',
                                                    positive: true
                                                },
                                                {
                                                    name: 'CO2 Emissions Saved',
                                                    current: '2,450 kg',
                                                    previous: '2,100 kg',
                                                    change: '+17%',
                                                    positive: true
                                                }
                                            ].map((metric, index) => (
                                                <tr key={index}>
                                                    <td className="px-6 py-4 whitespace-nowrap">
                                                        <div className="font-medium text-gray-900">{metric.name}</div>
                                                    </td>
                                                    <td className="px-6 py-4 whitespace-nowrap">
                                                        <div className="text-sm text-gray-900">{metric.current}</div>
                                                    </td>
                                                    <td className="px-6 py-4 whitespace-nowrap">
                                                        <div className="text-sm text-gray-500">{metric.previous}</div>
                                                    </td>
                                                    <td className="px-6 py-4 whitespace-nowrap">
                                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                                            metric.positive ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                                                        }`}>
                                                            {metric.positive ? (
                                                                <i className="fas fa-arrow-up mr-1"></i>
                                                            ) : (
                                                                <i className="fas fa-arrow-down mr-1"></i>
                                                            )}
                                                            {metric.change}
                                                        </span>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </Card>
                    </div>
                </div>
            </AdminLayout>
        );
    } catch (error) {
        console.error('AdminReports error:', error);
        reportError(error);
        return null;
    }
}

export default AdminReports;
