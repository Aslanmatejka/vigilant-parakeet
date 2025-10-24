import React from 'react';
import AdminLayout from './AdminLayout';
import Button from '../../components/common/Button';
import Card from '../../components/common/Card';
import dataService from '../../utils/dataService';
import supabase from '../../utils/supabaseClient';

const formatDate = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
};

function FoodDistributionManagement() {
    const [listings, setListings] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [stats, setStats] = React.useState({
        total: 0,
        available: 0,
        claimed: 0,
        pending: 0
    });

    React.useEffect(() => {
        fetchListings();

        const subscription = supabase
            .channel('food-distribution')
            .on(
                'postgres_changes',
                {
                    event: '*',
                    schema: 'public',
                    table: 'food_listings'
                },
                () => {
                    console.log('Food listings changed, refreshing...');
                    fetchListings();
                }
            )
            .subscribe();

        return () => {
            supabase.removeChannel(subscription);
        };
    }, []);

    const fetchListings = async () => {
        try {
            setLoading(true);
            const data = await dataService.getFoodListings();

            setListings(data);

            const total = data.length;
            const available = data.filter(item => item.status === 'available').length;
            const claimed = data.filter(item => item.status === 'claimed').length;
            const pending = data.filter(item => item.status === 'pending').length;

            setStats({ total, available, claimed, pending });
        } catch (error) {
            console.error('Error fetching listings:', error);
            setListings([]);
        } finally {
            setLoading(false);
        }
    };

    const handleStatusChange = async (listingId, newStatus) => {
        try {
            await dataService.updateFoodListingStatus(listingId, newStatus);
            await fetchListings();
        } catch (error) {
            console.error('Error updating status:', error);
            alert('Failed to update status');
        }
    };

    const handleDelete = async (listingId) => {
        if (!confirm('Are you sure you want to delete this listing?')) return;

        try {
            const { error } = await supabase
                .from('food_listings')
                .delete()
                .eq('id', listingId);

            if (error) throw error;
            await fetchListings();
        } catch (error) {
            console.error('Error deleting listing:', error);
            alert('Failed to delete listing');
        }
    };

    const getStatusBadge = (status) => {
        const statusStyles = {
            available: 'bg-green-100 text-green-800',
            pending: 'bg-yellow-100 text-yellow-800',
            claimed: 'bg-blue-100 text-blue-800',
            approved: 'bg-green-100 text-green-800',
            declined: 'bg-red-100 text-red-800'
        };

        return (
            <span className={`px-2 py-1 text-xs font-semibold rounded-full ${statusStyles[status] || 'bg-gray-100 text-gray-800'}`}>
                {status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown'}
            </span>
        );
    };

    return (
        <AdminLayout active="distribution">
            <div className="p-6">
                <div className="mb-6">
                    <h1 className="text-2xl font-bold text-gray-900">Food Distribution Management</h1>
                    <p className="mt-2 text-gray-600">Manage and track all food listings in the system</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                    <div className="bg-white rounded-lg shadow p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-blue-100 rounded-full p-3">
                                <i className="fas fa-list text-blue-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">Total Listings</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.total}</p>
                            </div>
                        </div>
                    </div>

                    <div className="bg-white rounded-lg shadow p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-green-100 rounded-full p-3">
                                <i className="fas fa-check-circle text-green-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">Available</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.available}</p>
                            </div>
                        </div>
                    </div>

                    <div className="bg-white rounded-lg shadow p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-yellow-100 rounded-full p-3">
                                <i className="fas fa-clock text-yellow-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">Pending</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.pending}</p>
                            </div>
                        </div>
                    </div>

                    <div className="bg-white rounded-lg shadow p-6">
                        <div className="flex items-center">
                            <div className="flex-shrink-0 bg-red-100 rounded-full p-3">
                                <i className="fas fa-hand-holding-heart text-red-600 text-xl"></i>
                            </div>
                            <div className="ml-4">
                                <p className="text-sm font-medium text-gray-500">Claimed</p>
                                <p className="text-2xl font-bold text-gray-900">{stats.claimed}</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="bg-white rounded-lg shadow overflow-hidden">
                    <div className="px-6 py-4 border-b border-gray-200">
                        <h2 className="text-lg font-semibold">All Food Listings ({listings.length})</h2>
                    </div>

                    {loading ? (
                        <div className="p-8 text-center">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
                            <p className="mt-4 text-gray-600">Loading listings...</p>
                        </div>
                    ) : listings.length === 0 ? (
                        <div className="p-8 text-center">
                            <i className="fas fa-box-open text-gray-400 text-4xl mb-4"></i>
                            <p className="text-gray-600">No food listings yet</p>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="min-w-full divide-y divide-gray-200">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Food Item
                                        </th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Category
                                        </th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Quantity
                                        </th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Expiry Date
                                        </th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Status
                                        </th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Created
                                        </th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            Actions
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {listings.map(listing => (
                                        <tr key={listing.id}>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center">
                                                    {listing.image_url && (
                                                        <img
                                                            src={listing.image_url}
                                                            alt={listing.title || listing.name}
                                                            className="h-10 w-10 rounded object-cover mr-3"
                                                        />
                                                    )}
                                                    <div>
                                                        <div className="text-sm font-medium text-gray-900">
                                                            {listing.title || listing.name}
                                                        </div>
                                                        <div className="text-sm text-gray-500 line-clamp-1">
                                                            {listing.description}
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {listing.category || 'N/A'}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                                {listing.quantity} {listing.unit || ''}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {listing.expiry_date ? formatDate(listing.expiry_date) : 'N/A'}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                {getStatusBadge(listing.status)}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {formatDate(listing.created_at)}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium space-x-2">
                                                {listing.status === 'pending' && (
                                                    <>
                                                        <Button
                                                            variant="primary"
                                                            size="sm"
                                                            onClick={() => handleStatusChange(listing.id, 'approved')}
                                                        >
                                                            Approve
                                                        </Button>
                                                        <Button
                                                            variant="danger"
                                                            size="sm"
                                                            onClick={() => handleStatusChange(listing.id, 'declined')}
                                                        >
                                                            Decline
                                                        </Button>
                                                    </>
                                                )}
                                                {listing.status === 'approved' && (
                                                    <Button
                                                        variant="secondary"
                                                        size="sm"
                                                        onClick={() => handleStatusChange(listing.id, 'available')}
                                                    >
                                                        Make Available
                                                    </Button>
                                                )}
                                                <Button
                                                    variant="danger"
                                                    size="sm"
                                                    onClick={() => handleDelete(listing.id)}
                                                >
                                                    Delete
                                                </Button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
        </AdminLayout>
    );
}

export default FoodDistributionManagement;
