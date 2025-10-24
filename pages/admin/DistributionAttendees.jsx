import React from 'react';
import AdminLayout from './AdminLayout';
import supabase from '../../utils/supabaseClient';
import Button from '../../components/common/Button';

const DistributionAttendees = () => {
  const [attendees, setAttendees] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [stats, setStats] = React.useState({
    totalClaims: 0,
    totalPeople: 0,
    totalStudents: 0,
    totalStaff: 0
  });

  React.useEffect(() => {
    fetchAttendees();

    const subscription = supabase
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

    return () => {
      supabase.removeChannel(subscription);
    };
  }, []);

  const fetchAttendees = async () => {
    try {
      setLoading(true);

      const { data: claims, error } = await supabase
        .from('food_claims')
        .select(`
          *,
          claimer:users!food_claims_claimer_id_fkey(
            id,
            name,
            email,
            phone,
            avatar_url
          ),
          listing:food_listings(
            id,
            title,
            name
          )
        `)
        .order('claimed_at', { ascending: false });

      if (error) throw error;

      const claimsData = claims || [];
      setAttendees(claimsData);

      const totalClaims = claimsData.length;
      const totalPeople = claimsData.reduce((sum, claim) => sum + (claim.people || 0), 0);
      const totalStudents = claimsData.reduce((sum, claim) => sum + (claim.students || 0), 0);
      const totalStaff = claimsData.reduce((sum, claim) => sum + (claim.school_staff || 0), 0);

      setStats({
        totalClaims,
        totalPeople,
        totalStudents,
        totalStaff
      });
    } catch (error) {
      console.error('Error fetching attendees:', error);
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

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
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
            <div className="flex-shrink-0 bg-green-100 rounded-full p-3">
              <i className="fas fa-users text-green-600 text-xl"></i>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Total People</p>
              <p className="text-2xl font-bold text-gray-900">{stats.totalPeople}</p>
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
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading attendees...</p>
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
                    People
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Breakdown
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
                          <div className="h-10 w-10 rounded-full bg-green-100 flex items-center justify-center">
                            <i className="fas fa-user text-green-600"></i>
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
                        {claim.listing?.title || claim.listing?.name || 'N/A'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {claim.people || 0} people
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <div>Students: {claim.students || 0}</div>
                      <div>Staff: {claim.school_staff || 0}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(claim.claimed_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                        claim.status === 'completed'
                          ? 'bg-green-100 text-green-800'
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
