import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import Dashboard from '../pages/Dashboard';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  getAnalyticsSummary: vi.fn(),
}));

vi.mock('../components/ForecastAlerts', () => ({ default: () => <div data-testid="forecast-alerts" /> }));
vi.mock('../components/AnomalyAlerts', () => ({ default: () => <div data-testid="anomaly-alerts" /> }));
vi.mock('../components/SavingsRecommendations', () => ({ default: () => <div data-testid="savings-recommendations" /> }));
vi.mock('../components/MerchantAnalytics', () => ({ default: () => <div data-testid="merchant-analytics" /> }));

import { getAnalyticsSummary, getMe } from '../utils/api';

const mockAnalytics = {
  total_income: 50000,
  total_expenses: 30000,
  net_cashflow: 20000,
  transaction_count: 45,
  category_breakdown: [
    { category: 'Groceries', amount: 12000 },
    { category: 'Transport', amount: 8000 },
    { category: 'Food & Dining', amount: 6000 },
    { category: 'Shopping', amount: 4000 },
  ],
  spending_trend: [
    { month: '2026-08', amount: 25000 },
    { month: '2026-09', amount: 30000 },
  ],
};

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

describe('Dashboard page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('shows skeleton loading state', () => {
    getAnalyticsSummary.mockReturnValue(new Promise(() => {}));
    renderWithAuth(<Dashboard />);
    expect(document.querySelector('.skeleton')).toBeTruthy();
  });

  it('renders summary cards after loading', async () => {
    getAnalyticsSummary.mockResolvedValue(mockAnalytics);
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('Total Income')).toBeInTheDocument();
      expect(screen.getByText('Total Expenses')).toBeInTheDocument();
      expect(screen.getByText('Net Cash Flow')).toBeInTheDocument();
      expect(screen.getByText('Transactions')).toBeInTheDocument();
    });
  });

  it('renders period presets', async () => {
    getAnalyticsSummary.mockResolvedValue(mockAnalytics);
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('This Month')).toBeInTheDocument();
      expect(screen.getByText('Last Month')).toBeInTheDocument();
      expect(screen.getByText('All Time')).toBeInTheDocument();
    });
  });

  it('calls getAnalyticsSummary with default preset on mount', async () => {
    getAnalyticsSummary.mockResolvedValue(mockAnalytics);
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      expect(getAnalyticsSummary).toHaveBeenCalledTimes(1);
      const call = getAnalyticsSummary.mock.calls[0][0];
      expect(call.start).toBeTruthy();
      expect(call.end).toBeTruthy();
    });
  });

  it('calls getAnalyticsSummary when preset changes', async () => {
    getAnalyticsSummary.mockResolvedValue(mockAnalytics);
    renderWithAuth(<Dashboard />);
    await waitFor(() => expect(screen.getByText('Last Month')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Last Month'));
    await waitFor(() => {
      expect(getAnalyticsSummary).toHaveBeenCalledTimes(2);
    });
  });

  it('shows date inputs for custom range', async () => {
    getAnalyticsSummary.mockResolvedValue(mockAnalytics);
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      const dateInputs = document.querySelectorAll('input[type="date"]');
      expect(dateInputs.length).toBe(2);
    });
  });

  it('calls getAnalyticsSummary with custom dates', async () => {
    getAnalyticsSummary.mockResolvedValue(mockAnalytics);
    renderWithAuth(<Dashboard />);
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalledTimes(1));
    let dateInputs = document.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '2026-06-01' } });
    await waitFor(() => expect(getAnalyticsSummary.mock.calls.length).toBeGreaterThan(1));
    dateInputs = document.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[1], { target: { value: '2026-06-30' } });
    await waitFor(() => {
      const calls = getAnalyticsSummary.mock.calls;
      const lastCall = calls[calls.length - 1][0];
      expect(lastCall.start).toBe('2026-06-01');
      expect(lastCall.end).toBe('2026-06-30');
    });
  });

  it('shows error state', async () => {
    getAnalyticsSummary.mockRejectedValue(new Error('fail'));
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load dashboard data')).toBeInTheDocument();
    });
  });

  it('shows empty state when no data', async () => {
    getAnalyticsSummary.mockResolvedValue({
      total_income: 0, total_expenses: 0, net_cashflow: 0, transaction_count: 0,
      category_breakdown: [], spending_trend: [],
    });
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('No spending data for this period.')).toBeInTheDocument();
    });
  });

  it('shows spending trend chart when multiple months', async () => {
    getAnalyticsSummary.mockResolvedValue(mockAnalytics);
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('Spending Trend')).toBeInTheDocument();
    });
  });

  it('does not show trend chart for single month', async () => {
    getAnalyticsSummary.mockResolvedValue({
      ...mockAnalytics,
      spending_trend: [{ month: '2026-09', amount: 30000 }],
    });
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      expect(screen.queryByText('Spending Trend')).not.toBeInTheDocument();
    });
  });
});
