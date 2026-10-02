import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import NotificationBell from '../components/NotificationBell';

vi.mock('../utils/api', () => ({
  getNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markNotificationUnread: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  deleteNotification: vi.fn(),
}));

import {
  getNotifications,
  markNotificationRead,
  markNotificationUnread,
  markAllNotificationsRead,
  deleteNotification,
} from '../utils/api';

const makeNotification = (overrides = {}) => ({
  id: 1,
  user_id: 7,
  type: 'budget_threshold',
  title: 'Food budget threshold',
  message: 'You have reached 85% of your Food budget.',
  severity: 'warning',
  is_read: false,
  created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
  related_entity_type: 'budget_goal',
  related_entity_id: 3,
  metadata: { category: 'Food', period: '2026-10' },
  ...overrides,
});

const emptyResponse = (overrides = {}) => ({
  notifications: [],
  total: 0,
  page: 1,
  limit: 10,
  pages: 0,
  unread_count: 0,
  ...overrides,
});

// The component makes two kinds of call: a lightweight badge poll (limit: 1)
// on mount and the paged list fetch (limit: 10) when the panel opens. Dispatching
// on `limit` keeps tests independent of call ordering.
const mockBadge = (unread_count = 0) => {
  getNotifications.mockImplementation(({ limit } = {}) =>
    limit === 1
      ? Promise.resolve(emptyResponse({ unread_count }))
      : Promise.resolve(emptyResponse({ unread_count }))
  );
};

// Queue successive list responses. The badge poll always mirrors the most
// recent list response, so unread counts stay internally consistent.
const mockListSequence = (initialUnread, responses) => {
  let call = 0;
  let latestUnread = initialUnread;
  getNotifications.mockImplementation(({ limit } = {}) => {
    if (limit === 1) return Promise.resolve(emptyResponse({ unread_count: latestUnread }));
    const next = responses[Math.min(call, responses.length - 1)];
    call += 1;
    const resolved = typeof next === 'function' ? next() : Promise.resolve(next);
    resolved.then((data) => {
      latestUnread = data.unread_count;
    });
    return resolved;
  });
};

