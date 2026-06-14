import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy API calls to the local backend in dev so VITE_API_URL can stay empty
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
