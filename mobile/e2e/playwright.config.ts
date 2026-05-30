// ─────────────────────────────────────────────────────────────────────────
// F10A — Playwright config for mobile Expo Web smoke matrix.
// ─────────────────────────────────────────────────────────────────────────
// Why Playwright on Expo Web (decision recorded in F10_MOBILE_COVERAGE_ROADMAP.md §6):
//   - Linux-runnable CI (no Mac/Android emulator needed for first smoke).
//   - Reuses PII / console-error patterns from `frontend/e2e-smoke`.
//   - `mobile/.maestro/` already covers deep native flows (login, biometric,
//     offline) for future F10B+ — not duplicated here.
//
// Run locally:
//   cd mobile
//   MOBILE_E2E_BASE_URL=http://localhost:8081 \
//   MOBILE_E2E_FRONTDESK_EMAIL=... MOBILE_E2E_FRONTDESK_PASSWORD=... \
//   MOBILE_E2E_GM_EMAIL=... MOBILE_E2E_GM_PASSWORD=... \
//   MOBILE_E2E_HK_EMAIL=... MOBILE_E2E_HK_PASSWORD=... \
//   MOBILE_E2E_GUEST_EMAIL=... MOBILE_E2E_GUEST_PASSWORD=... \
//   npx playwright test --config=e2e/playwright.config.ts
// ─────────────────────────────────────────────────────────────────────────

import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.MOBILE_E2E_BASE_URL;
if (!BASE_URL) {
    throw new Error(
        '[mobile-smoke] MOBILE_E2E_BASE_URL env-var zorunlu. ' +
        'Expo Web bundle URL (ör. http://localhost:8081). ' +
        'Detay: mobile/e2e/README.md',
    );
}

export default defineConfig({
    testDir: '.',
    testMatch: /smoke\.spec\.ts$/,
    timeout: 60_000,
    expect: { timeout: 10_000 },
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,
    workers: 1,
    reporter: [
        ['list'],
        ['html', { open: 'never', outputFolder: 'playwright-mobile-smoke-report' }],
        ['json', { outputFile: 'playwright-mobile-smoke-report/results.json' }],
        // F10A drill-report (markdown) → docs/drill_reports/YYYYMMDD_f10a_mobile_smoke.md
        ['./markdown-reporter.mjs'],
    ],
    outputDir: 'test-results-mobile-smoke',
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
            name: 'mobile-pixel7',
            use: { ...devices['Pixel 7'] },
        },
    ],
});
