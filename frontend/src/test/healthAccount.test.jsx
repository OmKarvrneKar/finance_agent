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
import HealthScoreCard from '../components/HealthScoreCard';

const api = axios.create();

const scoredData = {
  overall_score: 75.5,
  insufficient_data: false,
  months_analyzed: 6,
  components: {
    savings_rate: {
      score: 75.0,
      raw_value: 20.0,
      weight: '40%',
      description: 'Savings rate: 20.00%. Higher is better (30%+ = excellent). Weight: 40%.',
    },
    budget_adherence: {
      score: 100.0,
      raw_value: 100.0,
      weight: '25%',
      description: 'Budget adherence: 100.00% of budgets on track. Weight: 25%.',
    },
    income_stability: {
      score: 85.0,
      raw_value: 85.0,
      weight: '20%',
      description: 'Income stability: 85.00/100 (lower variation = higher score). Weight: 20%.',
    },
    spending_consistency: {
      score: 60.0,
      raw_value: 60.0,
      weight: '15%',
      description: 'Spending consistency: 60.00/100 (lower variation = higher score). Weight: 15%.',
    },
  },
  formula: {
    overall: 'weighted_average(...)',
    savings_rate_score: 'piecewise_linear: 0%->0, 5%->25, 10%->50, 20%->75, 30%+->100',
    budget_adherence_score: 'percentage_of_budgets_on_track (0-100), or null if no budgets (weight redistributed)',
    income_stability_score: 'max(0, 100 - coefficient_of_variation_of_income)',
    spending_consistency_score: 'max(0, 100 - coefficient_of_variation_of_expenses)',
    weights: 'savings=40%, budget=25%, income_stability=20%, spending_consistency=15%',
  },
};

const insufficientData = {
  overall_score: null,
  insufficient_data: true,
  months_analyzed: 0,
  components: {
    savings_rate: { score: null, raw_value: null, weight: '40%', description: 'Insufficient data to calculate savings_rate.' },
    budget_adherence: { score: null, raw_value: null, weight: '25%', description: 'Insufficient data to calculate budget_adherence.' },
    income_stability: { score: null, raw_value: null, weight: '20%', description: 'Insufficient data to calculate income_stability.' },
    spending_consistency: { score: null, raw_value: null, weight: '15%', description: 'Insufficient data to calculate spending_consistency.' },
  },
  formula: { overall: '', weights: '' },
};

const healthCalls = () => api.get.mock.calls.map(([url]) => url).filter((u) => u.startsWith('/health'));

const lastHealthCall = () => {
  const calls = healthCalls();
  return calls[calls.length - 1];
};

describe('Financial Health card and account selector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: scoredData });
  });

  it('All Accounts omits account_id from the health request', async () => {
    const { container } = render(<HealthScoreCard />);
    await waitFor(() => expect(container.textContent).toContain('Financial Health Score'));
    expect(lastHealthCall()).toBe('/health');
  });

  it('selected account sends account_id to the health request', async () => {
    const { container } = render(<HealthScoreCard accountId={7} />);
    await waitFor(() => expect(container.textContent).toContain('Financial Health Score'));
    expect(lastHealthCall()).toBe('/health?account_id=7');
  });

  it('switching accounts refetches the health score with the new account_id', async () => {
    const view = render(<HealthScoreCard accountId={5} />);
    await waitFor(() => expect(lastHealthCall()).toBe('/health?account_id=5'));
    view.rerender(<HealthScoreCard accountId={6} />);
    await waitFor(() => expect(lastHealthCall()).toBe('/health?account_id=6'));
    expect(healthCalls().length).toBeGreaterThanOrEqual(2);
    view.rerender(<HealthScoreCard />);
    await waitFor(() => expect(lastHealthCall()).toBe('/health'));
  });

  it('renders the backend health score directly for the selected account', async () => {
    const { container } = render(<HealthScoreCard accountId={7} />);
    await waitFor(() => expect(container.textContent).toContain('Financial Health Score'));
    expect(container.textContent).toContain('75');       // overall score
    expect(container.textContent).toContain('Good');    // grade label from backend score
    expect(container.textContent).toContain('6 months of data');
    expect(container.textContent).toContain('Savings 40%');
  });

  it('renders every backend metric with scores, raw values and descriptions', async () => {
    const { container } = render(<HealthScoreCard accountId={7} />);
    await waitFor(() => expect(container.textContent).toContain('Savings Rate'));
    expect(container.textContent).toContain('Budget Adherence');
    expect(container.textContent).toContain('Income Stability');
    expect(container.textContent).toContain('Spending Consistency');
    // component scores straight from the response
    expect(container.textContent).toContain('100');
    expect(container.textContent).toContain('85');
    expect(container.textContent).toContain('60');
    // raw metric values
    expect(container.textContent).toContain('(20%)');
    expect(container.textContent).toContain('(100%)');
    // backend descriptions/recommendations
    expect(container.textContent).toContain('Savings rate: 20.00%');
    expect(container.textContent).toContain('Income stability: 85.00/100');
    expect(container.textContent).toContain('Budget adherence: 100.00%');
    expect(container.textContent).toContain('Spending consistency: 60.00/100');
  });

  it('shows the loading skeleton while fetching', async () => {
    api.get.mockImplementation(() => new Promise(() => {}));
    const { container } = render(<HealthScoreCard accountId={7} />);
    expect(container.querySelector('.skeleton')).toBeTruthy();
    expect(container.textContent).not.toContain('Financial Health Score');
  });

  it('shows the API error state when the health request fails', async () => {
    api.get.mockRejectedValue(new Error('network down'));
    const { container } = render(<HealthScoreCard accountId={7} />);
    await waitFor(() => expect(container.textContent).toContain('Failed to load health score'));
    expect(container.textContent).not.toContain('Financial Health Score');
  });

  it('shows the insufficient data state for an account without enough history', async () => {
    api.get.mockResolvedValue({ data: insufficientData });
    const { container } = render(<HealthScoreCard accountId={7} />);
    await waitFor(() => expect(container.textContent).toContain('Not enough data to calculate score'));
    expect(container.textContent).toContain('Upload at least 2 months');
  });

  it('existing health UI behavior without any account prop', async () => {
    const { container } = render(<HealthScoreCard />);
    await waitFor(() => expect(container.textContent).toContain('Financial Health Score'));
    // score circle, month basis, weight header, component grid and descriptions
    expect(container.textContent).toContain('75');
    expect(container.textContent).toContain('Good');
    expect(container.textContent).toContain('6 months of data');
    expect(container.textContent).toContain('Budget 25%');
    expect(container.textContent).toContain('Income 20%');
    expect(container.textContent).toContain('Spending 15%');
    expect(container.textContent).toContain('(20%)');
    expect(container.textContent).not.toContain('Insufficient data to calculate');
    expect(lastHealthCall()).toBe('/health');
  });
});
