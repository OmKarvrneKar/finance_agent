import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider, useAuth } from '../context/AuthContext';
import Login from '../pages/Login';
import Register from '../pages/Register';
import ProtectedRoute from '../components/ProtectedRoute';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
}));

import { getMe } from '../utils/api';

beforeEach(() => {
  localStorage.clear();
  getMe.mockReset().mockRejectedValue(new Error('no auth'));
  global.fetch = vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) });
});

const wrap = (ui, { route = '/' } = {}) => (
  <MemoryRouter initialEntries={[route]}>
    <AuthProvider>{ui}</AuthProvider>
  </MemoryRouter>
);

describe('AuthContext', () => {
  it('starts unauthenticated when no token', async () => {
    const TestComp = () => {
      const { isAuthenticated, loading } = useAuth();
      if (loading) return <span>loading</span>;
      return <span>{isAuthenticated ? 'auth' : 'unauth'}</span>;
    };
    render(wrap(<TestComp />));
    await waitFor(() => {
      expect(screen.getByText('unauth')).toBeInTheDocument();
    });
  });

  it('starts authenticated when getMe returns user', async () => {
    getMe.mockResolvedValueOnce({ email: 'test@test.com' });
    const TestComp = () => {
      const { isAuthenticated, user, loading } = useAuth();
      if (loading) return <span>loading</span>;
      return <span>{isAuthenticated ? (user?.email || 'loaded') : 'unauth'}</span>;
    };
    render(wrap(<TestComp />));
    await waitFor(() => {
      expect(screen.getByText('test@test.com')).toBeInTheDocument();
    });
  });
});

describe('Login page', () => {
  it('renders login form', async () => {
    render(wrap(<Login />));
    await waitFor(() => {
      expect(screen.getByText('Sign in')).toBeInTheDocument();
    });
    expect(screen.getByText('Welcome back')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('••••••••')).toBeInTheDocument();
  });

  it('shows register link', async () => {
    render(wrap(<Login />));
    await waitFor(() => {
      expect(screen.getByText('Sign in')).toBeInTheDocument();
    });
    expect(screen.getByText('Register')).toHaveAttribute('href', '/register');
  });

  it('shows error on failed login', async () => {
    global.fetch.mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({ detail: 'Invalid credentials' }) });
    render(wrap(<Login />));
    await waitFor(() => {
      expect(screen.getByText('Sign in')).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), { target: { value: 'bad@test.com' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByText('Sign in'));
    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });
  });
});

describe('Register page', () => {
  it('renders register form', async () => {
    render(wrap(<Register />));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText('John Doe')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument();
  });

  it('shows success message on registration', async () => {
    global.fetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ id: 1 }) });
    render(wrap(<Register />));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText('John Doe'), { target: { value: 'Test User' } });
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), { target: { value: 'new@test.com' } });
    fireEvent.change(screen.getByPlaceholderText('Min 8 characters'), { target: { value: 'Password123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => {
      expect(screen.getByText('Account created! Redirecting to login...')).toBeInTheDocument();
    });
  });

  it('shows error on failed registration', async () => {
    global.fetch.mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({ detail: 'Email already exists' }) });
    render(wrap(<Register />));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText('John Doe'), { target: { value: 'Test' } });
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), { target: { value: 'dup@test.com' } });
    fireEvent.change(screen.getByPlaceholderText('Min 8 characters'), { target: { value: 'Password123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => {
      expect(screen.getByText('Email already exists')).toBeInTheDocument();
    });
  });
});

describe('ProtectedRoute', () => {
  it('redirects to /login when not authenticated', async () => {
    render(wrap(
      <ProtectedRoute><div>secret</div></ProtectedRoute>
    ));
    await waitFor(() => {
      expect(screen.queryByText('secret')).not.toBeInTheDocument();
    });
  });

  it('renders children when authenticated', async () => {
    getMe.mockResolvedValueOnce({ email: 'test@test.com' });
    render(wrap(
      <ProtectedRoute><div>secret</div></ProtectedRoute>
    ));
    await waitFor(() => {
      expect(screen.getByText('secret')).toBeInTheDocument();
    });
  });
});
