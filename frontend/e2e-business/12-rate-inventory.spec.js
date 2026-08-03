import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'rate-inventory';

test.describe('Scope 12 — Rate / Inventory / Availability', () => {
    test('Unified Rate Manager + availability grid', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const candidates = ['/channels?tab=unified-rate-manager', '/rate-manager', '/channels'];
        let opened = false;
        for (const path of candidates) {
            const r = await page.goto(path, { waitUntil: 'networkidle' }).catch(() => null);
            const insp = await inspectPageContent(page);
            if (r?.ok() && !insp.empty && !insp.has500) {
                rec(testInfo, { module: M, scope: 12, step: `Rate manager bulundu`, status: PASS, endpoint: path, http: r.status() });
                opened = true;
                break;
            }
        }
        if (!opened) rec(testInfo, { module: M, scope: 12, step: 'Rate manager sayfası bulunamadı', status: REVIEW });

        for (const t of ['Min Stay', 'Stop-Sale', 'Close to Arrival', 'Availability', 'Inventory']) {
            const c = await page.locator(`text=/${t.replace(/[-\/]/g, '.')}/i`).count();
            rec(testInfo, { module: M, scope: 12, step: `Kontrol: ${t}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }

        rec(testInfo, { module: M, scope: 12, step: 'Gerçek inventory mutation + OTA push', status: SKIP, note: 'External etki — sandbox/dry-run zorunlu.' });
        rec(testInfo, { module: M, scope: 12, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
