import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8001/api";

const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
});

// Handle 401 responses — redirect to login (cookie is HttpOnly, no localStorage to clean)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Auth
export const loginUser = async (email, password) => {
  const response = await api.post('/auth/login', new URLSearchParams({ username: email, password }), {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return response.data;
};

export const registerUser = async (email, password, fullName) => {
  const response = await api.post('/auth/register', { email, password, full_name: fullName });
  return response.data;
};

export const getMe = async () => {
  const response = await api.get('/auth/me');
  return response.data;
};

export const logoutUser = async () => {
  const response = await api.post('/auth/logout');
  return response.data;
};

// Transactions
export const uploadStatement = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/upload-statement', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const getTransactions = async (page = 1, limit = 10, category = '', type = '') => {
  const params = new URLSearchParams({ page, limit });
  if (category) params.append('category', category);
  if (type) params.append('transaction_type', type);
  const response = await api.get(`/transactions?${params.toString()}`);
  return response.data;
};

export const searchTransactions = async ({ page = 1, limit = 10, q = '', category = '', date_from = '', date_to = '', amount_min = '', amount_max = '', transaction_type = '' } = {}) => {
  const params = new URLSearchParams({ page, limit });
  if (q) params.append('q', q);
  if (category) params.append('category', category);
  if (date_from) params.append('date_from', date_from);
  if (date_to) params.append('date_to', date_to);
  if (amount_min) params.append('amount_min', amount_min);
  if (amount_max) params.append('amount_max', amount_max);
  if (transaction_type) params.append('transaction_type', transaction_type);
  const response = await api.get(`/transactions?${params.toString()}`);
  return response.data;
};

export const getTransactionsExport = async ({ start_date = '', end_date = '', category = '', transaction_type = '', search = '' } = {}) => {
  const params = new URLSearchParams();
  if (start_date) params.append('start_date', start_date);
  if (end_date) params.append('end_date', end_date);
  if (category) params.append('category', category);
  if (transaction_type) params.append('transaction_type', transaction_type);
  if (search) params.append('search', search);
  const qs = params.toString();
  const response = await api.get(`/transactions/export${qs ? '?' + qs : ''}`, { responseType: 'blob' });
  return response;
};

export const getTransaction = async (id) => {
  const response = await api.get(`/transactions/${id}`);
  return response.data;
};

export const updateTransaction = async (id, data) => {
  const response = await api.put(`/transactions/${id}`, data);
  return response.data;
};

export const deleteTransaction = async (id) => {
  const response = await api.delete(`/transactions/${id}`);
  return response.data;
};

// Agent
export const askAgent = async (question) => {
  const response = await api.post('/agent/ask', { question });
  return response.data;
};

export const getAllTransactions = async () => {
  const response = await api.get('/transactions?limit=10000');
  return response.data;
};

// Forecast
export const getForecastSummary = async (month = '') => {
  const params = month ? `?month=${month}` : '';
  const response = await api.get(`/forecast/summary${params}`);
  return response.data;
};

export const getForecastAlerts = async (month = '') => {
  const params = month ? `?month=${month}` : '';
  const response = await api.get(`/forecast/alerts${params}`);
  return response.data;
};

export const getCategoryForecast = async (category, month = '') => {
  const params = month ? `?month=${month}` : '';
  const response = await api.get(`/forecast/category/${encodeURIComponent(category)}${params}`);
  return response.data;
};

export const getImprovedForecast = async (month = '', category = '') => {
  const params = new URLSearchParams();
  if (month) params.set('month', month);
  if (category) params.set('category', category);
  const qs = params.toString();
  const response = await api.get(`/forecast/improved${qs ? '?' + qs : ''}`);
  return response.data;
};

// Health Score
export const getHealthScore = async () => {
  const response = await api.get('/health');
  return response.data;
};

// Budgets
export const getBudgets = async (month = '') => {
  const params = month ? `?month=${month}` : '';
  const response = await api.get(`/budgets${params}`);
  return response.data;
};

export const createUpdateBudget = async (category, monthly_cap) => {
  const response = await api.post('/budgets', { category, monthly_cap });
  return response.data;
};

export const deleteBudget = async (category) => {
  const response = await api.delete(`/budgets/${encodeURIComponent(category)}`);
  return response.data;
};

// Goals
export const getSavingsGoals = async (status = null) => {
  const params = status ? { status } : {};
  const response = await api.get('/goals', { params });
  return response.data;
};

export const getSavingsGoal = async (id) => {
  const response = await api.get(`/goals/${id}`);
  return response.data;
};

export const createSavingsGoal = async (goal) => {
  const response = await api.post('/goals', goal);
  return response.data;
};

export const updateSavingsGoal = async (id, updates) => {
  const response = await api.put(`/goals/${id}`, updates);
  return response.data;
};

export const deleteSavingsGoal = async (id) => {
  const response = await api.delete(`/goals/${id}`);
  return response.data;
};

export const contributeToGoal = async (id, amount) => {
  const response = await api.post(`/goals/${id}/contribute`, { amount });
  return response.data;
};

export const getGoalsSummary = async () => {
  const response = await api.get('/goals/summary');
  return response.data;
};

// Simulate
export const simulateWhatIf = async (simRequest) => {
  const response = await api.post('/simulate', simRequest);
  return response.data;
};

// Receipts
export const uploadReceipt = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/receipts/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return response.data;
};

