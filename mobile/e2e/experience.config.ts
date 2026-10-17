import { defineConfig } from '@playwright/test';

// Isolated UI contracts: every API response is intercepted with synthetic
// fixtures. No credentials, live reservations, email or financial writes.
export default defineConfig({
  testDir: '.',
  testMatch: /(product-experience|guest-requests)\.spec\.ts$/,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: 'list',
  outputDir: '/tmp/syroce-mobile-experience-results',
  use: {
    baseURL: process.env.MOBILE_PREVIEW_URL || 'http://localhost:8086',
    browserName: 'chromium',
    channel: 'chrome',
    viewport: { width: 393, height: 852 },
    locale: 'tr-TR',
    timezoneId: 'Europe/Istanbul',
    screenshot: 'only-on-failure',
  },
});
