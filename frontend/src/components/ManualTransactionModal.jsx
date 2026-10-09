import { useState, useEffect } from 'react';
import { createTransaction, getAccounts } from '../utils/api';

const CATEGORIES = [
  'Food & Dining', 'Groceries', 'Shopping', 'Transport',
  'Bills & Utilities', 'Subscriptions', 'Entertainment',
  'Healthcare', 'Transfers', 'Salary/Income', 'ATM/Cash', 'Other'
];

const INITIAL_FORM = {
  transaction_type: '',
  amount: '',
  date: '',
  description: '',
  category: '',
  subcategory: '',
  account_id: '',
  is_recurring: false,
};

const formatApiError = (err, fallback) => {
  const detail = err.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ');
  return detail || fallback;
};

const labelStyle = { display: 'block', fontSize: '0.8rem', fontWeight: 500, marginBottom: '4px', color: 'var(--text-muted)' };
const inputStyle = { width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem', boxSizing: 'border-box' };

const ManualTransactionModal = ({ onClose, onCreated }) => {
  const [form, setForm] = useState(INITIAL_FORM);
  const [accounts, setAccounts] = useState([]);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState([]);
  const [serverError, setServerError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAccounts({ is_active: true })
      .then((data) => { if (!cancelled) setAccounts(Array.isArray(data) ? data : []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const validate = () => {
    const next = [];
    if (!form.transaction_type) next.push('Transaction type is required');
    const amount = form.amount.trim();
    if (!amount) next.push('Amount is required');
    else if (isNaN(parseFloat(amount))) next.push('Enter a valid amount');
    else if (parseFloat(amount) <= 0) next.push('Amount must be greater than 0');
    if (!form.date) next.push('Date is required');
    else if (isNaN(Date.parse(form.date))) next.push('Enter a valid date');
    if (!form.description.trim()) next.push('Description is required');
    if (!form.category) next.push('Category is required');
    return next;
  };

  const handleSubmit = async () => {
    setServerError('');
    setSuccess(false);
    const validationErrors = validate();
    if (validationErrors.length > 0) {
      setErrors(validationErrors);
      return;
    }
    setErrors([]);
    setSaving(true);
    try {
      const payload = {
        transaction_type: form.transaction_type === 'income' ? 'credit' : 'debit',
        amount: parseFloat(form.amount),
        date: form.date,
        description: form.description.trim(),
        category: form.category,
        is_recurring: form.is_recurring,
      };
      if (form.subcategory.trim()) payload.subcategory = form.subcategory.trim();
      if (form.account_id !== '') payload.account_id = Number(form.account_id);
      await createTransaction(payload);
      setForm(INITIAL_FORM);
      setSuccess(true);
      onCreated();
    } catch (err) {
      setServerError(formatApiError(err, 'Failed to create transaction'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ backgroundColor: 'white', borderRadius: '12px', padding: '32px', width: '100%', maxWidth: '440px', boxShadow: '0 20px 60px rgba(0,0,0,0.2)', maxHeight: '90vh', overflowY: 'auto' }}>
        <h2 style={{ margin: '0 0 24px', fontSize: '1.125rem', fontWeight: 600 }}>Add Transaction</h2>

        {serverError && (
          <div style={{ padding: '10px 14px', borderRadius: '8px', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)', fontSize: '0.875rem', marginBottom: '16px' }}>{serverError}</div>
        )}

        {errors.length > 0 && (
          <div style={{ padding: '10px 14px', borderRadius: '8px', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)', fontSize: '0.875rem', marginBottom: '16px' }}>
            {errors.map((e) => <div key={e}>{e}</div>)}
          </div>
        )}

        {success && (
          <div style={{ padding: '10px 14px', borderRadius: '8px', backgroundColor: 'var(--credit-bg)', color: 'var(--credit-text)', fontSize: '0.875rem', marginBottom: '16px' }}>
            Transaction added successfully.
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <span style={{ ...labelStyle, display: 'block' }}>Transaction Type</span>
            <div style={{ display: 'flex', backgroundColor: 'var(--bg-color)', borderRadius: '6px', padding: '3px', border: '1px solid var(--border-color)', gap: '2px' }}>
              {['expense', 'income'].map(t => (
                <button key={t} type="button" onClick={() => { setForm({ ...form, transaction_type: t }); setErrors([]); }}
                  aria-pressed={form.transaction_type === t}
                  style={{ flex: 1, padding: '6px 12px', fontSize: '0.8rem', borderRadius: '4px', border: 'none', cursor: 'pointer',
                    backgroundColor: form.transaction_type === t ? 'white' : 'transparent',
                    boxShadow: form.transaction_type === t ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                    color: form.transaction_type === t ? 'var(--text-main)' : 'var(--text-muted)',
                    fontWeight: form.transaction_type === t ? 600 : 400 }}>
                  {t === 'expense' ? 'Expense' : 'Income'}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ flex: 1 }}>
              <label htmlFor="manual-tx-amount" style={labelStyle}>Amount (₹)</label>
              <input id="manual-tx-amount" type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} min="0" step="0.01"
                style={inputStyle} />
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="manual-tx-date" style={labelStyle}>Date</label>
              <input id="manual-tx-date" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })}
                style={inputStyle} />
            </div>
          </div>

          <div>
            <label htmlFor="manual-tx-description" style={labelStyle}>Description</label>
            <input id="manual-tx-description" type="text" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
              style={inputStyle} />
          </div>

          <div>
            <label htmlFor="manual-tx-category" style={labelStyle}>Category</label>
            <select id="manual-tx-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
              style={{ ...inputStyle, width: '100%' }}>
              <option value="">Select category</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div>
            <label htmlFor="manual-tx-subcategory" style={labelStyle}>Subcategory</label>
            <input id="manual-tx-subcategory" type="text" value={form.subcategory} onChange={(e) => setForm({ ...form, subcategory: e.target.value })}
              placeholder="Optional" style={inputStyle} />
          </div>

          <div>
            <label htmlFor="manual-tx-account" style={labelStyle}>Account</label>
            <select id="manual-tx-account" value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })}
              style={{ ...inputStyle, width: '100%' }}>
              <option value="">All Accounts</option>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>

          <label htmlFor="manual-tx-recurring" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <input id="manual-tx-recurring" type="checkbox" checked={form.is_recurring} onChange={(e) => setForm({ ...form, is_recurring: e.target.checked })} />
            Recurring transaction
          </label>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '24px' }}>
          <button type="button" onClick={onClose} style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'white', fontSize: '0.875rem', cursor: 'pointer' }}>Cancel</button>
          <button type="button" onClick={handleSubmit} disabled={saving}
            style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: 'var(--primary-blue)', color: 'white', fontSize: '0.875rem', fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1 }}>
            {saving ? 'Adding...' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ManualTransactionModal;
