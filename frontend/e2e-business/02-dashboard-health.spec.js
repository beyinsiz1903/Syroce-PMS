import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';

const M = 'dashboard-health';

test.describe('Scope 2 — Dashboard + System Health', () => {
    test('Dashboard kartları + ana modüller', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/', { waitUntil: 'networkidle' });
        rec(testInfo, { module: M, scope: 2, step: 'Dashboard yükle', status: r?.ok() ? PASS : FAIL, endpoint: '/', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 2, step: 'İçerik dolu', status: insp.lengthChars > 100 ? PASS : REVIEW, note: `len=${insp.lengthChars}` });

        // Modül kartları (PMS, RMS gibi)
        const pmsCard = await page.locator('text=/^PMS$/').count();
        const rmsCard = await page.locator('text=/^RMS$/').count();
        rec(testInfo, { module: M, scope: 2, step: 'Modül kartları (PMS/RMS)', status: pmsCard + rmsCard >= 1 ? PASS : REVIEW, note: `pms=${pmsCard} rms=${rmsCard}` });

        rec(testInfo, { module: M, scope: 2, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });

    test('System Health pilot section + endpointleri', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/admin/system-health', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 2, step: 'System Health navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/admin/system-health', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 2, step: 'Sayfa içerik', status: insp.empty || insp.has500 ? FAIL : PASS });

        // Pilot section kart text'leri (Sprint A)
        const expected = ['Readiness', 'CM Outbox', 'Circuit Breaker', 'Atlas Backup', 'Observability'];
        for (const t of expected) {
            const found = await page.locator(`text=/${t}/i`).count();
            rec(testInfo, { module: M, scope: 2, step: `Pilot kart: ${t}`, status: found > 0 ? PASS : REVIEW, note: `count=${found}` });
        }

        // Backend health endpointleri
        const api = await makeApi(baseURL);
        for (const ep of ['/api/health/readiness', '/api/production-golive/readiness']) {
            const res = await safeGet(api, ep);
            rec(testInfo, { module: M, scope: 2, step: `GET ${ep}`, status: res.ok ? PASS : REVIEW, endpoint: ep, http: res.status });
        }
        await api.dispose();

        rec(testInfo, { module: M, scope: 2, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
        expect(insp.empty || insp.has500).toBeFalsy();
    });
});
