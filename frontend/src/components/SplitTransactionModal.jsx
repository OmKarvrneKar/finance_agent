import { useState, useEffect } from 'react';
import { getSplitSummary, createSplits, deleteSplit } from '../utils/api';
import { Plus, Trash2 } from 'lucide-react';

const CATEGORIES = [
  'Food & Dining', 'Groceries', 'Shopping', 'Transport',
  'Bills & Utilities', 'Subscriptions', 'Entertainment',
  'Healthcare', 'Transfers', 'Salary/Income', 'ATM/Cash', 'Other'
];

const parseDecimal = (val) => {
  if (val === '' || val === null || val === undefined) return '0';
  const s = String(val).trim();
  if (s === '') return '0';
  return s;
};

const formatAmount = (val) => {
  const num = parseFloat(parseDecimal(val));
  if (isNaN(num)) return '0.00';
  return num.toFixed(2);
};

const SplitTransactionModal = ({ transaction, onClose, onSaved }) => {
  const [splits, setSplits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const txAmount = parseFloat(transaction.amount);
  const splitTotal = splits.reduce((sum, s) => sum + (parseFloat(s.amount) || 0), 0);
  const remaining = txAmount - splitTotal;
  const isBalanced = Math.abs(remaining) < 0.005;

  useEffect(() => {
    const loadSplits = async () => {
      try {
        const summary = await getSplitSummary(transaction.id);
        if (summary.splits && summary.splits.length > 0) {
          setSplits(summary.splits.map(s => ({
            id: s.id,
            category: s.category,
            amount: String(s.amount),
            description: s.description || '',
          })));
        } else {
          setSplits([{ category: '', amount: '', description: '' }]);
        }
      } catch {
        setSplits([{ category: '', amount: '', description: '' }]);
      } finally {
        setLoading(false);
      }
    };
    loadSplits();
  }, [transaction.id]);

  const addSplit = () => {
    setSplits([...splits, { category: '', amount: '', description: '' }]);
  };

  const removeSplit = (index) => {
    if (splits.length <= 1) return;
    setSplits(splits.filter((_, i) => i !== index));
  };

  const updateSplit = (index, field, value) => {
    const updated = [...splits];
    updated[index] = { ...updated[index], [field]: value };
    setSplits(updated);
    setError('');
    setSuccess('');
  };

  const validate = () => {
    for (let i = 0; i < splits.length; i++) {
      const s = splits[i];
      if (!s.category || !s.category.trim()) {
        return `Split ${i + 1}: category is required.`;
      }
      const amt = parseFloat(s.amount);
      if (!s.amount || isNaN(amt) || amt <= 0) {
        return `Split ${i + 1}: amount must be a positive number.`;
      }
    }
    const cats = splits.map(s => s.category.trim().toLowerCase());
    const seen = new Set();
    for (let i = 0; i < cats.length; i++) {
      if (seen.has(cats[i])) {
        return `Split ${i + 1}: duplicate category "${splits[i].category}".`;
      }
      seen.add(cats[i]);
    }
    if (!isBalanced) {
      if (remaining > 0) {
        return `Under-allocated by ₹${Math.abs(remaining).toFixed(2)}. Add ₹${Math.abs(remaining).toFixed(2)} more.`;
      }
      return `Over-allocated by ₹${Math.abs(remaining).toFixed(2)}. Reduce by ₹${Math.abs(remaining).toFixed(2)}.`;
    }
    return null;
  };

  const handleSave = async () => {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await createSplits(transaction.id, splits.map(s => ({
        category: s.category.trim(),
        amount: s.amount,
        description: s.description || null,
      })));
      setSuccess('Splits saved successfully.');
      onSaved();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save splits.');
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveAll = async () => {
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const summary = await getSplitSummary(transaction.id);
      if (summary.splits) {
        for (const s of summary.splits) {
          await deleteSplit(s.id);
        }
      }
      setSplits([{ category: '', amount: '', description: '' }]);
      setSuccess('All splits removed.');
      onSaved();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to remove splits.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}
        onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '32px', width: '100%', maxWidth: '560px', maxHeight: '80vh', overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
          <p style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Loading splits...</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '32px', width: '100%', maxWidth: '560px', maxHeight: '80vh', overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
        <h2 style={{ margin: '0 0 8px', fontSize: '1.125rem', fontWeight: 600 }}>Split Transaction</h2>
        <p style={{ margin: '0 0 20px', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          {transaction.description} &mdash; ₹{formatAmount(transaction.amount)}
        </p>

        {error && (
          <div style={{ padding: '10px 14px', borderRadius: '8px', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)', fontSize: '0.875rem', marginBottom: '16px' }}>{error}</div>
        )}

        {success && (
          <div style={{ padding: '10px 14px', borderRadius: '8px', backgroundColor: 'var(--credit-bg)', color: 'var(--credit-text)', fontSize: '0.875rem', marginBottom: '16px' }}>{success}</div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '16px' }}>
          {/* Header row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px 1fr 36px', gap: '8px', padding: '0 0 4px', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            <span>Category</span>
            <span style={{ textAlign: 'right' }}>Amount</span>
            <span>Description</span>
            <span></span>
          </div>

          {/* Split rows */}
          {splits.map((split, index) => (
            <div key={index} data-testid={`split-row-${index}`} style={{ display: 'grid', gridTemplateColumns: '1fr 100px 1fr 36px', gap: '8px', alignItems: 'center' }}>
              <select
                value={split.category}
                onChange={(e) => updateSplit(index, 'category', e.target.value)}
                style={{ padding: '8px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem' }}
              >
                <option value="">Select...</option>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <input
                type="text"
                inputMode="decimal"
                value={split.amount}
                onChange={(e) => updateSplit(index, 'amount', e.target.value)}
                placeholder="0.00"
                style={{ padding: '8px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem', textAlign: 'right' }}
              />
              <input
                type="text"
                value={split.description}
                onChange={(e) => updateSplit(index, 'description', e.target.value)}
                placeholder="Optional"
                style={{ padding: '8px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem' }}
              />
              <button
                onClick={() => removeSplit(index)}
                disabled={splits.length <= 1}
                title="Remove split"
                style={{ background: 'none', border: 'none', cursor: splits.length <= 1 ? 'not-allowed' : 'pointer', padding: '4px', color: splits.length <= 1 ? '#d1d5db' : 'var(--text-muted)', borderRadius: '4px' }}
                onMouseOver={(e) => splits.length > 1 && (e.currentTarget.style.color = 'var(--debit-text)')}
                onMouseOut={(e) => e.currentTarget.style.color = splits.length <= 1 ? '#d1d5db' : 'var(--text-muted)'}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>

        {/* Add split button */}
        <button onClick={addSplit} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px', borderRadius: '6px', border: '1px dashed var(--border-color)', backgroundColor: 'transparent', fontSize: '0.8rem', color: 'var(--text-muted)', cursor: 'pointer', marginBottom: '16px' }}
          onMouseOver={(e) => { e.currentTarget.style.borderColor = 'var(--primary-blue)'; e.currentTarget.style.color = 'var(--primary-blue)'; }}
          onMouseOut={(e) => { e.currentTarget.style.borderColor = 'var(--border-color)'; e.currentTarget.style.color = 'var(--text-muted)'; }}>
          <Plus size={14} /> Add split
        </button>

        {/* Summary */}
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 0', borderTop: '1px solid var(--border-color)', fontSize: '0.875rem', fontWeight: 500 }}>
          <span>Transaction total:</span>
          <span>₹{formatAmount(txAmount)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: '0.875rem', fontWeight: 500 }}>
          <span>Split total:</span>
          <span style={{ color: isBalanced ? 'var(--credit-text)' : 'var(--debit-text)' }}>₹{formatAmount(splitTotal)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0 16px', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          <span>Remaining:</span>
          <span style={{ color: isBalanced ? 'var(--credit-text)' : remaining < 0 ? 'var(--debit-text)' : 'var(--text-main)' }}>
            ₹{formatAmount(remaining)}
          </span>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px' }}>
          <button onClick={handleRemoveAll} disabled={saving}
            style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'white', fontSize: '0.875rem', cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.6 : 1, color: 'var(--debit-text)' }}>
            Remove All
          </button>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button onClick={onClose} style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'white', fontSize: '0.875rem', cursor: 'pointer' }}>Cancel</button>
            <button onClick={handleSave} disabled={saving}
              style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: 'var(--primary-blue)', color: 'white', fontSize: '0.875rem', fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1 }}>
              {saving ? 'Saving...' : 'Save Splits'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SplitTransactionModal;
