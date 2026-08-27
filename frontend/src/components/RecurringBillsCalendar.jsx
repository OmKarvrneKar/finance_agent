import React, { useState, useEffect, useCallback } from 'react';
import { getRecurringCalendar } from '../utils/api';
import CategoryBadge from './CategoryBadge';
import {
  toISODate,
  addDays,
  formatDateDisplay,
  formatCurrency,
  getDefaultUpcomingRange,
  buildMonthCells,
  getMonthsInRange,
} from '../utils/dateUtils';
import {
  Calendar,
  List,
  AlertCircle,
  CalendarClock,
  HelpCircle,
  CheckCircle,
  Bot,
  ReceiptText,
} from 'lucide-react';

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const DATE_STATUS_META = {
  projected: { label: 'Projected', color: 'var(--credit-text)', bg: 'var(--credit-bg)', border: 'solid' },
  uncertain: { label: 'Date uncertain', color: '#b45309', bg: '#fffbeb', border: 'dashed' },
  missing: { label: 'Date missing', color: 'var(--text-muted)', bg: 'var(--bg-secondary)', border: 'dotted' },
};

const DateStatusBadge = ({ status }) => {
  const meta = DATE_STATUS_META[status] || DATE_STATUS_META.missing;
  return (
    <span
      data-testid={`date-status-${status}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px 8px',
        borderRadius: '9999px',
        fontSize: '0.7rem',
        fontWeight: 600,
        color: meta.color,
        backgroundColor: meta.bg,
        border: `1px ${meta.border} currentColor`,
        whiteSpace: 'nowrap',
      }}
    >
      {status === 'projected' && <CalendarClock size={12} />}
      {status === 'uncertain' && <HelpCircle size={12} />}
      {status === 'missing' && <AlertCircle size={12} />}
      {meta.label}
    </span>
  );
};

const ConfirmedBadge = ({ confirmed }) => {
  if (confirmed) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem', color: 'var(--credit-text)', fontWeight: 500 }}>
        <CheckCircle size={13} /> Confirmed
      </span>
    );
  }
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
      <Bot size={13} /> AI detected
    </span>
  );
};

const RecurringBillsCalendar = ({ startDate, endDate }) => {
  const defaults = getDefaultUpcomingRange(30);
  const [rangeStart, setRangeStart] = useState(startDate || defaults.start);
  const [rangeEnd, setRangeEnd] = useState(endDate || defaults.end);
  const [view, setView] = useState('calendar');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (startDate !== undefined || endDate !== undefined) {
      if (startDate && endDate) {
        setRangeStart(startDate);
        setRangeEnd(endDate);
      } else if (!startDate && !endDate) {
        const d = getDefaultUpcomingRange(30);
        setRangeStart(d.start);
        setRangeEnd(d.end);
      } else {
        if (startDate) setRangeStart(startDate);
        if (endDate) setRangeEnd(endDate);
      }
    }
  }, [startDate, endDate]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await getRecurringCalendar({
        start_date: rangeStart,
        end_date: rangeEnd,
      });
      setData(result);
    } catch (err) {
      if (err.response?.status === 401) return;
      setError('Failed to load recurring bills calendar');
    } finally {
      setLoading(false);
    }
  }, [rangeStart, rangeEnd]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const bills = data?.bills || [];
  const projectedBills = bills.filter((b) => b.expected_date);
  const undatedBills = bills.filter((b) => !b.expected_date);

  const billsByDate = {};
  projectedBills.forEach((b) => {
    if (!billsByDate[b.expected_date]) billsByDate[b.expected_date] = [];
    billsByDate[b.expected_date].push(b);
  });

  const months = getMonthsInRange(rangeStart, rangeEnd);
  const totalExpected = data?.total_expected_amount ?? '0.00';

  const handlePreset = (days) => {
    const today = new Date();
    setRangeStart(toISODate(today));
    setRangeEnd(toISODate(addDays(today, days)));
  };

  const billChip = (bill, compact = false) => (
    <div
      key={`${bill.description}-${bill.expected_date || 'none'}`}
      data-testid={`bill-${bill.description}`}
      style={{
        backgroundColor: 'var(--accent-bg)',
        borderLeft: `3px solid var(--accent-color)`,
        borderRadius: '4px',
        padding: compact ? '2px 4px' : '4px 6px',
        marginBottom: '2px',
        fontSize: compact ? '0.65rem' : '0.7rem',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
    >
      <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{bill.description}</div>
      {!compact && (
        <div style={{ color: 'var(--text-muted)' }}>{formatCurrency(bill.expected_amount)}</div>
      )}
    </div>
  );

  const renderUndatedSection = () => {
    if (undatedBills.length === 0) return null;
    return (
      <div
        data-testid="undated-bills"
        style={{
          marginTop: '20px',
          padding: '16px',
          borderRadius: '8px',
          border: '1px dashed var(--border-color)',
          backgroundColor: 'var(--bg-secondary)',
        }}
      >
        <h4 style={{ margin: '0 0 12px', fontSize: '0.9rem', color: 'var(--text-main)' }}>
          No fixed date ({undatedBills.length})
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {undatedBills.map((bill) => (
            <div
              key={bill.description}
              data-testid={`bill-${bill.description}`}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '12px',
                flexWrap: 'wrap',
                padding: '10px 12px',
                backgroundColor: 'var(--card-bg)',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
              }}
            >
              <div>
                <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{bill.description}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {formatCurrency(bill.expected_amount)} · {bill.frequency}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                {bill.category && <CategoryBadge category={bill.category} />}
                <DateStatusBadge status={bill.date_status} />
                <ConfirmedBadge confirmed={bill.is_user_confirmed} />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderCalendarView = () => {
    if (months.length === 0) {
      return <div style={{ color: 'var(--text-muted)', padding: '24px' }}>Select a valid date range.</div>;
    }
    return (
      <div data-testid="calendar-view" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {months.map(({ year, month }) => {
          const cells = buildMonthCells(year, month);
          const monthLabel = new Date(year, month, 1).toLocaleDateString(undefined, {
            month: 'long',
            year: 'numeric',
          });
          return (
            <div key={`${year}-${month}`}>
              <h4 style={{ margin: '0 0 10px', fontSize: '0.95rem', color: 'var(--text-main)' }}>{monthLabel}</h4>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(7, 1fr)',
                  gap: '4px',
                }}
              >
                {WEEKDAYS.map((d) => (
                  <div
                    key={d}
                    style={{
                      textAlign: 'center',
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      color: 'var(--text-muted)',
                      padding: '4px 0',
                    }}
                  >
                    {d}
                  </div>
                ))}
                {cells.map((iso, i) => (
                  <div
                    key={iso || `pad-${i}`}
                    data-testid={iso ? `day-${iso}` : undefined}
                    style={{
                      minHeight: '64px',
                      padding: '4px',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: iso ? (billsByDate[iso] ? 'var(--accent-bg)' : 'var(--card-bg)') : 'transparent',
                      opacity: iso ? 1 : 0.4,
                    }}
                  >
                    {iso && (
                      <>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '2px' }}>
                          {Number(iso.slice(8))}
                        </div>
                        {(billsByDate[iso] || []).map((b) => billChip(b, true))}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {renderUndatedSection()}
      </div>
    );
  };

  const renderListView = () => {
    if (bills.length === 0) return null;
    return (
      <div data-testid="list-view" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {bills.map((bill) => (
          <div
            key={`${bill.description}-${bill.expected_date || 'none'}`}
            data-testid={`bill-${bill.description}`}
            className="card"
            style={{
              padding: '14px 16px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '12px',
              flexWrap: 'wrap',
              borderLeft: `4px solid ${
                bill.date_status === 'projected'
                  ? 'var(--credit-text)'
                  : bill.date_status === 'uncertain'
                  ? '#d97706'
                  : 'var(--text-muted)'
              }`,
            }}
          >
            <div style={{ minWidth: '140px' }}>
              <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{bill.description}</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                {bill.frequency} · Last seen: {bill.last_seen}
              </div>
            </div>
            <div style={{ fontWeight: 600, color: 'var(--debit-text)' }} data-testid={`amount-${bill.description}`}>
              {formatCurrency(bill.expected_amount)}
            </div>
            <div data-testid={`date-${bill.description}`} style={{ fontSize: '0.85rem', color: 'var(--text-main)' }}>
              {bill.expected_date ? formatDateDisplay(bill.expected_date) : 'No fixed date'}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              {bill.category && <CategoryBadge category={bill.category} />}
              <DateStatusBadge status={bill.date_status} />
              <ConfirmedBadge confirmed={bill.is_user_confirmed} />
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="card" data-testid="recurring-bills-calendar" style={{ padding: '24px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '16px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '8px',
              backgroundColor: 'var(--accent-bg)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--accent-color)',
            }}
          >
            <Calendar size={18} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)' }}>
              Recurring Bills
            </h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Upcoming bills from detected recurring transactions
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '4px', backgroundColor: 'var(--bg-color)', borderRadius: '6px', padding: '3px', border: '1px solid var(--border-color)' }}>
          <button
            onClick={() => setView('calendar')}
            data-testid="view-calendar"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              fontSize: '0.8rem',
              borderRadius: '4px',
              border: 'none',
              cursor: 'pointer',
              backgroundColor: view === 'calendar' ? 'white' : 'transparent',
              boxShadow: view === 'calendar' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              color: view === 'calendar' ? 'var(--text-main)' : 'var(--text-muted)',
              fontWeight: view === 'calendar' ? 600 : 400,
            }}
          >
            <Calendar size={14} /> Calendar
          </button>
          <button
            onClick={() => setView('list')}
            data-testid="view-list"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              fontSize: '0.8rem',
              borderRadius: '4px',
              border: 'none',
              cursor: 'pointer',
              backgroundColor: view === 'list' ? 'white' : 'transparent',
              boxShadow: view === 'list' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              color: view === 'list' ? 'var(--text-main)' : 'var(--text-muted)',
              fontWeight: view === 'list' ? 600 : 400,
            }}
          >
            <List size={14} /> List
          </button>
        </div>
      </div>

      {/* Date range controls */}
      <div
        style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          flexWrap: 'wrap',
          marginBottom: '16px',
          paddingBottom: '16px',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        <div style={{ display: 'flex', gap: '4px' }}>
          {[30, 60, 90].map((days) => (
            <button
              key={days}
              onClick={() => handlePreset(days)}
              data-testid={`preset-${days}`}
              style={{
                padding: '4px 10px',
                fontSize: '0.75rem',
                borderRadius: '4px',
                border: '1px solid var(--border-color)',
                cursor: 'pointer',
                backgroundColor: 'var(--bg-secondary)',
                color: 'var(--text-muted)',
              }}
            >
              Next {days}d
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <input
            type="date"
            data-testid="range-start"
            value={rangeStart}
            onChange={(e) => setRangeStart(e.target.value)}
            style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.8rem' }}
          />
          <span style={{ color: 'var(--text-muted)' }}>to</span>
          <input
            type="date"
            data-testid="range-end"
            value={rangeEnd}
            onChange={(e) => setRangeEnd(e.target.value)}
            style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid var(--border-color)', fontSize: '0.8rem' }}
          />
        </div>
        <div
          data-testid="total-expected"
          style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'baseline',
            gap: '8px',
          }}
        >
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Total expected
          </span>
          <span style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--debit-text)' }}>
            {formatCurrency(totalExpected)}
          </span>
        </div>
      </div>

      {loading && (
        <div data-testid="loading-state">
          <div className="skeleton" style={{ height: '40px', width: '100%', marginBottom: '12px' }} />
          <div className="skeleton" style={{ height: '220px', width: '100%', marginBottom: '12px' }} />
          <div className="skeleton" style={{ height: '80px', width: '100%' }} />
        </div>
      )}

      {!loading && error && (
        <div
          data-testid="error-state"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '16px',
            borderRadius: '8px',
            backgroundColor: 'var(--debit-bg)',
            color: 'var(--debit-text)',
          }}
        >
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {!loading && !error && bills.length === 0 && (
        <div
          data-testid="empty-state"
          style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-muted)' }}
        >
          <ReceiptText size={40} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
          <h4 style={{ margin: '0 0 6px', color: 'var(--text-main)' }}>No upcoming recurring bills</h4>
          <p style={{ margin: 0 }}>
            No recurring debits project into {formatDateDisplay(rangeStart)} – {formatDateDisplay(rangeEnd)}.
          </p>
        </div>
      )}

      {!loading && !error && bills.length > 0 && (
        <div data-testid="bills-content">
          {view === 'calendar' ? renderCalendarView() : renderListView()}
        </div>
      )}
    </div>
  );
};

export default RecurringBillsCalendar;
