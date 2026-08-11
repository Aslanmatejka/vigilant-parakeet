import React from 'react';
import PropTypes from 'prop-types';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthContext } from '../../utils/AuthContext';
import { useCommunityRole } from '../../utils/hooks/useCommunityRole';

const DEFAULT_DONOR_REDIRECT = '/community-requests';

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
 * Routes for recipients (and guests when allowGuest).
 * Authenticated donors are redirected — they share food via /share and
 * fulfill needs on /community-requests instead of browsing/claiming/requesting.
 */
function RecipientRoute({ children, allowGuest = false, redirectTo = DEFAULT_DONOR_REDIRECT }) {
    const { isAuthenticated, loading, initialized } = useAuthContext();
    const communityRole = useCommunityRole();
    const location = useLocation();
    const isDonor = isAuthenticated && communityRole === 'donor';

    if (!allowGuest) {
        if (isAuthenticated) {
            if (isDonor) {
                return <Navigate to={redirectTo} replace />;
            }
            return children;
        }
        if (loading || !initialized) {
            return <LoadingScreen />;
        }
        const redirectPath = location.pathname + location.search;
        return <Navigate to={`/login?redirect=${encodeURIComponent(redirectPath)}`} replace />;
    }

    if (isDonor) {
        return <Navigate to={redirectTo} replace />;
    }
    return children;
}

RecipientRoute.propTypes = {
    children: PropTypes.node.isRequired,
    allowGuest: PropTypes.bool,
    redirectTo: PropTypes.string,
};

export default RecipientRoute;
