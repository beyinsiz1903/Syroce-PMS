import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'checkin-checkout';

test.describe('Scope 4 — Check-in / Check-out', () => {
    test('Front Desk / PMS sayfası check-in akışı keşfi', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/pms', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 4, step: 'PMS navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/pms', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 4, step: 'PMS içerik', status: insp.empty ? REVIEW : PASS, note: `len=${insp.lengthChars}` });

        const ciBtn = await page.locator('button:has-text("Check-in"), button:has-text("Giriş Yap")').count();
        const coBtn = await page.locator('button:has-text("Check-out"), button:has-text("Çıkış Yap")').count();
        rec(testInfo, { module: M, scope: 4, step: 'Check-in butonları görünür', status: ciBtn > 0 ? PASS : REVIEW, note: `count=${ciBtn}` });
        rec(testInfo, { module: M, scope: 4, step: 'Check-out butonları görünür', status: coBtn > 0 ? PASS : REVIEW, note: `count=${coBtn}` });

        rec(testInfo, { module: M, scope: 4, step: 'Gerçek check-in/out tetikleme', status: SKIP, note: 'Pilot dataset stabilitesi için destructive state geçişi yapılmadı; canlı drill\'de manuel doğrulama önerilir.' });
        rec(testInfo, { module: M, scope: 4, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