export const getPendingReceipts = async () => {
  const response = await api.get('/receipts/pending-review');
  return response.data;
};

export const confirmReceipt = async (id, data, force = false) => {
  const response = await api.post(`/receipts/${id}/confirm?force=${force}`, data);
  return response.data;
};

export const discardReceipt = async (id) => {
  const response = await api.post(`/receipts/${id}/discard`);
  return response.data;
};

// Analytics
export const getAnalyticsSummary = async ({ start_date = '', end_date = '' } = {}) => {
  const params = new URLSearchParams();
  if (start_date) params.append('start_date', start_date);
  if (end_date) params.append('end_date', end_date);
  const qs = params.toString();
  const response = await api.get(`/analytics/summary${qs ? '?' + qs : ''}`);
  return response.data;
};

export const getMerchantAnalytics = async ({ start_date = '', end_date = '', limit = 20, search = '' } = {}) => {
  const params = new URLSearchParams();
  if (start_date) params.append('start_date', start_date);
  if (end_date) params.append('end_date', end_date);
  if (limit) params.append('limit', limit);
  if (search) params.append('search', search);
  const qs = params.toString();
  const response = await api.get(`/analytics/merchants${qs ? '?' + qs : ''}`);
  return response.data;
};

export const getSpendingVelocity = async ({ window_days = 3 } = {}) => {
  const params = new URLSearchParams({ window_days: String(window_days) });
  const response = await api.get(`/analytics/spending-velocity?${params.toString()}`);
  return response.data;
};

// Anomalies
export const getAnomalies = async () => {
  const response = await api.get('/anomalies');
  return response.data;
};

export const dismissAnomaly = async (id) => {
  const response = await api.post(`/anomalies/${id}/dismiss`);
  return response.data;
};

export const confirmAnomaly = async (id) => {
  const response = await api.post(`/anomalies/${id}/confirm`);
  return response.data;
};

// Subscriptions / Recurring
export const fetchSubscriptions = async () => {
  const response = await api.get('/subscriptions');
  return response.data;
};

export const markRecurring = async (transactionId) => {
  const response = await api.post(`/transactions/${transactionId}/recurring`);
  return response.data;
};

export const unmarkRecurring = async (transactionId) => {
  const response = await api.delete(`/transactions/${transactionId}/recurring`);
  return response.data;
};

// Savings Recommendations
export const getSavingsRecommendations = async () => {
  const response = await api.get('/savings-recommendations');
  return response.data;
};

// Splits
export const getSplits = async (transactionId) => {
  const response = await api.get(`/transactions/${transactionId}/splits`);
  return response.data;
};

export const getSplitSummary = async (transactionId) => {
  const response = await api.get(`/transactions/${transactionId}/split-summary`);
  return response.data;
};

export const createSplits = async (transactionId, splits) => {
  const response = await api.post(`/transactions/${transactionId}/splits`, splits);
  return response.data;
};

export const updateSplit = async (splitId, data) => {
  const response = await api.put(`/splits/${splitId}`, data);
  return response.data;
};

export const deleteSplit = async (splitId) => {
  const response = await api.delete(`/splits/${splitId}`);
  return response.data;
};

// Notifications
// Read-only + explicit user actions only. Nothing here generates
// notifications; producers run on the backend and are never called on render.
export const getNotifications = async ({ page = 1, limit = 20, unread_only = false, type = '' } = {}) => {
  const params = new URLSearchParams({ page: String(page), limit: String(limit) });
  if (unread_only) params.append('unread_only', 'true');
  if (type) params.append('type', type);
  const response = await api.get(`/notifications?${params.toString()}`);
  return response.data;
};

export const markNotificationRead = async (id) => {
  const response = await api.patch(`/notifications/${id}/read`);
  return response.data;
};

export const markNotificationUnread = async (id) => {
  const response = await api.patch(`/notifications/${id}/unread`);
  return response.data;
};

export const markAllNotificationsRead = async () => {
  const response = await api.patch('/notifications/read-all');
  return response.data;
};

export const deleteNotification = async (id) => {
  const response = await api.delete(`/notifications/${id}`);
  return response.data;
};

// Goal progress analytics (Phase 3I)
// Read-only. All projection math happens on the backend; this component only
// displays what the API returns and never derives a metric itself.
export const getGoalProgress = async () => {
  const response = await api.get('/goals/progress');
  return response.data;
};

export const getGoalProgressDetail = async (id) => {
  const response = await api.get(`/goals/${id}/progress`);
  return response.data;
};

// Recurring Bills Calendar
export const getRecurringCalendar = async ({ start_date = '', end_date = '' } = {}) => {
  const params = new URLSearchParams();
  if (start_date) params.append('start_date', start_date);
  if (end_date) params.append('end_date', end_date);
  const qs = params.toString();
  const response = await api.get(`/recurring/calendar${qs ? '?' + qs : ''}`);
  return response.data;
};
