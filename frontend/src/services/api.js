import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

// System Status
export const getStatus = async () => {
  const response = await api.get('/status');
  return response.data;
};

// Strategies
export const getStrategies = async () => {
  const response = await api.get('/strategies');
  return response.data;
};

export const toggleStrategy = async (strategyId) => {
  const response = await api.post(`/strategies/${strategyId}/toggle`);
  return response.data;
};

export const startStrategy = async (strategyId) => {
  const response = await api.post(`/strategies/${strategyId}/start`);
  return response.data;
};

export const stopStrategy = async (strategyId) => {
  const response = await api.post(`/strategies/${strategyId}/stop`);
  return response.data;
};

// Capital Allocation
export const getCapital = async () => {
  const response = await api.get('/capital');
  return response.data;
};

// Performance Metrics
export const getPerformance = async () => {
  const response = await api.get('/performance');
  return response.data;
};

// Risk Metrics
export const getRisk = async () => {
  const response = await api.get('/risk');
  return response.data;
};

// Equity History
export const getHistory = async () => {
  const response = await api.get('/history');
  return response.data;
};

// Logs
export const getLogs = async () => {
  const response = await api.get('/logs');
  return response.data;
};

export default api;