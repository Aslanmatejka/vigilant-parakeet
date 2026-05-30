import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const mockNavigate = jest.fn();
const mockSearchParams = new URLSearchParams();
const mockSignIn = jest.fn(() => Promise.resolve());

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
  useSearchParams: () => [mockSearchParams],
}));

jest.mock('../utils/AuthContext', () => ({
  useAuthContext: jest.fn(() => ({
    signIn: mockSignIn,
    isAuthenticated: false,
    loading: false,
  })),
}));

jest.mock('../components/common/Button', () => {
  return function MockButton({ children, onClick, type, loading, disabled, ...props }) {
    return (
      <button type={type} onClick={onClick} disabled={disabled || loading} {...props}>
        {loading ? 'Loading...' : children}
      </button>
    );
  };
});

jest.mock('../components/common/Input', () => {
  return function MockInput({ id, name, type, value, onChange, ...props }) {
    return (
      <input id={id} name={name} type={type} value={value} onChange={onChange} {...props} />
    );
  };
});

import LoginPage from '../pages/LoginPage';
import { useAuthContext } from '../utils/AuthContext';

beforeEach(() => {
  jest.clearAllMocks();
  mockSearchParams.delete('message');
  mockSearchParams.delete('redirect');
  window.scrollTo = jest.fn();
  window.history.replaceState = jest.fn();
  useAuthContext.mockReturnValue({
    signIn: mockSignIn,
    isAuthenticated: false,
    loading: false,
  });
});

const renderLogin = () => {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <LoginPage />
    </MemoryRouter>
  );
};

describe('LoginPage', () => {
  test('renders sign in heading', () => {
    renderLogin();
    expect(screen.getByText('Sign in to your account')).toBeInTheDocument();
  });

  test('renders email and password fields', () => {
    renderLogin();
    expect(screen.getByLabelText('Email address')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });

  test('renders forgot password link', () => {
    renderLogin();
    expect(screen.getByText('Forgot password?')).toBeInTheDocument();
  });

  test('shows error for empty fields', async () => {
    renderLogin();
    const form = document.querySelector('form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Please fill in all required fields')).toBeInTheDocument();
    });
  });

  test('shows error for invalid email', async () => {
    renderLogin();
    const emailInput = screen.getByLabelText('Email address');
    const passwordInput = document.getElementById('password');

    fireEvent.change(emailInput, { target: { value: 'bad-email', name: 'email' } });
    fireEvent.change(passwordInput, { target: { value: 'password123', name: 'password' } });

    const form = document.querySelector('form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Please enter a valid email address')).toBeInTheDocument();
    });
  });

  test('shows error for short password', async () => {
    renderLogin();
    const emailInput = screen.getByLabelText('Email address');
    const passwordInput = document.getElementById('password');

    fireEvent.change(emailInput, { target: { value: 'user@test.com', name: 'email' } });
    fireEvent.change(passwordInput, { target: { value: 'short', name: 'password' } });

    const form = document.querySelector('form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Password must be at least 8 characters long')).toBeInTheDocument();
    });
  });

  test('calls signIn with email and password on valid submit', async () => {
    mockSignIn.mockResolvedValue();
    renderLogin();

    const emailInput = screen.getByLabelText('Email address');
    const passwordInput = document.getElementById('password');

    fireEvent.change(emailInput, { target: { value: 'user@test.com', name: 'email' } });
    fireEvent.change(passwordInput, { target: { value: 'password123', name: 'password' } });

    const form = document.querySelector('form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockSignIn).toHaveBeenCalledWith('user@test.com', 'password123');
    });
  });

  test('shows server error on signIn failure', async () => {
    mockSignIn.mockRejectedValue(new Error('Invalid login credentials'));
    renderLogin();

    const emailInput = screen.getByLabelText('Email address');
    const passwordInput = document.getElementById('password');

    fireEvent.change(emailInput, { target: { value: 'user@test.com', name: 'email' } });
    fireEvent.change(passwordInput, { target: { value: 'password123', name: 'password' } });

    const form = document.querySelector('form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Invalid email or password')).toBeInTheDocument();
    });
  });

  test('redirects when already authenticated', () => {
    useAuthContext.mockReturnValue({
      signIn: mockSignIn,
      isAuthenticated: true,
      loading: false,
    });

    renderLogin();

    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
  });

  test('clears error when input changes', async () => {
    renderLogin();

    // Trigger error first
    const form = document.querySelector('form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Please fill in all required fields')).toBeInTheDocument();
    });

    // Change input should clear error
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'a', name: 'email' },
    });

    expect(screen.queryByText('Please fill in all required fields')).not.toBeInTheDocument();
  });

  test('toggles password visibility', () => {
    renderLogin();
    const passwordInput = document.getElementById('password');
    expect(passwordInput).toHaveAttribute('type', 'password');

    // Find the eye toggle button (the button inside the password field div)
    const toggleBtn = passwordInput.parentElement.querySelector('button');
    fireEvent.click(toggleBtn);

    expect(passwordInput).toHaveAttribute('type', 'text');
  });
});
