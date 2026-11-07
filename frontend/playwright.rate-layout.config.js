import base from './playwright.guest-pricing.config';
export default {
  ...base,
  testMatch: 'rate-layout.spec.js',
  outputDir: 'test-results/rate-layout',
  webServer: { ...base.webServer, url: 'http://127.0.0.1:5212/e2e-local/rate-layout.html' },
};
