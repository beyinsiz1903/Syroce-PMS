import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-local',
  testMatch: 'mice.spec.js',
  outputDir: 'test-results/mice-local',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:19101', trace: 'retain-on-failure', channel: process.env.MICE_BROWSER_CHANNEL || undefined },
  projects: [
    { name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1440, height: 1000 } } },
    { name: 'phone', use: { browserName: 'chromium', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: { command: 'npm run start -- --host 127.0.0.1 --port 19101 --strictPort', url: 'http://127.0.0.1:19101', reuseExistingServer: false },
});
