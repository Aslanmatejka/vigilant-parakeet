
import React, { useEffect, useState } from 'react';
import dataService from '../../utils/dataService';
import AdminClaimDashboard from './AdminClaimDashboard';
import supabase from '../../utils/supabaseClient';
import { useAuthContext } from '../../utils/AuthContext';
import { debugAuthState } from '../../utils/authDebug';

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
          <div className="grid gap-6 grid-cols-1 md:grid-cols-3">
            {foods.map(food => (
              <div key={food.id} className="bg-white shadow-sm rounded-lg overflow-hidden hover:shadow-md transition-shadow">
                {food.image_url && (
                  <div className="relative h-64">
                    <img src={food.image_url} alt={food.title || food.name} className="w-full h-full object-cover" />
                  </div>
                )}
                <div className="p-4">
                  <h2 className="text-lg font-semibold mb-2">{food.title || food.name}</h2>
                  {food.description && <p className="mb-3 text-gray-600 text-sm">{food.description}</p>}
                  <div className="mb-3 space-y-1 text-sm text-gray-600">
                    {food.category && <div><span className="font-medium">Category:</span> {food.category}</div>}
                    {food.quantity && <div><span className="font-medium">Quantity:</span> {food.quantity} {food.unit || ''}</div>}
                    {food.expiry_date && <div><span className="font-medium">Expiry:</span> {food.expiry_date}</div>}
                    {food.location && <div><span className="font-medium">Location:</span> {food.location}</div>}
                  </div>
                  <div className="mb-4">
                    <span className="text-sm">Status: </span>
                    <span className="font-semibold text-yellow-600">{food.status}</span>
                  </div>
                </div>
                <div className="px-4 py-3 bg-gray-50 border-t flex gap-2 justify-end">
                  <button
                    className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600 text-sm"
                    onClick={() => handleAction(food.id, 'approved')}
                    disabled={food.status !== 'pending' || actionStatus[food.id] === 'loading'}
                  >Approve</button>
                  <button
                    className="bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600 text-sm"
                    onClick={() => handleAction(food.id, 'declined')}
                    disabled={food.status !== 'pending' || actionStatus[food.id] === 'loading'}
                  >Decline</button>
                  {actionStatus[food.id] === 'approved' && <span className="text-green-600 text-sm">✓</span>}
                  {actionStatus[food.id] === 'declined' && <span className="text-red-600 text-sm">✗</span>}
                  {actionStatus[food.id] === 'error' && <span className="text-red-600 text-sm">Error</span>}
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        <AdminClaimDashboard />
      )}
    </div>
  );
}

export default AdminDashboard;
