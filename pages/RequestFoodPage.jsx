import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import Button from '../components/common/Button';
import ErrorBoundary from '../components/common/ErrorBoundary';
import RequestFoodForm from '../components/food/RequestFoodForm';
import { useAuth } from '../utils/hooks/useSupabase';
import dataService from '../utils/dataService';
import supabase from '../utils/supabaseClient';
import { reportError } from '../utils/helpers';

function RequestFoodPageContent() {
  const navigate = useNavigate();
  const { user: authUser, isAuthenticated } = useAuth();
  const [loading, setLoading] = React.useState(false);
  const [submitError, setSubmitError] = React.useState(null);

  const handleSubmit = async (formData) => {
    setLoading(true);
    setSubmitError(null);
    try {
      if (!authUser || !isAuthenticated) {
        setSubmitError('Please log in to submit a food request.');
        setLoading(false);
        return;
      }

      let communityId = authUser.community_id || null;
      if (formData.school_district) {
        const { data: community } = await supabase
          .from('communities')
          .select('id')
          .eq('name', formData.school_district)
          .maybeSingle();
        if (community) communityId = community.id;
      }

      const listingData = {
        ...formData,
        user_id: authUser.id,
        community_id: communityId,
        listing_type: 'request',
      };
      if (listingData.expiry_date === '') listingData.expiry_date = null;
      if (listingData.pickup_by === '') listingData.pickup_by = null;

      const created = await dataService.createFoodListing(listingData);
      const status = String(created?.status || '').toLowerCase();

      window.dispatchEvent(new CustomEvent('foodShared'));

      if (status === 'pending') {
        toast.success('Request submitted for admin review. You’ll see it under Pending on My Listings.');
        navigate('/profile?tab=listings&filter=pending');
      } else {
        toast.success('Request posted — donors in your community can see it.');
        navigate('/profile?tab=listings');
      }
    } catch (error) {
      console.error('Request food submit failed:', error);
      reportError(error);
      setSubmitError(error.message || 'Failed to submit food request.');
      toast.error(error.message || 'Failed to submit food request.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      data-name="request-food-page"
      className="min-h-screen bg-gradient-to-b from-[#2CABE3]/5 via-white to-emerald-50/40"
      role="main"
    >
      <header className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10" aria-hidden="true">
          <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#2CABE3]/15 blur-3xl" />
          <div className="absolute top-10 -right-24 w-96 h-96 rounded-full bg-emerald-300/20 blur-3xl" />
        </div>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12 sm:pt-20 sm:pb-16">
          <div className="text-center">
            <span className="inline-flex items-center px-3 py-1 rounded-full bg-[#2CABE3]/10 text-[#2CABE3] text-xs font-semibold mb-5 ring-1 ring-[#2CABE3]/20">
              <i className="fas fa-hand-holding-heart mr-2" aria-hidden="true" />
              Food Near You
            </span>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-5 tracking-tight">
              Request Food{' '}
              <span className="bg-gradient-to-r from-[#2CABE3] to-emerald-500 bg-clip-text text-transparent">
                Assistance
              </span>
            </h1>
            <p className="text-base sm:text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
              If Find Food doesn’t have what you need, post a request for your school
              or community. Neighbors and donors can share matching food when they can.
            </p>
            <p className="mt-4">
              <Link
                to="/find"
                className="inline-flex items-center gap-2 text-sm font-semibold text-[#1a7a9e] hover:text-[#156a8a] underline-offset-4 hover:underline"
              >
                <i className="fas fa-search text-[#2CABE3]" aria-hidden="true" />
                Browse Find Food first
              </Link>
            </p>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 pb-12">
        <div className="mb-4 flex flex-wrap justify-end gap-2">
          <Button onClick={() => navigate('/find')} variant="secondary">
            Back to Find Food
          </Button>
          <Link
            to="/profile?tab=listings"
            className="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium text-[#1a7a9e] bg-white border border-[#2CABE3]/25 hover:bg-[#2CABE3]/10"
          >
            View my requests
          </Link>
        </div>

        <div className="bg-white rounded-2xl shadow-lg overflow-hidden border border-gray-100 p-6 sm:p-8 md:p-10">
          {submitError && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
              {submitError}
            </div>
          )}
          <RequestFoodForm onSubmit={handleSubmit} loading={loading} />
        </div>
      </div>
    </div>
  );
}

function RequestFoodPage() {
  return (
    <ErrorBoundary>
      <RequestFoodPageContent />
    </ErrorBoundary>
  );
}

export default RequestFoodPage;
