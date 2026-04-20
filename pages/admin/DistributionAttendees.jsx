import React from 'react';
import AdminLayout from './AdminLayout';
import supabase from '../../utils/supabaseClient';
import Button from '../../components/common/Button';
import { useAuthContext } from '../../utils/AuthContext';

const DistributionAttendees = () => {
  const { user, isAdmin, loading: authLoading, initialized } = useAuthContext();
  const [attendees, setAttendees] = React.useState([]);
  const [communities, setCommunities] = React.useState({});
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [stats, setStats] = React.useState({
    totalClaims: 0,
    totalStudents: 0,
    totalStaff: 0
  });

  React.useEffect(() => {
    if (!user || !isAdmin || authLoading || !initialized) {
      // If auth is done but user/admin not available, stop loading
      if (!authLoading && initialized) {
        setLoading(false);
      }
      return;
    }

    fetchCommunities();
    fetchAttendees();

    let subscription;
    try {
      subscription = supabase
        .channel('distribution-attendees')
        .on(
          'postgres_changes',
          {
            event: '*',
            schema: 'public',
            table: 'food_claims'
          },
          () => {
            console.log('Claims data changed, refreshing...');
            fetchAttendees();
          }
        )
        .subscribe();
    } catch (err) {
      console.error('Error subscribing to realtime:', err);
    }

    return () => {
      if (subscription) {
        supabase.removeChannel(subscription);
      }
    };
  }, [user, isAdmin, authLoading, initialized]);

  const fetchCommunities = async () => {
    try {
      const { data, error } = await supabase
        .from('communities')
        .select('id, name')
        .order('name', { ascending: true });
      if (error) throw error;
      const map = {};
      (data || []).forEach(c => { map[c.id] = c.name; });
      setCommunities(map);
    } catch (err) {
      console.error('Error fetching communities:', err);
    }
  };

  const fetchAttendees = async () => {
    try {
      setLoading(true);
      setError(null);

      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        console.warn('No active Supabase session — skipping fetch');
        setError('No active session. Please log in again.');
        setLoading(false);
        return;
      }

      const { data: claims, error: queryError } = await supabase
        .from('food_claims')
        .select(`
          *,
          claimer:users!claimer_id(
            id,
            name,
            email,
            phone,
            avatar_url
          ),
          food_listing:food_listings!food_id(
            id,
            title,
            quantity,
            unit,
            community_id
          )
        `)
        .order('created_at', { ascending: false });

      if (queryError) throw queryError;

      const claimsData = claims || [];
      setAttendees(claimsData);

      const totalClaims = claimsData.length;
      const totalStudents = claimsData.reduce((sum, claim) => sum + (claim.students || 0), 0);
      const totalStaff = claimsData.reduce((sum, claim) => sum + (claim.school_staff || 0), 0);

      setStats({
        totalClaims,
        totalStudents,
        totalStaff
      });
    } catch (err) {
      console.error('Error fetching attendees:', err);
      setError(err.message || 'Failed to load attendees');
      setAttendees([]);
    } finally {
      setLoading(false);
    }
  };

  const handleMarkReceived = async (claimId, currentStatus) => {
    try {
      const { error } = await supabase
        .from('food_claims')
        .update({ status: currentStatus === 'pending' ? 'completed' : 'pending' })
        .eq('id', claimId);

      if (error) throw error;
      await fetchAttendees();
    } catch (error) {
      console.error('Error updating claim status:', error);
      alert('Failed to update claim status');
    }
  };

  return (
    <AdminLayout active="attendees">
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Distribution Attendees</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0 bg-blue-100 rounded-full p-3">
              <i className="fas fa-clipboard-list text-blue-600 text-xl"></i>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Total Claims</p>
              <p className="text-2xl font-bold text-gray-900">{stats.totalClaims}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0 bg-yellow-100 rounded-full p-3">
              <i className="fas fa-graduation-cap text-yellow-600 text-xl"></i>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Students</p>
              <p className="text-2xl font-bold text-gray-900">{stats.totalStudents}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0 bg-red-100 rounded-full p-3">
              <i className="fas fa-chalkboard-teacher text-red-600 text-xl"></i>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">School Staff</p>
              <p className="text-2xl font-bold text-gray-900">{stats.totalStaff}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold">Event Attendees ({attendees.length})</h2>
        </div>

        {loading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading attendees...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center">
            <i className="fas fa-exclamation-triangle text-red-500 text-4xl mb-4"></i>
            <p className="text-red-600 font-medium mb-2">Error loading attendees</p>
            <p className="text-gray-500 text-sm mb-4">{error}</p>
            <button
              onClick={fetchAttendees}
              className="px-4 py-2 bg-[#2CABE3] text-white rounded hover:bg-[#2CABE3]/80"
            >
              Retry
            </button>
          </div>
        ) : attendees.length === 0 ? (
          <div className="p-8 text-center">
            <i className="fas fa-inbox text-gray-400 text-4xl mb-4"></i>
            <p className="text-gray-600">No attendees yet</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Attendee
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Food Item
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Qty Claimed
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Community
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Claimed At
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {attendees.map(claim => (
                  <tr key={claim.id}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        {claim.claimer?.avatar_url ? (
                          <img
                            className="h-10 w-10 rounded-full"
                            src={claim.claimer.avatar_url}
                            alt={claim.claimer.name}
                          />
                        ) : (
                          <div className="h-10 w-10 rounded-full bg-[#2CABE3]/20 flex items-center justify-center">
                            <i className="fas fa-user text-[#2CABE3]"></i>
                          </div>
                        )}
                        <div className="ml-4">
                          <div className="text-sm font-medium text-gray-900">
                            {claim.claimer?.name || 'Unknown User'}
                          </div>
                          <div className="text-sm text-gray-500">{claim.claimer?.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm text-gray-900">
                        {claim.food_listing?.title || 'N/A'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {claim.quantity || 0} {claim.food_listing?.unit || ''}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {claim.food_listing?.community_id ? (communities[claim.food_listing.community_id] || 'Unknown') : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(claim.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                        claim.status === 'completed'
                          ? 'bg-[#2CABE3]/20 text-[#2CABE3]'
                          : 'bg-yellow-100 text-yellow-800'
                      }`}>
                        {claim.status || 'pending'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <Button
                        variant={claim.status === 'completed' ? 'secondary' : 'primary'}
                        size="sm"
                        onClick={() => handleMarkReceived(claim.id, claim.status)}
                      >
                        {claim.status === 'completed' ? 'Mark Pending' : 'Mark Received'}
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
};

export default DistributionAttendees;
