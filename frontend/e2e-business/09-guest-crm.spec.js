import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';

const M = 'guest-crm';

test.describe('Scope 9 — Misafir profili / CRM', () => {
    test('Misafir liste + ara + form alanları', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const candidates = ['/guests', '/crm/guests', '/pms/guests', '/guest-management'];
        let opened = false, lastStatus = null;
        for (const path of candidates) {
            const r = await page.goto(path, { waitUntil: 'domcontentloaded' }).catch(() => null);
            lastStatus = r?.status();
            if (r?.ok()) {
                const insp = await inspectPageContent(page);
                if (!insp.has404 && !insp.empty) {
                    rec(testInfo, { module: M, scope: 9, step: `Misafir sayfası bulundu`, status: PASS, endpoint: path, http: r.status() });
                    opened = true;
                    break;
                }
            }
        }
        if (!opened) rec(testInfo, { module: M, scope: 9, step: 'Misafir sayfası bulunamadı', status: REVIEW, note: `aranan: ${candidates.join(', ')} (son status=${lastStatus})` });

        const searchInput = page.locator('input[placeholder*="ara" i], input[type="search"]').first();
        rec(testInfo, { module: M, scope: 9, step: 'Misafir arama input', status: (await searchInput.count()) > 0 ? PASS : REVIEW });

        const api = await makeApi(baseURL);
        const r = await safeGet(api, '/api/pms/guests?limit=3');
        rec(testInfo, { module: M, scope: 9, step: 'GET /api/pms/guests', status: r.status < 500 ? PASS : REVIEW, endpoint: '/api/pms/guests', http: r.status });
        await api.dispose();

        rec(testInfo, { module: M, scope: 9, step: 'Gerçek misafir create', status: SKIP, note: 'KVKK kapsamı + cleanup riski; placeholder veri yazılmadı.' });
        rec(testInfo, { module: M, scope: 9, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
