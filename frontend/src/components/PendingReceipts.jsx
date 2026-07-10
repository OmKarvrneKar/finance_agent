import React, { useState, useEffect } from 'react';
import { AlertTriangle, Check, X, FileText } from 'lucide-react';
import { getPendingReceipts, confirmReceipt, discardReceipt } from '../utils/api';

const PendingReceipts = ({ refreshTrigger, onResolved }) => {
  const [pending, setPending] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState({});
  const [error, setError] = useState(null);
  const [duplicateWarning, setDuplicateWarning] = useState(null);

  const fetchPending = async () => {
    try {
      const data = await getPendingReceipts();
      setPending(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchPending();
  }, [refreshTrigger]);

  const startEdit = (receipt) => {
    setEditingId(receipt.id);
    setFormData({
      merchant: receipt.merchant || '',
      date: receipt.date || '',
      amount: receipt.amount || '',
      category: receipt.category || ''
    });
    setError(null);
    setDuplicateWarning(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDuplicateWarning(null);
  };

  const handleConfirm = async (id, force = false) => {
    if (!formData.merchant || !formData.date || !formData.amount || !formData.category) {
        setError("All fields are required to confirm.");
        return;
    }

    setError(null);
    try {
      await confirmReceipt(id, {
        merchant: formData.merchant,
        date: formData.date,
        amount: parseFloat(formData.amount),
        category: formData.category
      }, force);
      
      setEditingId(null);
      setDuplicateWarning(null);
      fetchPending();
      if (onResolved) onResolved();
    } catch (err) {
      if (err.response?.status === 409) {
        setDuplicateWarning(err.response.data.detail);
      } else {
        setError(err.response?.data?.detail || "Failed to confirm.");
      }
    }
  };

  const handleDiscard = async (id) => {
    try {
      await discardReceipt(id);
      fetchPending();
      if (onResolved) onResolved();
    } catch (err) {
      console.error(err);
    }
  };

  if (pending.length === 0) return null;

  return (
    <div style={{ marginBottom: '32px' }}>
      <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <FileText size={20} color="#F59E0B" /> Pending Receipts ({pending.length})
      </h3>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {pending.map(p => {
          const isMissing = !p.merchant || !p.amount || !p.date;
          return (
          <div key={p.id} className="card" style={{ borderLeft: isMissing ? '4px solid #F59E0B' : '4px solid #10B981' }}>
            {editingId === p.id ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)' }}>Merchant</label>
                  <input type="text" value={formData.merchant} onChange={e => setFormData({...formData, merchant: e.target.value})} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: !formData.merchant ? '1px solid #F59E0B' : '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-main)' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)' }}>Date</label>
                  <input type="date" value={formData.date} onChange={e => setFormData({...formData, date: e.target.value})} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: !formData.date ? '1px solid #F59E0B' : '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-main)' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)' }}>Amount</label>
                  <input type="number" step="0.01" value={formData.amount} onChange={e => setFormData({...formData, amount: e.target.value})} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: !formData.amount ? '1px solid #F59E0B' : '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-main)' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)' }}>Category</label>
                  <input type="text" value={formData.category} onChange={e => setFormData({...formData, category: e.target.value})} style={{ width: '100%', padding: '8px', borderRadius: '4px', border: !formData.category ? '1px solid #F59E0B' : '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-main)' }} />
                </div>
                
                <div style={{ gridColumn: '1 / -1' }}>
                  {duplicateWarning && (
                    <div style={{ color: '#F59E0B', fontSize: '0.875rem', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <AlertTriangle size={16} /> {duplicateWarning}
                    </div>
                  )}
                  {error && <div style={{ color: '#EF4444', fontSize: '0.875rem', marginBottom: '8px' }}>{error}</div>}
                  
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn-primary" onClick={() => handleConfirm(p.id, !!duplicateWarning)} style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Check size={16} /> {duplicateWarning ? 'Force Save' : 'Confirm'}
                    </button>
                    <button className="btn-secondary" onClick={cancelEdit} style={{ padding: '8px 16px' }}>Cancel</button>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 500, color: 'var(--text-main)', fontSize: '1.1rem' }}>
                    {p.merchant || <span style={{ color: '#F59E0B', fontStyle: 'italic' }}>Missing Merchant</span>}
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                    {p.date || 'Missing Date'} • {p.category || 'Missing Category'}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    {p.amount ? `₹${p.amount}` : <span style={{ color: '#F59E0B', fontStyle: 'italic' }}>Missing</span>}
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button onClick={() => startEdit(p)} className="btn-primary" style={{ padding: '6px 12px', fontSize: '0.875rem' }}>Review</button>
                    <button onClick={() => handleDiscard(p.id)} className="btn-secondary" style={{ padding: '6px', color: '#EF4444' }}><X size={16} /></button>
                  </div>
                </div>
              </div>
            )}
            
            {isMissing && editingId !== p.id && (
              <div style={{ marginTop: '12px', fontSize: '0.875rem', color: '#F59E0B', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <AlertTriangle size={16} /> Needs review to complete missing fields.
              </div>
            )}
          </div>
        )})}
      </div>
    </div>
  );
};

export default PendingReceipts;
