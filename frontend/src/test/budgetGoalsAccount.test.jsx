import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BudgetGoals from '../components/BudgetGoals';

vi.mock('../utils/api', () => ({
  getBudgets: vi.fn(),
  createUpdateBudget: vi.fn(),
  deleteBudget: vi.fn(),
  getAllTransactions: vi.fn(),
  getAccounts: vi.fn(),
}));

import { getBudgets, getAllTransactions, getAccounts } from '../utils/api';

const budget = (overrides) => ({
  budget_id: 1,
  category: 'Food',
  monthly_cap: 1000,
  current_spend: 1400,
  percent_used: 140,
  days_left_in_month: 0,
  status: 'over',
  message: 'You are over your Food budget by ₹400.00.',
  ...overrides,
});

const unfilteredBudgets = [budget({})];
const accountABudgets = [budget({
  current_spend: 900,
  percent_used: 90,
  status: 'approaching',
  message: 'You are approaching your Food budget (90.0% used).',
})];
const accountBBudgets = [budget({
  current_spend: 300,
  percent_used: 30,
  status: 'on_track',
  message: 'You are on track for your Food budget.',
})];

const mockAccounts = [
  { id: 1, name: 'HDFC Salary', account_type: 'bank', is_active: true },
  { id: 2, name: 'HDFC Credit Card', account_type: 'credit_card', is_active: true },
];

const lastArg = () => getBudgets.mock.calls[getBudgets.mock.calls.length - 1][1];

describe('BudgetGoals account scoping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    getAccounts.mockResolvedValue(mockAccounts);
    getAllTransactions.mockResolvedValue({
      transactions: [{ category: 'Food' }, { category: 'Housing' }],
    });
    getBudgets.mockImplementation((month, account_id) =>
      Promise.resolve(
        account_id === '1' ? accountABudgets : account_id === '2' ? accountBBudgets : unfilteredBudgets
      )
    );
  });

  it('loads budgets without account_id and renders the all-account spend', async () => {
    render(<BudgetGoals />);
    await waitFor(() => expect(screen.getByText('₹1,400 spent')).toBeInTheDocument());
    expect(getBudgets.mock.calls[0][1]).toBeUndefined();
    expect(screen.getByText('140% Used')).toBeInTheDocument();
    expect(screen.getByText('You are over your Food budget by ₹400.00.')).toBeInTheDocument();
  });

  it('renders the account selector with active accounts', async () => {
    render(<BudgetGoals />);
    await waitFor(() => expect(screen.getByLabelText('Filter by account')).toBeInTheDocument());
    expect(getAccounts).toHaveBeenCalledWith({ is_active: true });
    const select = screen.getByLabelText('Filter by account');
    expect(screen.getByText('All Accounts')).toBeInTheDocument();
    expect(screen.getByText('HDFC Salary')).toBeInTheDocument();
    expect(screen.getByText('HDFC Credit Card')).toBeInTheDocument();
    expect(select).toHaveValue('');
  });

  it('refetches with the selected account and renders the scoped spend', async () => {
    render(<BudgetGoals />);
    await waitFor(() => expect(screen.getByText('₹1,400 spent')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() => expect(lastArg()).toBe('1'));
    // Scoped response (900) replaces the unfiltered one (1400).
    await waitFor(() => expect(screen.getByText('₹900 spent')).toBeInTheDocument());
    expect(screen.queryByText('₹1,400 spent')).not.toBeInTheDocument();
    expect(screen.getByText('90% Used')).toBeInTheDocument();
    expect(screen.getByText('You are approaching your Food budget (90.0% used).')).toBeInTheDocument();
  });

  it('switching accounts swaps the scoped spend again', async () => {
    render(<BudgetGoals />);
    await waitFor(() => expect(screen.getByText('₹1,400 spent')).toBeInTheDocument());

    const select = screen.getByLabelText('Filter by account');
    fireEvent.change(select, { target: { value: '1' } });
    await waitFor(() => expect(screen.getByText('₹900 spent')).toBeInTheDocument());

    fireEvent.change(select, { target: { value: '2' } });
    await waitFor(() => expect(lastArg()).toBe('2'));
    await waitFor(() => expect(screen.getByText('₹300 spent')).toBeInTheDocument());
    expect(screen.queryByText('₹900 spent')).not.toBeInTheDocument();
    expect(screen.getByText('30% Used')).toBeInTheDocument();
    // on_track -> no alert banner.
    expect(screen.queryByText(/over your Food budget/)).not.toBeInTheDocument();
    expect(screen.queryByText(/approaching your Food budget/)).not.toBeInTheDocument();
  });

  it('switching back to All Accounts refetches unscoped', async () => {
    render(<BudgetGoals />);
    await waitFor(() => expect(screen.getByText('₹1,400 spent')).toBeInTheDocument());

    const select = screen.getByLabelText('Filter by account');
    fireEvent.change(select, { target: { value: '1' } });
    await waitFor(() => expect(lastArg()).toBe('1'));

    fireEvent.change(select, { target: { value: '' } });
    await waitFor(() => expect(lastArg()).toBeUndefined());
    await waitFor(() => expect(screen.getByText('₹1,400 spent')).toBeInTheDocument());
    expect(screen.queryByText('₹900 spent')).not.toBeInTheDocument();
    expect(getBudgets.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it('shows no budget cards while loading', async () => {
    getBudgets.mockReturnValue(new Promise(() => {}));
    render(<BudgetGoals />);
    // Header and selector stay visible; server-driven content stays hidden.
    expect(screen.getByText('Budget Goals')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter by account')).toBeInTheDocument();
    expect(screen.queryByText('No budget goals set. Add one to start tracking!')).not.toBeInTheDocument();
    expect(screen.queryByText('₹1,400 spent')).not.toBeInTheDocument();
  });

  it('shows the empty state when no budgets exist', async () => {
    getBudgets.mockResolvedValue([]);
    render(<BudgetGoals />);
    await waitFor(() =>
      expect(screen.getByText('No budget goals set. Add one to start tracking!')).toBeInTheDocument()
    );
    expect(screen.queryByText('₹1,400 spent')).not.toBeInTheDocument();
  });

  it('falls back to the empty state when the budgets request fails', async () => {
    getBudgets.mockRejectedValue(new Error('network down'));
    render(<BudgetGoals />);
    await waitFor(() =>
      expect(screen.getByText('No budget goals set. Add one to start tracking!')).toBeInTheDocument()
    );
  });

  it('keeps the category dropdown populated from transactions regardless of account', async () => {
    render(<BudgetGoals />);
    await waitFor(() => expect(screen.getByText('₹1,400 spent')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() => expect(screen.getByText('₹900 spent')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Add Budget'));
    const categorySelect = screen.getByDisplayValue('Select category...');
    expect(categorySelect).toBeInTheDocument();
    // Categories still come from the unscoped transaction list (user-level caps).
    expect(categorySelect).toHaveTextContent('Food');
    expect(categorySelect).toHaveTextContent('Housing');
    expect(getAllTransactions).toHaveBeenCalled();
  });
});
