import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import Transactions from '../pages/Transactions';

vi.mock('../utils/api', () => ({
  searchTransactions: vi.fn(),
  deleteTransaction: vi.fn(),
}));

import { searchTransactions, deleteTransaction } from '../utils/api';

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
  localStorage.setItem('token', 'fake-jwt');
  localStorage.setItem('user', JSON.stringify({ email: 'test@test.com' }));
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
});
