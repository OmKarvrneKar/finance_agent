import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import MerchantAnalytics from '../components/MerchantAnalytics';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  getMerchantAnalytics: vi.fn(),
}));

import { getMerchantAnalytics, getMe } from '../utils/api';

const mockMerchantData = {
  merchants: [
    {
      merchant: 'Starbucks',
      total_spent: 150.00,
      transaction_count: 10,
      average_amount: 15.00,
      largest_transaction: 25.00,
      spending_percent: 37.5,
      first_seen: '2026-01-15',
      last_seen: '2026-09-20',
      category: 'coffee',
    },
    {
      merchant: 'Amazon',
      total_spent: 100.00,
      transaction_count: 5,
      average_amount: 20.00,
      largest_transaction: 50.00,
      spending_percent: 25.0,
      first_seen: '2026-02-10',
      last_seen: '2026-09-18',
      category: 'shopping',
    },
    {
      merchant: 'Netflix',
      total_spent: 50.00,
      transaction_count: 3,
      average_amount: 16.67,
      largest_transaction: 20.00,
      spending_percent: 12.5,
      first_seen: '2026-03-01',
      last_seen: '2026-09-01',
      category: 'entertainment',
    },
  ],
  total_merchants: 3,
  total_expenses: 400.00,
  date_range: { start_date: '2026-01-01', end_date: '2026-12-31' },
};

const mockEmptyMerchantData = {
  merchants: [],
  total_merchants: 0,
  total_expenses: 0,
  date_range: { start_date: '', end_date: '' },
};

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

const waitForLoad = async () => {
  await waitFor(() => {
    expect(screen.queryByText('Top Merchants')).toBeInTheDocument();
  });
};

