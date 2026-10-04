import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import Dashboard from '../pages/Dashboard';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  getAnalyticsSummary: vi.fn(),
  getAccounts: vi.fn(),
  getAccountsSummary: vi.fn(),
  getMerchantAnalytics: vi.fn(),
  getRecurringCalendar: vi.fn().mockResolvedValue({
    bills: [],
    start_date: '',
    end_date: '',
    total_expected_amount: '0.00',
    count: 0,
  }),
  getSpendingVelocity: vi.fn().mockResolvedValue({
    current_window_spend: '0.00',
    baseline_window_spend: '0.00',
    velocity_ratio: null,
    percentage_change: null,
    window_days: 3,
    baseline_method: 'test',
    alert_level: 'insufficient_data',
    start_date: '',
    end_date: '',
    baseline_windows_used: 0,
  }),
}));

vi.mock('../components/ForecastAlerts', () => ({ default: () => <div data-testid="forecast-alerts" /> }));
vi.mock('../components/AnomalyAlerts', () => ({ default: () => <div data-testid="anomaly-alerts" /> }));
vi.mock('../components/SavingsRecommendations', () => ({ default: () => <div data-testid="savings-recommendations" /> }));
vi.mock('../components/RecurringBillsCalendar', () => ({ default: () => <div data-testid="recurring-bills-calendar" /> }));
vi.mock('../components/SpendingVelocityCard', () => ({ default: () => <div data-testid="spending-velocity-card" /> }));

import {
  getAnalyticsSummary,
  getAccounts,
  getAccountsSummary,
  getMerchantAnalytics,
  getMe,
} from '../utils/api';

const mockAnalytics = {
  total_income: 50000,
  total_expenses: 30000,
  net_cashflow: 20000,
  transaction_count: 45,
  category_breakdown: [
    { category: 'Groceries', amount: 12000 },
    { category: 'Transport', amount: 8000 },
  ],
  spending_trend: [
    { month: '2026-08', amount: 25000 },
    { month: '2026-09', amount: 30000 },
  ],
};

const mockAccounts = [
  { id: 1, name: 'HDFC Salary', account_type: 'bank', currency: 'INR', is_active: true },
  { id: 2, name: 'HDFC Credit Card', account_type: 'credit_card', currency: 'INR', is_active: true },
];

const mockAccountSummary = [
  {
    account_id: 1,
    name: 'HDFC Salary',
    account_type: 'bank',
    currency: 'INR',
    current_balance: '5750.00',
    balance_nature: 'available',
    total_credits: '5000.00',
    total_debits: '250.00',
    transaction_count: 7,
  },
  {
    account_id: 2,
    name: 'HDFC Credit Card',
    account_type: 'credit_card',
    currency: 'INR',
    current_balance: '200.00',
    balance_nature: 'owed',
    total_credits: '100.00',
    total_debits: '300.00',
    transaction_count: 3,
  },
];

const mockMerchantData = {
  merchants: [],
  total_merchants: 0,
  total_expenses: 0,
  date_range: { start_date: '', end_date: '' },
};

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

const waitForSelector = async () => {
  await waitFor(() => expect(screen.getByTestId('account-option-all')).toBeInTheDocument());
};

