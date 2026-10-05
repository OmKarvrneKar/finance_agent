import React, { useState, useEffect } from 'react';
import { getImprovedForecast } from '../utils/api';
import { TrendingUp, TrendingDown, AlertCircle, Info } from 'lucide-react';

const CONFIDENCE_COLORS = {
  high: { bg: '#d1fae5', text: '#065f46' },
  medium: { bg: '#fef3c7', text: '#92400e' },
  low: { bg: '#fee2e2', text: '#991b1b' },
  none: { bg: 'var(--bg-secondary)', text: 'var(--text-muted)' },
};

const METHOD_LABELS = {
  actual_complete: 'Actual (Month Complete)',
  daily_run_rate: 'Daily Run Rate',
  moving_average: 'Moving Average',
  blended_daily_run_rate_and_moving_average: 'Blended (Run Rate + Average)',
  moving_average_fallback: 'Historical Average (Fallback)',
  actual_current_month: 'Actual (Current)',
  insufficient_data: 'Insufficient Data',
  unknown: 'Unknown',
};

const ForecastCard = ({ month, accountId }) => {
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getImprovedForecast(month, '', accountId);
        setForecast(data);
        setError(null);
      } catch (err) {
        setError('Failed to load forecast');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [month, accountId]);

  if (loading) {
    return (
      <div className="card" style={{ padding: '24px' }}>
        <div className="skeleton" style={{ height: '160px', width: '100%' }}></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card" style={{ padding: '24px', borderLeft: '4px solid var(--debit-text)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--debit-text)' }}>
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!forecast) return null;

  const confidence = CONFIDENCE_COLORS[forecast.confidence] || CONFIDENCE_COLORS.none;
  const isInsufficient = forecast.insufficient_data;

  return (
    <div className="card" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
        <div>
          <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
            Spending Forecast
          </h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
            {forecast.month}
          </p>
        </div>
        <span style={{
          padding: '4px 10px', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase',
          backgroundColor: confidence.bg, color: confidence.text,
        }}>
          {forecast.confidence} confidence
        </span>
      </div>

      {isInsufficient ? (
        <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text-muted)' }}>
          <Info size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
          <p style={{ fontWeight: 500, marginBottom: '4px' }}>Not enough data to forecast</p>
          <p style={{ fontSize: '0.85rem' }}>Upload more bank statements to enable forecasting.</p>
        </div>
      ) : (
        <>
          {/* Main numbers */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
            <div style={{ padding: '16px', backgroundColor: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Actual Spent</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-main)', marginTop: '4px' }}>
                ₹{Number(forecast.actual_spend).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                {forecast.num_transactions} transaction{forecast.num_transactions !== 1 ? 's' : ''}
              </div>
            </div>
            <div style={{ padding: '16px', backgroundColor: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Projected Month-End</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--primary-blue)', marginTop: '4px' }}>
                ₹{Number(forecast.projected_month_end).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              {forecast.historical_average && (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                  Avg: ₹{Number(forecast.historical_average).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              )}
            </div>
          </div>

          {/* Remaining + daily rate */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Remaining (Projected)</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', marginTop: '4px' }}>
                {forecast.remaining_spend !== null ? (
                  <>₹{Number(forecast.remaining_spend).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>N/A</span>
                )}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Daily Run Rate</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', marginTop: '4px' }}>
                {forecast.daily_run_rate ? (
                  <>₹{Number(forecast.daily_run_rate).toLocaleString('en-IN', { minimumFractionDigits: 2 })}/day</>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>N/A</span>
                )}
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
              <span>Day {forecast.days_passed} of {forecast.total_days_in_month}</span>
              <span>{forecast.days_remaining} days remaining</span>
            </div>
            <div style={{ height: '6px', backgroundColor: 'var(--border-light)', borderRadius: '3px', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${Math.min((forecast.days_passed / forecast.total_days_in_month) * 100, 100)}%`,
                backgroundColor: 'var(--primary-blue)',
                borderRadius: '3px',
              }} />
            </div>
          </div>

          {/* Method explanation */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '12px', backgroundColor: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            <Info size={16} style={{ marginTop: '2px', flexShrink: 0 }} />
            <div>
              <span style={{ fontWeight: 500, color: 'var(--text-main)' }}>
                {METHOD_LABELS[forecast.method] || forecast.method}:
              </span>{' '}
              {forecast.method_description}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ForecastCard;
