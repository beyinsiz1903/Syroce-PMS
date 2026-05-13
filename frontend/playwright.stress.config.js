// F7 — Stress E2E Scaffold (Playwright config)
//
// Bu suite stress tenant (E2E_STRESS_TENANT_ID) üzerinde 500-oda dataset ile çalışır.
// global-setup: stress admin login + gate verify + POST /api/admin/stress/seed (n=500)
// global-teardown: POST /api/admin/stress/cleanup (prefix-scoped, idempotent)
//
// Pilot tenant'a yazma yok. external_calls_made=[] zorunlu.
// `E2E_ALLOW_DESTRUCTIVE_STRESS=true` + `E2E_EXTERNAL_DRY_RUN=true` olmadan globalSetup gate'ten döner.

import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL;
if (!BASE_URL || !/^https?:\/\//i.test(BASE_URL)) {
    throw new Error('[playwright.stress.config] E2E_BASE_URL eksik veya geçersiz.');
}

const REQUIRED = [
    'E2E_STRESS_ADMIN_EMAIL',
    'E2E_STRESS_ADMIN_PASSWORD',
    'E2E_STRESS_TENANT_ID',
];
const missing = REQUIRED.filter((k) => !process.env[k]);
if (missing.length) {
    throw new Error(`[playwright.stress.config] Missing env: ${missing.join(', ')}`);
}

export default defineConfig({
    testDir: './e2e-stress/specs',
    timeout: 180_000,
    expect: { timeout: 15_000 },
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: 0,
    workers: 1,
    globalSetup: './e2e-stress/global-setup.js',
    globalTeardown: './e2e-stress/global-teardown.js',
    reporter: [
        ['list'],
        ['html', { open: 'never', outputFolder: 'playwright-stress-report' }],
        ['./e2e-stress/markdown-reporter.mjs'],
    ],
    outputDir: 'test-results-stress',
    use: {
        baseURL: BASE_URL,
        ignoreHTTPSErrors: true,
        screenshot: 'only-on-failure',
        trace: 'retain-on-failure',
        video: 'retain-on-failure',
    },
    projects: [
        {
            name: 'stress',
            use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
        },
    ],
});
