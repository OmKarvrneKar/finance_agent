import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import GoalTrackingDashboard from '../components/GoalTrackingDashboard';

vi.mock('../utils/api', () => ({
  getMe: vi.fn().mockRejectedValue(new Error('no auth')),
  logoutUser: vi.fn(),
  getGoalProgress: vi.fn(),
}));

import { getGoalProgress, getMe } from '../utils/api';
import { formatCurrency, formatDateDisplay } from '../utils/dateUtils';

// Mirrors GoalProgressResponse. Money arrives as a string because the backend
// serialises Decimal; progress_percent and projected_months_remaining are numbers.
const mockProgress = (overrides = {}) => ({
  goal_id: 1,
  goal_name: 'Emergency Fund',
  target_amount: '100000.00',
  current_amount: '25000.00',
  remaining_amount: '75000.00',
  progress_percent: 25.0,
  target_date: '2027-06-01',
  monthly_contribution_rate: '5000.00',
  average_monthly_contribution: '2500.00',
  contribution_count: 4,
  projected_completion_date: '2027-02-01',
  projected_months_remaining: 4,
  projection_status: 'on_track',
  ...overrides,
});

const listOf = (goals) => ({ goals, total: goals.length });

const renderDashboard = (ui = <GoalTrackingDashboard />) => {
  getMe.mockResolvedValue({ email: 'test@test.com' });
  return render(<MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>);
};

