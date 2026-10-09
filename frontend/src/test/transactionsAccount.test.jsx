import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import Transactions from '../pages/Transactions';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  searchTransactions: vi.fn(),
  deleteTransaction: vi.fn(),
  getTransactionsExport: vi.fn(),
  getAccounts: vi.fn(),
  createTransaction: vi.fn(),
}));

import { searchTransactions, getTransactionsExport, getAccounts, getMe } from '../utils/api';

const accounts = [
  { id: 1, name: 'HDFC Savings', account_type: 'bank', is_active: true },
  { id: 2, name: 'ICICI Credit', account_type: 'credit_card', is_active: true },
];

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

const waitForAccounts = async () => {
  await waitFor(() => expect(screen.getByText('HDFC Savings')).toBeInTheDocument());
};

describe('Transactions page account filtering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    getAccounts.mockResolvedValue(accounts);
    searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
    getTransactionsExport.mockResolvedValue({
      data: new Blob(),
      headers: { 'content-disposition': 'attachment; filename="transactions_export.csv"' },
    });
  });

  it('renders account selector defaulting to All Accounts with account options', async () => {
    renderWithAuth(<Transactions />);
    expect(screen.getByLabelText('Filter by account')).toHaveValue('');
    await waitForAccounts();
    expect(screen.getByText('ICICI Credit')).toBeInTheDocument();
    expect(getAccounts).toHaveBeenCalledWith({ is_active: true });
  });

  it('All Accounts passes empty account_id on initial load', async () => {
    renderWithAuth(<Transactions />);
    await waitFor(() => expect(searchTransactions).toHaveBeenCalledTimes(1));
    expect(searchTransactions).toHaveBeenCalledWith(
      expect.objectContaining({ account_id: '' })
    );
  });

  it('specific account passes account_id and refreshes the list', async () => {
    renderWithAuth(<Transactions />);
    await waitForAccounts();
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledTimes(2);
      expect(searchTransactions).toHaveBeenLastCalledWith(
        expect.objectContaining({ account_id: '1' })
      );
    });
    expect(screen.getByLabelText('Filter by account')).toHaveValue('1');
  });

  it('switching accounts refetches with the new account', async () => {
    renderWithAuth(<Transactions />);
    await waitForAccounts();
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() => expect(searchTransactions).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '2' } });
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledTimes(3);
      expect(searchTransactions).toHaveBeenLastCalledWith(
        expect.objectContaining({ account_id: '2' })
      );
    });
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '' } });
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledTimes(4);
      expect(searchTransactions).toHaveBeenLastCalledWith(
        expect.objectContaining({ account_id: '' })
      );
    });
  });

  it('pagination keeps the account filter', async () => {
    searchTransactions.mockResolvedValue({ transactions: [], total: 25 });
    renderWithAuth(<Transactions />);
    await waitForAccounts();
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() => expect(searchTransactions).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledTimes(3);
      expect(searchTransactions).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2, account_id: '1' })
      );
    });
  });

  it('export includes the account filter', async () => {
    renderWithAuth(<Transactions />);
    await waitForAccounts();
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() => expect(searchTransactions).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByText('Export CSV'));
    await waitFor(() => {
      expect(getTransactionsExport).toHaveBeenCalledWith(
        expect.objectContaining({ account_id: '1' })
      );
    });
  });

  it('shows filtered empty state when account has no transactions', async () => {
    renderWithAuth(<Transactions />);
    await waitForAccounts();
    expect(screen.getByText('No transactions yet. Upload a bank statement to get started.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() => {
      expect(screen.getByText('No transactions found matching your filters.')).toBeInTheDocument();
    });
  });

  it('shows loading state while fetching with an account selected', async () => {
    searchTransactions.mockReturnValue(new Promise(() => {}));
    renderWithAuth(<Transactions />);
    await waitForAccounts();
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    expect(screen.getByText('Loading transactions...')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter by account')).toHaveValue('1');
  });

  it('shows error state when fetch fails', async () => {
    searchTransactions.mockRejectedValue(new Error('Network error'));
    renderWithAuth(<Transactions />);
    await waitFor(() => {
      expect(screen.getByText('Failed to fetch transactions')).toBeInTheDocument();
    });
  });

  it('clear all resets the account selection', async () => {
    renderWithAuth(<Transactions />);
    await waitForAccounts();
    fireEvent.change(screen.getByLabelText('Filter by account'), { target: { value: '1' } });
    await waitFor(() => expect(searchTransactions).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByText('Clear all'));
    await waitFor(() => {
      expect(screen.getByLabelText('Filter by account')).toHaveValue('');
      expect(searchTransactions).toHaveBeenLastCalledWith(
        expect.objectContaining({ account_id: '' })
      );
    });
  });
});