describe('MerchantAnalytics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('merchant results render', () => {
    it('renders merchant names in the table', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getByText('Starbucks')).toBeInTheDocument();
      expect(screen.getByText('Amazon')).toBeInTheDocument();
      expect(screen.getByText('Netflix')).toBeInTheDocument();
    });

    it('renders the component heading', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getByText('Top Merchants')).toBeInTheDocument();
    });
  });

  describe('correct spending values displayed', () => {
    it('displays total spent for each merchant', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getAllByText('₹150.00').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('₹100.00').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('₹50.00').length).toBeGreaterThanOrEqual(1);
    });

    it('displays transaction count', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      const table = screen.getByRole('table');
      expect(within(table).getByText('10')).toBeInTheDocument();
      expect(within(table).getByText('5')).toBeInTheDocument();
      expect(within(table).getAllByText('3').length).toBeGreaterThanOrEqual(1);
    });

    it('displays average amount', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      const table = screen.getByRole('table');
      expect(within(table).getByText('₹15.00')).toBeInTheDocument();
      expect(within(table).getAllByText('₹20.00').length).toBeGreaterThanOrEqual(1);
      expect(within(table).getByText('₹16.67')).toBeInTheDocument();
    });

    it('displays largest transaction', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      const table = screen.getByRole('table');
      expect(within(table).getByText('₹25.00')).toBeInTheDocument();
      expect(within(table).getAllByText('₹50.00').length).toBeGreaterThanOrEqual(1);
      expect(within(table).getAllByText('₹20.00').length).toBeGreaterThanOrEqual(1);
    });

    it('displays spending percentage', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getByText('37.5%')).toBeInTheDocument();
      expect(screen.getByText('25.0%')).toBeInTheDocument();
      expect(screen.getByText('12.5%')).toBeInTheDocument();
    });

    it('displays category', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      const table = screen.getByRole('table');
      expect(within(table).getByText('coffee')).toBeInTheDocument();
      expect(within(table).getByText('shopping')).toBeInTheDocument();
      expect(within(table).getByText('entertainment')).toBeInTheDocument();
    });
  });

  describe('ordering displayed correctly', () => {
    it('renders merchants in the order returned by API (by spending)', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      const rows = screen.getAllByRole('row');
      expect(rows[1]).toHaveTextContent('Starbucks');
      expect(rows[2]).toHaveTextContent('Amazon');
      expect(rows[3]).toHaveTextContent('Netflix');
    });

    it('displays row numbers in order', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      const table = screen.getByRole('table');
      const rows = within(table).getAllByRole('row');
      const getFirstCell = (row) => within(row).getAllByRole('cell')[0];
      expect(within(getFirstCell(rows[1])).getByText('1')).toBeInTheDocument();
      expect(within(getFirstCell(rows[2])).getByText('2')).toBeInTheDocument();
      expect(within(getFirstCell(rows[3])).getByText('3')).toBeInTheDocument();
    });
  });

  describe('search behavior', () => {
    it('calls API with search parameter', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(getMerchantAnalytics).toHaveBeenCalledWith(
        expect.objectContaining({ search: '' })
      );
      const searchInput = screen.getByPlaceholderText('Search merchants...');
      fireEvent.change(searchInput, { target: { value: 'star' } });
      await waitFor(() => {
        expect(getMerchantAnalytics).toHaveBeenCalledWith(
          expect.objectContaining({ search: 'star' })
        );
      });
    });
  });

  describe('date-range behavior', () => {
    it('passes date range to API', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="2026-01-01" endDate="2026-06-30" />);
      await waitFor(() => {
        expect(getMerchantAnalytics).toHaveBeenCalledWith(
          expect.objectContaining({ start_date: '2026-01-01', end_date: '2026-06-30' })
        );
      });
    });
  });

  describe('empty state', () => {
    it('shows empty message when no merchants', async () => {
      getMerchantAnalytics.mockResolvedValue(mockEmptyMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getByText('No merchant data yet')).toBeInTheDocument();
      expect(screen.getByText('Upload transactions to see your top merchants.')).toBeInTheDocument();
    });

    it('displays zero merchants count', async () => {
      getMerchantAnalytics.mockResolvedValue(mockEmptyMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getByText(/0 merchants/)).toBeInTheDocument();
    });
  });

  describe('no-search-results state', () => {
    it('shows no results message when search returns empty', async () => {
      getMerchantAnalytics.mockResolvedValue(mockEmptyMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      const searchInput = screen.getByPlaceholderText('Search merchants...');
      fireEvent.change(searchInput, { target: { value: 'nonexistent' } });
      await waitFor(() => {
        expect(screen.getByText(/No merchants found matching "nonexistent"/)).toBeInTheDocument();
        expect(screen.getByText('Try a different search term.')).toBeInTheDocument();
      });
    });
  });

  describe('loading state', () => {
    it('shows skeleton while loading', async () => {
      getMerchantAnalytics.mockReturnValue(new Promise(() => {}));
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      expect(document.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
    });
  });

  describe('API error state', () => {
    it('shows error message on API failure', async () => {
      getMerchantAnalytics.mockRejectedValue(new Error('Network error'));
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitFor(() => {
        expect(screen.getByText('Failed to load merchant analytics')).toBeInTheDocument();
      });
    });
  });

  describe('authenticated API request', () => {
    it('calls getMerchantAnalytics on mount', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      expect(getMerchantAnalytics).toHaveBeenCalledTimes(1);
    });
  });

  describe('responsive/rendering sanity', () => {
    it('renders the full table structure', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      const table = screen.getByRole('table');
      expect(within(table).getByText('#')).toBeInTheDocument();
      expect(within(table).getByText('Merchant')).toBeInTheDocument();
      expect(within(table).getByText('Total Spent')).toBeInTheDocument();
      expect(within(table).getByText('Transactions')).toBeInTheDocument();
      expect(within(table).getByText('Average')).toBeInTheDocument();
      expect(within(table).getByText('Largest')).toBeInTheDocument();
      expect(within(table).getByText('% of Total')).toBeInTheDocument();
      expect(within(table).getByText('Category')).toBeInTheDocument();
    });

    it('renders search input and limit select', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getByPlaceholderText('Search merchants...')).toBeInTheDocument();
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('displays total expenses in header', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getByText(/Total spending: ₹400.00/)).toBeInTheDocument();
    });

    it('displays merchant count in header', async () => {
      getMerchantAnalytics.mockResolvedValue(mockMerchantData);
      renderWithAuth(<MerchantAnalytics startDate="" endDate="" />);
      await waitForLoad();
      expect(screen.getByText(/3 merchants/)).toBeInTheDocument();
    });
  });
});
