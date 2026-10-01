import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import SpendingVelocityCard from '../components/SpendingVelocityCard';

vi.mock('../utils/api', () => ({
  getSpendingVelocity: vi.fn(),
}));

import { getSpendingVelocity } from '../utils/api';

const baseResponse = {
  current_window_spend: '150.00',
  baseline_window_spend: '100.00',
  velocity_ratio: 1.5,
  percentage_change: 50.0,
  window_days: 3,
  baseline_method:
    'Mean spend over up to 10 most recent complete non-overlapping 3-day windows. Alert thresholds are pace multipliers vs the user own baseline.',
  alert_level: 'elevated',
  start_date: '2026-09-28',
  end_date: '2026-09-30',
  baseline_windows_used: 5,
  history_start_date: '2026-06-01',
};

describe('SpendingVelocityCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading skeleton initially', () => {
    getSpendingVelocity.mockReturnValue(new Promise(() => {}));
    const { container } = render(<SpendingVelocityCard />);
    expect(container.querySelector('.skeleton')).toBeTruthy();
    expect(screen.getByTestId('velocity-loading')).toBeInTheDocument();
  });

  it('renders normal state with backend values', async () => {
    getSpendingVelocity.mockResolvedValue({
      ...baseResponse,
      alert_level: 'normal',
      velocity_ratio: 1.0,
      percentage_change: 0.0,
    });
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-alert-badge')).toHaveTextContent('Normal');
    });
    expect(screen.getByTestId('velocity-current')).toHaveTextContent('₹150.00');
    expect(screen.getByTestId('velocity-baseline')).toHaveTextContent('₹100.00');
    expect(screen.getByTestId('velocity-ratio')).toHaveTextContent('1x');
    expect(screen.getByTestId('velocity-percent')).toHaveTextContent('0%');
    expect(screen.getByText('Last 3 days')).toBeInTheDocument();
  });

  it('renders elevated warning presentation', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-alert-badge')).toHaveTextContent('Elevated');
    });
  });

  it('renders high warning presentation', async () => {
    getSpendingVelocity.mockResolvedValue({
      ...baseResponse,
      alert_level: 'high',
      velocity_ratio: 2.5,
      percentage_change: 150.0,
    });
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-alert-badge')).toHaveTextContent('High');
    });
    expect(screen.getByTestId('velocity-ratio')).toHaveTextContent('2.5x');
    expect(screen.getByTestId('velocity-percent')).toHaveTextContent('150%');
  });

  it('renders very_high prominent alert', async () => {
    getSpendingVelocity.mockResolvedValue({
      ...baseResponse,
      alert_level: 'very_high',
      velocity_ratio: 3.5,
      percentage_change: 250.0,
    });
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-alert-badge')).toHaveTextContent('Very High');
    });
  });

  it('shows insufficient data message without misleading ratio', async () => {
    getSpendingVelocity.mockResolvedValue({
      ...baseResponse,
      alert_level: 'insufficient_data',
      velocity_ratio: null,
      percentage_change: null,
      baseline_windows_used: 1,
    });
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-insufficient-msg')).toBeInTheDocument();
    });
    expect(screen.getByTestId('velocity-alert-badge')).toHaveTextContent('Not enough history');
    expect(screen.getByTestId('velocity-ratio')).toHaveTextContent('—');
    expect(screen.getByTestId('velocity-percent')).toHaveTextContent('—');
  });

  it('shows no baseline explanation', async () => {
    getSpendingVelocity.mockResolvedValue({
      ...baseResponse,
      alert_level: 'no_baseline',
      velocity_ratio: null,
      percentage_change: null,
      baseline_window_spend: '0.00',
      baseline_windows_used: 5,
    });
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-no-baseline-msg')).toBeInTheDocument();
    });
    expect(screen.getByTestId('velocity-alert-badge')).toHaveTextContent('No baseline');
    expect(screen.getByTestId('velocity-ratio')).toHaveTextContent('—');
  });

  it('displays ratio and percentage from backend without recalculating', async () => {
    getSpendingVelocity.mockResolvedValue({
      ...baseResponse,
      velocity_ratio: 1.2345,
      percentage_change: 23.45,
      alert_level: 'elevated',
    });
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-ratio')).toHaveTextContent('1.2345x');
    });
    expect(screen.getByTestId('velocity-percent')).toHaveTextContent('23.45%');
  });

  it('calls API with selected window_days on mount', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(getSpendingVelocity).toHaveBeenCalledWith({ window_days: 3 });
    });
  });

  it('re-calls API when window selector changes', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    render(<SpendingVelocityCard />);
    await waitFor(() => expect(getSpendingVelocity).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId('window-option-7'));
    await waitFor(() => {
      expect(getSpendingVelocity).toHaveBeenCalledWith({ window_days: 7 });
    });

    fireEvent.click(screen.getByTestId('window-option-30'));
    await waitFor(() => {
      expect(getSpendingVelocity).toHaveBeenCalledWith({ window_days: 30 });
    });
  });

  it('renders all window selector options', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('window-option-1')).toBeInTheDocument();
      expect(screen.getByTestId('window-option-3')).toBeInTheDocument();
      expect(screen.getByTestId('window-option-7')).toBeInTheDocument();
      expect(screen.getByTestId('window-option-14')).toBeInTheDocument();
      expect(screen.getByTestId('window-option-30')).toBeInTheDocument();
    });
  });

  it('shows API error state', async () => {
    getSpendingVelocity.mockRejectedValue(new Error('fail'));
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-error')).toHaveTextContent('Failed to load spending velocity');
    });
  });

  it('shows methodology in info area when toggled', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    render(<SpendingVelocityCard />);
    await waitFor(() => expect(screen.getByTestId('velocity-content')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Baseline methodology'));
    expect(screen.getByTestId('velocity-methodology')).toBeInTheDocument();
    expect(screen.getByTestId('velocity-methodology')).toHaveTextContent('non-overlapping');
  });

  it('uses authenticated API request shape', async () => {
    getSpendingVelocity.mockResolvedValue(baseResponse);
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(getSpendingVelocity).toHaveBeenCalled();
    });
    expect(getSpendingVelocity.mock.calls[0][0]).toEqual({ window_days: 3 });
  });

  it('does not show current/baseline cards when API errors', async () => {
    getSpendingVelocity.mockRejectedValue(new Error('network'));
    render(<SpendingVelocityCard />);
    await waitFor(() => {
      expect(screen.getByTestId('velocity-error')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('velocity-current')).not.toBeInTheDocument();
    expect(screen.queryByTestId('velocity-ratio')).not.toBeInTheDocument();
  });
});
