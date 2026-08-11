import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

jest.mock('../utils/AuthContext', () => ({
  useAuthContext: jest.fn(),
}));

jest.mock('../utils/hooks/useCommunityRole', () => ({
  useCommunityRole: jest.fn(),
}));

import { useAuthContext } from '../utils/AuthContext';
import { useCommunityRole } from '../utils/hooks/useCommunityRole';
import RecipientRoute from '../components/common/RecipientRoute';

beforeEach(() => {
  jest.clearAllMocks();
});

const renderRecipientRoute = ({
  auth = {},
  role = null,
  allowGuest = false,
  path = '/find',
} = {}) => {
  useAuthContext.mockReturnValue({
    isAuthenticated: false,
    loading: false,
    initialized: true,
    ...auth,
  });
  useCommunityRole.mockReturnValue(role);

  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/find"
          element={
            <RecipientRoute allowGuest={allowGuest}>
              <div data-testid="recipient-content">Find Food</div>
            </RecipientRoute>
          }
        />
        <Route
          path="/near-me"
          element={
            <RecipientRoute>
              <div data-testid="recipient-content">Near Me</div>
            </RecipientRoute>
          }
        />
        <Route path="/community-requests" element={<div data-testid="community-requests">Community Requests</div>} />
        <Route path="/login" element={<div data-testid="login-page">Login</div>} />
      </Routes>
    </MemoryRouter>
  );
};

describe('RecipientRoute', () => {
  test('allows guests on allowGuest routes', () => {
    renderRecipientRoute({ allowGuest: true });
    expect(screen.getByTestId('recipient-content')).toBeInTheDocument();
  });

  test('redirects authenticated donors to community requests', () => {
    renderRecipientRoute({
      allowGuest: true,
      auth: { isAuthenticated: true },
      role: 'donor',
    });
    expect(screen.getByTestId('community-requests')).toBeInTheDocument();
    expect(screen.queryByTestId('recipient-content')).not.toBeInTheDocument();
  });

  test('allows authenticated recipients on allowGuest routes', () => {
    renderRecipientRoute({
      allowGuest: true,
      auth: { isAuthenticated: true },
      role: 'recipient',
    });
    expect(screen.getByTestId('recipient-content')).toBeInTheDocument();
  });

  test('requires login on protected recipient routes', () => {
    renderRecipientRoute({ path: '/near-me' });
    expect(screen.getByTestId('login-page')).toBeInTheDocument();
  });

  test('blocks donors on protected recipient routes', () => {
    renderRecipientRoute({
      path: '/near-me',
      auth: { isAuthenticated: true },
      role: 'donor',
    });
    expect(screen.getByTestId('community-requests')).toBeInTheDocument();
  });
});
