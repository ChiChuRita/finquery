import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

/**
 * Let the sandboxed chart runtime load its modules while developing.
 *
 * Charts render inside `sandbox="allow-scripts"`, so that document has an opaque origin and
 * sends `Origin: null` for every module it imports. The built app answers this in FastAPI
 * (`finquery.app.create_app`); the dev server, which refuses unknown origins on purpose, needs
 * the same allowance for that one origin.
 */
const sandboxedFrameCors = (): Plugin => ({
  name: 'finquery-sandboxed-frame-cors',
  apply: 'serve',
  configureServer(server) {
    server.middlewares.use((request, response, next) => {
      if (request.headers.origin === 'null') response.setHeader('access-control-allow-origin', 'null')
      next()
    })
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), sandboxedFrameCors()],
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
