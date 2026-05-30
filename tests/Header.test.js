import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock modules before importing component
const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
}));

const mockSignOut = jest.fn(() => Promise.resolve({ success: true }));
const mockStartTutorial = jest.fn();

jest.mock('../utils/AuthContext', () => ({
  useAuthContext: jest.fn(),
}));

jest.mock('../utils/TutorialContext', () => ({
  useTutorial: () => ({ startTutorial: mockStartTutorial }),
}));

jest.mock('../components/common/Avatar', () => {
  return function MockAvatar({ alt }) {
    return <div data-testid="avatar">{alt}</div>;
  };
});

jest.mock('../components/common/Button', () => {
  return function MockButton({ children, onClick }) {
    return <button onClick={onClick}>{children}</button>;
  };
});

import Header from '../components/common/Header';
import { useAuthContext } from '../utils/AuthContext';

beforeEach(() => {
  jest.clearAllMocks();
});

const renderHeader = (authState = {}) => {
  useAuthContext.mockReturnValue({
    user: null,
    isAuthenticated: false,
    signOut: mockSignOut,
    ...authState,
  });

  return render(
    <MemoryRouter>
      <Header />
    </MemoryRouter>
  );
};

describe('Header component', () => {
  test('renders logo and brand name', () => {
    renderHeader();
    expect(screen.getByText('DoGoods')).toBeInTheDocument();
  });

  test('renders navigation links', () => {
    renderHeader();
    expect(screen.getByText('Find Food')).toBeInTheDocument();
    expect(screen.getByText('Impact Story')).toBeInTheDocument();
    expect(screen.getByText('Recipes')).toBeInTheDocument();
    expect(screen.getByText('Sponsors')).toBeInTheDocument();
    expect(screen.getByText('Contact')).toBeInTheDocument();
  });

  test('shows Sign In and Sign Up when not authenticated', () => {
    renderHeader({ isAuthenticated: false });
    const signInLinks = screen.getAllByText('Sign In');
    expect(signInLinks.length).toBeGreaterThan(0);
  });

  test('shows user name when authenticated', () => {
    renderHeader({
      isAuthenticated: true,
      user: { name: 'Jane Doe', email: 'jane@test.com' },
    });
    const matches = screen.getAllByText('Jane Doe');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  test('shows "User" fallback when authenticated with no name', () => {
    renderHeader({
      isAuthenticated: true,
      user: {},
    });
    const matches = screen.getAllByText('User');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  test('calls signOut and navigates on logout click', async () => {
    renderHeader({
      isAuthenticated: true,
      user: { name: 'Jane Doe', email: 'jane@test.com' },
    });

    // Open the user dropdown - click the first Jane Doe (the name span)
    const nameElements = screen.getAllByText('Jane Doe');
    fireEvent.click(nameElements[0]);

    // Click sign out
    const signOutButtons = screen.getAllByText('Sign out');
    fireEvent.click(signOutButtons[0]);

    await waitFor(() => {
      expect(mockSignOut).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    });
  });

  test('navigates home even if signOut throws', async () => {
    mockSignOut.mockRejectedValueOnce(new Error('network error'));

    renderHeader({
      isAuthenticated: true,
      user: { name: 'Jane Doe', email: 'jane@test.com' },
    });

    const nameElements = screen.getAllByText('Jane Doe');
    fireEvent.click(nameElements[0]);
    const signOutButtons = screen.getAllByText('Sign out');
    fireEvent.click(signOutButtons[0]);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    });
  });

  test('toggles mobile menu on hamburger click', () => {
    renderHeader();
    const menuButton = screen.getByRole('button', { name: /open menu/i });
    expect(menuButton).toBeInTheDocument();
    fireEvent.click(menuButton);
    // Mobile menu contains the Menu heading
    expect(screen.getByText('Menu')).toBeInTheDocument();
  });
});
