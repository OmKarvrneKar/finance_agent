import React, { useState, useEffect } from 'react';
import {
  Target,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Clock,
  HelpCircle,
  MinusCircle,
  Info,
} from 'lucide-react';
import { getGoalProgress } from '../utils/api';
import { formatCurrency, formatDateDisplay } from '../utils/dateUtils';
import './GoalTrackingDashboard.css';

// Every value below is rendered exactly as the backend sent it. No money math,
// no percentage math, and no date derivation happens in this component -- in
// particular a projected date is only ever shown when the backend provided one.
const STATUS_PRESENTATION = {
  completed: {
    label: 'Goal completed',
    Icon: CheckCircle2,
    color: '#059669',
    bg: 'var(--credit-bg)',
    border: 'var(--credit-border)',
    // The target is already met, so there is nothing left to forecast.
    message: 'Target reached. No further projection is needed.',
  },
  on_track: {
    label: 'On track',
    Icon: TrendingUp,
    color: '#059669',
    bg: 'var(--credit-bg)',
    border: 'var(--credit-border)',
    message: 'Projected to finish by your target date.',
  },
  behind: {
    label: 'Behind target',
    Icon: AlertTriangle,
    color: '#D97706',
    bg: '#FEF3C7',
    border: '#FCD34D',
    message: 'At the current rate this goal will finish after its target date.',
  },
  no_progress: {
    label: 'No progress',
    Icon: MinusCircle,
    color: '#DC2626',
    bg: 'var(--debit-bg)',
    border: 'var(--debit-border)',
    message:
      'No reliable completion projection is available because contributions are not increasing.',
  },
  insufficient_data: {
    label: 'Not enough history',
    Icon: HelpCircle,
    color: 'var(--text-muted)',
    bg: 'var(--bg-secondary)',
    border: 'var(--border-color)',
    message:
      'More contribution history is required before a completion date can be projected.',
  },
  no_target_date: {
    label: 'No target date',
    Icon: Info,
    color: '#3B82F6',
    bg: '#EFF6FF',
    border: '#BFDBFE',
    message: 'Projected from your contribution rate. This goal has no target date.',
  },
};

const FALLBACK_STATUS = {
  label: 'Unknown',
  Icon: Info,
  color: 'var(--text-muted)',
  bg: 'var(--bg-secondary)',
  border: 'var(--border-color)',
  message: 'Projection status was not recognised.',
};

// The backend clamps progress to 0-100 and sends a number, so this is a plain
// passthrough for rendering rather than a recalculation.
const percentLabel = (value) =>
  `${Number(value ?? 0).toFixed(Number(value ?? 0) % 1 === 0 ? 0 : 2)}%`;

