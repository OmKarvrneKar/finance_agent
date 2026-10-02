export const toISODate = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

export const addDays = (d, n) => {
  const result = new Date(d);
  result.setDate(result.getDate() + n);
  return result;
};

export const parseISODate = (iso) => {
  if (!iso) return null;
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
};

export const formatDateDisplay = (iso) => {
  if (!iso) return null;
  const d = parseISODate(iso);
  if (!d) return null;
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

// Accepts a full ISO timestamp (e.g. "2026-10-02T14:30:00") as well as a
// bare date, since API responses carry datetime values.
export const parseISODateTime = (value) => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

export const formatDateTimeDisplay = (value) => {
  const d = parseISODateTime(value);
  if (!d) return null;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

export const formatRelativeTime = (value) => {
  const d = parseISODateTime(value);
  if (!d) return null;
  const diffMs = Date.now() - d.getTime();
  const diffMinutes = Math.round(diffMs / 60000);
  if (diffMinutes < 1) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDateDisplay(value.slice(0, 10));
};

export const formatCurrency = (amount) =>
  `₹${Number(amount || 0).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

export const getDefaultUpcomingRange = (days = 30) => {
  const today = new Date();
  return {
    start: toISODate(today),
    end: toISODate(addDays(today, days)),
  };
};

export const buildMonthCells = (year, month) => {
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const startDow = new Date(year, month, 1).getDay();
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push(
      `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    );
  }
  return cells;
};

export const getMonthsInRange = (startISO, endISO, maxMonths = 6) => {
  const start = parseISODate(startISO);
  const end = parseISODate(endISO);
  if (!start || !end) return [];
  const months = [];
  const cur = new Date(start.getFullYear(), start.getMonth(), 1);
  const endMonth = new Date(end.getFullYear(), end.getMonth(), 1);
  while (cur <= endMonth && months.length < maxMonths) {
    months.push({ year: cur.getFullYear(), month: cur.getMonth() });
    cur.setMonth(cur.getMonth() + 1);
  }
  return months;
};
