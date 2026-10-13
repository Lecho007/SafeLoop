import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/evaluations': 'http://127.0.0.1:8712',
      '/runs': 'http://127.0.0.1:8712',
      '/replay': 'http://127.0.0.1:8712',
      '/targets': 'http://127.0.0.1:8712',
    },
  },
  build: { outDir: 'dist', assetsDir: 'assets' },
})
