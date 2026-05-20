import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    allowedHosts: ['paper.otomasi.app'],
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        proxyTimeout: 0,
        timeout: 0
      }
    }
  },
  preview: {
    allowedHosts: ['paper.otomasi.app']
  }
})
