import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    coverage: {
      reporter: ['text', 'lcov'],
      include: ['src/components/**', 'src/stores/**'],
      exclude: ['**/node_modules/**', 'dist/**'],
    },
    css: false,
    include: ['tests/**/*.{spec,test}.{js,ts}'],
  },
})
