import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// Mock AuthContext
jest.mock('../utils/AuthContext', () => ({
  useAuthContext: jest.fn(),
  AuthProvider: ({ children }) => <div>{children}</div>,
}));

import { useAuthContext } from '../utils/AuthContext';

// Minimal ProtectedRoute matching app.jsx implementation
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading, initialized } = useAuthContext();
  const { useLocation, Navigate } = require('react-router-dom');
  const currentLocation = useLocation();

  if (isAuthenticated) return children;

  if (loading || !initialized) {
    return <div>Loading...</div>;
  }

  const redirectPath = currentLocation.pathname + currentLocation.search;
  return <Navigate to={`/login?redirect=${encodeURIComponent(redirectPath)}`} replace />;
};

beforeEach(() => {
  jest.clearAllMocks();
});

const renderRoute = (authState, initialPath = '/protected') => {
  useAuthContext.mockReturnValue({
    isAuthenticated: false,
    loading: false,
    initialized: true,
    ...authState,
  });

  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/protected"
          element={
            <ProtectedRoute>
              <div data-testid="secret">Protected Content</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div data-testid="login-page">Login Page</div>} />
      </Routes>
    </MemoryRouter>
  );
};

describe('ProtectedRoute', () => {
  test('renders children when user is authenticated', () => {
    renderRoute({ isAuthenticated: true });
    expect(screen.getByTestId('secret')).toHaveTextContent('Protected Content');
  });

  test('redirects to /login when not authenticated and initialized', () => {
    renderRoute({ isAuthenticated: false, loading: false, initialized: true });
    expect(screen.getByTestId('login-page')).toBeInTheDocument();
    expect(screen.queryByTestId('secret')).not.toBeInTheDocument();
  });

  test('shows loading spinner when still initializing', () => {
    renderRoute({ isAuthenticated: false, loading: true, initialized: false });
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.queryByTestId('secret')).not.toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  test('shows loading spinner when loading is false but not initialized', () => {
    renderRoute({ isAuthenticated: false, loading: false, initialized: false });
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  test('prioritizes isAuthenticated over loading state', () => {
    // Even if still loading, isAuthenticated from localStorage lets through
    renderRoute({ isAuthenticated: true, loading: true, initialized: false });
    expect(screen.getByTestId('secret')).toHaveTextContent('Protected Content');
  });
});
