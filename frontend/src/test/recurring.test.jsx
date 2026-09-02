import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import Transactions from '../pages/Transactions';
import TransactionRow from '../components/TransactionRow';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  searchTransactions: vi.fn(),
  deleteTransaction: vi.fn(),
  markRecurring: vi.fn(),
  unmarkRecurring: vi.fn(),
  getCategories: vi.fn().mockResolvedValue([]),
}));

import { searchTransactions, deleteTransaction, markRecurring, unmarkRecurring, getMe } from '../utils/api';

const mockTx = (overrides = {}) => ({
  id: '1',
  description: 'Netflix Subscription',
  amount: 499.00,
  category: 'Subscriptions',
  transaction_type: 'debit',
  date: '2026-09-15',
  is_recurring: false,
  is_user_confirmed_recurring: false,
  ...overrides,
});

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

describe('Recurring Transaction Toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders repeat button for each transaction', async () => {
    searchTransactions.mockResolvedValue({ transactions: [mockTx()], total: 1 });
    renderWithAuth(<Transactions />);
    await waitFor(() => {
      expect(screen.getByText('Netflix Subscription')).toBeInTheDocument();
    });
    const repeatButtons = screen.getAllByTitle(/Mark as recurring|Recurring/);
    expect(repeatButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('calls markRecurring when clicking repeat on non-recurring tx', async () => {
    searchTransactions.mockResolvedValue({ transactions: [mockTx()], total: 1 });
    markRecurring.mockResolvedValue({ is_recurring: true, is_user_confirmed_recurring: true });
    renderWithAuth(<Transactions />);
    await waitFor(() => expect(screen.getByText('Netflix Subscription')).toBeInTheDocument());

    const btn = screen.getAllByTitle('Mark as recurring')[0];
    fireEvent.click(btn);

    await waitFor(() => {
      expect(markRecurring).toHaveBeenCalledWith('1');
    });
  });

  it('calls unmarkRecurring when clicking repeat on recurring tx', async () => {
    searchTransactions.mockResolvedValue({
      transactions: [mockTx({ is_recurring: true, is_user_confirmed_recurring: true })],
      total: 1,
    });
    unmarkRecurring.mockResolvedValue({ is_recurring: false, is_user_confirmed_recurring: false });
    renderWithAuth(<Transactions />);
    await waitFor(() => expect(screen.getByText('Netflix Subscription')).toBeInTheDocument());

    const btn = screen.getAllByTitle(/Recurring/)[0];
    fireEvent.click(btn);

    await waitFor(() => {
      expect(unmarkRecurring).toHaveBeenCalledWith('1');
    });
  });

  it('shows error when markRecurring fails', async () => {
    searchTransactions.mockResolvedValue({ transactions: [mockTx()], total: 1 });
    markRecurring.mockRejectedValue(new Error('API error'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderWithAuth(<Transactions />);
    await waitFor(() => expect(screen.getByText('Netflix Subscription')).toBeInTheDocument());

    const btn = screen.getAllByTitle('Mark as recurring')[0];
    fireEvent.click(btn);

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });
    consoleSpy.mockRestore();
  });

  it('shows error when unmarkRecurring fails', async () => {
    searchTransactions.mockResolvedValue({
      transactions: [mockTx({ is_recurring: true, is_user_confirmed_recurring: true })],
      total: 1,
    });
    unmarkRecurring.mockRejectedValue(new Error('API error'));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderWithAuth(<Transactions />);
    await waitFor(() => expect(screen.getByText('Netflix Subscription')).toBeInTheDocument());

    const btn = screen.getAllByTitle(/Recurring/)[0];
    fireEvent.click(btn);

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });
    consoleSpy.mockRestore();
  });
});

describe('TransactionRow recurring toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders mark button for non-recurring transaction', () => {
    const tx = mockTx();
    render(
      <table><tbody>
        <TransactionRow transaction={tx} />
      </tbody></table>
    );
    expect(screen.getByTitle('Mark as recurring')).toBeInTheDocument();
  });

  it('renders unmark button for user-confirmed recurring transaction', () => {
    const tx = mockTx({ is_recurring: true, is_user_confirmed_recurring: true });
    render(
      <table><tbody>
        <TransactionRow transaction={tx} />
      </tbody></table>
    );
    expect(screen.getByTitle(/Recurring \(User confirmed\)/)).toBeInTheDocument();
  });

  it('renders unmark button for AI-detected recurring transaction', () => {
    const tx = mockTx({ is_recurring: true, is_user_confirmed_recurring: false });
    render(
      <table><tbody>
        <TransactionRow transaction={tx} />
      </tbody></table>
    );
    expect(screen.getByTitle(/Recurring \(AI detected\)/)).toBeInTheDocument();
  });

  it('calls markRecurring on click for non-recurring', async () => {
    markRecurring.mockResolvedValue({ is_recurring: true, is_user_confirmed_recurring: true });
    const tx = mockTx();
    render(
      <table><tbody>
        <TransactionRow transaction={tx} />
      </tbody></table>
    );
    fireEvent.click(screen.getByTitle('Mark as recurring'));
    await waitFor(() => {
      expect(markRecurring).toHaveBeenCalledWith('1');
    });
  });

  it('calls unmarkRecurring on click for recurring', async () => {
    unmarkRecurring.mockResolvedValue({ is_recurring: false, is_user_confirmed_recurring: false });
    const tx = mockTx({ is_recurring: true, is_user_confirmed_recurring: true });
    render(
      <table><tbody>
        <TransactionRow transaction={tx} />
      </tbody></table>
    );
    fireEvent.click(screen.getByTitle(/Recurring/));
    await waitFor(() => {
      expect(unmarkRecurring).toHaveBeenCalledWith('1');
    });
  });
});
