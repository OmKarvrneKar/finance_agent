import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import EditTransactionModal from '../components/EditTransactionModal';

vi.mock('../utils/api', () => ({
  updateTransaction: vi.fn(),
}));

import { updateTransaction } from '../utils/api';

const mockTx = {
  id: '1',
  description: 'Starbucks Coffee',
  amount: 450,
  category: 'Food & Dining',
  transaction_type: 'debit',
  date: '2026-09-15',
  is_recurring: false,
};

describe('EditTransactionModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders modal with pre-filled values', () => {
    render(<EditTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByText('Edit Transaction')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Starbucks Coffee')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Food & Dining')).toBeInTheDocument();
    expect(screen.getByDisplayValue('450')).toBeInTheDocument();
  });

  it('calls updateTransaction on save', async () => {
    updateTransaction.mockResolvedValue({});
    const onSaved = vi.fn();
    render(<EditTransactionModal transaction={mockTx} onClose={() => {}} onSaved={onSaved} />);
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => {
      expect(updateTransaction).toHaveBeenCalledWith('1', expect.objectContaining({
        description: 'Starbucks Coffee',
        category: 'Food & Dining',
        amount: 450,
      }));
      expect(onSaved).toHaveBeenCalled();
    });
  });

  it('shows error on save failure', async () => {
    updateTransaction.mockRejectedValue({ response: { data: { detail: 'Not found' } } });
    render(<EditTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => {
      expect(screen.getByText('Not found')).toBeInTheDocument();
    });
  });

  it('calls onClose when cancel clicked', () => {
    const onClose = vi.fn();
    render(<EditTransactionModal transaction={mockTx} onClose={onClose} onSaved={() => {}} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when backdrop clicked', () => {
    const onClose = vi.fn();
    const { container } = render(<EditTransactionModal transaction={mockTx} onClose={onClose} onSaved={() => {}} />);
    // Click the overlay backdrop
    fireEvent.click(container.firstChild);
    expect(onClose).toHaveBeenCalled();
  });

  it('allows editing fields', () => {
    render(<EditTransactionModal transaction={mockTx} onClose={() => {}} onSaved={() => {}} />);
    const descInput = screen.getByDisplayValue('Starbucks Coffee');
    fireEvent.change(descInput, { target: { value: 'New Description' } });
    expect(descInput).toHaveValue('New Description');
  });
});
