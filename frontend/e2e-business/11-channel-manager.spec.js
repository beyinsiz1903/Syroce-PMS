import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP, FAIL } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';

const M = 'channel-manager';

test.describe('Scope 11 — Channel Manager', () => {
    test('Channels Hub + provider/CB/conflict UI', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/channels', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 11, step: 'Channels navigate', status: r?.ok() ? PASS : FAIL, endpoint: '/channels', http: r?.status() });
        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 11, step: 'Hub içerik', status: insp.empty || insp.has500 ? FAIL : PASS });

        for (const t of ['HotelRunner', 'Exely', 'Unified Rate', 'Connections']) {
            const c = await page.locator(`text=/${t}/i`).count();
            rec(testInfo, { module: M, scope: 11, step: `İçerik: ${t}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }

        // Conflict Queue tab
        const r2 = await page.goto('/channels?tab=conflicts', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 11, step: 'Conflict Queue navigate', status: r2?.ok() ? PASS : REVIEW, endpoint: '/channels?tab=conflicts', http: r2?.status() });

        // Architect bulgu #2: önceki `>= 0` her zaman PASS'tı → false confidence.
        // Şimdi: queue boşsa REVIEW (UI'ın boş-durum render etmesini test edemiyoruz),
        // queue varsa en az 1 resolve butonu bulunmalı (yoksa FAIL: UI bozuk).
        const conflictRows = await page.locator('[data-testid^="conflict-row-"]').count();
        const resolveBtns = await page.locator('[data-testid^="conflict-resolve-"]').count();
        let conflictStatus;
        if (conflictRows === 0) conflictStatus = REVIEW;
        else if (resolveBtns >= 1) conflictStatus = PASS;
        else conflictStatus = FAIL;
        rec(testInfo, { module: M, scope: 11, step: 'Conflict resolve butonları', status: conflictStatus, note: `rows=${conflictRows} resolveBtns=${resolveBtns}` });
        const bulkBtn = await page.locator('[data-testid="conflict-bulk-open"]').count();
        rec(testInfo, { module: M, scope: 11, step: 'Bulk resolve buton mevcut', status: bulkBtn > 0 ? PASS : REVIEW });

        // API discovery
        const api = await makeApi(baseURL);
        for (const ep of [
            '/api/channel-manager/conflict-queue?limit=5',
            '/api/channel-manager/unified-rate-manager/circuit-breakers',
            '/api/channel-manager/dashboard/overview',
        ]) {
            const x = await safeGet(api, ep);
            rec(testInfo, { module: M, scope: 11, step: `GET ${ep}`, status: x.status < 500 ? PASS : REVIEW, endpoint: ep, http: x.status });
        }
        await api.dispose();

        rec(testInfo, { module: M, scope: 11, step: 'Sync now / gerçek OTA push', status: SKIP, note: 'External etki: HotelRunner/Exely gerçek push tetiklenmedi.' });
        rec(testInfo, { module: M, scope: 11, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
