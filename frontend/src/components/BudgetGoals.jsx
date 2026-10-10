import { useState, useEffect } from 'react';
import { Target, AlertTriangle, Plus, Trash2 } from 'lucide-react';
import { getBudgets, createUpdateBudget, deleteBudget, getAllTransactions, getAccounts } from '../utils/api';

const BudgetGoals = () => {
  const [budgets, setBudgets] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [accounts, setAccounts] = useState([]);
  const [reloadKey, setReloadKey] = useState(0);
  
  const [newCat, setNewCat] = useState('');
  const [newCap, setNewCap] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAccounts({ is_active: true })
      .then((data) => { if (!cancelled) setAccounts(Array.isArray(data) ? data : []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [budgetsData, txsData] = await Promise.all([
          getBudgets('', selectedAccount || undefined),
          getAllTransactions()
        ]);
        setBudgets(budgetsData);
        
        const uniqueCats = [...new Set((txsData.transactions || []).map(t => t.category))].filter(Boolean);
        setCategories(uniqueCats);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [selectedAccount, reloadKey]);

  const handleSaveBudget = async (e) => {
    e.preventDefault();
    if (!newCat || !newCap) return;
    try {
      await createUpdateBudget(newCat, parseFloat(newCap));
      setNewCat('');
      setNewCap('');
      setIsEditing(false);
      setReloadKey((k) => k + 1);
    } catch (err) {
      console.error('Failed to save budget', err);
    }
  };

  const handleDelete = async (category) => {
    try {
      await deleteBudget(category);
      setReloadKey((k) => k + 1);
    } catch (err) {
      console.error('Failed to delete', err);
    }
  };

  const formatCurrency = (val) => `₹${Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

  const approachingOrOver = budgets.filter(b => b.status === 'approaching' || b.status === 'over');

  return (
    <div style={{ marginBottom: '32px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Target size={24} color="var(--primary-blue)" /> Budget Goals
        </h2>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <select
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
            aria-label="Filter by account"
            style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', outline: 'none', fontSize: '0.875rem' }}
          >
            <option value="">All Accounts</option>
            {accounts.map(a => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          <button onClick={() => setIsEditing(!isEditing)} className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.875rem', display: 'flex', gap: '6px', alignItems: 'center' }}>
            {isEditing ? 'Cancel' : <><Plus size={14} /> Add Budget</>}
          </button>
        </div>
      </div>

      {isEditing && (
        <form onSubmit={handleSaveBudget} className="card" style={{ marginBottom: '24px', display: 'flex', gap: '16px', alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Category</label>
            <select value={newCat} onChange={e => setNewCat(e.target.value)} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-main)' }} required>
              <option value="" disabled>Select category...</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Monthly Cap (₹)</label>
            <input type="number" min="1" step="1" value={newCap} onChange={e => setNewCap(e.target.value)} placeholder="e.g. 5000" style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-main)' }} required />
          </div>
          <button type="submit" className="btn-primary" style={{ padding: '8px 16px' }}>Save</button>
        </form>
      )}

      {!loading && (
        <>
          {approachingOrOver.length > 0 && !isEditing && (
            <div style={{ marginBottom: '24px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {approachingOrOver.map((b, i) => (
                <div key={i} style={{ padding: '12px 16px', borderRadius: '8px', display: 'flex', gap: '12px', alignItems: 'center', backgroundColor: b.status === 'over' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(245, 158, 11, 0.1)', border: `1px solid ${b.status === 'over' ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}` }}>
                  <AlertTriangle size={20} color={b.status === 'over' ? '#EF4444' : '#F59E0B'} />
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>{b.message}</div>
                </div>
              ))}
            </div>
          )}

          {budgets.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
              No budget goals set. Add one to start tracking!
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
              {budgets.map(b => {
                const isOver = b.status === 'over';
                const isWarning = b.status === 'approaching';
                const color = isOver ? '#EF4444' : isWarning ? '#F59E0B' : '#10B981';
                const pct = Math.min(b.percent_used, 100);

                return (
                  <div key={b.category} className="card" style={{ position: 'relative' }}>
                    <button onClick={() => handleDelete(b.category)} style={{ position: 'absolute', top: '16px', right: '16px', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }} title="Remove Goal">
                      <Trash2 size={16} />
                    </button>
                    <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px' }}>{b.category}</h3>
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.875rem', marginBottom: '8px' }}>
                      <span style={{ color: 'var(--text-muted)' }}>{formatCurrency(b.current_spend)} spent</span>
                      <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{formatCurrency(b.monthly_cap)}</span>
                    </div>
                    
                    <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--border-color)', borderRadius: '4px', overflow: 'hidden', marginBottom: '8px' }}>
                      <div style={{ width: `${pct}%`, height: '100%', backgroundColor: color, transition: 'width 0.3s ease' }}></div>
                    </div>
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                      <span style={{ color }}>{b.percent_used}% Used</span>
                      <span style={{ color: 'var(--text-muted)' }}>{b.days_left_in_month} days left</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default BudgetGoals;
