import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthContext } from '../../utils/AuthContext';

function LoadingScreen() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#2CABE3]" />
    </div>
  );
}

/**
 * AdminRoute - Protected route component that redirects to login if:
 * 1. User is not authenticated
 * 2. User is not an admin
 */
function AdminRoute({ children }) {
  const { isAuthenticated, isAdmin, loading, initialized } = useAuthContext();
  const location = useLocation();

  if (loading || !initialized) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    const redirectPath = location.pathname + location.search;
    return (
      <Navigate
        to={`/login?redirect=${encodeURIComponent(redirectPath || '/admin')}`}
        replace
      />
    );
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  return children;
}

export default AdminRoute;
