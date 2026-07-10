import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8001/api";

const api = axios.create({
  baseURL: BASE_URL,
});

export const fetchSubscriptions = async () => {
  const response = await api.get('/subscriptions');
  return response.data;
};

export const uploadStatement = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/upload-statement', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
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

export const askAgent = async (question) => {
  const response = await api.post('/agent/ask', { question });
  return response.data;
};

export const getAllTransactions = async () => {
  // Fetch up to 10000 transactions for the dashboard
  const response = await api.get('/transactions?limit=10000');
  return response.data;
};

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

export const getSavingsGoals = async () => {
  const response = await api.get('/goals');
  return response.data;
};

export const createSavingsGoal = async (goal) => {
  const response = await api.post('/goals', goal);
  return response.data;
};

export const simulateWhatIf = async (simRequest) => {
  const response = await api.post('/simulate', simRequest);
  return response.data;
};

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
