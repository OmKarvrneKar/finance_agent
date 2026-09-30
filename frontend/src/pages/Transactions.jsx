import React, { useState, useEffect, useCallback } from 'react';
import { searchTransactions, deleteTransaction, getTransactionsExport } from '../utils/api';
import TransactionRow from '../components/TransactionRow';
import EditTransactionModal from '../components/EditTransactionModal';
import SplitTransactionModal from '../components/SplitTransactionModal';
import { Filter, ChevronLeft, ChevronRight, RefreshCw, Search, Trash2, Download } from 'lucide-react';

const CATEGORIES = [
  '', 'Food & Dining', 'Groceries', 'Shopping', 'Transport',
  'Bills & Utilities', 'Subscriptions', 'Entertainment',
  'Healthcare', 'Transfers', 'Salary/Income', 'ATM/Cash', 'Other'
];

const Transactions = () => {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState('');
  const [type, setType] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [amountMin, setAmountMin] = useState('');
  const [amountMax, setAmountMax] = useState('');
  const [editingTx, setEditingTx] = useState(null);
  const [splittingTx, setSplittingTx] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportSuccess, setExportSuccess] = useState(false);
  const limit = 10;

  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await searchTransactions({
        page, limit, q: searchQuery, category,
        transaction_type: type, date_from: dateFrom, date_to: dateTo,
        amount_min: amountMin, amount_max: amountMax,
      });
      setTransactions(data.transactions || []);
      setTotal(data.total || 0);
    } catch (err) {
      if (err.response?.status === 401) return;
      setError('Failed to fetch transactions');
    } finally {
      setLoading(false);
    }
  }, [page, searchQuery, category, type, dateFrom, dateTo, amountMin, amountMax]);

  useEffect(() => { fetchTransactions(); }, [fetchTransactions]);

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this transaction?')) return;
    setDeleting(id);
    try {
      await deleteTransaction(id);
      fetchTransactions();
    } catch {
      setError('Failed to delete transaction');
    } finally {
      setDeleting(null);
    }
  };

  const handleExport = async () => {
    if (exporting) return;
    setExporting(true);
    setExportSuccess(false);
    setError('');
    try {
      const response = await getTransactionsExport({
        start_date: dateFrom,
        end_date: dateTo,
        category,
        transaction_type: type,
        search: searchQuery,
      });
      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const disposition = response.headers?.['content-disposition'] || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      link.download = match ? match[1] : 'transactions_export.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      setExportSuccess(true);
      setTimeout(() => setExportSuccess(false), 3000);
    } catch (err) {
      if (err.response?.status === 401) return;
      setError('Failed to export transactions');
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="layout-container">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 className="page-title">Transactions</h1>
          <p className="page-description">View, search, and manage all your categorized transactions.</p>
        </div>
        <button onClick={fetchTransactions} className="btn-secondary" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <RefreshCw size={16} /> Refresh
        </button>
        <button onClick={handleExport} disabled={exporting} className="btn-secondary" style={{ display: 'flex', gap: '8px', alignItems: 'center', opacity: exporting ? 0.6 : 1 }}>
          <Download size={16} /> {exporting ? 'Exporting...' : 'Export CSV'}
        </button>
      </div>

      {error && (
        <div style={{ padding: '12px 16px', borderRadius: '8px', backgroundColor: 'var(--debit-bg)', color: 'var(--debit-text)', marginBottom: '16px', fontSize: '0.875rem' }}>
          {error}
        </div>
      )}

      {exportSuccess && (
        <div style={{ padding: '12px 16px', borderRadius: '8px', backgroundColor: 'var(--credit-bg)', color: 'var(--credit-text)', marginBottom: '16px', fontSize: '0.875rem' }}>
          CSV exported successfully.
        </div>
      )}

      <div className="card" style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Search bar */}
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, padding: '8px 12px', border: '1px solid var(--border-color)', borderRadius: '8px', backgroundColor: 'var(--bg-color)' }}>
              <Search size={16} style={{ color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Search by merchant or description..."
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setPage(1); }}
                style={{ border: 'none', outline: 'none', flex: 1, fontSize: '0.875rem', background: 'transparent' }}
              />
            </div>
          </div>

          {/* Filters row */}
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)' }}>
              <Filter size={16} />
              <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>Filters:</span>
            </div>

            <select
              value={category}
              onChange={(e) => { setCategory(e.target.value); setPage(1); }}
              style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', outline: 'none', fontSize: '0.875rem' }}
            >
              <option value="">All Categories</option>
              {CATEGORIES.filter(c => c).map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>

            <div style={{ display: 'flex', backgroundColor: 'var(--bg-color)', borderRadius: '6px', padding: '3px', border: '1px solid var(--border-color)' }}>
              {['', 'debit', 'credit'].map(t => (
                <button key={t} onClick={() => { setType(t); setPage(1); }}
                  style={{ padding: '4px 12px', fontSize: '0.8rem', borderRadius: '4px', border: 'none', cursor: 'pointer',
                    backgroundColor: type === t ? 'white' : 'transparent', boxShadow: type === t ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                    color: type === t ? 'var(--text-main)' : 'var(--text-muted)', fontWeight: type === t ? 600 : 400 }}>
                  {t === '' ? 'All' : t === 'debit' ? 'Debits' : 'Credits'}
                </button>
              ))}
            </div>

            <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
              placeholder="From" style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem' }} />
            <span style={{ color: 'var(--text-muted)' }}>to</span>
            <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
              placeholder="To" style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem' }} />

            <input type="number" value={amountMin} onChange={(e) => { setAmountMin(e.target.value); setPage(1); }}
              placeholder="Min ₹" min="0" step="0.01"
              style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem', width: '100px' }} />
            <span style={{ color: 'var(--text-muted)' }}>to</span>
            <input type="number" value={amountMax} onChange={(e) => { setAmountMax(e.target.value); setPage(1); }}
              placeholder="Max ₹" min="0" step="0.01"
              style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.875rem', width: '100px' }} />

            {(searchQuery || category || type || dateFrom || dateTo || amountMin || amountMax) && (
              <button onClick={() => { setSearchQuery(''); setCategory(''); setType(''); setDateFrom(''); setDateTo(''); setAmountMin(''); setAmountMax(''); setPage(1); }}
                style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', fontSize: '0.8rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
                Clear all
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)', fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                <th style={{ padding: '14px 24px', fontWeight: 600 }}>Date</th>
                <th style={{ padding: '14px 24px', fontWeight: 600 }}>Description</th>
                <th style={{ padding: '14px 24px', fontWeight: 600, textAlign: 'right' }}>Amount</th>
                <th style={{ padding: '14px 24px', fontWeight: 600 }}>Type</th>
                <th style={{ padding: '14px 24px', fontWeight: 600 }}>Category</th>
                <th style={{ padding: '14px 24px', fontWeight: 600, textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="6" style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading transactions...</td></tr>
              ) : transactions.length === 0 ? (
                <tr><td colSpan="6" style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {searchQuery || category || type || dateFrom || dateTo || amountMin || amountMax
                    ? 'No transactions found matching your filters.' : 'No transactions yet. Upload a bank statement to get started.'}
                </td></tr>
              ) : (
                transactions.map((tx) => (
                  <TransactionRow key={tx.id} transaction={tx}
                    onEdit={() => setEditingTx(tx)}
                    onDelete={() => handleDelete(tx.id)}
                    onSplit={() => setSplittingTx(tx)}
                    isDeleting={deleting === tx.id} />
                ))
              )}
            </tbody>
          </table>
        </div>

        {!loading && total > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 24px', borderTop: '1px solid var(--border-color)', backgroundColor: '#fafafa' }}>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Showing <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{Math.min((page - 1) * limit + 1, total)}</span> to <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{Math.min(page * limit, total)}</span> of <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{total}</span>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '6px 12px', border: '1px solid var(--border-color)', borderRadius: '6px',
                  backgroundColor: page === 1 ? '#f1f5f9' : 'white', color: page === 1 ? '#94a3b8' : 'var(--text-main)', opacity: page === 1 ? 0.5 : 1, cursor: 'pointer' }}>
                <ChevronLeft size={16} /> Prev
              </button>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '6px 12px', border: '1px solid var(--border-color)', borderRadius: '6px',
                  backgroundColor: page >= totalPages ? '#f1f5f9' : 'white', color: page >= totalPages ? '#94a3b8' : 'var(--text-main)', opacity: page >= totalPages ? 0.5 : 1, cursor: 'pointer' }}>
                Next <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {editingTx && <EditTransactionModal transaction={editingTx} onClose={() => setEditingTx(null)} onSaved={() => { setEditingTx(null); fetchTransactions(); }} />}
      {splittingTx && <SplitTransactionModal transaction={splittingTx} onClose={() => setSplittingTx(null)} onSaved={() => { setSplittingTx(null); fetchTransactions(); }} />}
    </div>
  );
};

export default Transactions;
