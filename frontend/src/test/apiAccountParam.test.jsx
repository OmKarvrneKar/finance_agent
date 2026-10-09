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
import { searchTransactions, getTransactionsExport } from '../utils/api';

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
