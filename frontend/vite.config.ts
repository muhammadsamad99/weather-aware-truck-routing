/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the API runs on Django (port 8000); in production Django serves this build itself.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    chunkSizeWarningLimit: 1200, // MapLibre alone is ~800 kB
  },
  worker: {
    format: 'es', // MapLibre starts its worker as a module worker
  },
  test: {
    environment: 'jsdom',
  },
})
