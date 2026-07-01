import { useState, useEffect } from 'react';
import { useAuthContext } from '../utils/AuthContext';
import dataService from '../utils/dataService';
import DonationScheduleForm from '../components/donations/DonationScheduleForm';
import DonationScheduleList from '../components/donations/DonationScheduleList';
import Card from '../components/common/Card';
import Button from '../components/common/Button';

const DonationSchedules = () => {
  const { user } = useAuthContext();
  const [showForm, setShowForm] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState(null);
  const [stats, setStats] = useState({
    totalDonated: 0,
    totalDonations: 0,
    activeSchedules: 0
  });
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (user?.id) {
      loadStats();
    }
  }, [user?.id, refreshKey]);

  const loadStats = async () => {
    try {
      const data = await dataService.getUserDonationStats(user.id);
      setStats(data);
    } catch (error) {
      console.error('Failed to load donation stats:', error);
    }
  };

  const handleEdit = (schedule) => {
    setEditingSchedule(schedule);
    setShowForm(true);
  };

  const handleFormSuccess = () => {
    setShowForm(false);
    setEditingSchedule(null);
    setRefreshKey(prev => prev + 1);
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingSchedule(null);
  };

  const handleCreateNew = () => {
    setEditingSchedule(null);
    setShowForm(true);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40">
      {/* Hero */}
      <header className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10" aria-hidden="true">
          <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
          <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
        </div>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
          <div className="text-center">
            <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
              <i className="fas fa-calendar-check mr-2" aria-hidden="true"></i>
              Recurring Giving
            </span>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
              Donation{" "}
              <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                Schedules
              </span>
            </h1>
            <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
              Set up recurring donations to support the community on a regular basis.
            </p>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card>
            <div className="text-center">
              <p className="text-sm text-gray-600 mb-1">Total Donated</p>
              <p className="text-3xl font-bold text-primary-600">
                ${stats.totalDonated.toFixed(2)}
              </p>
            </div>
          </Card>

          <Card>
            <div className="text-center">
              <p className="text-sm text-gray-600 mb-1">Total Donations</p>
              <p className="text-3xl font-bold text-blue-600">
                {stats.totalDonations}
              </p>
            </div>
          </Card>

          <Card>
            <div className="text-center">
              <p className="text-sm text-gray-600 mb-1">Active Schedules</p>
              <p className="text-3xl font-bold text-purple-600">
                {stats.activeSchedules}
              </p>
            </div>
          </Card>
        </div>

        {!showForm && (
          <div className="mb-6">
            <Button onClick={handleCreateNew}>
              <svg className="h-5 w-5 mr-2 inline" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Create New Schedule
            </Button>
          </div>
        )}

        {showForm && (
          <div className="mb-8">
            <DonationScheduleForm
              schedule={editingSchedule}
              onSuccess={handleFormSuccess}
              onCancel={handleFormCancel}
            />
          </div>
        )}

        <DonationScheduleList
          key={refreshKey}
          userId={user?.id}
          onEdit={handleEdit}
        />
      </div>
    </div>
  );
};

export default DonationSchedules;
