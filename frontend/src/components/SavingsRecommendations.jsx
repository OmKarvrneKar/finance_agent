import React, { useState, useEffect } from 'react';
import { getSavingsRecommendations } from '../utils/api';
import { AlertCircle, TrendingDown, Lightbulb, DollarSign, Target, Info } from 'lucide-react';

const TYPE_LABELS = {
  high_spending_category: 'High Spending Category',
  high_frequency_merchant: 'High-Frequency Merchant',
  spending_increase: 'Spending Increase',
};

const TYPE_ICONS = {
  high_spending_category: Target,
  high_frequency_merchant: TrendingDown,
  spending_increase: TrendingDown,
};

const CONFIDENCE_COLORS = {
  high: { bg: '#d1fae5', text: '#065f46' },
  medium: { bg: '#fef3c7', text: '#92400e' },
  low: { bg: '#fee2e2', text: '#991b1b' },
};

const SavingsRecommendations = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const result = await getSavingsRecommendations();
        setData(result);
        setError(null);
      } catch (err) {
        if (err.response?.status === 401) return;
        setError('Failed to load savings recommendations');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="card" style={{ padding: '24px' }}>
        <div className="skeleton" style={{ height: '120px', width: '100%' }}></div>
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

  const { recommendations, total_estimated_monthly_savings, ai_explanations, ai_summary, ai_error, months_of_data } = data;

  const getExplanation = (index) => {
    if (!ai_explanations || ai_explanations.length === 0) return null;
    return ai_explanations.find(e => e.recommendation_index === index) || null;
  };

  return (
    <div className="card" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
            Savings Recommendations
          </h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: '4px 0 0' }}>
            Data-driven suggestions based on {months_of_data} month{months_of_data !== 1 ? 's' : ''} of spending
          </p>
        </div>
        {recommendations.length > 0 && (
          <div style={{
            padding: '8px 16px', borderRadius: '8px',
            backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '2px' }}>
              Estimated potential savings
            </div>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent-color)' }}>
              ₹{Number(total_estimated_monthly_savings).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>/month</div>
          </div>
        )}
      </div>

      {recommendations.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
          <Info size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
          <p style={{ fontWeight: 500, marginBottom: '4px' }}>No actionable recommendations yet</p>
          <p style={{ fontSize: '0.85rem' }}>
            {ai_summary || 'Keep tracking your transactions and check back once you have at least 2 months of data.'}
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {recommendations.map((rec, idx) => {
            const TypeIcon = TYPE_ICONS[rec.type] || TrendingDown;
            const explanation = getExplanation(idx + 1);
            const confColor = CONFIDENCE_COLORS[rec.confidence] || CONFIDENCE_COLORS.medium;

            return (
              <div key={idx} style={{
                padding: '16px', borderRadius: '8px',
                backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
              }}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{
                      width: '36px', height: '36px', borderRadius: '8px',
                      backgroundColor: 'var(--accent-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <TypeIcon size={18} style={{ color: 'var(--accent-color)' }} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.95rem' }}>
                        {rec.title}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {TYPE_LABELS[rec.type] || rec.type}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: '4px',
                      fontSize: '0.7rem', fontWeight: 600, textTransform: 'capitalize',
                      backgroundColor: confColor.bg, color: confColor.text,
                    }}>
                      {rec.confidence}
                    </span>
                    <span style={{
                      fontWeight: 700, fontSize: '1.05rem',
                      color: 'var(--accent-color)',
                    }}>
                      ₹{Number(rec.estimated_monthly_savings).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>

                {/* Description */}
                <p style={{ fontSize: '0.85rem', color: 'var(--text-main)', margin: '0 0 8px', lineHeight: 1.5 }}>
                  {rec.description}
                </p>

                {/* Supporting Data */}
                {rec.supporting_data && (
                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '8px' }}>
                    {rec.supporting_data.current_monthly_avg && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Current avg: ₹{Number(rec.supporting_data.current_monthly_avg).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    )}
                    {rec.supporting_data.monthly_frequency && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Frequency: {rec.supporting_data.monthly_frequency}x/month
                      </span>
                    )}
                    {rec.supporting_data.percent_above_average && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {rec.supporting_data.percent_above_average}% above average
                      </span>
                    )}
                    {rec.supporting_data.percent_increase && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        +{rec.supporting_data.percent_increase}% vs previous
                      </span>
                    )}
                  </div>
                )}

                {/* AI Explanation */}
                {explanation && (
                  <div style={{
                    marginTop: '12px', padding: '12px', borderRadius: '6px',
                    backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-color)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                      <Lightbulb size={14} style={{ color: '#f59e0b' }} />
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-main)' }}>AI Insight</span>
                    </div>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-main)', margin: '0 0 8px', lineHeight: 1.5 }}>
                      {explanation.explanation}
                    </p>
                    {explanation.practical_tips && explanation.practical_tips.length > 0 && (
                      <ul style={{ margin: 0, paddingLeft: '16px' }}>
                        {explanation.practical_tips.map((tip, ti) => (
                          <li key={ti} style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '2px' }}>
                            {tip}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {/* AI Failure Fallback */}
                {!explanation && ai_error && (
                  <div style={{
                    marginTop: '12px', padding: '8px 12px', borderRadius: '6px',
                    backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                    fontSize: '0.75rem', color: 'var(--text-muted)',
                  }}>
                    AI explanation unavailable — recommendation based on spending analysis
                  </div>
                )}

                {/* Estimated annual */}
                <div style={{ marginTop: '8px', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  Estimated potential annual savings: ₹{Number(rec.estimated_annual_savings).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </div>
            );
          })}

          {/* AI Summary */}
          {ai_summary && (
            <div style={{
              padding: '12px 16px', borderRadius: '8px',
              backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
              fontSize: '0.8rem', color: 'var(--text-main)', lineHeight: 1.5,
            }}>
              <Lightbulb size={14} style={{ color: '#f59e0b', marginRight: '6px', verticalAlign: 'middle' }} />
              {ai_summary}
            </div>
          )}

          {/* AI Error Banner */}
          {ai_error && (
            <div style={{
              padding: '8px 12px', borderRadius: '6px',
              backgroundColor: 'var(--debit-bg)', border: '1px solid var(--debit-text)',
              fontSize: '0.75rem', color: 'var(--debit-text)',
            }}>
              AI explanation unavailable: {ai_error}
            </div>
          )}

          {/* Disclaimer */}
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            <DollarSign size={10} style={{ verticalAlign: 'middle' }} />
            Savings amounts are estimates based on your spending patterns and are not guaranteed.
          </div>
        </div>
      )}
    </div>
  );
};

export default SavingsRecommendations;
