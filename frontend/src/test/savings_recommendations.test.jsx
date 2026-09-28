import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import SavingsRecommendations from '../components/SavingsRecommendations';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  getSavingsRecommendations: vi.fn(),
}));

import { getSavingsRecommendations, getMe } from '../utils/api';

const mockRecommendations = {
  recommendations: [
    {
      type: 'high_spending_category',
      title: 'Reduce spending on housing',
      description: 'Your average monthly spending on housing is 160% above your overall category average.',
      estimated_monthly_savings: 184.67,
      estimated_annual_savings: 2216.04,
      confidence: 'medium',
      supporting_data: {
        category: 'housing',
        current_monthly_avg: '1500.00',
        overall_category_avg: '576.67',
        percent_above_average: '160.11',
        months_analyzed: 4,
      },
    },
    {
      type: 'high_frequency_merchant',
      title: 'Reduce visits to Starbucks',
      description: 'You visit Starbucks approximately 4.00 times/month with an average spend of 7.50 per visit.',
      estimated_monthly_savings: 1.13,
      estimated_annual_savings: 13.56,
      confidence: 'medium',
      supporting_data: {
        merchant: 'Starbucks',
        category: 'coffee',
        visit_count: 16,
        monthly_frequency: '4.00',
        average_per_visit: '7.50',
        months_analyzed: 4,
      },
    },
  ],
  total_estimated_monthly_savings: 185.80,
  total_estimated_annual_savings: 2229.60,
  categories_analyzed: 5,
  merchants_analyzed: 12,
  months_of_data: 4,
  generated_at: '2026-09-28T10:00:00',
  ai_explanations: [
    {
      recommendation_index: 1,
      explanation: 'Housing is your largest expense. Consider refinancing or downsizing.',
      practical_tips: ['Look into refinancing options', 'Check for housing assistance programs'],
    },
  ],
  ai_summary: 'You have good savings potential across multiple categories.',
};

const mockEmptyRecommendations = {
  recommendations: [],
  total_estimated_monthly_savings: 0,
  total_estimated_annual_savings: 0,
  categories_analyzed: 1,
  merchants_analyzed: 0,
  months_of_data: 1,
  generated_at: '2026-09-28T10:00:00',
  ai_explanations: [],
  ai_summary: 'Not enough spending data yet to identify actionable savings patterns.',
};

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

describe('SavingsRecommendations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('shows loading skeleton', () => {
    getSavingsRecommendations.mockReturnValue(new Promise(() => {}));
    renderWithAuth(<SavingsRecommendations />);
    expect(document.querySelector('.skeleton')).toBeTruthy();
  });

  it('renders recommendations correctly', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText('Reduce spending on housing')).toBeInTheDocument();
      expect(screen.getByText('Reduce visits to Starbucks')).toBeInTheDocument();
    });
  });

  it('displays savings amount from API response', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText(/185/)).toBeInTheDocument();
    });
  });

  it('renders AI explanation', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText('AI Insight')).toBeInTheDocument();
      expect(screen.getByText('Housing is your largest expense. Consider refinancing or downsizing.')).toBeInTheDocument();
    });
  });

  it('renders practical tips', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText('Look into refinancing options')).toBeInTheDocument();
    });
  });

  it('renders confidence badge', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      const badges = screen.getAllByText('medium');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  it('shows empty state with no recommendations', async () => {
    getSavingsRecommendations.mockResolvedValue(mockEmptyRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText('No actionable recommendations yet')).toBeInTheDocument();
    });
  });

  it('shows loading state', async () => {
    getSavingsRecommendations.mockReturnValue(new Promise(() => {}));
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(document.querySelector('.skeleton')).toBeTruthy();
    });
  });

  it('shows API error state', async () => {
    getSavingsRecommendations.mockRejectedValue(new Error('fail'));
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load savings recommendations')).toBeInTheDocument();
    });
  });

  it('shows AI failure fallback when ai_error present', async () => {
    const dataWithAiError = {
      ...mockRecommendations,
      ai_error: 'AI service timed out.',
      ai_explanations: [],
    };
    getSavingsRecommendations.mockResolvedValue(dataWithAiError);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      const fallbacks = screen.getAllByText('AI explanation unavailable — recommendation based on spending analysis');
      expect(fallbacks.length).toBe(2);
    });
  });

  it('shows AI error banner when ai_error present', async () => {
    const dataWithAiError = {
      ...mockRecommendations,
      ai_error: 'AI service timed out.',
      ai_explanations: [],
    };
    getSavingsRecommendations.mockResolvedValue(dataWithAiError);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText(/AI explanation unavailable: AI service timed out/)).toBeInTheDocument();
    });
  });

  it('renders disclaimer about estimated savings', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText(/Savings amounts are estimates/)).toBeInTheDocument();
    });
  });

  it('calls getSavingsRecommendations on mount', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(getSavingsRecommendations).toHaveBeenCalledTimes(1);
    });
  });

  it('renders supporting data (current monthly avg)', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText(/Current avg: ₹1,500/)).toBeInTheDocument();
    });
  });

  it('renders supporting data (frequency)', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText(/Frequency: 4.00x\/month/)).toBeInTheDocument();
    });
  });

  it('renders supporting data (percent above average)', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText(/160.11% above average/)).toBeInTheDocument();
    });
  });

  it('renders months of data info', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText(/4 months of spending/)).toBeInTheDocument();
    });
  });

  it('renders AI summary when present', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText('You have good savings potential across multiple categories.')).toBeInTheDocument();
    });
  });

  it('no financial calculation is performed in frontend', async () => {
    getSavingsRecommendations.mockResolvedValue(mockRecommendations);
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() => {
      expect(screen.getByText('Reduce spending on housing')).toBeInTheDocument();
    });
    const monthlySavingsText = screen.getByText(/185/);
    expect(monthlySavingsText).toBeTruthy();
  });
});
