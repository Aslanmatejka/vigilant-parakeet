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

jest.mock('../utils/hooks/useCommunityRole.js', () => ({
  useCommunityRole: jest.fn(() => ''),
}));

jest.mock('../utils/dataService', () => ({
  __esModule: true,
  default: {
    countLiveListings: jest.fn(() => Promise.resolve(0)),
  },
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
import { useCommunityRole } from '../utils/hooks/useCommunityRole.js';

beforeEach(() => {
  jest.clearAllMocks();
  useCommunityRole.mockReturnValue('');
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
    // Nav label was rebranded "Sponsors" → "Partners" (href /sponsors stays).
    expect(screen.getByText('Partners')).toBeInTheDocument();
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

  test('recipient nav shows Find/Request Food but not Community Requests or Share Food', () => {
    useCommunityRole.mockReturnValue('recipient');
    renderHeader({
      isAuthenticated: true,
      user: { name: 'Recipient User', community_role: 'recipient' },
    });

    expect(screen.getAllByText('Find Food').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Request Food').length).toBeGreaterThan(0);
    expect(screen.queryByText('Community Requests')).not.toBeInTheDocument();
    expect(screen.queryByText('Share Food')).not.toBeInTheDocument();
  });

  test('donor nav shows Share Food and Community Requests but not Find/Request Food', () => {
    useCommunityRole.mockReturnValue('donor');
    renderHeader({
      isAuthenticated: true,
      user: { name: 'Donor User', community_role: 'donor' },
    });

    expect(screen.getAllByText('Share Food').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Community Requests').length).toBeGreaterThan(0);
    expect(screen.queryByText('Find Food')).not.toBeInTheDocument();
    expect(screen.queryByText('Request Food')).not.toBeInTheDocument();
  });
});
