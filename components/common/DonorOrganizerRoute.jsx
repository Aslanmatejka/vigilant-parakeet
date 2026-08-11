import React from 'react';
import PropTypes from 'prop-types';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthContext } from '../../utils/AuthContext';
import { useCommunityRole } from '../../utils/hooks/useCommunityRole';

function LoadingScreen() {
    return (
        <div className="min-h-screen flex items-center justify-center">
            <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mx-auto mb-4" />
                <p className="text-gray-600">Loading...</p>
            </div>
        </div>
    );
}

/**
 * Share/listings flows — donors and organizers (plus admins). Recipients are
 * redirected to Find Food; they request/claim instead of posting donations.
 */
function DonorOrganizerRoute({ children, redirectTo = '/find' }) {
    const { isAuthenticated, isAdmin, loading, initialized } = useAuthContext();
    const communityRole = useCommunityRole();
    const location = useLocation();
    const canShare = isAdmin
        || communityRole === 'donor'
        || communityRole === 'organizer';

    if (loading || !initialized) {
        return <LoadingScreen />;
    }

    if (!isAuthenticated) {
        const redirectPath = location.pathname + location.search;
        return (
            <Navigate
                to={`/login?redirect=${encodeURIComponent(redirectPath)}`}
                replace
            />
        );
    }

    if (communityRole === 'recipient') {
        return <Navigate to={redirectTo} replace />;
    }

    if (!canShare && communityRole) {
        return <Navigate to={redirectTo} replace />;
    }

    return children;
}

DonorOrganizerRoute.propTypes = {
    children: PropTypes.node.isRequired,
    redirectTo: PropTypes.string,
};

export default DonorOrganizerRoute;
