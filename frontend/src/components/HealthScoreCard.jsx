import React, { useState, useEffect } from 'react';
import { getHealthScore } from '../utils/api';
import { AlertCircle, TrendingUp, Wallet, BarChart3, DollarSign } from 'lucide-react';

const SCORE_COLORS = {
  excellent: { bg: '#d1fae5', text: '#065f46', ring: '#10b981' },
  good: { bg: '#dbeafe', text: '#1e40af', ring: '#3b82f6' },
  fair: { bg: '#fef3c7', text: '#92400e', ring: '#f59e0b' },
  poor: { bg: '#fee2e2', text: '#991b1b', ring: '#ef4444' },
};

function getScoreGrade(score) {
  if (score >= 80) return 'excellent';
  if (score >= 60) return 'good';
  if (score >= 40) return 'fair';
  return 'poor';
}

function getScoreLabel(score) {
  if (score >= 80) return 'Excellent';
  if (score >= 60) return 'Good';
  if (score >= 40) return 'Fair';
  return 'Poor';
}

const COMPONENT_ICONS = {
  savings_rate: DollarSign,
  budget_adherence: BarChart3,
  income_stability: TrendingUp,
  spending_consistency: Wallet,
};

const COMPONENT_LABELS = {
  savings_rate: 'Savings Rate',
  budget_adherence: 'Budget Adherence',
  income_stability: 'Income Stability',
  spending_consistency: 'Spending Consistency',
};

const HealthScoreCard = ({ accountId }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await getHealthScore(accountId);
        setData(result);
        setError(null);
      } catch (err) {
        setError('Failed to load health score');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [accountId]);

  if (loading) {
    return (
      <div className="card" style={{ padding: '24px' }}>
        <div className="skeleton" style={{ height: '200px', width: '100%' }}></div>
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

  if (!data) return null;

  const { overall_score, insufficient_data, components, formula, months_analyzed } = data;

  if (insufficient_data) {
    return (
      <div className="card" style={{ padding: '24px' }}>
        <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 16px' }}>
          Financial Health Score
        </h3>
        <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text-muted)' }}>
          <AlertCircle size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
          <p style={{ fontWeight: 500, marginBottom: '4px' }}>Not enough data to calculate score</p>
          <p style={{ fontSize: '0.85rem' }}>Upload at least 2 months of statements with both income and expenses.</p>
        </div>
      </div>
    );
  }

  const grade = getScoreGrade(overall_score);
  const gradeColor = SCORE_COLORS[grade];

  return (
    <div className="card" style={{ padding: '24px' }}>
      <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 20px' }}>
        Financial Health Score
      </h3>

      {/* Score display */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '24px', marginBottom: '24px' }}>
        <div style={{
          width: '100px', height: '100px', borderRadius: '50%',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          backgroundColor: gradeColor.bg, border: `4px solid ${gradeColor.ring}`,
        }}>
          <span style={{ fontSize: '1.8rem', fontWeight: 700, color: gradeColor.text, lineHeight: 1 }}>
            {Number(overall_score)}
          </span>
          <span style={{ fontSize: '0.65rem', color: gradeColor.text, textTransform: 'uppercase', fontWeight: 600 }}>
            {getScoreLabel(overall_score)}
          </span>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Based on {months_analyzed} month{months_analyzed !== 1 ? 's' : ''} of data
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Weights: Savings 40% | Budget 25% | Income 20% | Spending 15%
          </div>
        </div>
      </div>

      {/* Component breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        {Object.entries(components).map(([key, comp]) => {
          const Icon = COMPONENT_ICONS[key] || Wallet;
          const compGrade = comp.score !== null ? getScoreGrade(comp.score) : null;
          const compColor = compGrade ? SCORE_COLORS[compGrade] : { bg: 'var(--bg-secondary)', text: 'var(--text-muted)' };
          return (
            <div key={key} style={{
              padding: '12px', borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                <Icon size={14} style={{ color: 'var(--text-muted)' }} />
                <span style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-main)' }}>
                  {COMPONENT_LABELS[key]}
                </span>
                <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  {formula.weights.split(', ').find(w => w.startsWith(key.split('_')[0]))?.split(' ')[1] || ''}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '4px' }}>
                <span style={{
                  fontSize: '1.2rem', fontWeight: 700,
                  color: comp.score !== null ? compColor.text : 'var(--text-muted)',
                }}>
                  {comp.score !== null ? Number(comp.score) : '--'}
                </span>
                {comp.raw_value !== null && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    ({comp.raw_value}%)
                  </span>
                )}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.3 }}>
                {comp.description}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default HealthScoreCard;
