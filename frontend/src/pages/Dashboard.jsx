import React, { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { getAllTransactions } from '../utils/api';
import SummaryCard from '../components/SummaryCard';
import ForecastAlerts from '../components/ForecastAlerts';
import AnomalyAlerts from '../components/AnomalyAlerts';
import { List, ArrowDownCircle, ArrowUpCircle, Wallet } from 'lucide-react';

const COLORS = ['#3B82F6', '#059669', '#D97706', '#DC2626', '#7C3AED', '#0284C7', '#C026D3', '#0D9488', '#E11D48'];

const Dashboard = () => {
  const [data, setData] = useState({
    transactions: [],
    totalSpent: 0,
    totalIncome: 0,
    netSavings: 0,
    categoryData: [],
    topCategories: []
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await getAllTransactions();
        const txs = response.transactions || [];
        
        let spent = 0;
        let income = 0;
        const categoryMap = {};

        const currentDate = new Date();
        const currentMonth = currentDate.getMonth();
        const currentYear = currentDate.getFullYear();

        txs.forEach(tx => {
          if (tx.transaction_type === 'debit') {
            spent += tx.amount;
            
            // For pie chart: only current month debits
            const txDate = new Date(tx.date);
            if (txDate.getMonth() === currentMonth && txDate.getFullYear() === currentYear) {
              const cat = tx.category || 'Other';
              categoryMap[cat] = (categoryMap[cat] || 0) + tx.amount;
            }
          } else if (tx.transaction_type === 'credit') {
            income += tx.amount;
          }
        });

        // Format for PieChart
        const categoryData = Object.entries(categoryMap)
          .map(([name, value]) => ({ name, value }))
          .sort((a, b) => b.value - a.value);

        // All time top 5 categories for BarChart
        const allTimeCatMap = {};
        txs.forEach(tx => {
          if (tx.transaction_type === 'debit') {
            const cat = tx.category || 'Other';
            allTimeCatMap[cat] = (allTimeCatMap[cat] || 0) + tx.amount;
          }
        });
        
        const topCategories = Object.entries(allTimeCatMap)
          .map(([name, amount]) => ({ name, amount }))
          .sort((a, b) => b.amount - a.amount)
          .slice(0, 5);

        setData({
          transactions: txs,
          totalSpent: spent,
          totalIncome: income,
          netSavings: income - spent,
          categoryData,
          topCategories
        });
      } catch (error) {
        console.error('Failed to load dashboard data', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{ backgroundColor: 'var(--card-bg)', padding: '12px', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-md)' }}>
          <p style={{ margin: '0 0 8px', fontWeight: 600, color: 'var(--text-main)' }}>{payload[0].name}</p>
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
        <div className="skeleton" style={{ height: '80px', width: '100%' }}></div>
        <div className="skeleton" style={{ height: '300px', width: '100%' }}></div>
      </div>
    );
  }

  return (
    <div className="layout-container">

      <div className="page-header">
        <h1 className="page-title">Financial Dashboard</h1>
        <p className="page-description">Overview of your spending habits and financial health.</p>
      </div>

      <AnomalyAlerts />
      <ForecastAlerts />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '24px', marginBottom: '32px' }}>
        <SummaryCard title="Total Spent" value={data.totalSpent} icon={ArrowDownCircle} isCurrency={true} />
        <SummaryCard title="Total Income" value={data.totalIncome} icon={ArrowUpCircle} isCurrency={true} isIncome={true} />
        <SummaryCard title="Net Savings" value={data.netSavings} icon={Wallet} isCurrency={true} isIncome={data.netSavings >= 0} />
        <SummaryCard title="Transactions" value={data.transactions.length} icon={List} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '24px' }}>
        
        <div className="card">
          <h3 style={{ marginBottom: '8px', fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)' }}>Current Month Spending</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '24px' }}>Breakdown by category for the current calendar month.</p>
          
          {data.categoryData.length > 0 ? (
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data.categoryData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {data.categoryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend layout="vertical" verticalAlign="middle" align="right" />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              No spending data for this month yet.
            </div>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginBottom: '8px', fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)' }}>Top 5 Spending Categories</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '24px' }}>Highest expenses across all time.</p>
          
          {data.topCategories.length > 0 ? (
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.topCategories} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} stroke="var(--border-color)" />
                  <YAxis width={80} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} tickFormatter={(val) => `₹${val}`} stroke="none" />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
                  <Bar dataKey="amount" fill="var(--accent-color)" radius={[4, 4, 0, 0]} name="Amount (₹)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              No transaction data available.
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default Dashboard;
