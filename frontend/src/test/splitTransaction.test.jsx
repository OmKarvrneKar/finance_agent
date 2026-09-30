import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SplitTransactionModal from '../components/SplitTransactionModal';

vi.mock('../utils/api', () => ({
  getSplitSummary: vi.fn(),
  createSplits: vi.fn(),
  deleteSplit: vi.fn(),
}));

import { getSplitSummary, createSplits, deleteSplit } from '../utils/api';

const mockTx = {
  id: '1',
  description: 'Target Shopping',
  amount: '100.00',
  category: 'Shopping',
  transaction_type: 'debit',
  date: '2026-09-15',
};

const mockTxSmall = {
  id: '2',
  description: 'Coffee',
  amount: '50.00',
  category: 'Food & Dining',
  transaction_type: 'debit',
  date: '2026-09-15',
};

describe('SplitTransactionModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders unsplit transaction with empty split row', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/Target Shopping/)).toBeInTheDocument();
    });
    expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    expect(screen.getByText('Transaction total:')).toBeInTheDocument();
    expect(screen.getByText('Remaining:')).toBeInTheDocument();
  });

  it('renders existing splits', async () => {
    getSplitSummary.mockResolvedValue({
      splits: [
        { id: 1, category: 'Groceries', amount: '60.00', description: 'Food items' },
        { id: 2, category: 'Electronics', amount: '40.00', description: '' },
      ],
      is_split: true,
      remaining: '0.00',
    });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('60.00')).toBeInTheDocument();
      expect(screen.getByDisplayValue('40.00')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Food items')).toBeInTheDocument();
    });
  });

  it('adds a new split row', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    const addBtn = screen.getByText(/Add split/);
    fireEvent.click(addBtn);
    const rows = screen.getAllByTestId(/^split-row-/);
    expect(rows.length).toBe(2);
  });

  it('removes a split row', async () => {
    getSplitSummary.mockResolvedValue({
      splits: [
        { id: 1, category: 'Groceries', amount: '60.00', description: '' },
        { id: 2, category: 'Electronics', amount: '40.00', description: '' },
      ],
      is_split: true,
      remaining: '0.00',
    });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('60.00')).toBeInTheDocument();
    });
    const removeButtons = screen.getAllByTitle('Remove split');
    fireEvent.click(removeButtons[0]);
    const rows = screen.getAllByTestId(/^split-row-/);
    expect(rows.length).toBe(1);
  });

  it('shows under-allocation error when save clicked', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    // Fill only 50 of 100
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'Groceries' } });
    const amountInputs = screen.getAllByPlaceholderText('0.00');
    fireEvent.change(amountInputs[0], { target: { value: '50' } });
    fireEvent.click(screen.getByText('Save Splits'));
    await waitFor(() => {
      expect(screen.getByText(/Under-allocated/)).toBeInTheDocument();
    });
  });

  it('shows over-allocation error when save clicked', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'Groceries' } });
    const amountInputs = screen.getByPlaceholderText('0.00');
    fireEvent.change(amountInputs, { target: { value: '150' } });
    fireEvent.click(screen.getByText('Save Splits'));
    await waitFor(() => {
      expect(screen.getByText(/Over-allocated/)).toBeInTheDocument();
    });
  });

  it('shows duplicate category validation', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    // Add a second split
    fireEvent.click(screen.getByText(/Add split/));
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'Groceries' } });
    fireEvent.change(selects[1], { target: { value: 'Groceries' } });
    const amountInputs = screen.getAllByPlaceholderText('0.00');
    fireEvent.change(amountInputs[0], { target: { value: '50' } });
    fireEvent.change(amountInputs[1], { target: { value: '50' } });
    fireEvent.click(screen.getByText('Save Splits'));
    await waitFor(() => {
      expect(screen.getByText(/duplicate category/i)).toBeInTheDocument();
    });
  });

  it('shows zero amount validation', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'Groceries' } });
    const amountInputs = screen.getByPlaceholderText('0.00');
    fireEvent.change(amountInputs, { target: { value: '0' } });
    fireEvent.click(screen.getByText('Save Splits'));
    await waitFor(() => {
      expect(screen.getByText(/amount must be a positive number/)).toBeInTheDocument();
    });
  });

  it('shows negative amount validation', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'Groceries' } });
    const amountInputs = screen.getByPlaceholderText('0.00');
    fireEvent.change(amountInputs, { target: { value: '-10' } });
    fireEvent.click(screen.getByText('Save Splits'));
    await waitFor(() => {
      expect(screen.getByText(/amount must be a positive number/)).toBeInTheDocument();
    });
  });

  it('shows remaining amount correctly', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    expect(screen.getByText('Remaining:')).toBeInTheDocument();
    expect(screen.getAllByText('₹100.00').length).toBeGreaterThanOrEqual(1);
  });

  it('calls createSplits on successful save', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    createSplits.mockResolvedValue([]);
    const onSaved = vi.fn();
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={onSaved} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'Groceries' } });
    const amountInputs = screen.getByPlaceholderText('0.00');
    fireEvent.change(amountInputs, { target: { value: '100' } });
    fireEvent.click(screen.getByText('Save Splits'));
    await waitFor(() => {
      expect(createSplits).toHaveBeenCalledWith('1', expect.arrayContaining([
        expect.objectContaining({ category: 'Groceries', amount: '100' }),
      ]));
      expect(onSaved).toHaveBeenCalled();
    });
  });

  it('shows API error on save failure', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    createSplits.mockRejectedValue({ response: { data: { detail: 'Splits must sum to transaction amount' } } });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'Groceries' } });
    const amountInputs = screen.getByPlaceholderText('0.00');
    fireEvent.change(amountInputs, { target: { value: '100' } });
    fireEvent.click(screen.getByText('Save Splits'));
    await waitFor(() => {
      expect(screen.getByText('Splits must sum to transaction amount')).toBeInTheDocument();
    });
  });

  it('calls onClose when cancel clicked', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    const onClose = vi.fn();
    render(<SplitTransactionModal transaction={mockTx} onClose={onClose} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when backdrop clicked', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    const onClose = vi.fn();
    const { container } = render(<SplitTransactionModal transaction={mockTx} onClose={onClose} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    fireEvent.click(container.firstChild);
    expect(onClose).toHaveBeenCalled();
  });

  it('requires category for validation', async () => {
    getSplitSummary.mockResolvedValue({ splits: [], is_split: false, remaining: '100.00' });
    render(<SplitTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Split Transaction')).toBeInTheDocument();
    });
    const amountInputs = screen.getByPlaceholderText('0.00');
    fireEvent.change(amountInputs, { target: { value: '100' } });
    fireEvent.click(screen.getByText('Save Splits'));
    await waitFor(() => {
      expect(screen.getByText(/category is required/)).toBeInTheDocument();
    });
  });
});