describe('GoalTrackingDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  describe('goal rendering', () => {
    it('renders one card per goal with name, target and current amounts', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress(),
          mockProgress({ goal_id: 2, goal_name: 'Laptop Fund', target_amount: '80000.00', current_amount: '80000.00' }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-tracking')).toBeInTheDocument());
      expect(screen.getByText('Emergency Fund')).toBeInTheDocument();
      expect(screen.getByText('Laptop Fund')).toBeInTheDocument();

      const first = screen.getByTestId('goal-card-1');
      expect(within(first).getByTestId('goal-current-1')).toHaveTextContent(
        formatCurrency('25000.00')
      );
      expect(first).toHaveTextContent(formatCurrency('100000.00'));
      expect(screen.getByTestId('goal-tracking-count')).toHaveTextContent('2 goals');
    });

    it('formats currency with Indian grouping and two decimals', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([mockProgress({ current_amount: '1234567.5', target_amount: '2000000.00' })])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-current-1')).toBeInTheDocument());
      expect(screen.getByTestId('goal-current-1')).toHaveTextContent('₹12,34,567.50');
    });
  });

  describe('progress percentage and bar', () => {
    it('renders the percentage supplied by the backend without recalculating it', async () => {
      getGoalProgress.mockResolvedValue(listOf([mockProgress({ progress_percent: 25.0 })]));
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-percent-1')).toHaveTextContent('25%'));
    });

    it('keeps fractional percentages from the backend', async () => {
      getGoalProgress.mockResolvedValue(listOf([mockProgress({ progress_percent: 33.33 })]));
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-percent-1')).toHaveTextContent('33.33%'));
    });

    it('sets the progress bar width directly from progress_percent', async () => {
      getGoalProgress.mockResolvedValue(listOf([mockProgress({ progress_percent: 40 })]));
      renderDashboard();

      const track = await screen.findByTestId('goal-progress-bar-1');
      expect(track).toHaveAttribute('aria-valuenow', '40');
      expect(track.firstChild).toHaveStyle({ width: '40%' });
    });

    it('does not clamp or recompute an over-funded progress value', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([mockProgress({ progress_percent: 120, projection_status: 'completed' })])
      );
      renderDashboard();

      const track = await screen.findByTestId('goal-progress-bar-1');
      expect(track.firstChild).toHaveStyle({ width: '120%' });
    });
  });

  describe('remaining amount', () => {
    it('displays the backend remaining amount', async () => {
      getGoalProgress.mockResolvedValue(listOf([mockProgress({ remaining_amount: '75000.00' })]));
      renderDashboard();

      await waitFor(() =>
        expect(screen.getByTestId('goal-remaining-1')).toHaveTextContent('₹75,000.00')
      );
    });

    it('shows a negative remaining amount as an over-funding message', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([mockProgress({ remaining_amount: '-2500.00', projection_status: 'completed' })])
      );
      renderDashboard();

      const remaining = await screen.findByTestId('goal-remaining-1');
      expect(remaining).toHaveTextContent('Over by ₹2,500.00');
    });
  });

  describe('contribution rate', () => {
    it('shows monthly contribution rate and average contribution', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([mockProgress({ monthly_contribution_rate: '5000.00', average_monthly_contribution: '2500.00' })])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-rate-1')).toHaveTextContent('₹5,000.00'));
      expect(screen.getByTestId('goal-avg-contribution-1')).toHaveTextContent('₹2,500.00');
      expect(screen.getByTestId('goal-contributions-1')).toHaveTextContent('4');
    });

    it('shows Not available rather than inventing a rate when the backend sends null', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            monthly_contribution_rate: null,
            average_monthly_contribution: null,
            contribution_count: 1,
            projected_completion_date: null,
            projected_months_remaining: null,
            projection_status: 'insufficient_data',
          }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-rate-1')).toHaveTextContent('Not available'));
      expect(screen.getByTestId('goal-avg-contribution-1')).toHaveTextContent('Not available');
    });

    it('omits the contribution block entirely when nothing has been logged', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            monthly_contribution_rate: null,
            average_monthly_contribution: null,
            contribution_count: 0,
            projection_status: 'insufficient_data',
          }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-tracking')).toBeInTheDocument());
      expect(screen.queryByTestId('goal-contributions-1')).not.toBeInTheDocument();
    });
  });

  describe('projected completion date', () => {
    it('renders the projected date supplied by the backend', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([mockProgress({ projected_completion_date: '2027-02-01', projected_months_remaining: 4 })])
      );
      renderDashboard();

      const projected = await screen.findByTestId('goal-projected-date-1');
      expect(projected).toHaveTextContent(formatDateDisplay('2027-02-01'));
      expect(screen.getByTestId('goal-projected-months-1')).toHaveTextContent('4 months remaining');
    });

    it('uses the singular form for exactly one projected month', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([mockProgress({ projected_months_remaining: 1, projected_completion_date: '2026-11-01' })])
      );
      renderDashboard();

      await waitFor(() =>
        expect(screen.getByTestId('goal-projected-months-1')).toHaveTextContent('1 month remaining')
      );
    });

    it('never invents a completion date when the backend sends null', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            projected_completion_date: null,
            projected_months_remaining: null,
            projection_status: 'insufficient_data',
          }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-tracking')).toBeInTheDocument());
      expect(screen.queryByTestId('goal-projected-date-1')).not.toBeInTheDocument();
      expect(screen.queryByTestId('goal-projected-months-1')).not.toBeInTheDocument();
      expect(screen.queryByText(/Projected completion:/)).not.toBeInTheDocument();
    });

    it('shows the target date when provided and Not set otherwise', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({ goal_id: 1, target_date: '2027-06-01' }),
          mockProgress({ goal_id: 2, target_date: null, projection_status: 'no_target_date' }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-target-date-1')).toHaveTextContent(formatDateDisplay('2027-06-01')));
      expect(screen.getByTestId('goal-target-date-2')).toHaveTextContent('Not set');
    });
  });

  describe('projection status states', () => {
    it('renders completed goals as clearly achieved', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            current_amount: '100000.00',
            remaining_amount: '0.00',
            progress_percent: 100,
            projection_status: 'completed',
            projected_completion_date: null,
            projected_months_remaining: null,
          }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-status-1')).toHaveTextContent('Goal completed'));
      expect(screen.getByTestId('goal-completed-1')).toHaveTextContent('Target fully funded');
      expect(screen.getByTestId('goal-card-1')).toHaveAttribute('data-status', 'completed');
      expect(screen.queryByTestId('goal-projected-date-1')).not.toBeInTheDocument();
    });

    it('renders no_progress as no reliable projection being available', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            monthly_contribution_rate: null,
            average_monthly_contribution: null,
            contribution_count: 0,
            projection_status: 'no_progress',
            projected_completion_date: null,
            projected_months_remaining: null,
          }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-status-1')).toHaveTextContent('No progress'));
      expect(screen.getByTestId('goal-projection-1')).toHaveTextContent(
        'No reliable completion projection is available'
      );
      expect(screen.queryByTestId('goal-projected-date-1')).not.toBeInTheDocument();
    });

    it('explains that more contribution history is required for insufficient_data', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            monthly_contribution_rate: null,
            average_monthly_contribution: null,
            contribution_count: 1,
            projection_status: 'insufficient_data',
            projected_completion_date: null,
            projected_months_remaining: null,
          }),
        ])
      );
      renderDashboard();

      await waitFor(() =>
        expect(screen.getByTestId('goal-status-1')).toHaveTextContent('Not enough history')
      );
      expect(screen.getByTestId('goal-projection-1')).toHaveTextContent(
        'More contribution history is required'
      );
    });

    it('shows projected date alongside target date for on_track', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            projection_status: 'on_track',
            projected_completion_date: '2027-02-01',
            projected_months_remaining: 4,
            target_date: '2027-06-01',
          }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-status-1')).toHaveTextContent('On track'));
      expect(screen.getByTestId('goal-projected-date-1')).toHaveTextContent(formatDateDisplay('2027-02-01'));
      expect(screen.getByTestId('goal-target-date-1')).toHaveTextContent(formatDateDisplay('2027-06-01'));
      expect(screen.getByTestId('goal-projection-1')).toHaveTextContent(
        'Projected to finish by your target date'
      );
    });

    it('shows projected date after the target date for behind', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            projection_status: 'behind',
            projected_completion_date: '2028-01-01',
            projected_months_remaining: 11,
            target_date: '2027-06-01',
          }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-status-1')).toHaveTextContent('Behind target'));
      expect(screen.getByTestId('goal-projected-date-1')).toHaveTextContent(formatDateDisplay('2028-01-01'));
      expect(screen.getByTestId('goal-target-date-1')).toHaveTextContent(formatDateDisplay('2027-06-01'));
      expect(screen.getByTestId('goal-projection-1')).toHaveTextContent('after its target date');
    });

    it('explains no_target_date while still showing the projection', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([
          mockProgress({
            projection_status: 'no_target_date',
            target_date: null,
            projected_completion_date: '2027-02-01',
            projected_months_remaining: 4,
          }),
        ])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-status-1')).toHaveTextContent('No target date'));
      expect(screen.getByTestId('goal-projection-1')).toHaveTextContent('This goal has no target date');
      expect(screen.getByTestId('goal-projected-date-1')).toHaveTextContent(formatDateDisplay('2027-02-01'));
      expect(screen.getByTestId('goal-target-date-1')).toHaveTextContent('Not set');
    });

    it('falls back gracefully for an unrecognised status', async () => {
      getGoalProgress.mockResolvedValue(
        listOf([mockProgress({ projection_status: 'some_future_status' })])
      );
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-status-1')).toHaveTextContent('Unknown'));
      expect(screen.getByTestId('goal-projection-1')).toHaveTextContent('not recognised');
    });
  });

  describe('loading, empty and error states', () => {
    it('shows a loading state before data arrives', async () => {
      let resolve;
      getGoalProgress.mockReturnValue(new Promise((r) => { resolve = r; }));
      renderDashboard();

      expect(screen.getByTestId('goal-tracking-loading')).toBeInTheDocument();
      expect(screen.queryByTestId('goal-tracking')).not.toBeInTheDocument();

      resolve(listOf([mockProgress()]));
      await waitFor(() => expect(screen.getByTestId('goal-tracking')).toBeInTheDocument());
    });

    it('shows the empty state when the user has no goals', async () => {
      getGoalProgress.mockResolvedValue(listOf([]));
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-tracking-empty')).toBeInTheDocument());
      expect(screen.getByText('No savings goals to track yet.')).toBeInTheDocument();
      expect(screen.queryByTestId('goal-tracking-error')).not.toBeInTheDocument();
    });

    it('shows an API error state when the request fails', async () => {
      getGoalProgress.mockRejectedValue(new Error('boom'));
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-tracking-error')).toBeInTheDocument());
      expect(screen.getByText('Could not load goal progress. Please try again.')).toBeInTheDocument();
      expect(screen.queryByTestId('goal-tracking')).not.toBeInTheDocument();
    });

    it('surfaces the API detail message when the backend sends one', async () => {
      getGoalProgress.mockRejectedValue({ response: { data: { detail: 'Not authenticated' } } });
      renderDashboard();

      await waitFor(() => expect(screen.getByText('Not authenticated')).toBeInTheDocument());
    });

    it('retries the request when the retry button is used', async () => {
      getGoalProgress.mockRejectedValueOnce(new Error('boom'));
      renderDashboard();

      await waitFor(() => expect(screen.getByTestId('goal-tracking-error')).toBeInTheDocument());
      getGoalProgress.mockResolvedValue(listOf([mockProgress()]));

      fireEvent.click(screen.getByTestId('goal-tracking-retry'));
      await waitFor(() => expect(screen.getByTestId('goal-tracking')).toBeInTheDocument());
      expect(getGoalProgress).toHaveBeenCalledTimes(2);
    });
  });

  describe('authenticated request', () => {
    it('fetches progress through the api module, which attaches the auth token', async () => {
      getGoalProgress.mockResolvedValue(listOf([mockProgress()]));
      renderDashboard();

      await waitFor(() => expect(getGoalProgress).toHaveBeenCalledTimes(1));
    });

    it('refetches when the refresh key changes after a contribution', async () => {
      getGoalProgress.mockResolvedValue(listOf([mockProgress()]));
      const { rerender } = renderDashboard();

      await waitFor(() => expect(getGoalProgress).toHaveBeenCalledTimes(1));

      getMe.mockResolvedValue({ email: 'test@test.com' });
      rerender(
        <MemoryRouter>
          <AuthProvider>
            <GoalTrackingDashboard refreshKey={1} />
          </AuthProvider>
        </MemoryRouter>
      );

      await waitFor(() => expect(getGoalProgress).toHaveBeenCalledTimes(2));
    });
  });
});