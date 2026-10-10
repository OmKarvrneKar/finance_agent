import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import RecurringBillsCalendar from '../components/RecurringBillsCalendar';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  getRecurringCalendar: vi.fn(),
}));

import { getRecurringCalendar, getMe } from '../utils/api';

const mockCalendar = {
  bills: [],
  start_date: '2026-09-15',
  end_date: '2026-10-15',
  total_expected_amount: '0.00',
  count: 0,
};

const view = (props) => (
  <MemoryRouter>
    <AuthProvider>
      <RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" {...props} />
    </AuthProvider>
  </MemoryRouter>
);

const lastCall = () => getRecurringCalendar.mock.calls[getRecurringCalendar.mock.calls.length - 1][0];

describe('RecurringBillsCalendar account scoping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    getMe.mockResolvedValue({ email: 'test@test.com' });
    getRecurringCalendar.mockResolvedValue(mockCalendar);
  });

  it('omits account_id when no account is selected', async () => {
    render(view());
    await waitFor(() => expect(screen.getByTestId('empty-state')).toBeInTheDocument());
    const arg = getRecurringCalendar.mock.calls[0][0];
    expect(arg.start_date).toBe('2026-09-15');
    expect(arg.end_date).toBe('2026-10-15');
    expect(arg).not.toHaveProperty('account_id');
  });

  it('sends account_id when an account is selected', async () => {
    render(view({ accountId: 7 }));
    await waitFor(() => expect(getRecurringCalendar).toHaveBeenCalledTimes(1));
    expect(getRecurringCalendar.mock.calls[0][0]).toHaveProperty('account_id', 7);
  });

  it('refetches when the selected account changes', async () => {
    const { rerender } = render(view({ accountId: 5 }));
    await waitFor(() => expect(getRecurringCalendar).toHaveBeenCalledTimes(1));
    expect(getRecurringCalendar.mock.calls[0][0]).toHaveProperty('account_id', 5);

    rerender(view({ accountId: 6 }));
    await waitFor(() => {
      expect(lastCall()).toHaveProperty('account_id', 6);
    });
    expect(getRecurringCalendar.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('drops account_id when switching back to All Accounts', async () => {
    const { rerender } = render(view({ accountId: 5 }));
    await waitFor(() => expect(getRecurringCalendar).toHaveBeenCalledTimes(1));

    rerender(view());
    await waitFor(() => {
      expect(lastCall()).not.toHaveProperty('account_id');
    });
    expect(getRecurringCalendar.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
