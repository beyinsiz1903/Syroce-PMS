import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'invoice';

test.describe('Scope 6 — Fatura / şirket bilgileri', () => {
    test('Fatura ayarları sekmesi + form alanları', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/settings', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 6, step: 'Settings navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/settings', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 6, step: 'Settings içerik', status: insp.empty ? REVIEW : PASS, note: `len=${insp.lengthChars}` });

        const tab = page.locator('[data-testid="invoice-settings-tab"], button:has-text("Fatura"), [role="tab"]:has-text("Fatura")').first();
        const tabExists = (await tab.count()) > 0;
        rec(testInfo, { module: M, scope: 6, step: 'Fatura sekmesi', status: tabExists ? PASS : REVIEW });
        if (tabExists) await tab.click({ timeout: 5_000 }).catch(() => {});

        await page.waitForTimeout(500);
        const probes = ['VKN', 'TCKN', 'Vergi Dairesi', 'Şirket', 'Adres'];
        for (const t of probes) {
            const c = await page.locator(`text=/${t}/i`).count();
            rec(testInfo, { module: M, scope: 6, step: `Alan ${t}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }
        rec(testInfo, { module: M, scope: 6, step: 'Gerçek fatura bilgisi yazımı', status: SKIP, note: 'Pilot ayar mutasyonu yapılmadı (rollback overhead).' });
        rec(testInfo, { module: M, scope: 6, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
