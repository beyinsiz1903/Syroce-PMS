// Playwright e2e config — Syroce PMS smoke suite.
// Local dev: vite (5173 / start workflow on different port). Replit'te
// `EXPO_PUBLIC_API_URL` benzeri bir URL kullanmak yerine baseURL'i env ile
// override edilebilir bırakıyoruz.
//
// Çalıştırma:
//   yarn e2e          → headless, CI moduyla aynı
//   yarn e2e:ui       → interactive UI mode
//   E2E_BASE_URL=http://localhost:3000 yarn e2e
//
// Demo creds: hotel_id=100001 / username=demo / password=demo123
// Override: E2E_HOTEL_ID, E2E_USERNAME, E2E_PASSWORD

import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000';

export default defineConfig({
    testDir: './e2e',
    timeout: 60_000,
    expect: { timeout: 10_000 },
    fullyParallel: false, // Auth state shared across specs; sıralı koş
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 1 : 2,
    reporter: process.env.CI
        ? [['html', { open: 'never' }], ['github'], ['list']]
        : [['html', { open: 'never' }], ['list']],
    use: {
        baseURL: BASE_URL,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
        // Replit ortamında self-signed sertifika takılmasın
        ignoreHTTPSErrors: true,
        viewport: { width: 1440, height: 900 },
        locale: 'tr-TR',
        timezoneId: 'Europe/Istanbul',
    },
    projects: [
        {
            name: 'chromium-desktop',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
    // CI'da web server'ı PW başlatmasın — workflow'lar zaten çalışıyor.
    // Local dev'de manuel başlatılır (vite + uvicorn). İstersen aç:
    // webServer: { command: 'yarn start', url: BASE_URL, reuseExistingServer: true, timeout: 120_000 },
});
