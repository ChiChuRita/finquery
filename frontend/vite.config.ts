import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    // The chart runtime is a second page: charts render inside a sandboxed iframe, so their
    // React and TanStack Charts code never shares a window with the app.
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        'chart-runtime': path.resolve(__dirname, 'chart-runtime.html'),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
