import React, { useState, useEffect } from 'react';
import { getSavingsGoals, createSavingsGoal, updateSavingsGoal, deleteSavingsGoal, contributeToGoal, getGoalsSummary } from '../utils/api';
import { Target, Plus, Pencil, Trash2, TrendingUp, CheckCircle, XCircle } from 'lucide-react';

const STATUS_COLORS = {
  active: { bg: 'var(--credit-bg)', text: 'var(--credit-text)' },
  completed: { bg: '#d1fae5', text: '#065f46' },
  abandoned: { bg: 'var(--debit-bg)', text: 'var(--debit-text)' },
};

const Goals = () => {
  const [goals, setGoals] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingGoal, setEditingGoal] = useState(null);
  const [contributeModal, setContributeModal] = useState(null);
  const [form, setForm] = useState({ name: '', target_amount: '', target_date: '', description: '' });
  const [contributeAmount, setContributeAmount] = useState('');

  const loadData = async () => {
    try {
      const [goalsData, summaryData] = await Promise.all([
        getSavingsGoals(),
        getGoalsSummary(),
      ]);
      setGoals(goalsData);
      setSummary(summaryData);
      setError(null);
    } catch (err) {
      setError('Failed to load savings goals');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        name: form.name,
        target_amount: form.target_amount,
      };
      if (form.target_date) payload.target_date = form.target_date;
      if (form.description) payload.description = form.description;
      await createSavingsGoal(payload);
      setForm({ name: '', target_amount: '', target_date: '', description: '' });
      setShowForm(false);
      loadData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create goal');
    }
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    try {
      await updateSavingsGoal(editingGoal.id, {
        name: form.name,
        target_amount: form.target_amount,
        target_date: form.target_date || null,
        description: form.description || null,
      });
      setEditingGoal(null);
      setForm({ name: '', target_amount: '', target_date: '', description: '' });
      loadData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update goal');
    }
  };

  const handleDelete = async (goalId) => {
    if (!window.confirm('Are you sure you want to delete this goal?')) return;
    try {
      await deleteSavingsGoal(goalId);
      loadData();
    } catch (err) {
      setError('Failed to delete goal');
    }
  };

  const handleContribute = async (e) => {
    e.preventDefault();
    try {
      await contributeToGoal(contributeModal.id, contributeAmount);
      setContributeModal(null);
      setContributeAmount('');
      loadData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add contribution');
    }
  };

  const handleStatusChange = async (goalId, newStatus) => {
    try {
      await updateSavingsGoal(goalId, { status: newStatus });
      loadData();
    } catch (err) {
      setError('Failed to update status');
    }
  };

  const openEdit = (goal) => {
    setEditingGoal(goal);
    setForm({
      name: goal.name,
      target_amount: goal.target_amount,
      target_date: goal.target_date || '',
      description: goal.description || '',
    });
    setShowForm(false);
  };

  const resetForm = () => {
    setForm({ name: '', target_amount: '', target_date: '', description: '' });
    setShowForm(false);
    setEditingGoal(null);
  };

  if (loading) {
    return (
      <div className="layout-container">
        <div className="page-header">
          <h1 className="page-title"><Target size={28} /> Savings Goals</h1>
        </div>
        <div style={{ textAlign: 'center', padding: '64px', color: 'var(--text-muted)' }}>
          <div className="skeleton" style={{ height: '120px', width: '100%', marginBottom: '20px' }}></div>
          <div className="skeleton" style={{ height: '200px', width: '100%' }}></div>
        </div>
      </div>
    );
  }

  return (
    <div className="layout-container">
      <div className="page-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <div>
            <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Target size={28} /> Savings Goals
            </h1>
            <p className="page-description">Track progress toward your financial goals.</p>
          </div>
          <button className="btn btn-primary" onClick={() => { setShowForm(!showForm); setEditingGoal(null); }}>
            <Plus size={16} /> New Goal
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '12px 16px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)', marginBottom: '20px', border: '1px solid var(--debit-text)' }}>
          {error}
          <button onClick={() => setError(null)} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}>&times;</button>
        </div>
      )}

      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '32px' }}>
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Total Goals</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-main)' }}>{summary.total_goals}</div>
          </div>
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Active</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--credit-text)' }}>{summary.active_goals}</div>
          </div>
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Completed</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#065f46' }}>{summary.completed_goals}</div>
          </div>
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Overall Progress</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--primary-blue)' }}>{summary.overall_progress.toFixed(1)}%</div>
          </div>
        </div>
      )}

      {(showForm || editingGoal) && (
        <div className="card" style={{ padding: '24px', marginBottom: '24px' }}>
          <h3 style={{ marginBottom: '16px', color: 'var(--text-main)' }}>{editingGoal ? 'Edit Goal' : 'Create New Goal'}</h3>
          <form onSubmit={editingGoal ? handleUpdate : handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>Goal Name *</label>
                <input type="text" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required
                  style={{ width: '100%', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-main)' }} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>Target Amount (₹) *</label>
                <input type="number" step="0.01" min="0.01" value={form.target_amount} onChange={e => setForm({...form, target_amount: e.target.value})} required
                  style={{ width: '100%', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-main)' }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>Target Date (optional)</label>
                <input type="date" value={form.target_date} onChange={e => setForm({...form, target_date: e.target.value})}
                  style={{ width: '100%', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-main)' }} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>Description (optional)</label>
                <input type="text" value={form.description} onChange={e => setForm({...form, description: e.target.value})}
                  style={{ width: '100%', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-main)' }} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button type="button" onClick={resetForm} className="btn" style={{ padding: '8px 16px' }}>Cancel</button>
              <button type="submit" className="btn btn-primary" style={{ padding: '8px 16px' }}>{editingGoal ? 'Update Goal' : 'Create Goal'}</button>
            </div>
          </form>
        </div>
      )}

      {contributeModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card" style={{ padding: '24px', width: '400px', maxWidth: '90vw' }}>
            <h3 style={{ marginBottom: '16px', color: 'var(--text-main)' }}>Add Contribution to "{contributeModal.name}"</h3>
            <form onSubmit={handleContribute} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>Amount (₹) *</label>
                <input type="number" step="0.01" min="0.01" value={contributeAmount} onChange={e => setContributeAmount(e.target.value)} required autoFocus
                  style={{ width: '100%', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-main)' }} />
              </div>
              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => { setContributeModal(null); setContributeAmount(''); }} className="btn" style={{ padding: '8px 16px' }}>Cancel</button>
                <button type="submit" className="btn btn-primary" style={{ padding: '8px 16px' }}>Add Contribution</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {goals.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '64px 24px', backgroundColor: 'var(--bg-secondary)' }}>
          <Target size={48} color="var(--text-muted)" style={{ margin: '0 auto 16px', opacity: 0.5 }} />
          <h2 style={{ fontSize: '1.25rem', marginBottom: '8px', color: 'var(--text-main)' }}>No savings goals yet.</h2>
          <p style={{ color: 'var(--text-muted)' }}>Create your first goal to start tracking your savings progress.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '20px' }}>
          {goals.map((goal) => {
            const colors = STATUS_COLORS[goal.status] || STATUS_COLORS.active;
            return (
              <div key={goal.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h3 style={{ fontSize: '1.1rem', margin: 0, fontWeight: 600, color: 'var(--text-main)' }}>{goal.name}</h3>
                    {goal.description && (
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>{goal.description}</p>
                    )}
                  </div>
                  <span style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 600, backgroundColor: colors.bg, color: colors.text }}>
                    {goal.status}
                  </span>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '0.85rem' }}>
                    <span style={{ color: 'var(--text-muted)' }}>₹{Number(goal.current_amount).toLocaleString('en-IN')} of ₹{Number(goal.target_amount).toLocaleString('en-IN')}</span>
                    <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{goal.progress_percent.toFixed(1)}%</span>
                  </div>
                  <div style={{ height: '8px', backgroundColor: 'var(--border-light)', borderRadius: '4px', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.min(goal.progress_percent, 100)}%`, backgroundColor: goal.status === 'completed' ? '#065f46' : 'var(--primary-blue)', borderRadius: '4px', transition: 'width 0.3s ease' }} />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {goal.target_date && <div>Target: {new Date(goal.target_date).toLocaleDateString()}</div>}
                  {goal.projected_completion && <div>Projected: {new Date(goal.projected_completion).toLocaleDateString()}</div>}
                </div>

                <div style={{ display: 'flex', gap: '8px', borderTop: '1px solid var(--border-light)', paddingTop: '12px' }}>
                  {goal.status === 'active' && (
                    <>
                      <button className="btn btn-primary" style={{ flex: 1, padding: '8px', fontSize: '0.8rem' }} onClick={() => setContributeModal(goal)}>
                        <TrendingUp size={14} style={{ marginRight: '4px' }} /> Contribute
                      </button>
                      <button className="btn" style={{ padding: '8px', fontSize: '0.8rem' }} onClick={() => handleStatusChange(goal.id, 'completed')} title="Mark completed">
                        <CheckCircle size={14} />
                      </button>
                    </>
                  )}
                  {goal.status === 'completed' && (
                    <button className="btn" style={{ flex: 1, padding: '8px', fontSize: '0.8rem' }} onClick={() => handleStatusChange(goal.id, 'active')}>
                      Reopen
                    </button>
                  )}
                  {goal.status === 'abandoned' && (
                    <button className="btn" style={{ flex: 1, padding: '8px', fontSize: '0.8rem' }} onClick={() => handleStatusChange(goal.id, 'active')}>
                      Reactivate
                    </button>
                  )}
                  <button className="btn" style={{ padding: '8px' }} onClick={() => openEdit(goal)} title="Edit">
                    <Pencil size={14} />
                  </button>
                  <button className="btn" style={{ padding: '8px', color: 'var(--debit-text)' }} onClick={() => handleDelete(goal.id)} title="Delete">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Goals;
