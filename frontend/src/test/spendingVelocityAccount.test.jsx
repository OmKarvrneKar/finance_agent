import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import SpendingVelocityCard from '../components/SpendingVelocityCard';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockResolvedValue({ email: 'test@test.com' }),
  logoutUser: vi.fn(),
  getSpendingVelocity: vi.fn(),
}));

import { getSpendingVelocity, getMe } from '../utils/api';

const baseResponse = {
  current_window_spend: '150.00',
  baseline_window_spend: '100.00',
  velocity_ratio: 1.5,
  percentage_change: 50.0,
  window_days: 3,
  baseline_method:
    'Mean spend over up to 10 most recent complete non-overlapping 3-day windows.',
  alert_level: 'elevated',
  start_date: '2026-09-28',
  end_date: '2026-09-30',
  baseline_windows_used: 5,
  history_start_date: '2026-06-01',
};

const renderCard = (props = {}) => render(<SpendingVelocityCard {...props} />);

describe('SpendingVelocityCard account awareness', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('changing account selection refreshes velocity', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    const { rerender } = renderCard({ accountId: 5 });
    await waitFor(() => expect(getSpendingVelocity).toHaveBeenCalledTimes(1));
    expect(getSpendingVelocity.mock.calls[0][0]).toEqual({
      window_days: 3,
      account_id: 5,
    });

    rerender(<SpendingVelocityCard accountId={6} />);
    await waitFor(() => expect(getSpendingVelocity).toHaveBeenCalledTimes(2));
    expect(getSpendingVelocity.mock.calls[1][0]).toEqual({
      window_days: 3,
      account_id: 6,
    });
    await waitFor(() => expect(screen.getByTestId('velocity-content')).toBeInTheDocument());
  });

  it('shows loading state while fetching for an account', () => {
    getSpendingVelocity.mockReturnValue(new Promise(() => {}));
    renderCard({ accountId: 5 });
    expect(screen.getByTestId('velocity-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('velocity-content')).not.toBeInTheDocument();
  });

  it('shows API error state for account-scoped request', async () => {
    getSpendingVelocity.mockRejectedValue(new Error('fail'));
    renderCard({ accountId: 5 });
    await waitFor(() => {
      expect(screen.getByTestId('velocity-error')).toHaveTextContent('Failed to load spending velocity');
    });
    expect(screen.queryByTestId('velocity-content')).not.toBeInTheDocument();
  });

  it('shows insufficient_data from backend values', async () => {
    getSpendingVelocity.mockResolvedValue({
      ...baseResponse,
      alert_level: 'insufficient_data',
      velocity_ratio: null,
      percentage_change: null,
      baseline_windows_used: 0,
    });
    renderCard({ accountId: 5 });
    await waitFor(() => {
      expect(screen.getByTestId('velocity-alert-badge')).toHaveTextContent('Not enough history');
    });
    expect(screen.getByTestId('velocity-insufficient-msg')).toBeInTheDocument();
    expect(screen.getByTestId('velocity-ratio')).toHaveTextContent('—');
    expect(screen.getByTestId('velocity-percent')).toHaveTextContent('—');
  });

  it('displays all alert levels from backend values without recalculating', async () => {
    const levels = [
      ['normal', 'Normal'],
      ['elevated', 'Elevated'],
      ['high', 'High'],
      ['very_high', 'Very High'],
    ];
    for (const [level, label] of levels) {
      getSpendingVelocity.mockResolvedValue({
        ...baseResponse,
        alert_level: level,
        velocity_ratio: 2.5,
        percentage_change: 150.0,
      });
      const view = renderCard({ accountId: 5 });
      await waitFor(() => {
        expect(screen.getByTestId('velocity-alert-badge')).toHaveTextContent(label);
      });
      expect(screen.getByTestId('velocity-ratio')).toHaveTextContent('2.5x');
      expect(screen.getByTestId('velocity-percent')).toHaveTextContent('150%');
      view.unmount();
    }
  });

  it('preserves existing window selector and keeps account_id on change', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    renderCard({ accountId: 5 });
    await waitFor(() => expect(getSpendingVelocity).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId('window-option-7'));
    await waitFor(() => {
      expect(getSpendingVelocity).toHaveBeenCalledWith({
        window_days: 7,
        account_id: 5,
      });
    });

    fireEvent.click(screen.getByTestId('window-option-30'));
    await waitFor(() => {
      expect(getSpendingVelocity).toHaveBeenCalledWith({
        window_days: 30,
        account_id: 5,
      });
    });
    expect(screen.getByTestId('window-option-1')).toBeInTheDocument();
    expect(screen.getByTestId('window-option-14')).toBeInTheDocument();
  });

  it('makes authenticated request shape with account_id', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    render(
      <MemoryRouter>
        <AuthProvider>
          <SpendingVelocityCard accountId={12} />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(getMe).toHaveBeenCalled());
    await waitFor(() => expect(getSpendingVelocity).toHaveBeenCalledTimes(1));
    const call = getSpendingVelocity.mock.calls[0][0];
    expect(call).toEqual({ window_days: 3, account_id: 12 });
    expect(typeof call.account_id).toBe('number');
    await waitFor(() => expect(screen.getByTestId('velocity-content')).toBeInTheDocument());
  });
});
