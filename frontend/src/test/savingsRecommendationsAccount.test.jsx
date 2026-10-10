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

const base = {
  total_estimated_annual_savings: 1620,
  categories_analyzed: 3,
  merchants_analyzed: 3,
  months_of_data: 2,
  generated_at: '2026-10-01T10:00:00',
  ai_explanations: [],
  ai_summary: '',
};

const unfilteredRecs = {
  ...base,
  recommendations: [{
    type: 'high_spending_category',
    title: 'Reduce spending on Entertainment',
    description: 'Unfiltered rec driven by NULL-account Casino.',
    estimated_monthly_savings: 1507.84,
    estimated_annual_savings: 18094.08,
    confidence: 'medium',
    supporting_data: {},
  }],
  total_estimated_monthly_savings: 1552.84,
};

const accountARecs = {
  ...base,
  recommendations: [{
    type: 'high_spending_category',
    title: 'Reduce spending on Food',
    description: 'Account A scoped rec.',
    estimated_monthly_savings: 120,
    estimated_annual_savings: 1440,
    confidence: 'medium',
    supporting_data: {},
  }],
  total_estimated_monthly_savings: 135,
};

const accountBRecs = {
  ...base,
  recommendations: [{
    type: 'high_spending_category',
    title: 'Reduce spending on Housing',
    description: 'Account B scoped rec.',
    estimated_monthly_savings: 220,
    estimated_annual_savings: 2640,
    confidence: 'medium',
    supporting_data: {},
  }],
  total_estimated_monthly_savings: 250,
};

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

const lastArg = () =>
  getSavingsRecommendations.mock.calls[getSavingsRecommendations.mock.calls.length - 1][0];

describe('SavingsRecommendations account scoping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    getSavingsRecommendations.mockImplementation((account_id) =>
      Promise.resolve(
        account_id === 1 ? accountARecs : account_id === 2 ? accountBRecs : unfilteredRecs
      )
    );
  });

  it('calls getSavingsRecommendations without account_id when none is given', async () => {
    renderWithAuth(<SavingsRecommendations />);
    await waitFor(() =>
      expect(screen.getByText('Reduce spending on Entertainment')).toBeInTheDocument()
    );
    expect(getSavingsRecommendations.mock.calls[0][0]).toBeUndefined();
    expect(getSavingsRecommendations).toHaveBeenCalledTimes(1);
  });

  it('passes accountId through to getSavingsRecommendations', async () => {
    renderWithAuth(<SavingsRecommendations accountId={1} />);
    await waitFor(() => expect(screen.getByText('Reduce spending on Food')).toBeInTheDocument());
    expect(getSavingsRecommendations.mock.calls[0][0]).toBe(1);
    expect(screen.queryByText('Reduce spending on Entertainment')).not.toBeInTheDocument();
  });

  it('refetches with the new accountId and swaps the rendered recommendations', async () => {
    const { rerender } = renderWithAuth(<SavingsRecommendations />);
    await waitFor(() =>
      expect(screen.getByText('Reduce spending on Entertainment')).toBeInTheDocument()
    );

    rerender(
      <MemoryRouter>
        <AuthProvider>
          <SavingsRecommendations accountId={1} />
        </AuthProvider>
      </MemoryRouter>
    );
    await waitFor(() => expect(lastArg()).toBe(1));
    await waitFor(() => expect(screen.getByText('Reduce spending on Food')).toBeInTheDocument());
    expect(screen.queryByText('Reduce spending on Entertainment')).not.toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <AuthProvider>
          <SavingsRecommendations accountId={2} />
        </AuthProvider>
      </MemoryRouter>
    );
    await waitFor(() => expect(lastArg()).toBe(2));
    await waitFor(() => expect(screen.getByText('Reduce spending on Housing')).toBeInTheDocument());
    expect(screen.queryByText('Reduce spending on Food')).not.toBeInTheDocument();
  });

  it('refetches unscoped when accountId is cleared', async () => {
    const { rerender } = renderWithAuth(<SavingsRecommendations accountId={1} />);
    await waitFor(() => expect(screen.getByText('Reduce spending on Food')).toBeInTheDocument());

    rerender(
      <MemoryRouter>
        <AuthProvider>
          <SavingsRecommendations accountId={undefined} />
        </AuthProvider>
      </MemoryRouter>
    );
    await waitFor(() => expect(lastArg()).toBeUndefined());
    await waitFor(() =>
      expect(screen.getByText('Reduce spending on Entertainment')).toBeInTheDocument()
    );
    expect(screen.queryByText('Reduce spending on Food')).not.toBeInTheDocument();
    expect(getSavingsRecommendations.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('still shows the loading skeleton on the initial scoped fetch', () => {
    getSavingsRecommendations.mockReturnValue(new Promise(() => {}));
    renderWithAuth(<SavingsRecommendations accountId={1} />);
    expect(document.querySelector('.skeleton')).toBeTruthy();
  });
});
