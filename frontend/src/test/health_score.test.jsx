import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import HealthScoreCard from '../components/HealthScoreCard';

vi.mock('../utils/api', () => ({
  getHealthScore: vi.fn(),
}));

import { getHealthScore } from '../utils/api';

const mockScore = {
  overall_score: 75.50,
  insufficient_data: false,
  months_analyzed: 6,
  components: {
    savings_rate: {
      score: 75.00,
      raw_value: 20.00,
      weight: '40%',
      description: 'Savings rate: 20.00%. Higher is better (30%+ = excellent). Weight: 40%.',
    },
    budget_adherence: {
      score: 100.00,
      raw_value: 100.00,
      weight: '25%',
      description: 'Budget adherence: 100.00% of budgets on track. Weight: 25%.',
    },
    income_stability: {
      score: 85.00,
      raw_value: 85.00,
      weight: '20%',
      description: 'Income stability: 85.00/100 (lower variation = higher score). Weight: 20%.',
    },
    spending_consistency: {
      score: 60.00,
      raw_value: 60.00,
      weight: '15%',
      description: 'Spending consistency: 60.00/100 (lower variation = higher score). Weight: 15%.',
    },
  },
  formula: {
    overall: 'savings_rate * 0.40 + budget_adherence * 0.25 + income_stability * 0.20 + spending_consistency * 0.15',
    savings_rate_score: '0%->0, 5%->25, 10%->50, 20%->75, 30%+->100',
    budget_adherence_score: 'percentage_of_budgets_on_track (0-100)',
    income_stability_score: 'max(0, 100 - coefficient_of_variation_of_income)',
    spending_consistency_score: 'max(0, 100 - coefficient_of_variation_of_expenses)',
    weights: 'savings=40%, budget=25%, income_stability=20%, spending_consistency=15%',
  },
};

const mockInsufficient = {
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

describe('HealthScoreCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading skeleton initially', () => {
    getHealthScore.mockReturnValue(new Promise(() => {}));
    const { container } = render(<HealthScoreCard />);
    expect(container.querySelector('.skeleton')).toBeTruthy();
  });

  it('renders score with sufficient data', async () => {
    getHealthScore.mockResolvedValue(mockScore);
    render(<HealthScoreCard />);
    await waitFor(() => {
      expect(screen.getByText('Financial Health Score')).toBeTruthy();
    });
    expect(screen.getByText('75')).toBeTruthy();
    expect(screen.getByText('Good')).toBeTruthy();
    expect(screen.getByText(/6 months of data/)).toBeTruthy();
  });

  it('renders all four components', async () => {
    getHealthScore.mockResolvedValue(mockScore);
    render(<HealthScoreCard />);
    await waitFor(() => {
      expect(screen.getByText('Savings Rate')).toBeTruthy();
    });
    expect(screen.getByText('Budget Adherence')).toBeTruthy();
    expect(screen.getByText('Income Stability')).toBeTruthy();
    expect(screen.getByText('Spending Consistency')).toBeTruthy();
  });

  it('shows component scores', async () => {
    getHealthScore.mockResolvedValue(mockScore);
    render(<HealthScoreCard />);
    await waitFor(() => {
      expect(screen.getByText('75')).toBeTruthy();
    });
    expect(screen.getByText('100')).toBeTruthy();
    expect(screen.getByText('85')).toBeTruthy();
    expect(screen.getByText('60')).toBeTruthy();
  });

  it('shows component raw values', async () => {
    getHealthScore.mockResolvedValue(mockScore);
    render(<HealthScoreCard />);
    await waitFor(() => {
      expect(screen.getByText('(20%)')).toBeTruthy();
    });
    expect(screen.getByText('(100%)')).toBeTruthy();
  });

  it('shows component descriptions', async () => {
    getHealthScore.mockResolvedValue(mockScore);
    render(<HealthScoreCard />);
    await waitFor(() => {
      expect(screen.getByText(/Savings rate: 20.00%/)).toBeTruthy();
    });
    expect(screen.getByText(/Budget adherence: 100.00%/)).toBeTruthy();
  });

  it('shows insufficient data state', async () => {
    getHealthScore.mockResolvedValue(mockInsufficient);
    render(<HealthScoreCard />);
    await waitFor(() => {
      expect(screen.getByText('Not enough data to calculate score')).toBeTruthy();
    });
    expect(screen.getByText(/Upload at least 2 months/)).toBeTruthy();
  });

  it('shows error state', async () => {
    getHealthScore.mockRejectedValue(new Error('Network error'));
    render(<HealthScoreCard />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load health score')).toBeTruthy();
    });
  });

  it('shows weights in header', async () => {
    getHealthScore.mockResolvedValue(mockScore);
    render(<HealthScoreCard />);
    await waitFor(() => {
      expect(screen.getByText(/Savings 40%/)).toBeTruthy();
    });
    expect(screen.getByText(/Budget 25%/)).toBeTruthy();
    expect(screen.getByText(/Income 20%/)).toBeTruthy();
    expect(screen.getByText(/Spending 15%/)).toBeTruthy();
  });

  it('renders without crashing when data is null', async () => {
    getHealthScore.mockResolvedValue(null);
    let error = null;
    try {
      render(<HealthScoreCard />);
    } catch (e) {
      error = e;
    }
    expect(error).toBeNull();
  });
});