const openPanel = async () => {
  fireEvent.click(screen.getByTestId('notification-trigger'));
  await waitFor(() => expect(screen.getByTestId('notification-panel')).toBeInTheDocument());
};

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getNotifications.mockResolvedValue(emptyResponse());
  });

  describe('bell and unread badge', () => {
    it('renders the bell trigger', async () => {
      render(<NotificationBell />);
      expect(screen.getByTestId('notification-trigger')).toBeInTheDocument();
      await waitFor(() => expect(getNotifications).toHaveBeenCalled());
    });

    it('shows no badge when unread count is zero', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await waitFor(() => expect(getNotifications).toHaveBeenCalled());
      expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
    });

    it('shows the unread count badge', async () => {
      getNotifications.mockResolvedValue(emptyResponse({ unread_count: 5 }));
      render(<NotificationBell />);
      await waitFor(() => {
        expect(screen.getByTestId('notification-badge')).toHaveTextContent('5');
      });
    });

    it('caps the badge display at 99+', async () => {
      getNotifications.mockResolvedValue(emptyResponse({ unread_count: 250 }));
      render(<NotificationBell />);
      await waitFor(() => {
        expect(screen.getByTestId('notification-badge')).toHaveTextContent('99+');
      });
    });

    it('fetches the badge count only once on mount, not on every render', async () => {
      getNotifications.mockResolvedValue(emptyResponse({ unread_count: 2 }));
      const { rerender } = render(<NotificationBell />);
      await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(1));
      rerender(<NotificationBell />);
      rerender(<NotificationBell />);
      expect(getNotifications).toHaveBeenCalledTimes(1);
    });

    it('does not fetch the notification list before the panel is opened', async () => {
      render(<NotificationBell />);
      await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(1));
      // only the lightweight badge poll ran, with limit=1
      expect(getNotifications.mock.calls[0][0]).toMatchObject({ limit: 1 });
      expect(screen.queryByTestId('notification-panel')).not.toBeInTheDocument();
    });

    it('toggles the panel open and closed', async () => {
      render(<NotificationBell />);
      await openPanel();
      fireEvent.click(screen.getByTestId('notification-trigger'));
      await waitFor(() =>
        expect(screen.queryByTestId('notification-panel')).not.toBeInTheDocument()
      );
    });
  });

  describe('notification list rendering', () => {
    it('renders notification title, message, severity, timestamp and state', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification()],
          total: 1,
          pages: 1,
          unread_count: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-1')).toBeInTheDocument());

      const item = screen.getByTestId('notification-item-1');
      expect(within(item).getByText('Food budget threshold')).toBeInTheDocument();
      expect(within(item).getByText(/reached 85%/)).toBeInTheDocument();
      expect(within(item).getByText('Budget Threshold')).toBeInTheDocument();
      expect(within(item).getByText('5m ago')).toBeInTheDocument();
      expect(screen.getByTestId('notification-state-1')).toHaveTextContent('Unread');
    });

    it('renders a relative timestamp derived from created_at', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [
            makeNotification({ id: 2, created_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString() }),
          ],
          total: 1,
          pages: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-2')).toBeInTheDocument());
      expect(screen.getByText('3h ago')).toBeInTheDocument();
    });

    it('renders all four notification types', async () => {
      const notifications = [
        makeNotification({ id: 1, type: 'budget_threshold' }),
        makeNotification({ id: 2, type: 'budget_exceeded', severity: 'critical' }),
        makeNotification({ id: 3, type: 'spending_velocity', severity: 'warning' }),
        makeNotification({ id: 4, type: 'anomaly', severity: 'info' }),
      ];
      getNotifications.mockResolvedValue(
        emptyResponse({ notifications, total: 4, pages: 1, unread_count: 4 })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-4')).toBeInTheDocument());

      // Scope each lookup to its item; the type filter <option> labels repeat.
      expect(
        within(screen.getByTestId('notification-item-1')).getByText('Budget Threshold')
      ).toBeInTheDocument();
      expect(
        within(screen.getByTestId('notification-item-2')).getByText('Budget Exceeded')
      ).toBeInTheDocument();
      expect(
        within(screen.getByTestId('notification-item-3')).getByText('Spending Velocity')
      ).toBeInTheDocument();
      expect(
        within(screen.getByTestId('notification-item-4')).getByText('Anomaly')
      ).toBeInTheDocument();
    });

    it('renders unknown severity without crashing', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 5, severity: 'unmapped' })],
          total: 1,
          pages: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-5')).toBeInTheDocument());
    });

    it('falls back to the raw type when it is not a known label', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 6, type: 'mystery_type' })],
          total: 1,
          pages: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-6')).toBeInTheDocument());
      expect(screen.getByText('mystery_type')).toBeInTheDocument();
    });
  });

  describe('read/unread state', () => {
    it('distinguishes read from unread items', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [
            makeNotification({ id: 1, is_read: false }),
            makeNotification({ id: 2, is_read: true }),
          ],
          total: 2,
          pages: 1,
          unread_count: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-2')).toBeInTheDocument());

      expect(screen.getByTestId('notification-item-1').className).toContain(
        'notification-item-unread'
      );
      expect(screen.getByTestId('notification-item-2').className).toContain(
        'notification-item-read'
      );
      expect(screen.getByTestId('notification-state-1')).toHaveTextContent('Unread');
      expect(screen.getByTestId('notification-state-2')).toHaveTextContent('Read');
    });

    it('shows an unread dot only for unread notifications', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [
            makeNotification({ id: 1, is_read: false }),
            makeNotification({ id: 2, is_read: true }),
          ],
          total: 2,
          pages: 1,
          unread_count: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-2')).toBeInTheDocument());

      expect(screen.getByTestId('notification-unread-dot-1')).toBeInTheDocument();
      expect(screen.queryByTestId('notification-unread-dot-2')).not.toBeInTheDocument();
    });

    it('offers the correct action label per state', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [
            makeNotification({ id: 1, is_read: false }),
            makeNotification({ id: 2, is_read: true }),
          ],
          total: 2,
          pages: 1,
          unread_count: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-2')).toBeInTheDocument());

      expect(within(screen.getByTestId('toggle-read-1')).getByText(/Mark read/)).toBeTruthy();
      expect(within(screen.getByTestId('toggle-read-2')).getByText(/Mark unread/)).toBeTruthy();
    });
  });

  describe('mark read / mark unread actions', () => {
    it('marks an individual notification as read', async () => {
      markNotificationRead.mockResolvedValue({ ...makeNotification(), is_read: true });
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1, is_read: false })],
          total: 1,
          pages: 1,
          unread_count: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('toggle-read-1')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('toggle-read-1'));
      await waitFor(() => expect(markNotificationRead).toHaveBeenCalledWith(1));
    });

    it('marks an individual notification as unread when supported', async () => {
      markNotificationUnread.mockResolvedValue(makeNotification({ id: 2, is_read: false }));
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 2, is_read: true })],
          total: 1,
          pages: 1,
          unread_count: 0,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('toggle-read-2')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('toggle-read-2'));
      await waitFor(() => expect(markNotificationUnread).toHaveBeenCalledWith(2));
    });

    it('decrements the badge optimistically when marking read', async () => {
      markNotificationRead.mockResolvedValue(makeNotification({ id: 1, is_read: true }));
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1, is_read: false })],
          total: 1,
          pages: 1,
          unread_count: 3,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('toggle-read-1')).toBeInTheDocument());
      expect(screen.getByTestId('notification-badge')).toHaveTextContent('3');

      fireEvent.click(screen.getByTestId('toggle-read-1'));
      await waitFor(() => {
        expect(screen.getByTestId('notification-badge')).toHaveTextContent('2');
      });
    });

    it('increments the badge when marking unread', async () => {
      markNotificationUnread.mockResolvedValue(makeNotification({ id: 2, is_read: false }));
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 2, is_read: true })],
          total: 1,
          pages: 1,
          unread_count: 2,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('toggle-read-2')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('toggle-read-2'));
      await waitFor(() => {
        expect(screen.getByTestId('notification-badge')).toHaveTextContent('3');
      });
    });

    it('flips the item state optimistically without a refetch', async () => {
      markNotificationRead.mockResolvedValue(makeNotification({ id: 1, is_read: true }));
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1, is_read: false })],
          total: 1,
          pages: 1,
          unread_count: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-1')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('toggle-read-1'));
      await waitFor(() => {
        expect(screen.getByTestId('notification-state-1')).toHaveTextContent('Read');
      });
    });

    it('refetches to restore server state when marking read fails', async () => {
      markNotificationRead.mockRejectedValue(new Error('network down'));
      getNotifications.mockResolvedValue({
        notifications: [makeNotification({ id: 1, is_read: false })],
        total: 1,
        page: 1,
        limit: 10,
        pages: 1,
        unread_count: 1,
      });
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('toggle-read-1')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('toggle-read-1'));
      await waitFor(() => {
        expect(screen.getByTestId('notification-state-1')).toHaveTextContent('Unread');
      });
      // list + badge were refetched to resync
      expect(getNotifications.mock.calls.length).toBeGreaterThan(2);
    });

    it('marks all notifications as read', async () => {
      markAllNotificationsRead.mockResolvedValue({
        message: 'All notifications marked as read.',
        updated: 2,
        unread_count: 0,
      });
      mockListSequence(2, [
        // initial panel load: two unread items
        emptyResponse({
          notifications: [makeNotification({ id: 1, is_read: false }), makeNotification({ id: 2, is_read: false })],
          total: 2,
          pages: 1,
          unread_count: 2,
        }),
        // after marking all read
        emptyResponse({
          notifications: [makeNotification({ id: 1, is_read: true }), makeNotification({ id: 2, is_read: true })],
          total: 2,
          pages: 1,
          unread_count: 0,
        }),
      ]);
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('mark-all-read')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('mark-all-read'));
      await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalled());
      await waitFor(() => expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument());
    });

    it('hides mark all read when there is nothing unread', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1, is_read: true })],
          total: 1,
          pages: 1,
          unread_count: 0,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-1')).toBeInTheDocument());
      expect(screen.queryByTestId('mark-all-read')).not.toBeInTheDocument();
    });
  });

  describe('delete', () => {
    it('deletes a notification and removes it from the list', async () => {
      deleteNotification.mockResolvedValue({ message: 'Notification deleted.' });
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [
            makeNotification({ id: 1 }),
            makeNotification({ id: 2, title: 'Second' }),
          ],
          total: 2,
          pages: 1,
          unread_count: 2,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-2')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('delete-1'));
      await waitFor(() => {
        expect(screen.queryByTestId('notification-item-1')).not.toBeInTheDocument();
      });
      expect(deleteNotification).toHaveBeenCalledWith(1);
      expect(screen.getByTestId('notification-item-2')).toBeInTheDocument();
    });

    it('decrements the badge when deleting an unread notification', async () => {
      deleteNotification.mockResolvedValue({ message: 'Notification deleted.' });
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1, is_read: false })],
          total: 1,
          pages: 1,
          unread_count: 4,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('delete-1')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('delete-1'));
      await waitFor(() => {
        expect(screen.getByTestId('notification-badge')).toHaveTextContent('3');
      });
    });

    it('keeps the badge when deleting an already-read notification', async () => {
      deleteNotification.mockResolvedValue({ message: 'Notification deleted.' });
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1, is_read: true })],
          total: 1,
          pages: 1,
          unread_count: 4,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('delete-1')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('delete-1'));
      await waitFor(() => {
        expect(screen.getByTestId('notification-badge')).toHaveTextContent('4');
      });
    });

    it('restores the notification when delete fails', async () => {
      deleteNotification.mockRejectedValue(new Error('delete failed'));
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1 })],
          total: 1,
          pages: 1,
          unread_count: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('delete-1')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('delete-1'));
      await waitFor(() => {
        expect(screen.getByTestId('notification-item-1')).toBeInTheDocument();
      });
    });
  });

  describe('pagination', () => {
    it('shows the pagination control when there are multiple pages', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1 })],
          total: 25,
          page: 1,
          pages: 3,
          unread_count: 1,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-pagination')).toBeInTheDocument());
      expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 1 of 3');
    });

    it('requests the next page and updates the indicator', async () => {
      mockListSequence(1, [
        emptyResponse({ notifications: [], total: 25, page: 1, pages: 3, unread_count: 1 }),
        emptyResponse({
          notifications: [makeNotification({ id: 11, title: 'Page two item' })],
          total: 25,
          page: 2,
          pages: 3,
          unread_count: 1,
        }),
      ]);
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('page-next')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('page-next'));
      await waitFor(() => {
        expect(getNotifications).toHaveBeenCalledWith(expect.objectContaining({ page: 2 }));
      });
      await waitFor(() => {
        expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 2 of 3');
      });
    });

    it('returns to the previous page', async () => {
      mockListSequence(1, [
        emptyResponse({ notifications: [makeNotification({ id: 1 })], total: 25, page: 1, pages: 3, unread_count: 1 }),
        emptyResponse({ notifications: [makeNotification({ id: 2 })], total: 25, page: 2, pages: 3, unread_count: 1 }),
        emptyResponse({ notifications: [], total: 25, page: 1, pages: 3, unread_count: 1 }),
      ]);
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('page-prev')).toBeInTheDocument());
      expect(screen.getByTestId('page-prev')).toBeDisabled();

      fireEvent.click(screen.getByTestId('page-next'));
      await waitFor(() => expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 2 of 3'));

      fireEvent.click(screen.getByTestId('page-prev'));
      await waitFor(() => {
        expect(getNotifications).toHaveBeenCalledWith(expect.objectContaining({ page: 1 }));
      });
      await waitFor(() => expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 1 of 3'));
      expect(screen.getByTestId('page-prev')).toBeDisabled();
    });

    it('disables previous on the first page', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1 })],
          total: 25,
          page: 1,
          pages: 3,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('page-prev')).toBeInTheDocument());
      expect(screen.getByTestId('page-prev')).toBeDisabled();
      expect(screen.getByTestId('page-next')).not.toBeDisabled();
    });

    it('disables next on the last page', async () => {
      // Three pages; walk forward until the component sits on the last one.
      mockListSequence(1, [
        emptyResponse({ notifications: [makeNotification({ id: 1 })], total: 25, page: 1, pages: 3, unread_count: 1 }),
        emptyResponse({ notifications: [makeNotification({ id: 2 })], total: 25, page: 2, pages: 3, unread_count: 1 }),
        emptyResponse({ notifications: [makeNotification({ id: 3 })], total: 25, page: 3, pages: 3, unread_count: 1 }),
      ]);
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('page-next')).not.toBeDisabled());

      fireEvent.click(screen.getByTestId('page-next'));
      await waitFor(() => expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 2 of 3'));
      expect(screen.getByTestId('page-next')).not.toBeDisabled();

      fireEvent.click(screen.getByTestId('page-next'));
      await waitFor(() => expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 3 of 3'));
      expect(screen.getByTestId('page-next')).toBeDisabled();
      expect(screen.getByTestId('page-prev')).not.toBeDisabled();
    });

    it('hides pagination when everything fits on one page', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({ notifications: [makeNotification({ id: 1 })], total: 1, pages: 1 })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-1')).toBeInTheDocument());
      expect(screen.queryByTestId('notification-pagination')).not.toBeInTheDocument();
    });
  });

  describe('filters', () => {
    it('sends the selected type filter to the API', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('type-filter')).toBeInTheDocument());

      fireEvent.change(screen.getByTestId('type-filter'), { target: { value: 'anomaly' } });
      await waitFor(() => {
        expect(getNotifications).toHaveBeenCalledWith(
          expect.objectContaining({ type: 'anomaly', page: 1 })
        );
      });
    });

    it('offers all four notification types plus all', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('type-filter')).toBeInTheDocument());

      const options = within(screen.getByTestId('type-filter')).getAllByRole('option');
      expect(options.map((o) => o.value)).toEqual([
        'all',
        'budget_threshold',
        'budget_exceeded',
        'spending_velocity',
        'anomaly',
      ]);
    });

    it('sends no type filter when all is selected', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('type-filter')).toBeInTheDocument());

      await waitFor(() => {
        expect(getNotifications).toHaveBeenCalledWith(expect.objectContaining({ type: '' }));
      });
    });

    it('sends unread_only when the checkbox is enabled', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('unread-only-filter')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('unread-only-filter'));
      await waitFor(() => {
        expect(getNotifications).toHaveBeenCalledWith(
          expect.objectContaining({ unread_only: true })
        );
      });
    });

    it('sends unread_only false by default', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => {
        expect(getNotifications).toHaveBeenCalledWith(
          expect.objectContaining({ unread_only: false })
        );
      });
    });

    it('resets to page 1 when the type filter changes', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({
          notifications: [makeNotification({ id: 1 })],
          total: 25,
          page: 2,
          pages: 3,
        })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('type-filter')).toBeInTheDocument());

      fireEvent.change(screen.getByTestId('type-filter'), { target: { value: 'anomaly' } });
      await waitFor(() => {
        expect(getNotifications).toHaveBeenCalledWith(
          expect.objectContaining({ page: 1, type: 'anomaly' })
        );
      });
    });

    it('combines type filter and unread-only filter', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('type-filter')).toBeInTheDocument());

      fireEvent.change(screen.getByTestId('type-filter'), { target: { value: 'spending_velocity' } });
      fireEvent.click(screen.getByTestId('unread-only-filter'));
      await waitFor(() => {
        expect(getNotifications).toHaveBeenCalledWith(
          expect.objectContaining({ type: 'spending_velocity', unread_only: true })
        );
      });
    });
  });

  describe('loading, empty and error states', () => {
    it('shows a loading state while fetching the list', async () => {
      getNotifications.mockImplementation(({ limit } = {}) =>
        limit === 1 ? Promise.resolve(emptyResponse()) : new Promise(() => {})
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-loading')).toBeInTheDocument());
    });

    it('hides the loading state once loaded', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({ notifications: [makeNotification({ id: 1 })], total: 1, pages: 1 })
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-1')).toBeInTheDocument());
      expect(screen.queryByTestId('notification-loading')).not.toBeInTheDocument();
    });

    it('shows an empty state when there are no notifications', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-empty')).toBeInTheDocument());
      expect(screen.getByText('No notifications yet.')).toBeInTheDocument();
    });

    it('shows the empty state when a filter excludes everything', async () => {
      getNotifications.mockResolvedValue(emptyResponse({ total: 0, pages: 0 }));
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-empty')).toBeInTheDocument());
    });

    it('shows an error state when the API fails', async () => {
      getNotifications.mockImplementation(({ limit } = {}) =>
        limit === 1
          ? Promise.resolve(emptyResponse())
          : Promise.reject(new Error('boom'))
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-error')).toBeInTheDocument());
    });

    it('surfaces the backend error detail message', async () => {
      const failure = new Error('unauthorized');
      failure.response = { data: { detail: 'Invalid notification type' } };
      getNotifications.mockImplementation(({ limit } = {}) =>
        limit === 1 ? Promise.resolve(emptyResponse()) : Promise.reject(failure)
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() =>
        expect(screen.getByText('Invalid notification type')).toBeInTheDocument()
      );
    });

    it('falls back to a generic message without backend detail', async () => {
      getNotifications.mockImplementation(({ limit } = {}) =>
        limit === 1 ? Promise.resolve(emptyResponse()) : Promise.reject(new Error('boom'))
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() =>
        expect(screen.getByText(/Could not load notifications/)).toBeInTheDocument()
      );
    });

    it('does not show an error state for a failing badge poll alone', async () => {
      getNotifications.mockImplementation(({ limit } = {}) =>
        limit === 1 ? Promise.reject(new Error('badge failed')) : Promise.resolve(emptyResponse())
      );
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-empty')).toBeInTheDocument());
      expect(screen.queryByTestId('notification-error')).not.toBeInTheDocument();
      expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
    });

    it('retries on demand after a failure', async () => {
      let failing = true;
      getNotifications.mockImplementation(({ limit } = {}) => {
        if (limit === 1) return Promise.resolve(emptyResponse());
        if (failing) return Promise.reject(new Error('boom'));
        return Promise.resolve(
          emptyResponse({ notifications: [makeNotification({ id: 1 })], total: 1, pages: 1 })
        );
      });
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-error')).toBeInTheDocument());

      failing = false;
      fireEvent.click(screen.getByTestId('notification-retry'));
      await waitFor(() => expect(screen.getByTestId('notification-item-1')).toBeInTheDocument());
      expect(screen.queryByTestId('notification-error')).not.toBeInTheDocument();
    });

    it('clears a stale list when an error occurs', async () => {
      let listCall = 0;
      getNotifications.mockImplementation(({ limit } = {}) => {
        if (limit === 1) return Promise.resolve(emptyResponse());
        listCall += 1;
        if (listCall === 1) {
          return Promise.resolve(
            emptyResponse({
              notifications: [makeNotification({ id: 1 })],
              total: 25,
              page: 1,
              pages: 3,
              unread_count: 1,
            })
          );
        }
        return Promise.reject(new Error('boom'));
      });
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-item-1')).toBeInTheDocument());

      fireEvent.click(screen.getByTestId('page-next'));
      await waitFor(() => expect(screen.getByTestId('notification-error')).toBeInTheDocument());
      expect(screen.queryByTestId('notification-item-1')).not.toBeInTheDocument();
    });
  });

  describe('panel behaviour', () => {
    it('closes when clicking outside', async () => {
      getNotifications.mockResolvedValue(
        emptyResponse({ notifications: [makeNotification({ id: 1 })], total: 1, pages: 1 })
      );
      render(
        <div>
          <NotificationBell />
          <button type="button" data-testid="outside">elsewhere</button>
        </div>
      );
      await openPanel();
      fireEvent.mouseDown(screen.getByTestId('outside'));
      await waitFor(() =>
        expect(screen.queryByTestId('notification-panel')).not.toBeInTheDocument()
      );
    });

    it('closes on Escape', async () => {
      render(<NotificationBell />);
      await openPanel();
      fireEvent.keyDown(document, { key: 'Escape' });
      await waitFor(() =>
        expect(screen.queryByTestId('notification-panel')).not.toBeInTheDocument()
      );
    });

    it('closes via the close button', async () => {
      render(<NotificationBell />);
      await openPanel();
      fireEvent.click(screen.getByTestId('notification-close'));
      await waitFor(() =>
        expect(screen.queryByTestId('notification-panel')).not.toBeInTheDocument()
      );
    });

    it('requests through the shared api module with the expected paging defaults', async () => {
      getNotifications.mockResolvedValue(emptyResponse());
      render(<NotificationBell />);
      await openPanel();
      await waitFor(() => expect(screen.getByTestId('notification-empty')).toBeInTheDocument());
      // The list fetch (limit 10) went through the shared api module, which is
      // the only network layer and therefore the only place auth cookies apply.
      expect(getNotifications.mock.calls[0][0]).toMatchObject({ page: 1, limit: 1 });
      expect(getNotifications.mock.calls[1][0]).toMatchObject({ page: 1, limit: 10 });
    });
  });
});