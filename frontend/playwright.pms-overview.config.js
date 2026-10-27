import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-pms-overview',
  outputDir: 'test-results-pms-overview',
  timeout: 30000,
  workers: 1,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:19083', browserName: 'chromium', channel: process.env.PLAYWRIGHT_CHANNEL || undefined, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: 'npm run start -- --host 127.0.0.1 --port 19083 --strictPort', url: 'http://127.0.0.1:19083', reuseExistingServer: false, timeout: 60000 },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
    { name: 'tablet', use: { ...devices['iPad Pro 11'], defaultBrowserType: 'chromium' } },
    { name: 'phone', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
});
