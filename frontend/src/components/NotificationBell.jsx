import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Bell,
  AlertOctagon,
  AlertTriangle,
  Info,
  Check,
  Trash2,
  X,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import {
  getNotifications,
  markNotificationRead,
  markNotificationUnread,
  markAllNotificationsRead,
  deleteNotification,
} from '../utils/api';
import { formatDateTimeDisplay, formatRelativeTime } from '../utils/dateUtils';
import './NotificationBell.css';

// Labels mirror the backend NOTIFICATION_TYPES / severities exactly.
// This component only renders what the API returns; it never derives
// financial values or decides whether an alert should exist.
const TYPE_LABELS = {
  budget_threshold: 'Budget Threshold',
  budget_exceeded: 'Budget Exceeded',
  spending_velocity: 'Spending Velocity',
  anomaly: 'Anomaly',
};

const TYPE_FILTERS = ['all', ...Object.keys(TYPE_LABELS)];

const SEVERITY_COLORS = {
  critical: '#EF4444',
  warning: '#F59E0B',
  info: '#3B82F6',
};

const getSeverityIcon = (severity) => {
  if (severity === 'critical') return <AlertOctagon size={16} color={SEVERITY_COLORS.critical} />;
  if (severity === 'warning') return <AlertTriangle size={16} color={SEVERITY_COLORS.warning} />;
  return <Info size={16} color={SEVERITY_COLORS.info} />;
};

