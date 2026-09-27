import { useState } from 'react';
import { updateTransaction } from '../utils/api';

const CATEGORIES = [
  'Food & Dining', 'Groceries', 'Shopping', 'Transport',
  'Bills & Utilities', 'Subscriptions', 'Entertainment',
  'Healthcare', 'Transfers', 'Salary/Income', 'ATM/Cash', 'Other'
];

const EditTransactionModal = ({ transaction, onClose, onSaved }) => {
  const [form, setForm] = useState({
    description: transaction.description || '',
    category: transaction.category || '',
    amount: transaction.amount || '',
    date: transaction.date ? transaction.date.split('T')[0] : '',
    is_recurring: transaction.is_recurring || false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      await updateTransaction(transaction.id, {
        description: form.description,
        category: form.category,
        amount: parseFloat(form.amount),
        date: form.date,
        is_recurring: form.is_recurring,
      });
      onSaved();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update transaction');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '32px', width: '100%', maxWidth: '440px', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
        <h2 style={{ margin: '0 0 24px', fontSize: '1.125rem', fontWeight: 600 }}>Edit Transaction</h2>

        {error && (
          <div style={{ padding: '10px 14px', borderRadius: '8px', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)', fontSize: '0.875rem', marginBottom: '16px' }}>{error}</div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 500, marginBottom: '4px', color: 'var(--text-muted)' }}>Description</label>
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
              style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem', boxSizing: 'border-box' }} />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 500, marginBottom: '4px', color: 'var(--text-muted)' }}>Category</label>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
              style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem' }}>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 500, marginBottom: '4px', color: 'var(--text-muted)' }}>Amount (₹)</label>
              <input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} min="0" step="0.01"
                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem', boxSizing: 'border-box' }} />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 500, marginBottom: '4px', color: 'var(--text-muted)' }}>Date</label>
              <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem', boxSizing: 'border-box' }} />
            </div>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <input type="checkbox" checked={form.is_recurring} onChange={(e) => setForm({ ...form, is_recurring: e.target.checked })} />
            Recurring transaction
          </label>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '24px' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'white', fontSize: '0.875rem', cursor: 'pointer' }}>Cancel</button>
          <button onClick={handleSave} disabled={saving}
            style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: 'var(--primary-blue)', color: 'white', fontSize: '0.875rem', fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1 }}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default EditTransactionModal;
