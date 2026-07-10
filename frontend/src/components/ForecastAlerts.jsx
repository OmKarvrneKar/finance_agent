import React, { useState, useEffect } from 'react';
import { AlertTriangle, TrendingUp, CheckCircle, RefreshCw, Activity } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { getForecastAlerts, getForecastSummary } from '../utils/api';

const ForecastAlerts = () => {
  const [alerts, setAlerts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [alertsData, summaryData] = await Promise.all([
        getForecastAlerts(),
        getForecastSummary()
      ]);
      setAlerts(alertsData);
      setSummary(summaryData);
    } catch (err) {
      console.error('Failed to load forecast data', err);
      setError('Could not load forecasting data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const formatCurrency = (val) => `₹${Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

  const generateChartData = (forecastObj, histObj) => {
    if (!forecastObj || forecastObj.error) return [];
    
    const { spend_so_far, daily_run_rate, total_days, days_remaining } = forecastObj;
    const days_passed = total_days - days_remaining;
    const histAvg = (histObj && !histObj.error) ? histObj.historical_average : null;

    const data = [];
    for (let i = 1; i <= total_days; i++) {
      let actual = null;
      let projected = null;

      if (i <= days_passed) {
        // Approximate actual cumulative spend using linear run rate
        actual = (spend_so_far / days_passed) * i;
        projected = actual;
      } else {
        projected = spend_so_far + (daily_run_rate * (i - days_passed));
      }

      data.push({
        day: i,
        Actual: actual !== null ? Math.round(actual) : null,
        Projected: projected !== null ? Math.round(projected) : null,
        Historical: histAvg !== null ? Math.round(histAvg) : null
      });
    }
    return data;
  };

  if (loading) {
    return (
      <div className="card" style={{ marginBottom: '24px', display: 'flex', justifyContent: 'center', padding: '40px' }}>
        <RefreshCw size={24} color="var(--primary-blue)" style={{ animation: 'spin 2s linear infinite' }} />
      </div>
    );
  }

  if (error) {
    return null; // Fail gracefully
  }

  const chartData = summary ? generateChartData(summary.forecast, summary.historical) : [];
  const hasAlerts = alerts && alerts.length > 0;

  return (
    <div style={{ marginBottom: '32px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={24} color="var(--primary-blue)" /> Predictive Cash-Flow
        </h2>
        <button onClick={fetchData} className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.875rem', display: 'flex', gap: '6px', alignItems: 'center' }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
        
        {/* Alerts Section */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {!hasAlerts ? (
            <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '16px', backgroundColor: 'rgba(16, 185, 129, 0.05)', borderColor: 'rgba(16, 185, 129, 0.2)' }}>
              <div style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', padding: '12px', borderRadius: '50%', color: '#10B981' }}>
                <CheckCircle size={28} />
              </div>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#065F46', marginBottom: '4px' }}>You're on track this month 🎉</h3>
                <p style={{ fontSize: '0.875rem', color: '#047857' }}>Your spending is well within your historical average. Keep it up!</p>
              </div>
            </div>
          ) : (
            alerts.map((alert, idx) => {
              const isCritical = alert.severity === 'critical';
              const colorBase = isCritical ? '#EF4444' : '#F59E0B'; // Red or Amber
              const bgRgba = isCritical ? 'rgba(239, 68, 68, 0.05)' : 'rgba(245, 158, 11, 0.05)';
              const borderRgba = isCritical ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.2)';

              return (
                <div key={idx} className="card" style={{ backgroundColor: bgRgba, borderColor: borderRgba, padding: '20px' }}>
                  <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                    <div style={{ backgroundColor: `${colorBase}15`, padding: '10px', borderRadius: '50%', color: colorBase }}>
                      {isCritical ? <AlertTriangle size={24} /> : <TrendingUp size={24} />}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)' }}>{alert.category} Overspend Alert</h3>
                        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: colorBase, backgroundColor: `${colorBase}15`, padding: '4px 8px', borderRadius: '12px', textTransform: 'uppercase' }}>
                          {alert.severity}
                        </span>
                      </div>
                      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '16px', lineHeight: 1.5 }}>
                        {alert.message}
                      </p>
                      
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', fontSize: '0.875rem' }}>
                        <div>
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Spend So Far</div>
                          <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{formatCurrency(alert.current_spend)}</div>
                        </div>
                        <div>
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Forecast</div>
                          <div style={{ fontWeight: 600, color: colorBase }}>{formatCurrency(alert.forecasted_spend)}</div>
                        </div>
                        <div>
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Avg Limit</div>
                          <div style={{ fontWeight: 600, color: '#10B981' }}>{formatCurrency(alert.historical_average)}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Chart Section */}
        {chartData.length > 0 && (
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '8px' }}>Overall Spending Projection</h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '24px' }}>
              Projected end-of-month spend vs. 3-month historical average.
            </p>
            
            <div style={{ height: '250px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-color)" />
                  <XAxis dataKey="day" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} stroke="none" />
                  <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} tickFormatter={(val) => `₹${val}`} stroke="none" />
                  <Tooltip 
                    contentStyle={{ backgroundColor: 'var(--card-bg)', borderRadius: '8px', border: '1px solid var(--border-color)' }}
                    formatter={(value) => [`₹${value}`, undefined]}
                    labelFormatter={(label) => `Day ${label}`}
                  />
                  
                  {summary.historical && !summary.historical.error && (
                    <ReferenceLine y={summary.historical.historical_average} stroke="#10B981" strokeDasharray="3 3" label={{ position: 'top', fill: '#10B981', fontSize: 12, value: 'Avg' }} />
                  )}
                  
                  <Line type="monotone" dataKey="Actual" stroke="var(--primary-blue)" strokeWidth={3} dot={false} activeDot={{ r: 6 }} />
                  <Line type="monotone" dataKey="Projected" stroke="#94A3B8" strokeWidth={2} strokeDasharray="5 5" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ForecastAlerts;
