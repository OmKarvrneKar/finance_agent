import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import Subscriptions from '../pages/Subscriptions';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  fetchSubscriptions: vi.fn(),
  getAccounts: vi.fn(),
}));

import { fetchSubscriptions, getAccounts, getMe } from '../utils/api';

const mockSubs = [
  {
    description: 'Netflix',
    category: 'Subscriptions',
    occurrences: 4,
    average_amount: 17.99,
    frequency: 'Bi-weekly',
    estimated_monthly_cost: 38.8584,
    estimated_annual_cost: 466.3008,
    last_seen: '2026-09-01',
    is_user_confirmed: true,
  },
  {
    description: 'Gym',
    category: 'Healthcare',
    occurrences: 2,
    average_amount: 40,
    frequency: 'Monthly',
    estimated_monthly_cost: 40,
    estimated_annual_cost: 480,
    last_seen: '2026-09-10',
    is_user_confirmed: false,
  },
];

const mockAccounts = [
  { id: 1, name: 'HDFC Salary', account_type: 'bank', is_active: true },
  { id: 3, name: 'HDFC Credit Card', account_type: 'credit_card', is_active: true },
];

const renderPage = () => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Subscriptions />
      </AuthProvider>
    </MemoryRouter>
  );
};

const lastSubsCall = () => fetchSubscriptions.mock.calls[fetchSubscriptions.mock.calls.length - 1][0];

describe('Subscriptions account selector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    getAccounts.mockResolvedValue(mockAccounts);
    fetchSubscriptions.mockImplementation((account_id) =>
      Promise.resolve(account_id ? mockSubs.filter((s) => s.description === 'Gym') : mockSubs)
    );
  });

  it('loads active accounts and requests subscriptions without account_id initially', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Netflix')).toBeInTheDocument());
    expect(getAccounts).toHaveBeenCalledWith({ is_active: true });
    expect(fetchSubscriptions.mock.calls[0][0]).toBeUndefined();

    const select = screen.getByLabelText('Filter by account');
    expect(select).toBeInTheDocument();
    expect(screen.getByText('All Accounts')).toBeInTheDocument();
    expect(screen.getByText('HDFC Salary')).toBeInTheDocument();
    expect(screen.getByText('HDFC Credit Card')).toBeInTheDocument();
    // Both subscriptions from the all-accounts response are rendered.
    expect(screen.getByText('Gym')).toBeInTheDocument();
  });

  it('refetches with the selected account and renders the scoped response', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Netflix')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '3' } });
    await waitFor(() => expect(lastSubsCall()).toBe('3'));
    // Scoped response (Gym only) replaces the unfiltered list.
    await waitFor(() => expect(screen.queryByText('Netflix')).not.toBeInTheDocument());
    expect(screen.getByText('Gym')).toBeInTheDocument();
  });

  it('switching back to All Accounts refetches without account_id', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Netflix')).toBeInTheDocument());

    const select = screen.getByLabelText('Filter by account');
    fireEvent.change(select, { target: { value: '3' } });
    await waitFor(() => expect(lastSubsCall()).toBe('3'));

    fireEvent.change(select, { target: { value: '' } });
    await waitFor(() => expect(lastSubsCall()).toBeUndefined());
    await waitFor(() => expect(screen.getByText('Netflix')).toBeInTheDocument());
    expect(fetchSubscriptions.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it('shows the empty state when the scoped response is empty', async () => {
    fetchSubscriptions.mockImplementation((account_id) => Promise.resolve(account_id ? [] : mockSubs));
    renderPage();
    await waitFor(() => expect(screen.getByText('Netflix')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() =>
      expect(screen.getByText('No recurring subscriptions detected yet.')).toBeInTheDocument()
    );
    expect(screen.queryByText('Netflix')).not.toBeInTheDocument();
  });

  it('keeps working when the accounts request fails', async () => {
    getAccounts.mockRejectedValue(new Error('network down'));
    renderPage();
    await waitFor(() => expect(screen.getByText('Netflix')).toBeInTheDocument());
    const select = screen.getByLabelText('Filter by account');
    expect(select.options.length).toBe(1);
    expect(select.options[0].textContent).toBe('All Accounts');
    expect(fetchSubscriptions.mock.calls[0][0]).toBeUndefined();
  });
});
