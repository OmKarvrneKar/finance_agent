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
