// ─────────────────────────────────────────────────────────────────────────
// Playwright config — UI E2E SMOKE suite
// ─────────────────────────────────────────────────────────────────────────
// Mevcut `playwright.config.js` (core PMS happy-path) ile karışmasın diye
// ayrı config + ayrı testDir (`e2e-smoke/`).
//
// Çalıştırma:
//   E2E_BASE_URL=https://app.example.com \
//   E2E_ADMIN_EMAIL=admin@... \
//   E2E_ADMIN_PASSWORD=... \
//   yarn test:e2e:smoke
//
// Çıktı:
//   - HTML report:  frontend/playwright-smoke-report/
//   - Markdown:     docs/drill_reports/YYYYMMDD_ui_e2e_smoke.md
//   - Trace/video/screenshot: frontend/test-results-smoke/
// ─────────────────────────────────────────────────────────────────────────

import { defineConfig, devices } from '@playwright/test';

// Fail-fast: env eksikse anında hata. Hardcoded fallback YOK — yanlış
// ortama (localhost) sessizce smoke koşmasını engeller.
const BASE_URL = process.env.E2E_BASE_URL;
if (!BASE_URL) {
    throw new Error(
        '[smoke] E2E_BASE_URL env-var zorunlu. Komut: ' +
        'E2E_BASE_URL=https://app.example.com E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... yarn test:e2e:smoke'
    );
}

export default defineConfig({
    testDir: './e2e-smoke',
    timeout: 60_000,
    expect: { timeout: 10_000 },
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,
    workers: 1,
    reporter: [
        ['list'],
        ['html', { open: 'never', outputFolder: 'playwright-smoke-report' }],
        ['./e2e-smoke/markdown-reporter.mjs'],
    ],
    outputDir: 'test-results-smoke',
    use: {
        baseURL: BASE_URL,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
        ignoreHTTPSErrors: true,
        locale: 'tr-TR',
        timezoneId: 'Europe/Istanbul',
    },
    projects: [
        {
            name: 'desktop',
            use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
        },
        {
            name: 'mobile',
            use: { ...devices['Pixel 7'] },
        },
    ],
});
