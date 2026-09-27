import React, { useState, useEffect, useCallback } from 'react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, LineChart, Line } from 'recharts';
import { getAnalyticsSummary } from '../utils/api';
import SummaryCard from '../components/SummaryCard';
import ForecastCard from '../components/ForecastCard';
import ForecastAlerts from '../components/ForecastAlerts';
import AnomalyAlerts from '../components/AnomalyAlerts';
import { ArrowDownCircle, ArrowUpCircle, Wallet, Calendar, TrendingDown, TrendingUp } from 'lucide-react';

const COLORS = ['#3B82F6', '#059669', '#D97706', '#DC2626', '#7C3AED', '#0284C7', '#C026D3', '#0D9488', '#E11D48'];

const RANGE_PRESETS = [
  { label: 'This Month', value: 'this_month' },
  { label: 'Last Month', value: 'last_month' },
  { label: 'Last 3 Months', value: 'last_3_months' },
  { label: 'This Year', value: 'this_year' },
  { label: 'All Time', value: 'all_time' },
];

function getPresetDates(preset) {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  switch (preset) {
    case 'this_month':
      return { start: `${y}-${String(m + 1).padStart(2, '0')}-01`, end: `${y}-${String(m + 1).padStart(2, '0')}-${new Date(y, m + 1, 0).getDate()}` };
    case 'last_month': {
      const pm = m === 0 ? 11 : m - 1;
      const py = m === 0 ? y - 1 : y;
      return { start: `${py}-${String(pm + 1).padStart(2, '0')}-01`, end: `${py}-${String(pm + 1).padStart(2, '0')}-${new Date(py, pm + 1, 0).getDate()}` };
    }
    case 'last_3_months': {
      const d = new Date(y, m - 2, 1);
      return { start: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`, end: `${y}-${String(m + 1).padStart(2, '0')}-${new Date(y, m + 1, 0).getDate()}` };
    }
    case 'this_year':
      return { start: `${y}-01-01`, end: `${y}-12-31` };
    case 'all_time':
    default:
      return { start: '', end: '' };
  }
}

const Dashboard = () => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [preset, setPreset] = useState('this_month');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [useCustom, setUseCustom] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const dates = useCustom
        ? { start: customStart, end: customEnd }
        : getPresetDates(preset);
      const data = await getAnalyticsSummary(dates);
      setAnalytics(data);
    } catch (err) {
      if (err.response?.status === 401) return;
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, [preset, customStart, customEnd, useCustom]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{ backgroundColor: 'var(--card-bg)', padding: '12px', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-md)' }}>
          <p style={{ margin: '0 0 8px', fontWeight: 600, color: 'var(--text-main)' }}>{payload[0].name || payload[0].payload?.month}</p>
          <p style={{ margin: 0, color: 'var(--text-muted)' }}>
            ₹{Number(payload[0].value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
      );
    }
    return null;
  };

  if (loading) {
    return (
      <div className="layout-container" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <div className="skeleton" style={{ height: '60px', width: '100%' }}></div>
        <div className="skeleton" style={{ height: '80px', width: '100%' }}></div>
        <div className="skeleton" style={{ height: '300px', width: '100%' }}></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="layout-container">
        <div className="page-header">
          <h1 className="page-title">Financial Dashboard</h1>
        </div>
        <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)' }}>{error}</div>
      </div>
    );
  }

  const data = analytics || { total_income: 0, total_expenses: 0, net_cashflow: 0, transaction_count: 0, category_breakdown: [], spending_trend: [] };
  const categoryData = data.category_breakdown.map(c => ({ name: c.category, value: Number(c.amount) }));
  const trendData = data.spending_trend.map(t => ({ month: t.month, amount: Number(t.amount) }));
  const topCategories = categoryData.slice(0, 5);

  return (
    <div className="layout-container">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 className="page-title">Financial Dashboard</h1>
          <p className="page-description">Overview of your spending habits and financial health.</p>
        </div>
      </div>

      {/* Date Range Controls */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)' }}>
            <Calendar size={16} />
            <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>Period:</span>
          </div>

          <div style={{ display: 'flex', gap: '4px', backgroundColor: 'var(--bg-color)', borderRadius: '6px', padding: '3px', border: '1px solid var(--border-color)' }}>
            {RANGE_PRESETS.map(p => (
              <button key={p.value} onClick={() => { setPreset(p.value); setUseCustom(false); }}
                style={{ padding: '5px 12px', fontSize: '0.8rem', borderRadius: '4px', border: 'none', cursor: 'pointer',
                  backgroundColor: !useCustom && preset === p.value ? 'white' : 'transparent',
                  boxShadow: !useCustom && preset === p.value ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                  color: !useCustom && preset === p.value ? 'var(--text-main)' : 'var(--text-muted)',
                  fontWeight: !useCustom && preset === p.value ? 600 : 400 }}>
                {p.label}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input type="date" value={customStart} onChange={(e) => { setCustomStart(e.target.value); setUseCustom(true); }}
              style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.8rem' }} />
            <span style={{ color: 'var(--text-muted)' }}>to</span>
            <input type="date" value={customEnd} onChange={(e) => { setCustomEnd(e.target.value); setUseCustom(true); }}
              style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.8rem' }} />
          </div>
        </div>
      </div>

      <AnomalyAlerts />
      <ForecastAlerts />

      {/* Forecast Card */}
      {!useCustom && preset === 'this_month' && (
        <div style={{ marginBottom: '24px' }}>
          <ForecastCard />
        </div>
      )}

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        <SummaryCard title="Total Income" value={data.total_income} icon={ArrowUpCircle} isCurrency={true} isIncome={true} />
        <SummaryCard title="Total Expenses" value={data.total_expenses} icon={ArrowDownCircle} isCurrency={true} />
        <SummaryCard title="Net Cash Flow" value={data.net_cashflow} icon={Wallet} isCurrency={true} isIncome={data.net_cashflow >= 0} />
        <SummaryCard title="Transactions" value={data.transaction_count} icon={Calendar} />
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '24px' }}>

        {/* Category Breakdown */}
        <div className="card">
          <h3 style={{ marginBottom: '8px', fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)' }}>Category Breakdown</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '24px' }}>Expenses by category for the selected period.</p>
          {categoryData.length > 0 ? (
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={categoryData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2} dataKey="value">
                    {categoryData.map((_, i) => <Cell key={`cell-${i}`} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend layout="vertical" verticalAlign="middle" align="right" />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              No spending data for this period.
            </div>
          )}
        </div>

        {/* Top Categories */}
        <div className="card">
          <h3 style={{ marginBottom: '8px', fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)' }}>Top Categories</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '24px' }}>Highest expenses for the selected period.</p>
          {topCategories.length > 0 ? (
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topCategories} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} stroke="var(--border-color)" />
                  <YAxis width={80} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} tickFormatter={(val) => `₹${val}`} stroke="none" />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
                  <Bar dataKey="value" fill="var(--accent-color)" radius={[4, 4, 0, 0]} name="Amount (₹)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              No data available.
            </div>
          )}
        </div>

        {/* Spending Trend */}
        {trendData.length > 1 && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <h3 style={{ marginBottom: '8px', fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)' }}>Spending Trend</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '24px' }}>Monthly spending over the selected period.</p>
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} stroke="var(--border-color)" />
                  <YAxis width={80} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} tickFormatter={(val) => `₹${val}`} stroke="none" />
                  <Tooltip content={<CustomTooltip />} />
                  <Line type="monotone" dataKey="amount" stroke="var(--accent-color)" strokeWidth={2} dot={{ r: 4 }} name="Spending (₹)" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
