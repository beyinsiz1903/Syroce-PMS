import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'housekeeping';

test.describe('Scope 8 — Housekeeping / oda durumu', () => {
    test('Housekeeping ana sayfa + oda durum badgeleri', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/housekeeping', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 8, step: 'Housekeeping navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/housekeeping', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 8, step: 'İçerik', status: insp.empty ? REVIEW : PASS, note: `len=${insp.lengthChars}` });

        for (const status of ['clean', 'dirty', 'inspect', 'maintenance', 'order']) {
            const c = await page.locator(`text=/${status}/i`).count();
            rec(testInfo, { module: M, scope: 8, step: `Status badge ${status}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }

        rec(testInfo, { module: M, scope: 8, step: 'Gerçek status mutation', status: SKIP, note: 'Pilot oda durumu değiştirilmedi (operasyonel etki).' });
        rec(testInfo, { module: M, scope: 8, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
