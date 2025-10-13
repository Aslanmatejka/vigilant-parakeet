import React, { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthContext } from '../../utils/AuthContext';

/**
 * AdminRoute - Protected route component that redirects to login if:
 * 1. User is not authenticated
 * 2. User is not an admin
 */
function AdminRoute({ children }) {
  const { isAuthenticated, isAdmin, loading } = useAuthContext();

  // Show loading state while checking authentication
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-green-500"></div>
      </div>
    );
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login?redirect=/admin" replace />;
  }

  // Redirect to homepage if authenticated but not admin
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  // Render children if user is authenticated and is an admin
  return children;
}

export default AdminRoute;
