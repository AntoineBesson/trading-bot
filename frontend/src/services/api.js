import axios from 'axios';

const api = axios.create({
  baseURL: '/api', // Points to the Vite proxy configured above
  headers: {
    'Content-Type': 'application/json',
  },
});

// Define your endpoints here
export const getStatus = () => api.get('/status');

// We will add more later (getStrategies, toggleStrategy, etc.)
export default api;