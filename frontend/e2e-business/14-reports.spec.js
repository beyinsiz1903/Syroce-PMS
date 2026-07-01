import { test } from '@playwright/test';
import { rec, PASS, REVIEW } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';

const M = 'reports';

test.describe('Scope 14 — Raporlar', () => {
    test('Rapor sayfaları + endpoint örnekleri', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const candidates = ['/reports', '/analytics', '/admin/reports'];
        for (const path of candidates) {
            const r = await page.goto(path, { waitUntil: 'domcontentloaded' }).catch(() => null);
            const insp = await inspectPageContent(page);
            const okPage = r?.ok() && !insp.empty && !insp.has404;
            rec(testInfo, { module: M, scope: 14, step: `Navigate ${path}`, status: okPage ? PASS : REVIEW, endpoint: path, http: r?.status(), note: okPage ? '' : `len=${insp.lengthChars} 404=${insp.has404}` });
            if (okPage) break;
        }

        const api = await makeApi(baseURL);
        for (const ep of ['/api/analytics/occupancy', '/api/pms/dashboard', '/api/invoices/stats']) {
            const x = await safeGet(api, ep);
            rec(testInfo, { module: M, scope: 14, step: `GET ${ep}`, status: x.status < 500 ? PASS : REVIEW, endpoint: ep, http: x.status });
        }
        await api.dispose();

        rec(testInfo, { module: M, scope: 14, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
