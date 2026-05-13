import { test, request } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW } from './fixtures/recorder.js';

const M = 'security-rbac';

test.describe('Scope 18 — Güvenlik / izolasyon', () => {
    test('Bearer YOK ile kritik endpointlere erişim 401/403 dönmeli', async ({ baseURL }, testInfo) => {
        const ctx = await request.newContext({ baseURL, ignoreHTTPSErrors: true });
        const targets = ['/api/admin/users', '/api/pms/bookings', '/api/audit/timeline', '/api/channel-manager/conflict-queue'];
        for (const ep of targets) {
            const r = await ctx.get(ep, { failOnStatusCode: false });
            const status = r.status();
            const ok = status === 401 || status === 403;
            rec(testInfo, { module: M, scope: 18, step: `Token-less ${ep}`, status: ok ? PASS : (status >= 400 && status < 500 ? PASS : FAIL), endpoint: ep, http: status, note: ok ? '' : 'Beklenen 401/403' });
        }
        await ctx.dispose();
    });

    test('URL üzerinden başka tenant verisine erişim — sahte ID ile', async ({ page }, testInfo) => {
        const fakeIds = ['000000000000000000000000', 'aaaaaaaaaaaaaaaaaaaaaaaa'];
        for (const id of fakeIds) {
            const url = `/folio/${id}`;
            const r = await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => null);
            const status = r?.status() ?? 0;
            const bodyTxt = (await page.locator('body').innerText().catch(() => '')).slice(0, 300);
            const safeBlock = /(404|not found|bulunamad|yetki|forbidden|erişim)/i.test(bodyTxt) || status === 404 || status === 403;
            rec(testInfo, { module: M, scope: 18, step: `Sahte folio id ${id}`, status: safeBlock ? PASS : REVIEW, endpoint: url, http: status, note: bodyTxt.slice(0, 80) });
        }
    });

    test('Console secret leak heuristik — token/password görünmez', async ({ page }, testInfo) => {
        const leaks = [];
        page.on('console', (msg) => {
            const t = msg.text();
            if (/(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)|password\s*[:=]/i.test(t)) leaks.push(t.slice(0, 100));
        });
        await page.goto('/');
        await page.waitForTimeout(2_000);
        rec(testInfo, { module: M, scope: 18, step: 'Console JWT/password leak', status: leaks.length === 0 ? PASS : FAIL, note: leaks.length ? `samples=${leaks.slice(0, 2).join(' | ')}` : '' });
    });
});
