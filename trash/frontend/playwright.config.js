// Playwright config for PaperFull E2E tests.
// Pointed at local PM2 instance: frontend on :8000, backend on :8001 via proxy.
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 600_000, // 10 minutes for complete workflow test
  expect: { timeout: 10_000 },
  fullyParallel: false, // shared DB between tests
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'playwright-report/results.json' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'workflow-with-video',
      testMatch: '**/complete-workflow.spec.js',
      use: {
        ...devices['Desktop Chrome'],
        video: 'on',
        trace: 'on',
        screenshot: 'on',
      },
    },
    {
      name: 'cs-student-iot',
      testMatch: '**/cs-student-iot.spec.js',
      use: {
        ...devices['Desktop Chrome'],
        video: 'on',
        trace: 'on',
        screenshot: 'on',
        headless: true,
      },
    },
  ],
});
