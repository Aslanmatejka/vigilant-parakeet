import React, { useEffect, useState } from 'react';
import dataService from '../../utils/dataService';
import AdminClaimDashboard from './AdminClaimDashboard';
import supabase from '../../utils/supabaseClient';
import { useAuthContext } from '../../utils/AuthContext';
import { debugAuthState } from '../../utils/authDebug';
import AdminLayout from '../../pages/admin/AdminLayout';

function AdminDashboard() {
  const [foods, setFoods] = useState([]);
  const [loading, setLoading] = useState(false);
  const [actionStatus, setActionStatus] = useState({});
  const [activeTab, setActiveTab] = useState('pending');
  const { isAuthenticated, isAdmin } = useAuthContext();

  // Debug auth state on component mount
  useEffect(() => {
    debugAuthState().then(state => {
      console.log('Auth state in AdminDashboard:', state);
    });
  }, []);

  useEffect(() => {
    if (activeTab === 'pending') {
      fetchPendingFoods();
    }

    // Real-time subscription for food listings
    const subscription = supabase
      .channel('admin-food-listings')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'food_listings'
        },
        (payload) => {
          console.log('Food listing changed:', payload);
          if (activeTab === 'pending') {
            fetchPendingFoods();
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(subscription);
    };
  }, [activeTab]);

  async function fetchPendingFoods() {
    setLoading(true);
    try {
      const listings = await dataService.getFoodListings({ status: 'pending' });
      setFoods(listings || []);
    } catch (err) {
      setFoods([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleAction(id, action) {
    setActionStatus({ ...actionStatus, [id]: 'loading' });
    try {
      await dataService.updateFoodListingStatus(id, action);
      setActionStatus({ ...actionStatus, [id]: action });
      fetchPendingFoods();
    } catch (err) {
      setActionStatus({ ...actionStatus, [id]: 'error' });
    }
  }

  return (
    <AdminLayout active="dashboard">
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-6">Admin Dashboard</h1>
      <div className="mb-6 flex gap-4">
        <button
          className={`px-4 py-2 rounded ${activeTab === 'pending' ? 'bg-green-600 text-white' : 'bg-gray-200 text-gray-700'}`}
          onClick={() => setActiveTab('pending')}
        >Pending Foods</button>
        <button
          className={`px-4 py-2 rounded ${activeTab === 'claimed' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'}`}
          onClick={() => setActiveTab('claimed')}
        >Claimed Foods</button>
      </div>
      {activeTab === 'pending' ? (
        loading ? (
          <div>Loading...</div>
        ) : (
          <div className="grid gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
            {foods.map(food => (
              <div key={food.id} className="bg-white shadow rounded p-4 flex flex-col items-center">
                {food.image_url && (
                  <img src={food.image_url} alt={food.title || food.name} className="w-32 h-32 object-cover mb-2 rounded" />
                )}
                <h2 className="text-lg font-semibold mb-2">{food.title || food.name}</h2>
                {food.description && <p className="mb-2 text-gray-700 text-center">{food.description}</p>}
                <div className="mb-2 text-sm text-gray-600">
                  {food.category && <span className="mr-2"><strong>Category:</strong> {food.category}</span>}
                  {food.quantity && <span className="mr-2"><strong>Quantity:</strong> {food.quantity} {food.unit || ''}</span>}
                  {food.expiry_date && <span className="mr-2"><strong>Expiry:</strong> {food.expiry_date}</span>}
                  {food.location && <span className="mr-2"><strong>Location:</strong> {food.location}</span>}
                </div>
                <p className="mb-4">Status: <span className="font-bold text-yellow-600">{food.status}</span></p>
                <div className="flex gap-2">
                  <button
                    className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600"
                    onClick={() => handleAction(food.id, 'approved')}
                    disabled={food.status !== 'pending' || actionStatus[food.id] === 'loading'}
                  >Approve</button>
                  <button
                    className="bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600"
                    onClick={() => handleAction(food.id, 'declined')}
                    disabled={food.status !== 'pending' || actionStatus[food.id] === 'loading'}
                  >Decline</button>
                  {actionStatus[food.id] === 'approved' && <span className="text-green-600 ml-2">Approved</span>}
                  {actionStatus[food.id] === 'declined' && <span className="text-red-600 ml-2">Declined</span>}
                  {actionStatus[food.id] === 'error' && <span className="text-red-600 ml-2">Error</span>}
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        <AdminClaimDashboard />
      )}
    </div>
    </AdminLayout>
  );
}

export default AdminDashboard;
