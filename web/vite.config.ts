import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  // GitHub Pages serves this as a project site under
  // /train-tracker-query-web/, not the origin root -- asset URLs 404 once
  // deployed without this. Only applied at build time so `vite`/`vite
  // preview` (dev/local) keep serving from `/`.
  base: command === 'build' ? '/train-tracker-query-web/' : '/',
}))
