import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('axios', () => {
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  };
  return { default: { create: vi.fn(() => instance) } };
});

import axios from 'axios';
import AnomalyAlerts from '../components/AnomalyAlerts';

const api = axios.create();

const anomalyFixture = [
  {
    id: 'duplicate_1-2',
    type: 'duplicate',
    severity: 'critical',
    transaction_ids: [1, 2],
    merchant: 'Target',
    amount: 45,
    dates: ['2026-03-01', '2026-03-02'],
    gap_hours: 24,
    date: null,
    message: 'Possible duplicate: Target charged ₹45.00 twice within 1 days.',
  },
  {
    id: 'price_jump_3',
    type: 'price_jump',
    severity: 'warning',
    transaction_ids: [3],
    merchant: 'Netflix',
    amount: 150,
    previous_amount: 100,
    new_amount: 150,
    percent_increase: 50,
    date: '2026-03-01',
    message: 'Price jump: Netflix increased by 50% (from ₹100.00 to ₹150.00).',
  },
  {
    id: 'unfamiliar_merchant_4',
    type: 'unfamiliar_merchant',
    severity: 'info',
    transaction_ids: [4],
    merchant: 'Big Bazaar',
    amount: 1000,
    date: '2026-03-12',
    message: 'Unusually large new expense: Big Bazaar for ₹1000.00.',
  },
];

const anomalyCalls = () => api.get.mock.calls.map(([url]) => url).filter((u) => u.startsWith('/anomalies'));

const lastAnomalyCall = () => {
  const calls = anomalyCalls();
  return calls[calls.length - 1];
};

describe('Anomaly alerts and account selector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: anomalyFixture });
    api.post.mockResolvedValue({ data: { message: 'ok' } });
  });

  it('All Accounts omits account_id from the anomalies request', async () => {
    render(<AnomalyAlerts />);
    await waitFor(() => expect(screen.getByText('Anomaly Alerts')).toBeInTheDocument());
    expect(lastAnomalyCall()).toBe('/anomalies');
  });

  it('selected account sends account_id to the anomalies request', async () => {
    render(<AnomalyAlerts accountId={7} />);
    await waitFor(() => expect(screen.getByText('Anomaly Alerts')).toBeInTheDocument());
    expect(lastAnomalyCall()).toBe('/anomalies?account_id=7');
  });

  it('switching accounts refetches anomalies with the new account_id', async () => {
    const view = render(<AnomalyAlerts accountId={5} />);
    await waitFor(() => expect(lastAnomalyCall()).toBe('/anomalies?account_id=5'));
    view.rerender(<AnomalyAlerts accountId={6} />);
    await waitFor(() => expect(lastAnomalyCall()).toBe('/anomalies?account_id=6'));
    expect(anomalyCalls().length).toBeGreaterThanOrEqual(2);
    view.rerender(<AnomalyAlerts />);
    await waitFor(() => expect(lastAnomalyCall()).toBe('/anomalies'));
  });

  it('renders backend anomaly data directly', async () => {
    const { container } = render(<AnomalyAlerts accountId={7} />);
    await waitFor(() => expect(screen.getByText('Anomaly Alerts')).toBeInTheDocument());
    // type labels derived from backend anomaly type
    expect(screen.getByText('Possible duplicate charge')).toBeInTheDocument();
    expect(screen.getByText('Price increase')).toBeInTheDocument();
    expect(screen.getByText('New large expense')).toBeInTheDocument();
    // merchants
    expect(screen.getByText('Target')).toBeInTheDocument();
    expect(screen.getByText('Netflix')).toBeInTheDocument();
    expect(screen.getByText('Big Bazaar')).toBeInTheDocument();
    // messages straight from the backend
    expect(screen.getByText('Possible duplicate: Target charged ₹45.00 twice within 1 days.')).toBeInTheDocument();
    expect(screen.getByText('Price jump: Netflix increased by 50% (from ₹100.00 to ₹150.00).')).toBeInTheDocument();
    // amounts, dates, increase
    expect(screen.getByText('₹45')).toBeInTheDocument();
    expect(screen.getByText('₹150')).toBeInTheDocument();
    expect(screen.getByText('₹1000')).toBeInTheDocument();
    expect(screen.getByText('2026-03-01, 2026-03-02')).toBeInTheDocument();
    expect(screen.getByText(/Increase:/).textContent).toContain('50%');
    // severity colors from backend severity
    expect(container.innerHTML).toContain('#EF4444');
    expect(container.innerHTML).toContain('#F59E0B');
    expect(container.innerHTML).toContain('#3B82F6');
  });

  it('shows the empty state when there are no anomalies', async () => {
    api.get.mockResolvedValue({ data: [] });
    render(<AnomalyAlerts accountId={7} />);
    await waitFor(() => expect(screen.getByText(/No unusual activity detected/)).toBeInTheDocument());
    expect(screen.getByText(/Your spending looks normal/)).toBeInTheDocument();
    expect(screen.queryByText('Anomaly Alerts')).not.toBeInTheDocument();
  });

  it('renders nothing while loading', async () => {
    api.get.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<AnomalyAlerts accountId={7} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the API error state when the anomalies request fails', async () => {
    api.get.mockRejectedValue(new Error('network down'));
    const { container } = render(<AnomalyAlerts accountId={7} />);
    await waitFor(() => expect(container.textContent).toContain('Failed to load anomalies'));
    expect(container.textContent).not.toContain('No unusual activity detected');
    expect(screen.queryByText('Anomaly Alerts')).not.toBeInTheDocument();
  });

  it('dismiss removes the anomaly and calls the backend', async () => {
    render(<AnomalyAlerts accountId={7} />);
    await waitFor(() => expect(screen.getByText('Anomaly Alerts')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Dismiss')[0]);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/anomalies/duplicate_1-2/dismiss'));
    await waitFor(() => {
      expect(screen.queryByText('Possible duplicate: Target charged ₹45.00 twice within 1 days.')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Price increase')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it('confirm flags the anomaly as an issue via the backend', async () => {
    render(<AnomalyAlerts accountId={7} />);
    await waitFor(() => expect(screen.getByText('Anomaly Alerts')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Flag as issue')[0]);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/anomalies/duplicate_1-2/confirm'));
    await waitFor(() => {
      expect(screen.queryByText('Possible duplicate: Target charged ₹45.00 twice within 1 days.')).not.toBeInTheDocument();
    });
    expect(screen.getByText('New large expense')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it('existing anomaly UI behavior without any account prop', async () => {
    const extra = {
      id: 'custom_9',
      type: 'weird_type',
      severity: 'info',
      transaction_ids: [9],
      merchant: 'Odd Shop',
      amount: null,
      date: '2026-05-01',
      message: 'Something odd happened.',
    };
    api.get.mockResolvedValue({ data: [...anomalyFixture, extra] });
    const { container } = render(<AnomalyAlerts />);
    await waitFor(() => expect(screen.getByText('Anomaly Alerts')).toBeInTheDocument());
    expect(lastAnomalyCall()).toBe('/anomalies');
    // unknown anomaly type falls back to the existing default label
    expect(screen.getByText('Unusual activity')).toBeInTheDocument();
    // both actions on every card
    expect(screen.getAllByText('Flag as issue')).toHaveLength(4);
    expect(screen.getAllByText('Dismiss')).toHaveLength(4);
    // missing amount renders no amount instead of a broken value
    expect(container.textContent).not.toContain('₹null');
    expect(screen.getByText('Something odd happened.')).toBeInTheDocument();
  });
});
