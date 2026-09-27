import React from 'react';
import CategoryBadge from './CategoryBadge';
import { Repeat, Pencil, Trash2 } from 'lucide-react';

const TransactionRow = ({ transaction, onEdit, onDelete, isDeleting }) => {
  const isDebit = transaction.transaction_type === 'debit';
  const amountClass = isDebit ? 'amount-debit' : 'amount-credit';
  const amountPrefix = isDebit ? '-' : '+';

  const formatDate = (dateString) => {
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return new Date(dateString).toLocaleDateString(undefined, options);
  };

  return (
    <tr style={{ borderBottom: '1px solid var(--border-light)' }}>
      <td style={{ whiteSpace: 'nowrap', color: 'var(--text-muted)', padding: '14px 24px' }}>
        {formatDate(transaction.date)}
      </td>
      <td style={{ padding: '14px 24px' }}>
        <div style={{ fontWeight: 500, color: 'var(--text-main)' }}>
          {transaction.description}
        </div>
        {transaction.subcategory && (
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            {transaction.subcategory}
          </div>
        )}
      </td>
      <td className={amountClass} style={{ fontWeight: 600, textAlign: 'right', whiteSpace: 'nowrap', padding: '14px 24px' }}>
        {amountPrefix}₹{transaction.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
      </td>
      <td style={{ padding: '14px 24px' }}>
        <span style={{
          padding: '4px 8px', borderRadius: '4px', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: '600',
          backgroundColor: isDebit ? 'var(--debit-bg)' : 'var(--credit-bg)',
          color: isDebit ? 'var(--debit-text)' : 'var(--credit-text)'
        }}>
          {transaction.transaction_type}
        </span>
      </td>
      <td style={{ padding: '14px 24px' }}>
        <CategoryBadge category={transaction.category} />
      </td>
      <td style={{ textAlign: 'center', padding: '14px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px' }}>
          {transaction.is_recurring && (
            <Repeat size={14} title="Recurring" style={{ color: 'var(--primary-blue)', opacity: 0.5 }} />
          )}
          {onEdit && (
            <button onClick={onEdit} title="Edit" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', borderRadius: '4px', color: 'var(--text-muted)' }}
              onMouseOver={(e) => e.currentTarget.style.color = 'var(--accent-color)'}
              onMouseOut={(e) => e.currentTarget.style.color = 'var(--text-muted)'}>
              <Pencil size={14} />
            </button>
          )}
          {onDelete && (
            <button onClick={onDelete} disabled={isDeleting} title="Delete"
              style={{ background: 'none', border: 'none', cursor: isDeleting ? 'not-allowed' : 'pointer', padding: '4px', borderRadius: '4px', color: 'var(--text-muted)', opacity: isDeleting ? 0.5 : 1 }}
              onMouseOver={(e) => !isDeleting && (e.currentTarget.style.color = 'var(--debit-text)')}
              onMouseOut={(e) => e.currentTarget.style.color = 'var(--text-muted)'}>
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
};

export default TransactionRow;
