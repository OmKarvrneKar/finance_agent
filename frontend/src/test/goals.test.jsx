import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import Goals from '../pages/Goals';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  getSavingsGoals: vi.fn(),
  getSavingsGoal: vi.fn(),
  createSavingsGoal: vi.fn(),
  updateSavingsGoal: vi.fn(),
  deleteSavingsGoal: vi.fn(),
  contributeToGoal: vi.fn(),
  getGoalsSummary: vi.fn(),
  getGoalProgress: vi.fn().mockResolvedValue({ goals: [], total: 0 }),
}));

import { getSavingsGoals, createSavingsGoal, deleteSavingsGoal, contributeToGoal, getGoalsSummary, getMe, getGoalProgress } from '../utils/api';

const mockGoal = (overrides = {}) => ({
  id: 1,
  name: 'Emergency Fund',
  description: '6 months of expenses',
  target_amount: '100000',
  current_amount: '25000',
  target_date: '2027-06-01',
  status: 'active',
  progress_percent: 25.0,
  projected_completion: null,
  created_at: '2026-09-01T00:00:00',
  updated_at: '2026-09-27T00:00:00',
  ...overrides,
});

const mockSummary = {
  total_goals: 2,
  active_goals: 1,
  completed_goals: 1,
  total_target: '150000',
  total_saved: '50000',
  overall_progress: 33.33,
};

const renderWithAuth = (ui) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

const emptySummary = { total_goals: 0, active_goals: 0, completed_goals: 0, total_target: '0', total_saved: '0', overall_progress: 0 };

