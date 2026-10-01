import React, { useState, useEffect } from 'react';
import { getSpendingVelocity } from '../utils/api';
import { formatCurrency } from '../utils/dateUtils';
import { Zap, Info, AlertTriangle, AlertCircle, Clock } from 'lucide-react';

const WINDOW_OPTIONS = [1, 3, 7, 14, 30];

const ALERT_STYLES = {
  normal: { bg: '#d1fae5', text: '#065f46', border: '#10b981', label: 'Normal' },
  elevated: { bg: '#fef3c7', text: '#92400e', border: '#f59e0b', label: 'Elevated' },
  high: { bg: '#ffedd5', text: '#9a3412', border: '#f97316', label: 'High' },
  very_high: { bg: '#fee2e2', text: '#991b1b', border: '#ef4444', label: 'Very High' },
  insufficient_data: { bg: '#f3f4f6', text: '#4b5563', border: '#9ca3af', label: 'Not enough history' },
  no_baseline: { bg: '#f3f4f6', text: '#4b5563', border: '#9ca3af', label: 'No baseline' },
};

const SpendingVelocityCard = () => {
  const [windowDays, setWindowDays] = useState(3);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showMethod, setShowMethod] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const result = await getSpendingVelocity({ window_days: windowDays });
        if (!cancelled) setData(result);
      } catch (err) {
        if (cancelled) return;
        if (err.response?.status === 401) return;
        setError('Failed to load spending velocity');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [windowDays]);

  const alertLevel = data?.alert_level || 'insufficient_data';
  const alertStyle = ALERT_STYLES[alertLevel] || ALERT_STYLES.insufficient_data;
  const hasRatio = data?.velocity_ratio != null;
  const hasPct = data?.percentage_change != null;
  const compareLabel = `Last ${data?.window_days ?? windowDays} day${(data?.window_days ?? windowDays) !== 1 ? 's' : ''}`;

  return (
    <div className="card" style={{ padding: '20px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
        <Zap size={18} style={{ color: 'var(--accent-color)' }} />
        <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-main)' }}>
          Spending Velocity
        </h3>
        <button
          type="button"
          onClick={() => setShowMethod((v) => !v)}
          aria-label="Baseline methodology"
          title="How this is calculated"
          style={{
            marginLeft: 'auto', border: 'none', background: 'transparent', cursor: 'pointer',
            color: 'var(--text-muted)', display: 'flex', alignItems: 'center', padding: '4px',
          }}
        >
          <Info size={16} />
        </button>
      </div>

      {showMethod && data?.baseline_method && (
        <div
          data-testid="velocity-methodology"
          style={{
            marginBottom: '14px', padding: '10px 12px', borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
            fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.45,
          }}
        >
          {data.baseline_method}
        </div>
      )}

      <div style={{ display: 'flex', gap: '6px', marginBottom: '16px', flexWrap: 'wrap' }}>
        {WINDOW_OPTIONS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setWindowDays(d)}
            data-testid={`window-option-${d}`}
            style={{
              padding: '5px 12px', fontSize: '0.8rem', borderRadius: '6px', cursor: 'pointer',
              border: '1px solid var(--border-color)',
              backgroundColor: windowDays === d ? 'var(--accent-color)' : 'var(--bg-secondary)',
              color: windowDays === d ? '#fff' : 'var(--text-main)',
              fontWeight: windowDays === d ? 600 : 400,
            }}
          >
            {d}d
          </button>
        ))}
      </div>

      {loading && (
        <div className="skeleton" style={{ height: '90px', width: '100%' }} data-testid="velocity-loading" />
      )}

      {!loading && error && (
        <div
          data-testid="velocity-error"
          style={{ padding: '12px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)', fontSize: '0.875rem' }}
        >
          {error}
        </div>
      )}

      {!loading && !error && data && (
        <div data-testid="velocity-content">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
            <span
              data-testid="velocity-alert-badge"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                padding: '4px 10px', borderRadius: '999px',
                backgroundColor: alertStyle.bg, color: alertStyle.text,
                border: `1px solid ${alertStyle.border}`,
                fontSize: '0.75rem', fontWeight: 600,
              }}
            >
              {(alertLevel === 'elevated' || alertLevel === 'high') && <AlertTriangle size={13} />}
              {alertLevel === 'very_high' && <AlertCircle size={13} />}
              {(alertLevel === 'insufficient_data' || alertLevel === 'no_baseline') && <Clock size={13} />}
              {alertStyle.label}
            </span>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{compareLabel}</span>
            {data.start_date && data.end_date && (
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {data.start_date} → {data.end_date}
              </span>
            )}
          </div>

          {alertLevel === 'insufficient_data' && (
            <p data-testid="velocity-insufficient-msg" style={{ margin: '0 0 12px', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Not enough history to compare spending pace. Add more transactions over time to enable velocity alerts.
            </p>
          )}
          {alertLevel === 'no_baseline' && (
            <p data-testid="velocity-no-baseline-msg" style={{ margin: '0 0 12px', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Historical baseline is zero for this window, so a pace ratio cannot be calculated.
            </p>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px' }}>
            <div style={{ padding: '10px 12px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                Current spend
              </div>
              <div data-testid="velocity-current" style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)' }}>
                {formatCurrency(data.current_window_spend)}
              </div>
            </div>
            <div style={{ padding: '10px 12px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                Baseline spend
              </div>
              <div data-testid="velocity-baseline" style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-main)' }}>
                {formatCurrency(data.baseline_window_spend)}
              </div>
            </div>
            <div style={{ padding: '10px 12px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                Velocity ratio
              </div>
              <div data-testid="velocity-ratio" style={{ fontSize: '1.05rem', fontWeight: 700, color: hasRatio ? alertStyle.text : 'var(--text-muted)' }}>
                {hasRatio ? `${data.velocity_ratio}x` : '—'}
              </div>
            </div>
            <div style={{ padding: '10px 12px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                Change vs baseline
              </div>
              <div data-testid="velocity-percent" style={{ fontSize: '1.05rem', fontWeight: 700, color: hasPct ? alertStyle.text : 'var(--text-muted)' }}>
                {hasPct ? `${data.percentage_change}%` : '—'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SpendingVelocityCard;
