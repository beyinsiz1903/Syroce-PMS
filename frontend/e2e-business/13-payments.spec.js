import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'payments';

test.describe('Scope 13 — Ödemeler', () => {
    test('Folio ödeme kontrolleri (UI keşfi)', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/folio', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 13, step: 'Folio navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/folio', http: r?.status() });
        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 13, step: 'İçerik', status: insp.empty || insp.has500 ? REVIEW : PASS });

        for (const t of ['Nakit', 'Kart', 'Havale', 'Ödeme', 'Refund']) {
            const c = await page.locator(`text=/${t}/i`).count();
            rec(testInfo, { module: M, scope: 13, step: `Method/aksiyon: ${t}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }

        rec(testInfo, { module: M, scope: 13, step: 'Gerçek payment gateway çağrısı', status: SKIP, note: 'External — sandbox gerekli; pilot\'ta tetiklenmedi.' });
        rec(testInfo, { module: M, scope: 13, step: 'Negatif tutar / fazla ödeme validation', status: REVIEW, note: 'Form simülasyonu için açık folio gerekli — ön koşul karşılanmadı.' });
        rec(testInfo, { module: M, scope: 13, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
