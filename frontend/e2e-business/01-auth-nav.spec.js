import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'auth-nav';

test.describe('Scope 1 — Login & temel gezinme', () => {
    test('Dashboard açılır + sidebar/profil çalışır', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const resp = await page.goto('/', { waitUntil: 'domcontentloaded' });
        rec(testInfo, { module: M, scope: 1, step: 'GET /', status: resp?.ok() ? PASS : FAIL, endpoint: '/', http: resp?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 1, step: 'Dashboard içerik', status: insp.empty || insp.has404 || insp.has500 ? FAIL : PASS, note: `len=${insp.lengthChars}` });

        // Sidebar nav links — herhangi bir nav linki görünür mü?
        const navLinks = page.locator('nav a, [role="navigation"] a, aside a');
        const linkCount = await navLinks.count().catch(() => 0);
        rec(testInfo, { module: M, scope: 1, step: 'Sidebar nav linkleri', status: linkCount >= 3 ? PASS : REVIEW, note: `count=${linkCount}` });

        // Profil/avatar/logout menü tetikleyici
        const profileTrigger = page.locator('[data-testid*="profile"], [aria-label*="profil" i], button:has-text("çıkış")').first();
        rec(testInfo, { module: M, scope: 1, step: 'Profil menü tetikleyici', status: (await profileTrigger.count()) > 0 ? PASS : REVIEW });

        rec(testInfo, { module: M, scope: 1, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
        rec(testInfo, { module: M, scope: 1, step: 'Network 4xx/5xx', status: obs.networkErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.networkErrors.length}` });
        expect(insp.empty || insp.has500).toBeFalsy();
    });

    test('Yanlış şifre — login fail davranışı', async ({ browser }, testInfo) => {
        // Yeni izole context (storageState YOK)
        const ctx = await browser.newContext({ baseURL: process.env.E2E_BASE_URL, ignoreHTTPSErrors: true });
        const page = await ctx.newPage();
        await page.goto('/login');
        await page.locator('[data-testid="hotel-login-email"]').fill(process.env.E2E_ADMIN_EMAIL);
        await page.locator('[data-testid="hotel-login-password"]').fill('YANLIS_SIFRE_E2E_!');
        const respPromise = page.waitForResponse((r) => /\/(api\/)?auth\/login/.test(r.url()), { timeout: 15_000 }).catch(() => null);
        await page.locator('[data-testid="hotel-login-btn"]').click();
        const resp = await respPromise;
        const status = resp?.status() ?? 0;
        rec(testInfo, { module: M, scope: 1, step: 'Yanlış şifre 4xx döner', status: status >= 400 && status < 500 ? PASS : REVIEW, endpoint: '/auth/login', http: status });
        const errorVisible = await page.locator('text=/(hatal[ıi]|invalid|incorrect|yanl[ıi][şs])/i').first().isVisible({ timeout: 5_000 }).catch(() => false);
        rec(testInfo, { module: M, scope: 1, step: 'Hata mesajı UI', status: errorVisible ? PASS : REVIEW });
        await ctx.close();
    });

    test('Session refresh — sayfa yenileme sonrası oturum korunur', async ({ page }, testInfo) => {
        await page.goto('/');
        await page.reload({ waitUntil: 'domcontentloaded' });
        const url = new URL(page.url());
        const onLogin = /\/login/.test(url.pathname);
        rec(testInfo, { module: M, scope: 1, step: 'Reload sonrası login\'e atılma', status: onLogin ? FAIL : PASS, note: url.pathname });
        expect(onLogin).toBeFalsy();
    });
});