const GoalTrackingDashboard = ({ refreshKey = 0 }) => {
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadGoals = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getGoalProgress();
      setGoals(data.goals || []);
    } catch (err) {
      setError(
        err?.response?.data?.detail || 'Could not load goal progress. Please try again.'
      );
      setGoals([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGoals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  if (loading) {
    return (
      <div className="goal-tracking" data-testid="goal-tracking-loading">
        <div className="goal-tracking-header">
          <h3 className="goal-tracking-title">
            <Target size={20} /> Goal Tracking
          </h3>
        </div>
        <div className="goal-tracking-grid">
          <div className="skeleton" style={{ height: '200px' }} />
          <div className="skeleton" style={{ height: '200px' }} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="goal-tracking" data-testid="goal-tracking-error">
        <div className="goal-tracking-header">
          <h3 className="goal-tracking-title">
            <Target size={20} /> Goal Tracking
          </h3>
        </div>
        <div className="goal-tracking-error">
          <AlertTriangle size={20} color="#DC2626" />
          <p className="goal-tracking-error-text">{error}</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={loadGoals}
            data-testid="goal-tracking-retry"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (goals.length === 0) {
    return (
      <div className="goal-tracking" data-testid="goal-tracking-empty">
        <div className="goal-tracking-header">
          <h3 className="goal-tracking-title">
            <Target size={20} /> Goal Tracking
          </h3>
        </div>
        <div className="goal-tracking-empty">
          <Target size={32} color="var(--text-muted)" style={{ opacity: 0.5 }} />
          <p>No savings goals to track yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="goal-tracking" data-testid="goal-tracking">
      <div className="goal-tracking-header">
        <h3 className="goal-tracking-title">
          <Target size={20} /> Goal Tracking
        </h3>
        <span className="goal-tracking-count">
          {goals.length} goal{goals.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className="goal-tracking-grid">
        {goals.map((goal) => {
          const status = STATUS_PRESENTATION[goal.projection_status] || FALLBACK_STATUS;
          const { Icon } = status;
          // Only render a projected date the backend actually supplied.
          const hasProjection =
            goal.projected_completion_date !== null &&
            goal.projected_completion_date !== undefined;

          return (
            <div
              key={goal.goal_id}
              className="goal-card"
              data-testid={`goal-card-${goal.goal_id}`}
              data-status={goal.projection_status}
            >
              <div className="goal-card-header">
                <h4 className="goal-card-name">{goal.goal_name}</h4>
                <span
                  className="goal-status-badge"
                  style={{ backgroundColor: status.bg, color: status.color, borderColor: status.border }}
                  data-testid={`goal-status-${goal.goal_id}`}
                >
                  <Icon size={13} /> {status.label}
                </span>
              </div>

              <div className="goal-amounts">
                <div className="goal-amount-main">
                  <span className="goal-amount-value" data-testid={`goal-current-${goal.goal_id}`}>
                    {formatCurrency(goal.current_amount)}
                  </span>
                  <span className="goal-amount-target">
                    of {formatCurrency(goal.target_amount)}
                  </span>
                </div>
                <span className="goal-percent" data-testid={`goal-percent-${goal.goal_id}`}>
                  {percentLabel(goal.progress_percent)}
                </span>
              </div>

              <div
                className="goal-progress-track"
                role="progressbar"
                aria-valuenow={goal.progress_percent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${goal.goal_name} progress`}
                data-testid={`goal-progress-bar-${goal.goal_id}`}
              >
                <div
                  className="goal-progress-fill"
                  style={{
                    width: `${goal.progress_percent}%`,
                    backgroundColor: status.color,
                  }}
                />
              </div>

              <div className="goal-meta">
                <div className="goal-meta-row">
                  <span className="goal-meta-label">Remaining</span>
                  <span
                    className="goal-meta-value"
                    data-testid={`goal-remaining-${goal.goal_id}`}
                  >
                    {Number(goal.remaining_amount) < 0
                      ? `Over by ${formatCurrency(Math.abs(Number(goal.remaining_amount)).toFixed(2))}`
                      : formatCurrency(goal.remaining_amount)}
                  </span>
                </div>
                <div className="goal-meta-row">
                  <span className="goal-meta-label">Target date</span>
                  <span
                    className="goal-meta-value"
                    data-testid={`goal-target-date-${goal.goal_id}`}
                  >
                    {goal.target_date ? formatDateDisplay(goal.target_date) : 'Not set'}
                  </span>
                </div>
              </div>

              {(goal.monthly_contribution_rate !== null &&
                goal.monthly_contribution_rate !== undefined) || (
                goal.contribution_count > 0
              ) ? (
                <div className="goal-contributions" data-testid={`goal-contributions-${goal.goal_id}`}>
                  <div className="goal-meta-row">
                    <span className="goal-meta-label">Monthly rate</span>
                    <span
                      className="goal-meta-value"
                      data-testid={`goal-rate-${goal.goal_id}`}
                    >
                      {goal.monthly_contribution_rate !== null &&
                      goal.monthly_contribution_rate !== undefined
                        ? formatCurrency(goal.monthly_contribution_rate)
                        : 'Not available'}
                    </span>
                  </div>
                  <div className="goal-meta-row">
                    <span className="goal-meta-label">Avg contribution</span>
                    <span
                      className="goal-meta-value"
                      data-testid={`goal-avg-contribution-${goal.goal_id}`}
                    >
                      {goal.average_monthly_contribution !== null &&
                      goal.average_monthly_contribution !== undefined
                        ? formatCurrency(goal.average_monthly_contribution)
                        : 'Not available'}
                    </span>
                  </div>
                  <div className="goal-meta-row">
                    <span className="goal-meta-label">Contributions logged</span>
                    <span className="goal-meta-value">{goal.contribution_count}</span>
                  </div>
                </div>
              ) : null}

              <div
                className="goal-projection"
                style={{ backgroundColor: status.bg, borderColor: status.border }}
                data-testid={`goal-projection-${goal.goal_id}`}
              >
                <div className="goal-projection-head">
                  <Icon size={15} color={status.color} />
                  <span style={{ color: status.color, fontWeight: 600 }}>
                    {status.message}
                  </span>
                </div>
                {hasProjection && (
                  <div className="goal-projection-dates">
                    <span>
                      Projected completion:{' '}
                      <strong data-testid={`goal-projected-date-${goal.goal_id}`}>
                        {formatDateDisplay(goal.projected_completion_date)}
                      </strong>
                    </span>
                    {goal.projected_months_remaining !== null &&
                    goal.projected_months_remaining !== undefined ? (
                      <span data-testid={`goal-projected-months-${goal.goal_id}`}>
                        <Clock size={12} /> {goal.projected_months_remaining} month
                        {goal.projected_months_remaining === 1 ? '' : 's'} remaining
                      </span>
                    ) : null}
                  </div>
                )}
                {goal.projection_status === 'completed' && (
                  <div className="goal-projection-dates">
                    <span data-testid={`goal-completed-${goal.goal_id}`}>
                      <CheckCircle2 size={12} /> Target fully funded
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default GoalTrackingDashboard;