describe('Dashboard account selector and summary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    getAnalyticsSummary.mockResolvedValue(mockAnalytics);
    getAccounts.mockResolvedValue(mockAccounts);
    getAccountsSummary.mockResolvedValue(mockAccountSummary);
    getMerchantAnalytics.mockResolvedValue(mockMerchantData);
  });

  it('account selector renders', async () => {
    renderWithAuth(<Dashboard />);
    await waitForSelector();
    expect(screen.getByTestId('account-selector')).toBeInTheDocument();
    expect(screen.getByTestId('account-option-all')).toBeInTheDocument();
    expect(screen.getByTestId('account-option-1')).toBeInTheDocument();
    expect(screen.getByTestId('account-option-2')).toBeInTheDocument();
    expect(getAccounts).toHaveBeenCalledWith({ is_active: true });
  });

  it('All Accounts is the default and sends no account_id', async () => {
    renderWithAuth(<Dashboard />);
    await waitForSelector();
    expect(screen.getByTestId('selected-account-label')).toHaveTextContent('All Accounts');
    expect(screen.getByTestId('account-option-all')).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalled());
    const call = getAnalyticsSummary.mock.calls[0][0];
    expect('account_id' in call).toBe(false);
  });

  it('account selection updates the selected label', async () => {
    renderWithAuth(<Dashboard />);
    await waitForSelector();
    fireEvent.click(screen.getByTestId('account-option-1'));
    await waitFor(() => {
      expect(screen.getByTestId('selected-account-label')).toHaveTextContent('HDFC Salary');
    });
    expect(screen.getByTestId('account-option-1')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('account-option-all')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('account-summary-card-1').style.boxShadow).toContain('#3B82F6');
  });

  it('passes account_id to supported analytics endpoints', async () => {
    renderWithAuth(<Dashboard />);
    await waitForSelector();
    await waitFor(() => expect(getMerchantAnalytics).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('account-option-2'));
    await waitFor(() => {
      const last = getAnalyticsSummary.mock.calls[getAnalyticsSummary.mock.calls.length - 1][0];
      expect(last.account_id).toBe(2);
    });
    await waitFor(() => {
      const last = getMerchantAnalytics.mock.calls[getMerchantAnalytics.mock.calls.length - 1][0];
      expect(last.account_id).toBe(2);
    });
  });

  it('analytics refresh when an account is selected', async () => {
    renderWithAuth(<Dashboard />);
    await waitForSelector();
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId('account-option-1'));
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalledTimes(2));
  });

  it('account summary renders backend-provided fields', async () => {
    renderWithAuth(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId('account-summary-card-1')).toBeInTheDocument());
    const card = screen.getByTestId('account-summary-card-1');
    expect(card).toHaveTextContent('HDFC Salary');
    expect(screen.getByTestId('account-type-1')).toHaveTextContent('Bank');
    expect(card).toHaveTextContent('INR 5,750.00');
    expect(screen.getByTestId('account-credits-1')).toHaveTextContent('INR 5,000.00');
    expect(screen.getByTestId('account-debits-1')).toHaveTextContent('INR 250.00');
    expect(screen.getByTestId('account-count-1')).toHaveTextContent('7');
  });

  it('renders multiple accounts with distinct types', async () => {
    renderWithAuth(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId('account-summary-card-2')).toBeInTheDocument());
    expect(screen.getByTestId('account-summary-card-1')).toBeInTheDocument();
    expect(screen.getByTestId('account-type-1')).toHaveTextContent('Bank');
    expect(screen.getByTestId('account-type-2')).toHaveTextContent('Credit Card');
    expect(screen.getByTestId('account-option-1')).toHaveTextContent('HDFC Salary');
    expect(screen.getByTestId('account-option-2')).toHaveTextContent('HDFC Credit Card');
  });

  it('shows empty state when the user has no accounts', async () => {
    getAccounts.mockResolvedValue([]);
    getAccountsSummary.mockResolvedValue([]);
    renderWithAuth(<Dashboard />);
    await waitForSelector();
    expect(screen.queryByTestId('account-option-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('account-option-all')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('accounts-empty')).toBeInTheDocument());
    expect(screen.getByTestId('accounts-empty')).toHaveTextContent('No accounts yet.');
  });

  it('shows loading state while accounts load', async () => {
    getAccounts.mockReturnValue(new Promise(() => {}));
    getAccountsSummary.mockReturnValue(new Promise(() => {}));
    renderWithAuth(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId('accounts-loading')).toBeInTheDocument());
    expect(screen.queryByTestId('account-option-all')).not.toBeInTheDocument();
  });

  it('shows API error state when accounts fail to load', async () => {
    getAccounts.mockRejectedValue(new Error('network down'));
    getAccountsSummary.mockRejectedValue(new Error('network down'));
    renderWithAuth(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('account-summary')).toHaveTextContent('Failed to load accounts');
    });
    expect(screen.getByTestId('account-selector')).toHaveTextContent('Failed to load accounts');
    expect(screen.getByText('Total Income')).toBeInTheDocument();
  });

  it('handles authentication failure silently', async () => {
    getAccounts.mockRejectedValue({ response: { status: 401 } });
    getAccountsSummary.mockRejectedValue({ response: { status: 401 } });
    renderWithAuth(<Dashboard />);
    await waitFor(() => expect(screen.getByText('Total Income')).toBeInTheDocument());
    expect(screen.queryByText('Failed to load accounts')).not.toBeInTheDocument();
    expect(screen.getByTestId('account-option-all')).toBeInTheDocument();
  });

  it('existing dashboard behavior without account_id', async () => {
    renderWithAuth(<Dashboard />);
    await waitForSelector();
    await waitFor(() => expect(getMerchantAnalytics).toHaveBeenCalled());
    const analyticsCall = getAnalyticsSummary.mock.calls[0][0];
    expect('account_id' in analyticsCall).toBe(false);
    expect(analyticsCall.start).toBeTruthy();
    expect(analyticsCall.end).toBeTruthy();
    const merchantCall = getMerchantAnalytics.mock.calls[0][0];
    expect('account_id' in merchantCall).toBe(false);
    expect(screen.getByText('Total Income')).toBeInTheDocument();
    expect(screen.getByText('Net Cash Flow')).toBeInTheDocument();
  });
});
