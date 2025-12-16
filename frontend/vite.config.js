import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// REPLACE THIS WITH YOUR REAL GCP IP ADDRESS
const REMOTE_SERVER_IP = 'http://104.154.236.199:8080';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: REMOTE_SERVER_IP,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''), // Removes '/api' prefix
        secure: false,
      },
    },
  },
})