import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../common/Button';
import dataService from '../../utils/dataService';
import { useAuthContext } from '../../utils/AuthContext';
import { debugAuthState } from '../../utils/authDebug';

function AdminClaimDashboard() {
  const [pendingClaims, setPendingClaims] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionStatus, setActionStatus] = useState({});
  const { isAuthenticated, isAdmin } = useAuthContext();
  const navigate = useNavigate();

  useEffect(() => {
    // Check authentication before fetching data
    if (isAuthenticated && isAdmin) {
      fetchPendingClaims();
      // Debug auth state on component mount
      debugAuthState().then(state => {
        console.log('Auth state in AdminClaimDashboard:', state);
      });
    } else if (isAuthenticated && !isAdmin) {
      setError('You do not have admin permissions to access this page.');
    } else if (!isAuthenticated) {
      navigate('/login?redirect=/admin');
    }
  }, [isAuthenticated, isAdmin, navigate]);

  async function fetchPendingClaims() {
    setLoading(true);
    setError(null);
    try {
      const data = await dataService.getFoodClaims({ status: 'pending' });
      setPendingClaims(data);
    } catch (err) {
      console.error('Error fetching claims:', err);
      setError(err.message || 'Failed to fetch pending claims.');
    } finally {
      setLoading(false);
    }
  }

  async function handleReview(claimId, approve) {
    setActionStatus({ ...actionStatus, [claimId]: 'loading' });
    try {
      await dataService.updateFoodClaimStatus(claimId, approve ? 'approved' : 'declined');
      setActionStatus({ ...actionStatus, [claimId]: approve ? 'approved' : 'declined' });
      // Refresh list
      fetchPendingClaims();
    } catch (err) {
      setActionStatus({ ...actionStatus, [claimId]: 'error' });
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-10 px-4">
      <h1 className="text-3xl font-bold mb-6">Admin Dashboard: Pending Food Claims</h1>
      
      <div className="bg-blue-50 border-l-4 border-blue-500 p-4 mb-6 rounded">
        <p className="text-blue-700">
          <span className="font-bold">Note:</span> School information is now displayed for each claim, including school name, 
          district, case worker contact details, and more.
        </p>
      </div>
      
      {loading && <div>Loading...</div>}
      {error && <div className="text-red-600">{error}</div>}
      <div className="space-y-6">
        {pendingClaims.length === 0 && !loading ? (
          <div className="text-gray-600">No pending claims.</div>
        ) : (
          pendingClaims.map(claim => (
            <div key={claim.id} className="bg-white rounded shadow p-6 border">
              <div className="font-bold text-lg mb-2">{claim.food_listings?.title || 'Food Item'}</div>
              <div className="mb-2">{claim.food_listings?.description}</div>
              <div className="relative h-48 mb-2">
                <img src={claim.food_listings?.image_url} alt={claim.food_listings?.title} className="w-full h-full object-cover rounded-lg" />
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="font-semibold text-gray-800 mb-2 border-b pb-1">Claimer Information</h3>
                  <div className="mb-2">Name: {claim.requester_name}</div>
                  <div className="mb-2">Email: {claim.requester_email}</div>
                  <div className="mb-2">Phone: {claim.requester_phone}</div>
                  <div className="mb-2">Members: {claim.members_count}</div>
                  <div className="mb-2">Pickup/Dropoff: {claim.pickup_time || claim.dropoff_time} at {claim.pickup_place || claim.dropoff_place}</div>
                </div>
                
                <div className="bg-blue-50 p-4 rounded-lg">
                  <h3 className="font-semibold text-blue-800 mb-2 border-b pb-1">School Information</h3>
                  <div className="mb-2">School Name: {claim.school || 'Not provided'}</div>
                  <div className="mb-2">School District: {claim.school_district || 'Not provided'}</div>
                  <div className="mb-2">Case Worker/Contact: {claim.school_contact || 'Not provided'}</div>
                  <div className="mb-2">Contact Email: {claim.school_contact_email || 'Not provided'}</div>
                  <div className="mb-2">Contact Phone: {claim.school_contact_phone || 'Not provided'}</div>
                </div>
              </div>

              <div className="flex gap-4 mt-4">
                <Button variant="primary" onClick={() => handleReview(claim.id, true)} disabled={actionStatus[claim.id] === 'loading'}>
                  Approve
                </Button>
                <Button variant="danger" onClick={() => handleReview(claim.id, false)} disabled={actionStatus[claim.id] === 'loading'}>
                  Decline
                </Button>
                {actionStatus[claim.id] === 'approved' && <span className="text-green-600 ml-2">Approved</span>}
                {actionStatus[claim.id] === 'declined' && <span className="text-red-600 ml-2">Declined</span>}
                {actionStatus[claim.id] === 'error' && <span className="text-red-600 ml-2">Error</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default AdminClaimDashboard;
