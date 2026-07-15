import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default defineConfig({
  plugins: [
    vue(),
    {
      name: 'check-localhost-leak',
      apply: 'build',
      async closeBundle() {
        const fs = await import('fs')
        const path = await import('path')
        const distDir = path.resolve(__dirname, 'dist')
        const checkDir = (dir: string) => {
          for (const file of fs.readdirSync(dir)) {
            const full = path.join(dir, file)
            const stat = fs.statSync(full)
            if (stat.isDirectory()) checkDir(full)
            else if (file.endsWith('.js') || file.endsWith('.css')) {
              const content = fs.readFileSync(full, 'utf-8')
              if (content.includes('localhost:')) {
                const lines = content.split('\n')
                for (let i = 0; i < lines.length; i++) {
                  if (lines[i].includes('localhost:')) {
                    console.error(`\n❌ BUILD FAILED: Found localhost reference in ${full}:${i + 1}`)
                    console.error(lines[i].slice(0, 200))
                    process.exit(1)
                  }
                }
              }
            }
          }
        }
        checkDir(distDir)
      }
    }
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  test: {
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**'],
    passWithNoTests: true
  },
  server: {
    port: 8000,
    allowedHosts: ['paper.otomasi.app', 'paperfull.app', 'www.paperfull.app'],
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
    allowedHosts: ['paper.otomasi.app', 'paperfull.app', 'www.paperfull.app']
  },
  build: {
    target: 'es2020',
    sourcemap: false,
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'markdown': ['marked', 'dompurify'],
          'highlight': ['highlight.js'],
          'katex': ['katex']
        },
        assetFileNames: (assetInfo) => {
          const info = (assetInfo.name ?? '').split('.')
          const ext = info[info.length - 1]
          if (/png|jpe?g|svg|gif|tiff|bmp|ico/i.test(ext)) {
            return `assets/images/[name]-[hash][extname]`
          } else if (/woff2?|ttf|eot/i.test(ext)) {
            return `assets/fonts/[name]-[hash][extname]`
          }
          return `assets/[name]-[hash][extname]`
        },
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
      }
    }
  }
})
