import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL;
if (!BASE_URL || !/^https?:\/\//i.test(BASE_URL)) {
    throw new Error('[playwright.business.config] E2E_BASE_URL eksik veya geçersiz. Pilot URL gerekli.');
}
if (!process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD) {
    throw new Error('[playwright.business.config] E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD secret olarak set edilmeli.');
}

const desktop = {
    name: 'desktop',
    use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
};
const tablet = {
    name: 'tablet',
    use: { ...devices['iPad (gen 7)'] },
};
const mobile = {
    name: 'mobile',
    use: { ...devices['Pixel 7'] },
};

const ENABLED_PROJECTS = (process.env.E2E_BUSINESS_PROJECTS || 'desktop')
    .split(',')
    .map((p) => p.trim().toLowerCase())
    .filter(Boolean);
const ALL = { desktop, tablet, mobile };
const projects = ENABLED_PROJECTS.map((p) => ALL[p]).filter(Boolean);
if (projects.length === 0) projects.push(desktop);

export default defineConfig({
    testDir: './e2e-business',
    timeout: 90_000,
    expect: { timeout: 12_000 },
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: 0,
    workers: 1,
    globalSetup: './e2e-business/global-setup.js',
    reporter: [
        ['list'],
        ['html', { open: 'never', outputFolder: 'playwright-business-report' }],
        ['./e2e-business/markdown-reporter.mjs'],
    ],
    outputDir: 'test-results-business',
    use: {
        baseURL: BASE_URL,
        ignoreHTTPSErrors: true,
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
        trace: 'retain-on-failure',
        actionTimeout: 15_000,
        navigationTimeout: 30_000,
        storageState: 'e2e-business/.auth/admin.json',
        extraHTTPHeaders: {
            'Origin': BASE_URL,
            'Referer': BASE_URL
        }
    },
    projects,
});
