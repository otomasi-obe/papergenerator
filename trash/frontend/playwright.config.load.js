import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e/load',
  timeout: 300_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 10,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report-load' }],
    ['json', { outputFile: 'load-test-results.json' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
