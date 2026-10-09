import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import ManualTransactionModal from '../components/ManualTransactionModal';
import Transactions from '../pages/Transactions';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  searchTransactions: vi.fn(),
  deleteTransaction: vi.fn(),
  getTransactionsExport: vi.fn(),
  createTransaction: vi.fn(),
  getAccounts: vi.fn(),
}));

import { searchTransactions, createTransaction, getAccounts, getMe } from '../utils/api';

const account = { id: 1, name: 'HDFC Savings', account_type: 'bank', is_active: true };

const renderModal = (onCreated = vi.fn()) => {
  const onClose = vi.fn();
  render(<ManualTransactionModal onClose={onClose} onCreated={onCreated} />);
  return { onClose, onCreated };
};

const fillValidForm = () => {
  fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Coffee Shop' } });
  fireEvent.change(screen.getByLabelText('Amount (₹)'), { target: { value: '250' } });
  fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2026-10-01' } });
  fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Food & Dining' } });
  fireEvent.click(screen.getByRole('button', { name: 'Expense' }));
};

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

describe('ManualTransactionModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    getAccounts.mockResolvedValue([account]);
    searchTransactions.mockResolvedValue({ transactions: [], total: 0 });
  });

  it('renders form with all fields', async () => {
    renderModal();
    expect(screen.getByText('Add Transaction')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expense' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Income' })).toBeInTheDocument();
    expect(screen.getByLabelText('Amount (₹)')).toBeInTheDocument();
    expect(screen.getByLabelText('Date')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
    expect(screen.getByLabelText('Category')).toBeInTheDocument();
    expect(screen.getByLabelText('Subcategory')).toBeInTheDocument();
    expect(screen.getByLabelText('Account')).toBeInTheDocument();
    expect(screen.getByLabelText('Recurring transaction')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText('Account')).toHaveValue('');
      expect(screen.getByText('All Accounts')).toBeInTheDocument();
      expect(screen.getByText(account.name)).toBeInTheDocument();
    });
    expect(getAccounts).toHaveBeenCalledWith({ is_active: true });
  });

  it('creates an expense transaction', async () => {
    createTransaction.mockResolvedValue({ id: 1 });
    const { onCreated } = renderModal();
    fillValidForm();
    fireEvent.change(screen.getByLabelText('Subcategory'), { target: { value: 'Cafe' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(createTransaction).toHaveBeenCalledWith({
        transaction_type: 'debit',
        amount: 250,
        date: '2026-10-01',
        description: 'Coffee Shop',
        category: 'Food & Dining',
        subcategory: 'Cafe',
        is_recurring: false,
      });
      expect(onCreated).toHaveBeenCalled();
    });
  });

  it('creates an income transaction', async () => {
    createTransaction.mockResolvedValue({ id: 2 });
    const { onCreated } = renderModal();
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: 'Income' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(createTransaction).toHaveBeenCalledWith({
        transaction_type: 'credit',
        amount: 250,
        date: '2026-10-01',
        description: 'Coffee Shop',
        category: 'Food & Dining',
        is_recurring: false,
      });
      expect(onCreated).toHaveBeenCalled();
    });
  });

  it('validates required fields before submitting', () => {
    renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('Transaction type is required')).toBeInTheDocument();
    expect(screen.getByText('Amount is required')).toBeInTheDocument();
    expect(screen.getByText('Date is required')).toBeInTheDocument();
    expect(screen.getByText('Description is required')).toBeInTheDocument();
    expect(screen.getByText('Category is required')).toBeInTheDocument();
    expect(createTransaction).not.toHaveBeenCalled();
  });

  it('rejects an invalid amount', () => {
    renderModal();
    fillValidForm();
    fireEvent.change(screen.getByLabelText('Amount (₹)'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('Amount must be greater than 0')).toBeInTheDocument();
    expect(createTransaction).not.toHaveBeenCalled();
  });

  it('validates category is selected', () => {
    renderModal();
    fillValidForm();
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('Category is required')).toBeInTheDocument();
    expect(createTransaction).not.toHaveBeenCalled();
  });

  it('includes account_id when a specific account is selected', async () => {
    createTransaction.mockResolvedValue({ id: 3 });
    renderModal();
    fillValidForm();
    await waitFor(() => expect(screen.getByText(account.name)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Account'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(createTransaction).toHaveBeenCalledWith(expect.objectContaining({ account_id: 1 }));
    });
  });

  it('omits account_id when All Accounts is selected', async () => {
    createTransaction.mockResolvedValue({ id: 4 });
    renderModal();
    fillValidForm();
    await waitFor(() => expect(screen.getByText(account.name)).toBeInTheDocument());
    expect(screen.getByLabelText('Account')).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(createTransaction).toHaveBeenCalledTimes(1);
    });
    const payload = createTransaction.mock.calls[0][0];
    expect(payload).not.toHaveProperty('account_id');
  });

  it('shows success state after successful creation', async () => {
    createTransaction.mockResolvedValue({ id: 5 });
    const { onCreated } = renderModal();
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(screen.getByText('Transaction added successfully.')).toBeInTheDocument();
      expect(onCreated).toHaveBeenCalledTimes(1);
    });
  });

  it('displays backend validation errors from a 422 response', async () => {
    createTransaction.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: [
            { msg: 'Input should be a valid decimal' },
            { msg: 'Account not found' },
          ],
        },
      },
    });
    const { onCreated } = renderModal();
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(screen.getByText('Input should be a valid decimal; Account not found')).toBeInTheDocument();
    });
    expect(screen.queryByText('Transaction added successfully.')).not.toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it('displays a backend error message', async () => {
    createTransaction.mockRejectedValue({
      response: { status: 404, data: { detail: 'Account not found.' } },
    });
    const { onCreated } = renderModal();
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(screen.getByText('Account not found.')).toBeInTheDocument();
    });
    expect(onCreated).not.toHaveBeenCalled();
  });

  it('resets the form after successful creation', async () => {
    createTransaction.mockResolvedValue({ id: 6 });
    renderModal();
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(screen.getByText('Transaction added successfully.')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Description')).toHaveValue('');
    expect(screen.getByLabelText('Amount (₹)')).toHaveValue(null);
    expect(screen.getByLabelText('Date')).toHaveValue('');
    expect(screen.getByLabelText('Category')).toHaveValue('');
    expect(screen.getByLabelText('Subcategory')).toHaveValue('');
    expect(screen.getByLabelText('Recurring transaction')).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('Transaction type is required')).toBeInTheDocument();
    expect(createTransaction).toHaveBeenCalledTimes(1);
  });

  it('refreshes the transaction list after successful creation', async () => {
    const newTx = {
      id: '99',
      description: 'Coffee Shop',
      amount: 250,
      category: 'Food & Dining',
      transaction_type: 'debit',
      date: '2026-10-01',
      is_recurring: false,
    };
    searchTransactions
      .mockResolvedValueOnce({ transactions: [], total: 0 })
      .mockResolvedValueOnce({ transactions: [newTx], total: 1 });
    createTransaction.mockResolvedValue({ id: 99 });
    renderWithAuth(<Transactions />);
    await waitFor(() => {
      expect(screen.getByText('No transactions yet. Upload a bank statement to get started.')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add Transaction' }));
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => {
      expect(searchTransactions).toHaveBeenCalledTimes(2);
      expect(screen.getByText('Coffee Shop')).toBeInTheDocument();
    });
    expect(createTransaction).toHaveBeenCalledTimes(1);
  });
});
