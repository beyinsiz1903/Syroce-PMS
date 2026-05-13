import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';

const M = 'folio';

test.describe('Scope 5 — Folio', () => {
    test('Folio ana sayfa + masraf/ödeme/refund/void buton keşfi', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/folio', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 5, step: 'Folio navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/folio', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 5, step: 'Folio içerik', status: insp.empty || insp.has500 ? REVIEW : PASS });

        const probes = [
            ['Masraf Ekle', 'Masraf ekle butonu'],
            ['Ödeme', 'Ödeme alanı/butonu'],
            ['Refund', 'Refund butonu'],
            ['Void', 'Void butonu'],
            ['Split', 'Split (folio bölme)'],
            ['Merge', 'Merge (folio birleştirme)'],
        ];
        for (const [text, label] of probes) {
            const c = await page.locator(`text=/${text}/i`).count();
            rec(testInfo, { module: M, scope: 5, step: `${label} mevcut`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }

        // data-testid'li sekmeler (FolioDetailView)
        for (const tab of ['folio-tab-timeline', 'folio-tab-tax', 'folio-tab-splits', 'folio-tab-voids']) {
            const c = await page.locator(`[data-testid="${tab}"]`).count();
            rec(testInfo, { module: M, scope: 5, step: `Tab ${tab}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }

        rec(testInfo, { module: M, scope: 5, step: 'Gerçek refund/void tetikleme', status: SKIP, note: 'Pilot canlı veri üzerinde finansal işlem tetiklenmedi; sandbox\'ta üretilmiş test folio gereklidir (üretim adımı bu suite kapsamı dışı).' });
        rec(testInfo, { module: M, scope: 5, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });

    test('Folio API discovery (read-only)', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        for (const ep of ['/api/pms-core/folio/list?limit=5', '/api/frontdesk/folio/summary']) {
            const r = await safeGet(api, ep);
            rec(testInfo, { module: M, scope: 5, step: `GET ${ep}`, status: r.status < 500 ? PASS : REVIEW, endpoint: ep, http: r.status });
        }
        await api.dispose();
    });
});
