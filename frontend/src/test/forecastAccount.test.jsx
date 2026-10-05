import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';

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
import ForecastCard from '../components/ForecastCard';
import ForecastAlerts from '../components/ForecastAlerts';
import {
  getForecastSummary,
  getForecastAlerts,
  getCategoryForecast,
  getImprovedForecast,
} from '../utils/api';

const api = axios.create();

const improvedData = {
  month: '2026-10',
  insufficient_data: false,
  method: 'daily_run_rate',
  method_description: 'Based on your daily average spend.',
  actual_spend: 100.0,
  projected_month_end: 310.0,
  historical_average: 120.0,
  daily_run_rate: 10.0,
  remaining_spend: 210.0,
  num_transactions: 5,
  days_passed: 4,
  days_remaining: 27,
  total_days_in_month: 31,
  confidence: 'medium',
  months_of_history: 3,
};

const summaryData = {
  month: '2026-10',
  forecast: {
    spend_so_far: 100.0,
    daily_run_rate: 10.0,
    total_days: 31,
    days_remaining: 27,
    forecasted_total: 310.0,
  },
  historical: { historical_average: 120.0, months_used: 3, recent_months: [] },
};

const requestedUrls = () => api.get.mock.calls.map(([url]) => url);

const urlsFor = (path) => requestedUrls().filter((u) => u.startsWith(path));

const lastUrlFor = (path) => {
  const list = urlsFor(path);
  return list[list.length - 1];
};

describe('Forecast views and account selector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation((url) => {
      if (url.startsWith('/forecast/improved')) return Promise.resolve({ data: improvedData });
      if (url.startsWith('/forecast/summary')) return Promise.resolve({ data: summaryData });
      if (url.startsWith('/forecast/alerts')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
  });

  it('All Accounts sends no account_id on every forecast endpoint', async () => {
    await getForecastSummary('2026-10');
    await getForecastAlerts('2026-10');
    await getCategoryForecast('Food', '2026-10');
    await getImprovedForecast('2026-10');
    expect(requestedUrls()).toEqual([
      '/forecast/summary?month=2026-10',
      '/forecast/alerts?month=2026-10',
      '/forecast/category/Food?month=2026-10',
      '/forecast/improved?month=2026-10',
    ]);
  });

  it('selected account sends account_id on every forecast endpoint', async () => {
    await getForecastSummary('2026-10', 7);
    await getForecastAlerts('2026-10', 7);
    await getCategoryForecast('Food', '2026-10', 7);
    await getImprovedForecast('2026-10', '', 7);
    expect(requestedUrls()).toEqual([
      '/forecast/summary?month=2026-10&account_id=7',
      '/forecast/alerts?month=2026-10&account_id=7',
      '/forecast/category/Food?month=2026-10&account_id=7',
      '/forecast/improved?month=2026-10&account_id=7',
    ]);
  });

  it('switching accounts refetches the forecast views with the new account_id', async () => {
    const card = render(<ForecastCard month="" accountId={5} />);
    const alerts = render(<ForecastAlerts accountId={5} />);
    await waitFor(() => {
      expect(lastUrlFor('/forecast/improved')).toContain('account_id=5');
      expect(lastUrlFor('/forecast/alerts')).toContain('account_id=5');
      expect(lastUrlFor('/forecast/summary')).toContain('account_id=5');
    });
    card.rerender(<ForecastCard month="" accountId={6} />);
    alerts.rerender(<ForecastAlerts accountId={6} />);
    await waitFor(() => {
      expect(lastUrlFor('/forecast/improved')).toContain('account_id=6');
      expect(lastUrlFor('/forecast/alerts')).toContain('account_id=6');
      expect(lastUrlFor('/forecast/summary')).toContain('account_id=6');
    });
    expect(urlsFor('/forecast/improved').length).toBeGreaterThanOrEqual(2);
    expect(urlsFor('/forecast/alerts').length).toBeGreaterThanOrEqual(2);
  });

  it('forecast summary view requests the selected account and renders its data', async () => {
    const scoped = render(<ForecastAlerts accountId={7} />);
    await waitFor(() => expect(lastUrlFor('/forecast/summary')).toBe('/forecast/summary?account_id=7'));
    await waitFor(() => expect(scoped.container.textContent).toContain('Overall Spending Projection'));
    expect(lastUrlFor('/forecast/alerts')).toBe('/forecast/alerts?account_id=7');
    scoped.unmount();

    const allAccounts = render(<ForecastAlerts />);
    await waitFor(() => expect(lastUrlFor('/forecast/summary')).toBe('/forecast/summary'));
    await waitFor(() => expect(lastUrlFor('/forecast/alerts')).toBe('/forecast/alerts'));
  });

  it('improved forecast view requests the selected account and renders its data', async () => {
    const scoped = render(<ForecastCard month="" accountId={7} />);
    await waitFor(() => expect(lastUrlFor('/forecast/improved')).toBe('/forecast/improved?account_id=7'));
    await waitFor(() => expect(scoped.container.textContent).toContain('Spending Forecast'));
    expect(scoped.container.textContent).toContain('₹100.00');
    scoped.unmount();

    const allAccounts = render(<ForecastCard month="" />);
    await waitFor(() => expect(lastUrlFor('/forecast/improved')).toBe('/forecast/improved'));
  });

  it('forecast alerts view requests the selected account and shows empty state without alerts', async () => {
    const scoped = render(<ForecastAlerts accountId={7} />);
    await waitFor(() => expect(lastUrlFor('/forecast/alerts')).toBe('/forecast/alerts?account_id=7'));
    await waitFor(() => expect(scoped.container.textContent).toContain("You're on track this month"));
    scoped.unmount();

    const allAccounts = render(<ForecastAlerts />);
    await waitFor(() => expect(lastUrlFor('/forecast/alerts')).toBe('/forecast/alerts'));
  });

  it('category forecast supports account_id alongside month', async () => {
    await getCategoryForecast('Food & Dining', '2026-10');
    expect(lastUrlFor('/forecast/category/')).toBe('/forecast/category/Food%20%26%20Dining?month=2026-10');

    await getCategoryForecast('Food & Dining', '2026-10', 7);
    expect(lastUrlFor('/forecast/category/')).toBe(
      '/forecast/category/Food%20%26%20Dining?month=2026-10&account_id=7'
    );

    await getCategoryForecast('Groceries');
    expect(lastUrlFor('/forecast/category/')).toBe('/forecast/category/Groceries');
  });

  it('handles loading and API error states for the forecast views', async () => {
    let release;
    api.get.mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    const loadingCard = render(<ForecastCard month="" accountId={1} />);
    expect(loadingCard.container.querySelector('.skeleton')).toBeInTheDocument();
    release({ data: improvedData });
    await waitFor(() => expect(loadingCard.container.textContent).toContain('Spending Forecast'));
    loadingCard.unmount();

    api.get.mockRejectedValue(new Error('boom'));
    const failingCard = render(<ForecastCard month="" accountId={1} />);
    await waitFor(() => expect(failingCard.container.textContent).toContain('Failed to load forecast'));
    failingCard.unmount();

    api.get.mockImplementation(() => new Promise(() => {}));
    const loadingAlerts = render(<ForecastAlerts accountId={1} />);
    expect(loadingAlerts.container.textContent).not.toContain('Predictive Cash-Flow');
    loadingAlerts.unmount();

    api.get.mockRejectedValue(new Error('boom'));
    const failingAlerts = render(<ForecastAlerts accountId={1} />);
    await waitFor(() => expect(failingAlerts.container.firstChild).toBeNull());
  });
});
