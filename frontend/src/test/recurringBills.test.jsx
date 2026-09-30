import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
  bills: [
    {
      description: 'Netflix',
      category: 'Subscriptions',
      expected_amount: '15.99',
      expected_date: '2026-10-01',
      date_status: 'projected',
      frequency: 'Monthly',
      is_user_confirmed: false,
      occurrences: 2,
      last_seen: '2026-09-01',
    },
    {
      description: 'Gym Membership',
      category: 'Healthcare',
      expected_amount: '40.00',
      expected_date: null,
      date_status: 'uncertain',
      frequency: 'Monthly (Assumed)',
      is_user_confirmed: true,
      occurrences: 1,
      last_seen: '2026-09-01',
    },
    {
      description: 'Mystery Charge',
      category: 'Other',
      expected_amount: '5.00',
      expected_date: null,
      date_status: 'missing',
      frequency: 'Unknown',
      is_user_confirmed: false,
      occurrences: 0,
      last_seen: 'Unknown',
    },
  ],
  start_date: '2026-09-15',
  end_date: '2026-10-15',
  total_expected_amount: '60.99',
  count: 3,
};

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(
    <MemoryRouter>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>
  );
};

describe('RecurringBillsCalendar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('calendar renders with month grid', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('calendar-view')).toBeInTheDocument();
    });
    expect(screen.getByText('September 2026')).toBeInTheDocument();
    expect(screen.getByText('October 2026')).toBeInTheDocument();
  });

  it('recurring bill renders in calendar and list', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('bill-Netflix')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('view-list'));
    await waitFor(() => {
      expect(screen.getByTestId('list-view')).toBeInTheDocument();
      expect(screen.getByTestId('bill-Netflix')).toBeInTheDocument();
      expect(screen.getByTestId('bill-Gym Membership')).toBeInTheDocument();
      expect(screen.getByTestId('bill-Mystery Charge')).toBeInTheDocument();
    });
  });

  it('expected amount displays', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('bill-Netflix')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('view-list'));
    await waitFor(() => {
      expect(screen.getByTestId('amount-Netflix')).toHaveTextContent('₹15.99');
      expect(screen.getByTestId('amount-Gym Membership')).toHaveTextContent('₹40.00');
    });
  });

  it('projected date displays', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('bill-Netflix')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('view-list'));
    await waitFor(() => {
      expect(screen.getByTestId('date-Netflix')).toHaveTextContent(/Oct/);
      expect(screen.getByTestId('date-status-projected')).toBeInTheDocument();
    });
  });

  it('uncertain date displays correctly', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('undated-bills')).toBeInTheDocument();
      expect(screen.getByTestId('bill-Gym Membership')).toBeInTheDocument();
      expect(screen.getAllByText(/Date uncertain/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText(/No fixed date/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('missing date displays correctly', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('bill-Mystery Charge')).toBeInTheDocument();
      expect(screen.getAllByText('Date missing').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('date-range changes trigger correct API request', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(getRecurringCalendar).toHaveBeenCalledWith({
        start_date: '2026-09-15',
        end_date: '2026-10-15',
      });
    });

    fireEvent.change(screen.getByTestId('range-start'), { target: { value: '2026-10-01' } });
    fireEvent.change(screen.getByTestId('range-end'), { target: { value: '2026-10-31' } });

    await waitFor(() => {
      expect(getRecurringCalendar).toHaveBeenCalledWith({
        start_date: '2026-10-01',
        end_date: '2026-10-31',
      });
    });
  });

  it('preset buttons update date range and API request', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar />);
    await waitFor(() => {
      expect(getRecurringCalendar).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(screen.getByTestId('preset-60'));
    await waitFor(() => {
      expect(getRecurringCalendar).toHaveBeenCalledTimes(2);
      const lastCall = getRecurringCalendar.mock.calls[1][0];
      expect(lastCall.start_date).toBeTruthy();
      expect(lastCall.end_date).toBeTruthy();
      expect(lastCall.start_date < lastCall.end_date).toBe(true);
    });
  });

  it('total expected amount displays', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('total-expected')).toHaveTextContent('₹60.99');
    });
  });

  it('empty state', async () => {
    getRecurringCalendar.mockResolvedValue({
      bills: [],
      start_date: '2026-09-15',
      end_date: '2026-10-15',
      total_expected_amount: '0.00',
      count: 0,
    });
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      expect(screen.getByText('No upcoming recurring bills')).toBeInTheDocument();
    });
  });

  it('loading state', () => {
    getRecurringCalendar.mockReturnValue(new Promise(() => {}));
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
    expect(document.querySelector('.skeleton')).toBeTruthy();
  });

  it('API error state', async () => {
    getRecurringCalendar.mockRejectedValue(new Error('Network error'));
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('error-state')).toBeInTheDocument();
      expect(screen.getByText('Failed to load recurring bills calendar')).toBeInTheDocument();
    });
  });

  it('authenticated request uses getRecurringCalendar', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(getRecurringCalendar).toHaveBeenCalled();
    });
    const arg = getRecurringCalendar.mock.calls[0][0];
    expect(arg).toHaveProperty('start_date');
    expect(arg).toHaveProperty('end_date');
  });

  it('shows frequency and category on list view', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('bill-Netflix')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('view-list'));
    await waitFor(() => {
      expect(screen.getAllByText(/Monthly/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Subscriptions')).toBeInTheDocument();
    });
  });

  it('shows user-confirmed status when available', async () => {
    getRecurringCalendar.mockResolvedValue(mockCalendar);
    renderWithAuth(<RecurringBillsCalendar startDate="2026-09-15" endDate="2026-10-15" />);
    await waitFor(() => {
      expect(screen.getByTestId('bill-Gym Membership')).toBeInTheDocument();
      expect(screen.getAllByText('Confirmed').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('AI detected').length).toBeGreaterThanOrEqual(1);
    });
  });
});
