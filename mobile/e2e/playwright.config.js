// F10A — Playwright config for mobile Expo Web smoke.
// Doctrine: read-only against pilot, fail-closed on missing base URL,
// strict timeout budgets so a hung route doesn't drag the whole suite.

import { defineConfig, devices } from '@playwright/test';

// Fail-closed doctrine: refuse to silently fall back to localhost. CI
// must explicitly set E2E_MOBILE_BASE_URL (pilot deploy URL or the
// Replit Mobile Web workflow URL — see mobile/e2e/README.md).
const BASE_URL = process.env.E2E_MOBILE_BASE_URL;
if (!BASE_URL) {
    throw new Error(
        '[F10A] E2E_MOBILE_BASE_URL is required — refusing to run mobile '
        + 'smoke against an undefined target. Set it to the Expo Web URL '
        + '(e.g. http://localhost:8080 for local Mobile Web workflow, or '
        + 'the deployed pilot Expo Web URL for CI).',
    );
}

export default defineConfig({
    testDir: '.',
    testMatch: /.*\.spec\.js$/,
    timeout: 30_000,
    expect: { timeout: 5_000 },
    forbidOnly: !!process.env.CI,
    fullyParallel: false,
    workers: 1,
    retries: process.env.CI ? 1 : 0,
    reporter: [
        ['list'],
        ['json', { outputFile: 'test-results/mobile-smoke.json' }],
    ],
    use: {
        baseURL: BASE_URL,
        actionTimeout: 10_000,
        navigationTimeout: 15_000,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'off',
        ignoreHTTPSErrors: true,
    },
    projects: [
        {
            name: 'mobile-chromium',
            use: { ...devices['Pixel 7'] },
        },
        {
            name: 'tablet-chromium',
            use: { ...devices['iPad Pro 11'] },
        },
    ],
});
