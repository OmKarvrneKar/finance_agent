import React, { useState, useEffect } from 'react';
import { Lightbulb, Settings2 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { simulateWhatIf, getAllTransactions, getSavingsGoals, createSavingsGoal } from '../utils/api';

const WhatIfSimulator = () => {
  const [categories, setCategories] = useState([]);
  const [goals, setGoals] = useState([]);
  
  const [category, setCategory] = useState('');
  const [percentChange, setPercentChange] = useState(0);
  const [selectedGoal, setSelectedGoal] = useState('');
  
  const [newGoalName, setNewGoalName] = useState('');
  const [newGoalTarget, setNewGoalTarget] = useState('');
  const [showAddGoal, setShowAddGoal] = useState(false);

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const initData = async () => {
      try {
        const [txsData, goalsData] = await Promise.all([
          getAllTransactions(),
          getSavingsGoals()
        ]);
        const uniqueCats = [...new Set((txsData.transactions || []).map(t => t.category))].filter(Boolean);
        setCategories(uniqueCats);
        setGoals(goalsData);
      } catch (err) {
        console.error(err);
      }
    };
    initData();
  }, []);

  const handleSimulate = async (e) => {
    e.preventDefault();
    if (!category) return;
    setLoading(true);
    setError(null);
    try {
      const res = await simulateWhatIf({ category, percent_change: parseFloat(percentChange), months: 12, goal_name: selectedGoal || null });
      setResult(res);
    } catch (err) {
      setError(err.response?.data?.detail || 'Simulation failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleAddGoal = async (e) => {
    e.preventDefault();
    if (!newGoalName || !newGoalTarget) return;
    try {
      const added = await createSavingsGoal({ name: newGoalName, target_amount: parseFloat(newGoalTarget) });
      setGoals([...goals, added]);
      setSelectedGoal(added.name);
      setShowAddGoal(false);
      setNewGoalName('');
      setNewGoalTarget('');
    } catch (err) {
      console.error(err);
    }
  };

  const formatCurrency = (val) => `₹${Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

  const chartData = result ? [
    { name: 'Monthly Spend', Baseline: result.baseline_monthly_spend, Simulated: result.new_monthly_spend },
    { name: '1-Year Spend', Baseline: result.baseline_monthly_spend * 12, Simulated: result.new_monthly_spend * 12 }
  ] : [];

  return (
    <div className="card" style={{ marginBottom: '32px' }}>
      <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <Lightbulb size={24} color="var(--primary-blue)" /> What-If Simulator
      </h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '24px' }}>
        See how small habit changes affect your long-term savings trajectory.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
        {/* Form Column */}
        <form onSubmit={handleSimulate} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Category</label>
            <select value={category} onChange={e => setCategory(e.target.value)} style={{ width: '100%', padding: '10px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-main)' }} required>
              <option value="" disabled>Select category to adjust...</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
              <label style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Adjustment</label>
              <span style={{ fontSize: '0.875rem', fontWeight: 600, color: percentChange < 0 ? '#10B981' : percentChange > 0 ? '#EF4444' : 'var(--text-main)' }}>
                {percentChange > 0 ? '+' : ''}{percentChange}%
              </span>
            </div>
            <input type="range" min="-100" max="100" step="5" value={percentChange} onChange={e => setPercentChange(e.target.value)} style={{ width: '100%' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              <span>Cut spending</span>
              <span>Increase spending</span>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Link to Savings Goal (Optional)</label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <select value={selectedGoal} onChange={e => setSelectedGoal(e.target.value)} style={{ flex: 1, padding: '10px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-main)' }}>
                <option value="">None</option>
                {goals.map(g => <option key={g.name} value={g.name}>{g.name} ({formatCurrency(g.target_amount)})</option>)}
              </select>
              <button type="button" className="btn-secondary" onClick={() => setShowAddGoal(!showAddGoal)} style={{ padding: '0 12px' }}>+</button>
            </div>
          </div>

          {showAddGoal && (
            <div style={{ padding: '12px', border: '1px solid var(--border-color)', borderRadius: '8px', backgroundColor: 'var(--bg-color)', display: 'flex', gap: '8px' }}>
              <input type="text" placeholder="Goal Name" value={newGoalName} onChange={e => setNewGoalName(e.target.value)} style={{ flex: 1, padding: '6px', borderRadius: '4px', border: '1px solid var(--border-color)' }} />
              <input type="number" placeholder="Target (₹)" value={newGoalTarget} onChange={e => setNewGoalTarget(e.target.value)} style={{ width: '100px', padding: '6px', borderRadius: '4px', border: '1px solid var(--border-color)' }} />
              <button type="button" className="btn-primary" onClick={handleAddGoal} style={{ padding: '6px 12px' }}>Add</button>
            </div>
          )}

          <button type="submit" className="btn-primary" style={{ padding: '12px', marginTop: '8px', display: 'flex', justifyContent: 'center', gap: '8px' }} disabled={loading}>
            <Settings2 size={18} /> {loading ? 'Calculating...' : 'Simulate'}
          </button>
          {error && <div style={{ color: '#EF4444', fontSize: '0.875rem' }}>{error}</div>}
        </form>

        {/* Results Column */}
        <div style={{ borderLeft: '1px solid var(--border-color)', paddingLeft: '32px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          {!result ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Adjust the sliders and run a simulation to see the impact.</div>
          ) : (
            <div>
              <div style={{ fontSize: '1.1rem', color: 'var(--text-main)', lineHeight: 1.5, marginBottom: '24px' }}>
                If you change your <strong>{result.category}</strong> spending by <strong>{result.percent_change > 0 ? '+' : ''}{result.percent_change}%</strong>, 
                your monthly spend goes from {formatCurrency(result.baseline_monthly_spend)} to {formatCurrency(result.new_monthly_spend)}.
                <br/><br/>
                That's a difference of <strong style={{ color: result.monthly_delta > 0 ? '#10B981' : '#EF4444' }}>{formatCurrency(Math.abs(result.monthly_delta))} / month</strong>.
                Over a year, you would {result.monthly_delta > 0 ? 'save' : 'lose'} <strong>{formatCurrency(Math.abs(result.projected_total_over_period))}</strong>.
              </div>

              {result.months_to_goal && (
                <div style={{ backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#065F46', padding: '16px', borderRadius: '8px', marginBottom: '24px', fontWeight: 500 }}>
                  🎉 At this rate, you'd reach your target for <strong>{selectedGoal}</strong> in just <strong>{result.months_to_goal} months</strong>!
                </div>
              )}

              <div style={{ height: '200px', width: '100%' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 10, right: 0, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-color)" />
                    <XAxis dataKey="name" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} stroke="none" />
                    <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} tickFormatter={(val) => `₹${val}`} stroke="none" width={60} />
                    <Tooltip cursor={{ fill: 'rgba(0,0,0,0.03)' }} formatter={(val) => `₹${val}`} />
                    <Legend />
                    <Bar dataKey="Baseline" fill="#94A3B8" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Simulated" fill="var(--primary-blue)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default WhatIfSimulator;
