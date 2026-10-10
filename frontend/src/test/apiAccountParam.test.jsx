import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('axios', () => {
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  };
  return { default: { create: vi.fn(() => instance) } };
});

import axios from 'axios';
import { searchTransactions, getTransactionsExport, fetchSubscriptions, getRecurringCalendar, getSavingsRecommendations } from '../utils/api';

const api = axios.create();

const lastUrl = () => api.get.mock.calls[api.get.mock.calls.length - 1][0];

describe('account_id query parameter construction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { transactions: [], total: 0 } });
  });

  it('searchTransactions omits account_id when All Accounts is selected', async () => {
    await searchTransactions({ account_id: '' });
    expect(lastUrl()).not.toContain('account_id');
  });

  it('searchTransactions includes account_id when a specific account is selected', async () => {
    await searchTransactions({ account_id: '5' });
    expect(lastUrl()).toContain('account_id=5');
  });

  it('searchTransactions combines account_id with other filters', async () => {
    await searchTransactions({ account_id: '3', category: 'Groceries', page: 2 });
    const url = lastUrl();
    expect(url).toContain('account_id=3');
    expect(url).toContain('category=Groceries');
    expect(url).toContain('page=2');
  });

  it('getTransactionsExport omits account_id when All Accounts is selected', async () => {
    api.get.mockResolvedValue({ data: new Blob(), headers: {} });
    await getTransactionsExport({ account_id: '' });
    expect(lastUrl()).not.toContain('account_id');
  });

  it('getTransactionsExport includes account_id when a specific account is selected', async () => {
    api.get.mockResolvedValue({ data: new Blob(), headers: {} });
    await getTransactionsExport({ account_id: '7', search: 'coffee' });
    const url = lastUrl();
    expect(url).toContain('account_id=7');
    expect(url).toContain('search=coffee');
  });
});

describe('search and date-range query parameter construction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { transactions: [], total: 0 } });
  });

  it('searchTransactions sends backend search param instead of q', async () => {
    await searchTransactions({ q: 'coffee' });
    const url = lastUrl();
    expect(url).toContain('search=coffee');
    expect(url).not.toMatch(/[?&]q=/);
  });

  it('searchTransactions sends start_date/end_date instead of date_from/date_to', async () => {
    await searchTransactions({ date_from: '2026-07-01', date_to: '2026-07-31' });
    const url = lastUrl();
    expect(url).toContain('start_date=2026-07-01');
    expect(url).toContain('end_date=2026-07-31');
    expect(url).not.toContain('date_from');
    expect(url).not.toContain('date_to');
  });

  it('searchTransactions combines search, dates, account, and category with backend param names', async () => {
    await searchTransactions({
      q: 'coffee',
      date_from: '2026-07-01',
      date_to: '2026-07-31',
      account_id: '5',
      category: 'Groceries',
    });
    const url = lastUrl();
    expect(url).toContain('search=coffee');
    expect(url).toContain('start_date=2026-07-01');
    expect(url).toContain('end_date=2026-07-31');
    expect(url).toContain('account_id=5');
    expect(url).toContain('category=Groceries');
    expect(url).not.toMatch(/[?&]q=/);
    expect(url).not.toContain('date_from');
    expect(url).not.toContain('date_to');
  });

  it('searchTransactions omits search and date params when empty', async () => {
    await searchTransactions({});
    const url = lastUrl();
    expect(url).not.toContain('search=');
    expect(url).not.toContain('start_date');
    expect(url).not.toContain('end_date');
    expect(url).toContain('page=1');
    expect(url).toContain('limit=10');
  });

  it('getTransactionsExport keeps start_date/end_date/search param names', async () => {
    api.get.mockResolvedValue({ data: new Blob(), headers: {} });
    await getTransactionsExport({
      start_date: '2026-07-01',
      end_date: '2026-07-31',
      search: 'coffee',
    });
    const url = lastUrl();
    expect(url).toContain('start_date=2026-07-01');
    expect(url).toContain('end_date=2026-07-31');
    expect(url).toContain('search=coffee');
  });
});

describe('account_id on subscriptions and recurring calendar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: [] });
  });

  it('fetchSubscriptions omits account_id for All Accounts', async () => {
    await fetchSubscriptions();
    expect(lastUrl()).toBe('/subscriptions');
  });

  it('fetchSubscriptions includes account_id when an account is selected', async () => {
    await fetchSubscriptions('7');
    expect(lastUrl()).toBe('/subscriptions?account_id=7');
  });

  it('getRecurringCalendar omits account_id when no account is selected', async () => {
    api.get.mockResolvedValue({ data: { bills: [] } });
    await getRecurringCalendar({ start_date: '2026-09-15', end_date: '2026-10-15' });
    const url = lastUrl();
    expect(url).toContain('/recurring/calendar?');
    expect(url).toContain('start_date=2026-09-15');
    expect(url).toContain('end_date=2026-10-15');
    expect(url).not.toContain('account_id');
  });

  it('getRecurringCalendar combines account_id with the date range', async () => {
    api.get.mockResolvedValue({ data: { bills: [] } });
    await getRecurringCalendar({ start_date: '2026-09-15', end_date: '2026-10-15', account_id: 4 });
    const url = lastUrl();
    expect(url).toContain('start_date=2026-09-15');
    expect(url).toContain('end_date=2026-10-15');
    expect(url).toContain('account_id=4');
  });
});

describe('account_id on savings recommendations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { recommendations: [] } });
  });

  it('getSavingsRecommendations omits account_id for All Accounts', async () => {
    await getSavingsRecommendations();
    expect(lastUrl()).toBe('/savings-recommendations');
  });

  it('getSavingsRecommendations includes account_id when an account is selected', async () => {
    await getSavingsRecommendations(7);
    expect(lastUrl()).toBe('/savings-recommendations?account_id=7');
  });
});
