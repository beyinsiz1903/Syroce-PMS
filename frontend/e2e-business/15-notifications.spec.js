import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'notifications';

test.describe('Scope 15 — Bildirimler / mesajlar', () => {
    test('Notification center + mailing keşfi', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const candidates = ['/notifications', '/mailing', '/admin/notifications'];
        let opened = false;
        for (const p of candidates) {
            const r = await page.goto(p, { waitUntil: 'domcontentloaded' }).catch(() => null);
            const insp = await inspectPageContent(page);
            if (r?.ok() && !insp.has404 && !insp.empty) {
                rec(testInfo, { module: M, scope: 15, step: `Bildirim sayfası: ${p}`, status: PASS, endpoint: p, http: r.status() });
                opened = true;
                break;
            }
        }
        if (!opened) rec(testInfo, { module: M, scope: 15, step: 'Bildirim sayfası bulunamadı', status: REVIEW });

        // Üst barda zil ikonu / unread badge keşfi (her sayfada olabilir)
        await page.goto('/').catch(() => {});
        const bell = await page.locator('[aria-label*="bildirim" i], [data-testid*="notification"], button:has(svg.lucide-bell)').count();
        rec(testInfo, { module: M, scope: 15, step: 'Top-bar bildirim ikonu', status: bell > 0 ? PASS : REVIEW, note: `count=${bell}` });

        rec(testInfo, { module: M, scope: 15, step: 'Gerçek e-posta/SMS gönderim', status: SKIP, note: 'External etki — Resend/SMS gateway tetiklenmedi.' });
        rec(testInfo, { module: M, scope: 15, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