describe('Goals page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders page title', async () => {
    getSavingsGoals.mockResolvedValue([]);
    getGoalsSummary.mockResolvedValue(emptySummary);
    renderWithAuth(<Goals />);
    expect(screen.getByText('Savings Goals')).toBeInTheDocument();
  });

  it('shows empty state when no goals', async () => {
    getSavingsGoals.mockResolvedValue([]);
    getGoalsSummary.mockResolvedValue(emptySummary);
    renderWithAuth(<Goals />);
    await waitFor(() => {
      expect(screen.getByText('No savings goals yet.')).toBeInTheDocument();
    });
  });

  it('displays goals after loading', async () => {
    getSavingsGoals.mockResolvedValue([
      mockGoal(),
      mockGoal({ id: 2, name: 'Vacation', current_amount: '50000', target_amount: '50000', progress_percent: 100, status: 'completed' }),
    ]);
    getGoalsSummary.mockResolvedValue(mockSummary);
    renderWithAuth(<Goals />);
    await waitFor(() => {
      expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
      expect(screen.getByText('Vacation')).toBeInTheDocument();
    });
  });

  it('shows progress percentage', async () => {
    getSavingsGoals.mockResolvedValue([mockGoal()]);
    getGoalsSummary.mockResolvedValue(mockSummary);
    renderWithAuth(<Goals />);
    await waitFor(() => {
      expect(screen.getByText('25.0%')).toBeInTheDocument();
    });
  });

  it('opens create form on New Goal click', async () => {
    getSavingsGoals.mockResolvedValue([]);
    getGoalsSummary.mockResolvedValue(emptySummary);
    renderWithAuth(<Goals />);
    await waitFor(() => {
      expect(screen.getByText('New Goal')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('New Goal'));
    await waitFor(() => {
      expect(screen.getByText('Create New Goal')).toBeInTheDocument();
    });
  });

  it('calls createSavingsGoal on form submit', async () => {
    getSavingsGoals.mockResolvedValue([]);
    getGoalsSummary.mockResolvedValue(emptySummary);
    createSavingsGoal.mockResolvedValue({});
    renderWithAuth(<Goals />);
    await waitFor(() => {
      expect(screen.getByText('New Goal')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('New Goal'));
    const nameInput = screen.getAllByRole('textbox')[0];
    fireEvent.change(nameInput, { target: { value: 'New Fund' } });
    const amountInput = screen.getAllByRole('spinbutton')[0];
    fireEvent.change(amountInput, { target: { value: '50000' } });
    fireEvent.click(screen.getByText('Create Goal'));
    await waitFor(() => {
      expect(createSavingsGoal).toHaveBeenCalledWith(expect.objectContaining({ name: 'New Fund', target_amount: '50000' }));
    });
  });

  it('calls deleteSavingsGoal on delete click', async () => {
    getSavingsGoals.mockResolvedValue([mockGoal()]);
    getGoalsSummary.mockResolvedValue(mockSummary);
    deleteSavingsGoal.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithAuth(<Goals />);
    await waitFor(() => expect(screen.getByText('Emergency Fund')).toBeInTheDocument());
    fireEvent.click(screen.getAllByTitle('Delete')[0]);
    await waitFor(() => {
      expect(deleteSavingsGoal).toHaveBeenCalledWith(1);
    });
    window.confirm.mockRestore();
  });

  it('opens contribute modal and submits', async () => {
    getSavingsGoals.mockResolvedValue([mockGoal()]);
    getGoalsSummary.mockResolvedValue(mockSummary);
    contributeToGoal.mockResolvedValue({});
    renderWithAuth(<Goals />);
    await waitFor(() => expect(screen.getByText('Emergency Fund')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Contribute'));
    await waitFor(() => {
      expect(screen.getByText(/Add Contribution to/)).toBeInTheDocument();
    });
    const amountInput = screen.getByRole('spinbutton');
    fireEvent.change(amountInput, { target: { value: '5000' } });
    fireEvent.click(screen.getByText('Add Contribution'));
    await waitFor(() => {
      expect(contributeToGoal).toHaveBeenCalledWith(1, '5000');
    });
  });

  it('shows error state on load failure', async () => {
    getSavingsGoals.mockRejectedValue(new Error('Network error'));
    getGoalsSummary.mockRejectedValue(new Error('Network error'));
    renderWithAuth(<Goals />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load savings goals')).toBeInTheDocument();
    });
  });

  describe('goal tracking dashboard integration', () => {
    const progressPayload = {
      goals: [
        {
          goal_id: 1,
          goal_name: 'Emergency Fund',
          target_amount: '100000.00',
          current_amount: '25000.00',
          remaining_amount: '75000.00',
          progress_percent: 25,
          target_date: '2027-06-01',
          monthly_contribution_rate: '5000.00',
          average_monthly_contribution: '2500.00',
          contribution_count: 4,
          projected_completion_date: '2027-02-01',
          projected_months_remaining: 4,
          projection_status: 'on_track',
        },
      ],
      total: 1,
    };

    it('renders the tracking dashboard on the goals page', async () => {
      getSavingsGoals.mockResolvedValue([mockGoal()]);
      getGoalsSummary.mockResolvedValue(mockSummary);
      getGoalProgress.mockResolvedValue(progressPayload);
      renderWithAuth(<Goals />);

      await waitFor(() => expect(screen.getByTestId('goal-tracking')).toBeInTheDocument());
      expect(screen.getByTestId('goal-status-1')).toHaveTextContent('On track');
    });

    it('does not render the tracking section while the page itself is loading', async () => {
      getSavingsGoals.mockReturnValue(new Promise(() => {}));
      getGoalsSummary.mockReturnValue(new Promise(() => {}));
      renderWithAuth(<Goals />);

      // Flush AuthProvider's own resolution so the loading assertion is not racing it.
      await act(async () => {});
      expect(screen.queryByTestId('goal-tracking')).not.toBeInTheDocument();
      expect(screen.queryByTestId('goal-tracking-loading')).not.toBeInTheDocument();
    });

    it('refetches progress after a contribution is recorded', async () => {
      getSavingsGoals.mockResolvedValue([mockGoal()]);
      getGoalsSummary.mockResolvedValue(mockSummary);
      contributeToGoal.mockResolvedValue({});
      getGoalProgress.mockResolvedValue(progressPayload);
      renderWithAuth(<Goals />);

      await waitFor(() => expect(getGoalProgress).toHaveBeenCalledTimes(1));

      fireEvent.click(screen.getByText('Contribute'));
      fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '5000' } });
      fireEvent.click(screen.getByText('Add Contribution'));

      await waitFor(() => expect(contributeToGoal).toHaveBeenCalledWith(1, '5000'));
      // The read-only projection must pick up the new contribution immediately.
      await waitFor(() => expect(getGoalProgress).toHaveBeenCalledTimes(2));
    });
  });
});
