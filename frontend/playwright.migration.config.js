import { defineConfig, devices } from '@playwright/test';

// Deliberately local + synthetic: never logs into a real property.
export default defineConfig({
  testDir: './e2e-migration',
  outputDir: 'test-results-migration',
  timeout: 30000,
  workers: 1,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:19082', browserName: 'chromium', channel: process.env.PLAYWRIGHT_CHANNEL || undefined, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: 'npm run start -- --host 127.0.0.1 --port 19082 --strictPort', url: 'http://127.0.0.1:19082', reuseExistingServer: false, timeout: 60000 },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'phone', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
    { name: 'tablet', use: { ...devices['iPad Pro 11'], defaultBrowserType: 'chromium' } },
  ],
});