const NotificationBell = () => {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [typeFilter, setTypeFilter] = useState('all');
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const containerRef = useRef(null);

  // Badge count is fetched once on mount so the bell is accurate before the
  // user ever opens it. The list itself is only fetched when the panel opens,
  // so nothing runs on every render.
  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await getNotifications({ page: 1, limit: 1 });
      setUnreadCount(data.unread_count ?? 0);
    } catch (err) {
      // A failed badge poll must never surface an error state on the nav bar;
      // the panel reports its own errors when opened.
      console.error(err);
    }
  }, []);

  useEffect(() => {
    fetchUnreadCount();
  }, [fetchUnreadCount]);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getNotifications({
        page,
        limit,
        unread_only: unreadOnly,
        type: typeFilter === 'all' ? '' : typeFilter,
      });
      setNotifications(data.notifications || []);
      setTotal(data.total ?? 0);
      setPages(data.pages ?? 0);
      setUnreadCount(data.unread_count ?? 0);
    } catch (err) {
      setError(
        err?.response?.data?.detail || 'Could not load notifications. Please try again.'
      );
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  }, [page, limit, unreadOnly, typeFilter]);

  useEffect(() => {
    if (open) fetchNotifications();
  }, [open, fetchNotifications]);

  // Close the panel on outside click and on Escape.
  useEffect(() => {
    if (!open) return undefined;
    const handleOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleEscape = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handleOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  const handleToggleRead = async (notification) => {
    // Optimistic update, reverted from the server if the call fails.
    const nextIsRead = !notification.is_read;
    setNotifications((prev) =>
      prev.map((n) => (n.id === notification.id ? { ...n, is_read: nextIsRead } : n))
    );
    setUnreadCount((prev) => Math.max(0, prev + (nextIsRead ? -1 : 1)));
    try {
      if (nextIsRead) {
        await markNotificationRead(notification.id);
      } else {
        await markNotificationUnread(notification.id);
      }
    } catch (err) {
      console.error(err);
      await fetchNotifications();
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      await fetchNotifications();
      await fetchUnreadCount();
    } catch (err) {
      console.error(err);
      setError('Could not mark all notifications as read.');
    }
  };

  const handleDelete = async (notification) => {
    const previous = notifications;
    setNotifications((prev) => prev.filter((n) => n.id !== notification.id));
    if (!notification.is_read) setUnreadCount((prev) => Math.max(0, prev - 1));
    setTotal((prev) => Math.max(0, prev - 1));
    try {
      await deleteNotification(notification.id);
    } catch (err) {
      console.error(err);
      setNotifications(previous);
      await fetchNotifications();
    }
  };

  const handleRetry = () => {
    setPage(1);
    fetchNotifications();
  };

  const handleTypeChange = (value) => {
    setTypeFilter(value);
    setPage(1);
  };

  const handleUnreadToggle = () => {
    setUnreadOnly((prev) => !prev);
    setPage(1);
  };

  const hasPrevious = page > 1;
  const hasNext = page < pages;

  return (
    <div className="notification-bell" ref={containerRef}>
      <button
        type="button"
        className="notification-trigger"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={
          unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'
        }
        data-testid="notification-trigger"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="notification-badge" data-testid="notification-badge">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="notification-panel"
          role="dialog"
          aria-label="Notifications"
          data-testid="notification-panel"
        >
          <div className="notification-panel-header">
            <h3 className="notification-panel-title">Notifications</h3>
            <div className="notification-header-actions">
              {unreadCount > 0 && (
                <button
                  type="button"
                  className="notification-action"
                  onClick={handleMarkAllRead}
                  data-testid="mark-all-read"
                >
                  <Check size={14} /> Mark all read
                </button>
              )}
              <button
                type="button"
                className="notification-icon-btn"
                onClick={() => setOpen(false)}
                aria-label="Close notifications"
                data-testid="notification-close"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <div className="notification-filters">
            <select
              className="notification-select"
              value={typeFilter}
              onChange={(event) => handleTypeChange(event.target.value)}
              aria-label="Filter by notification type"
              data-testid="type-filter"
            >
              {TYPE_FILTERS.map((value) => (
                <option key={value} value={value}>
                  {value === 'all' ? 'All types' : TYPE_LABELS[value]}
                </option>
              ))}
            </select>
            <label className="notification-checkbox">
              <input
                type="checkbox"
                checked={unreadOnly}
                onChange={handleUnreadToggle}
                data-testid="unread-only-filter"
              />
              Unread only
            </label>
          </div>

          <div className="notification-list">
            {loading && (
              <div className="notification-loading" data-testid="notification-loading">
                Loading notifications…
              </div>
            )}

            {!loading && error && (
              <div className="notification-error" data-testid="notification-error">
                <p className="notification-error-text">{error}</p>
                <button
                  type="button"
                  className="notification-action"
                  onClick={handleRetry}
                  data-testid="notification-retry"
                >
                  Retry
                </button>
              </div>
            )}

            {!loading && !error && notifications.length === 0 && (
              <div className="notification-empty" data-testid="notification-empty">
                <Bell size={24} />
                <p>No notifications yet.</p>
              </div>
            )}

            {!loading &&
              !error &&
              notifications.map((notification) => (
                <div
                  key={notification.id}
                  className={
                    notification.is_read
                      ? 'notification-item notification-item-read'
                      : 'notification-item notification-item-unread'
                  }
                  data-testid={`notification-item-${notification.id}`}
                  data-read={notification.is_read ? 'true' : 'false'}
                >
                  <div className="notification-item-top">
                    <span className="notification-item-icon">
                      {getSeverityIcon(notification.severity)}
                    </span>
                    <span className="notification-item-title">{notification.title}</span>
                    {!notification.is_read && (
                      <span
                        className="notification-unread-dot"
                        data-testid={`notification-unread-dot-${notification.id}`}
                      />
                    )}
                  </div>

                  <p className="notification-item-message">{notification.message}</p>

                  <div className="notification-item-meta">
                    <span
                      className="notification-type-tag"
                      style={{
                        color: SEVERITY_COLORS[notification.severity] || 'var(--text-muted)',
                      }}
                    >
                      {TYPE_LABELS[notification.type] || notification.type}
                    </span>
                    <span
                      className="notification-timestamp"
                      title={formatDateTimeDisplay(notification.created_at) || ''}
                    >
                      {formatRelativeTime(notification.created_at)}
                    </span>
                    <span
                      className="notification-state-label"
                      data-testid={`notification-state-${notification.id}`}
                    >
                      {notification.is_read ? 'Read' : 'Unread'}
                    </span>
                  </div>

                  <div className="notification-item-actions">
                    <button
                      type="button"
                      className="notification-action"
                      onClick={() => handleToggleRead(notification)}
                      data-testid={`toggle-read-${notification.id}`}
                    >
                      {notification.is_read ? 'Mark unread' : 'Mark read'}
                    </button>
                    <button
                      type="button"
                      className="notification-action notification-action-danger"
                      onClick={() => handleDelete(notification)}
                      data-testid={`delete-${notification.id}`}
                    >
                      <Trash2 size={14} /> Delete
                    </button>
                  </div>
                </div>
              ))}
          </div>

          {!loading && !error && pages > 1 && (
            <div className="notification-pagination" data-testid="notification-pagination">
              <button
                type="button"
                className="notification-icon-btn"
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                disabled={!hasPrevious}
                aria-label="Previous page"
                data-testid="page-prev"
              >
                <ChevronLeft size={16} />
              </button>
              <span data-testid="page-indicator">
                Page {page} of {pages}
              </span>
              <button
                type="button"
                className="notification-icon-btn"
                onClick={() => setPage((prev) => prev + 1)}
                disabled={!hasNext}
                aria-label="Next page"
                data-testid="page-next"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}

          {!loading && !error && !unreadOnly && total > 0 && (
            <div className="notification-footer">
              {total} notification{total === 1 ? '' : 's'}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationBell;