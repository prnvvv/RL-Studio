import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin API during development (leave VITE_API_BASE_URL empty), including the WebSocket stream.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', ws: true, changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    env: {
      // Keep API assertions relative regardless of a local .env override.
      VITE_API_BASE_URL: '',
    },
  },
})
