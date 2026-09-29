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
}));

import { searchTransactions, deleteTransaction, getTransactionsExport, getMe } from '../utils/api';

const mockTx = (overrides = {}) => ({
  id: '1',
  description: 'Starbucks Coffee',
  amount: 450.00,
  category: 'Food & Dining',
  transaction_type: 'debit',
  date: '2026-09-15',
  is_recurring: false,
  ...overrides,
});

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

describe('Transactions page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders page title and search input', async () => {
    searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
    renderWithAuth(<Transactions />);
    expect(screen.getByText('Transactions')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search by merchant or description...')).toBeInTheDocument();
  });

  it('displays transactions after loading', async () => {
    searchTransactions.mockResolvedValue({
      transactions: [mockTx(), mockTx({ id: '2', description: 'Uber Ride', amount: 200 })],
      total: 2,
    });
    renderWithAuth(<Transactions />);
    await waitFor(() => {
      expect(screen.getByText('Starbucks Coffee')).toBeInTheDocument();
      expect(screen.getByText('Uber Ride')).toBeInTheDocument();
    });
  });

  it('shows empty state when no results', async () => {
    searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
    renderWithAuth(<Transactions />);
    await waitFor(() => {
      expect(screen.getByText('No transactions yet. Upload a bank statement to get started.')).toBeInTheDocument();
    });
  });

  it('calls searchTransactions with search query', async () => {
    searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
    renderWithAuth(<Transactions />);
    fireEvent.change(screen.getByPlaceholderText('Search by merchant or description...'), { target: { value: 'starbucks' } });
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'starbucks' })
      );
    });
  });

  it('calls searchTransactions with category filter', async () => {
    searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
    renderWithAuth(<Transactions />);
    fireEvent.change(screen.getByDisplayValue('All Categories'), { target: { value: 'Food & Dining' } });
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledWith(
        expect.objectContaining({ category: 'Food & Dining' })
      );
    });
  });

  it('calls searchTransactions with amount filters', async () => {
    searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
    renderWithAuth(<Transactions />);
    fireEvent.change(screen.getByPlaceholderText('Min ₹'), { target: { value: '100' } });
    fireEvent.change(screen.getByPlaceholderText('Max ₹'), { target: { value: '500' } });
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledWith(
        expect.objectContaining({ amount_min: '100', amount_max: '500' })
      );
    });
  });

  it('calls searchTransactions with date filters', async () => {
    searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
    const result = renderWithAuth(<Transactions />);
    const dateInputs = result.container.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '2026-01-01' } });
    fireEvent.change(dateInputs[1], { target: { value: '2026-12-31' } });
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: '2026-01-01', date_to: '2026-12-31' })
      );
    });
  });

  it('shows pagination when results exist', async () => {
    searchTransactions.mockResolvedValue({
      transactions: [mockTx()],
      total: 25,
    });
    renderWithAuth(<Transactions />);
    await waitFor(() => {
      expect(screen.getByText(/Showing/)).toBeInTheDocument();
      expect(screen.getByText('Next')).toBeInTheDocument();
      expect(screen.getByText('Prev')).toBeInTheDocument();
    });
  });

  it('calls deleteTransaction on delete click', async () => {
    searchTransactions.mockResolvedValue({ transactions: [mockTx()], total: 1 });
    deleteTransaction.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithAuth(<Transactions />);
    await waitFor(() => expect(screen.getByText('Starbucks Coffee')).toBeInTheDocument());
    fireEvent.click(screen.getAllByTitle('Delete')[0]);
    await waitFor(() => {
      expect(deleteTransaction).toHaveBeenCalledWith('1');
    });
    window.confirm.mockRestore();
  });

  it('does not delete when confirm is cancelled', async () => {
    searchTransactions.mockResolvedValue({ transactions: [mockTx()], total: 1 });
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderWithAuth(<Transactions />);
    await waitFor(() => expect(screen.getByText('Starbucks Coffee')).toBeInTheDocument());
    fireEvent.click(screen.getAllByTitle('Delete')[0]);
    expect(deleteTransaction).not.toHaveBeenCalled();
    window.confirm.mockRestore();
  });

  it('clears all filters when clear button clicked', async () => {
    searchTransactions.mockResolvedValue({ transactions: [mockTx()], total: 1 });
    renderWithAuth(<Transactions />);
    await waitFor(() => expect(screen.getByText('Starbucks Coffee')).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText('Search by merchant or description...'), { target: { value: 'test' } });
    await waitFor(() => expect(screen.getByText('Clear all')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Clear all'));
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search by merchant or description...')).toHaveValue('');
    });
  });

  it('shows error state', async () => {
    searchTransactions.mockRejectedValue(new Error('Network error'));
    renderWithAuth(<Transactions />);
    await waitFor(() => {
      expect(screen.getByText('Failed to fetch transactions')).toBeInTheDocument();
    });
  });

  describe('CSV Export', () => {
    it('renders export button', async () => {
      searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
      renderWithAuth(<Transactions />);
      expect(screen.getByText('Export CSV')).toBeInTheDocument();
    });

    it('calls getTransactionsExport with active filters', async () => {
      searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
      const mockBlob = new Blob(['date,description\n'], { type: 'text/csv' });
      getTransactionsExport.mockResolvedValue({
        data: mockBlob,
        headers: { 'content-disposition': 'attachment; filename="transactions_export.csv"' },
      });
      renderWithAuth(<Transactions />);
      fireEvent.change(screen.getByPlaceholderText('Search by merchant or description...'), { target: { value: 'starbucks' } });
      await waitFor(() => {
        fireEvent.click(screen.getByText('Export CSV'));
      });
      await waitFor(() => {
        expect(getTransactionsExport).toHaveBeenCalledWith(
          expect.objectContaining({ search: 'starbucks' })
        );
      });
    });

    it('passes category filter to export', async () => {
      searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
      getTransactionsExport.mockResolvedValue({
        data: new Blob(),
        headers: { 'content-disposition': 'attachment; filename="transactions_export.csv"' },
      });
      renderWithAuth(<Transactions />);
      fireEvent.change(screen.getByDisplayValue('All Categories'), { target: { value: 'Food & Dining' } });
      fireEvent.click(screen.getByText('Export CSV'));
      await waitFor(() => {
        expect(getTransactionsExport).toHaveBeenCalledWith(
          expect.objectContaining({ category: 'Food & Dining' })
        );
      });
    });

    it('shows loading state while exporting', async () => {
      searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
      let resolveExport;
      getTransactionsExport.mockReturnValue(new Promise((r) => { resolveExport = r; }));
      renderWithAuth(<Transactions />);
      fireEvent.click(screen.getByText('Export CSV'));
      await waitFor(() => {
        expect(screen.getByText('Exporting...')).toBeInTheDocument();
      });
      resolveExport({ data: new Blob(), headers: {} });
      await waitFor(() => {
        expect(screen.getByText('Export CSV')).toBeInTheDocument();
      });
    });

    it('prevents duplicate export requests', async () => {
      searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
      let resolveExport;
      getTransactionsExport.mockReturnValue(new Promise((r) => { resolveExport = r; }));
      renderWithAuth(<Transactions />);
      fireEvent.click(screen.getByText('Export CSV'));
      await waitFor(() => expect(screen.getByText('Exporting...')).toBeInTheDocument());
      fireEvent.click(screen.getByText('Exporting...'));
      expect(getTransactionsExport).toHaveBeenCalledTimes(1);
      resolveExport({ data: new Blob(), headers: {} });
    });

    it('shows error on export failure', async () => {
      searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
      getTransactionsExport.mockRejectedValue(new Error('Network error'));
      renderWithAuth(<Transactions />);
      fireEvent.click(screen.getByText('Export CSV'));
      await waitFor(() => {
        expect(screen.getByText('Failed to export transactions')).toBeInTheDocument();
      });
    });

    it('shows success feedback after export', async () => {
      searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
      getTransactionsExport.mockResolvedValue({
        data: new Blob(),
        headers: { 'content-disposition': 'attachment; filename="transactions_export.csv"' },
      });
      renderWithAuth(<Transactions />);
      fireEvent.click(screen.getByText('Export CSV'));
      await waitFor(() => {
        expect(screen.getByText('CSV exported successfully.')).toBeInTheDocument();
      });
    });
  });
});
