import React, { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { getMerchantAnalytics } from '../utils/api';
import { AlertCircle, Search, Store, TrendingDown } from 'lucide-react';

const COLORS = ['#3B82F6', '#059669', '#D97706', '#DC2626', '#7C3AED', '#0284C7', '#C026D3', '#0D9488', '#E11D48'];

const MerchantAnalytics = ({ startDate, endDate, accountId }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [limit, setLimit] = useState(10);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getMerchantAnalytics({
        start_date: startDate || '',
        end_date: endDate || '',
        limit,
        search,
        ...(accountId !== undefined ? { account_id: accountId } : {}),
      });
      setData(result);
    } catch (err) {
      if (err.response?.status === 401) return;
      setError('Failed to load merchant analytics');
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, limit, search, accountId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSearchChange = (e) => {
    setSearch(e.target.value);
  };

  const handleLimitChange = (e) => {
    setLimit(Number(e.target.value));
  };

  if (loading) {
    return (
      <div className="card" style={{ padding: '24px' }}>
        <div className="skeleton" style={{ height: '60px', width: '100%', marginBottom: '16px' }}></div>
        <div className="skeleton" style={{ height: '300px', width: '100%' }}></div>
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

  const { merchants, total_merchants, total_expenses } = data;
  const chartData = merchants.slice(0, 8).map(m => ({
    name: m.merchant.length > 15 ? m.merchant.slice(0, 12) + '...' : m.merchant,
    fullName: m.merchant,
    value: Number(m.total_spent),
  }));

  return (
    <div className="card" style={{ padding: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '36px', height: '36px', borderRadius: '8px',
            backgroundColor: 'var(--accent-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Store size={18} style={{ color: 'var(--accent-color)' }} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
              Top Merchants
            </h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: '4px 0 0' }}>
              {total_merchants} merchant{total_merchants !== 1 ? 's' : ''} · Total spending: ₹{Number(total_expenses).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: '1 1 200px', maxWidth: '300px' }}>
          <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search merchants..."
            value={search}
            onChange={handleSearchChange}
            aria-label="Search merchants"
            style={{
              width: '100%', padding: '8px 10px 8px 32px',
              borderRadius: '6px', border: '1px solid var(--border-color)',
              fontSize: '0.85rem', backgroundColor: 'var(--bg-color)',
            }}
          />
        </div>
        <select
          value={limit}
          onChange={handleLimitChange}
          aria-label="Limit merchants"
          style={{
            padding: '8px 12px', borderRadius: '6px',
            border: '1px solid var(--border-color)', fontSize: '0.85rem',
            backgroundColor: 'var(--bg-color)',
          }}
        >
          <option value={5}>Top 5</option>
          <option value={10}>Top 10</option>
          <option value={20}>Top 20</option>
          <option value={50}>Top 50</option>
          <option value={100}>All</option>
        </select>
      </div>

      {/* Empty States */}
      {merchants.length === 0 && (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
          <TrendingDown size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
          <p style={{ fontWeight: 500, marginBottom: '4px' }}>
            {search ? `No merchants found matching "${search}"` : 'No merchant data yet'}
          </p>
          <p style={{ fontSize: '0.85rem' }}>
            {search ? 'Try a different search term.' : 'Upload transactions to see your top merchants.'}
          </p>
        </div>
      )}

      {/* Chart */}
      {merchants.length > 0 && (
        <div style={{ height: '250px', width: '100%', marginBottom: '24px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} stroke="var(--border-color)" />
              <YAxis width={70} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} tickFormatter={(val) => `₹${val}`} stroke="none" />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const item = payload[0].payload;
                    return (
                      <div style={{ backgroundColor: 'var(--card-bg)', padding: '12px', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-md)' }}>
                        <p style={{ margin: '0 0 8px', fontWeight: 600, color: 'var(--text-main)' }}>{item.fullName}</p>
                        <p style={{ margin: 0, color: 'var(--text-muted)' }}>
                          ₹{item.value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </p>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Bar dataKey="value" fill="var(--accent-color)" radius={[4, 4, 0, 0]} name="Spending (₹)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table */}
      {merchants.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                <th style={{ textAlign: 'left', padding: '10px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>#</th>
                <th style={{ textAlign: 'left', padding: '10px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Merchant</th>
                <th style={{ textAlign: 'right', padding: '10px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total Spent</th>
                <th style={{ textAlign: 'right', padding: '10px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Transactions</th>
                <th style={{ textAlign: 'right', padding: '10px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Average</th>
                <th style={{ textAlign: 'right', padding: '10px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Largest</th>
                <th style={{ textAlign: 'right', padding: '10px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>% of Total</th>
                <th style={{ textAlign: 'left', padding: '10px 12px', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Category</th>
              </tr>
            </thead>
            <tbody>
              {merchants.map((m, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>{idx + 1}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 500, color: 'var(--text-main)' }}>{m.merchant}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600, color: 'var(--debit-text)' }}>
                    ₹{Number(m.total_spent).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-main)' }}>{m.transaction_count}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-main)' }}>
                    ₹{Number(m.average_amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-main)' }}>
                    ₹{Number(m.largest_transaction).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600,
                      backgroundColor: COLORS[idx % COLORS.length] + '18',
                      color: COLORS[idx % COLORS.length],
                    }}>
                      {Number(m.spending_percent).toFixed(1)}%
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>{m.category}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default MerchantAnalytics;
