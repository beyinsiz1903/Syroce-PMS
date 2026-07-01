import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'settings';

test.describe('Scope 16 — Ayarlar', () => {
    test('Settings ana sayfa + sekmeler', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/settings', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 16, step: 'Settings navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/settings', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 16, step: 'İçerik', status: insp.empty || insp.has500 ? REVIEW : PASS, note: `len=${insp.lengthChars}` });

        for (const t of ['Otel', 'Vergi', 'Para Birimi', 'Saat Dilimi', 'Dil', 'Logo']) {
            const c = await page.locator(`text=/${t}/i`).count();
            rec(testInfo, { module: M, scope: 16, step: `Sekme/alan: ${t}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }
        const saveBtn = await page.locator('button:has-text("Kaydet"), button:has-text("Güncelle")').count();
        rec(testInfo, { module: M, scope: 16, step: 'Kaydet butonu görünür', status: saveBtn > 0 ? PASS : REVIEW, note: `count=${saveBtn}` });

        rec(testInfo, { module: M, scope: 16, step: 'Gerçek ayar mutation', status: SKIP, note: 'Pilot tenant ayarları değiştirilmedi.' });
        rec(testInfo, { module: M, scope: 16, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
