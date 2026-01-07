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

export const killStrategy = async (strategyId) => {
  const response = await api.post(`/strategies/${strategyId}/kill`);
  return response.data;
};

export const killAllStrategies = async () => {
  const response = await api.post('/emergency/kill-all');
  return response.data;
};

// Capital Allocation
export const getCapital = async () => {
  const response = await api.get('/capital');
  return response.data;
};

// Allocations (detailed)
export const getAllocations = async () => {
  const response = await api.get('/allocations');
  return response.data;
};

export const updateAllocation = async (strategyId, equity, leverage) => {
  const response = await api.put(`/allocations/${strategyId}`, { equity, leverage });
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

export const getRiskLimits = async () => {
  const response = await api.get('/risk/limits');
  return response.data;
};

export const updateRiskLimits = async (limits) => {
  const response = await api.put('/risk/limits', limits);
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

// Monte Carlo
export const getMonteCarlo = async (forceRefresh = false) => {
  const response = await api.get('/montecarlo', { params: { force_refresh: forceRefresh } });
  return response.data;
};

export const updateMonteCarloSettings = async (intervalHours) => {
  const response = await api.put('/montecarlo/settings', null, { params: { interval_hours: intervalHours } });
  return response.data;
};

// Positions (for heatmap)
export const getPositions = async () => {
  const response = await api.get('/positions');
  return response.data;
};

export default api;