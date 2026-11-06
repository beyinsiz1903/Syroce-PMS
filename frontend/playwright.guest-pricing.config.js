import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-local', testMatch: 'guest-pricing.spec.js', workers: 1, retries: 0,
  outputDir: 'test-results/guest-pricing', reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5212', locale: 'tr-TR', screenshot: 'only-on-failure',
    // Optional already-installed browser for offline developer environments.
    launchOptions: process.env.GUEST_PRICING_BROWSER ? { executablePath: process.env.GUEST_PRICING_BROWSER } : {},
  },
  webServer: {
    command: 'npm run start -- --host 127.0.0.1 --port 5212 --strictPort',
    url: 'http://127.0.0.1:5212/e2e-local/guest-pricing.html', reuseExistingServer: false,
  },
});
