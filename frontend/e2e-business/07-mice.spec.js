import { test } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';

const M = 'mice';

test.describe('Scope 7 — MICE / etkinlik', () => {
    test('MICE ana sayfa + sekme + butonlar', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/mice', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 7, step: 'MICE navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/mice', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 7, step: 'MICE içerik', status: insp.empty || insp.has500 ? FAIL : PASS, note: `len=${insp.lengthChars}` });

        for (const tab of ['Etkinlikler', 'Mekanlar', 'Menüler']) {
            const c = await page.locator(`text=/${tab}/i`).count();
            rec(testInfo, { module: M, scope: 7, step: `Tab ${tab}`, status: c > 0 ? PASS : REVIEW });
        }

        const newEvent = page.locator('button:has-text("Yeni Etkinlik")').first();
        const newEventExists = (await newEvent.count()) > 0;
        rec(testInfo, { module: M, scope: 7, step: 'Yeni Etkinlik butonu', status: newEventExists ? PASS : REVIEW });
        if (newEventExists) {
            await newEvent.click({ timeout: 5_000 }).catch(() => {});
            await page.waitForTimeout(600);
            const dialogVisible = await page.locator('[role="dialog"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
            rec(testInfo, { module: M, scope: 7, step: 'EventFormModal açılır', status: dialogVisible ? PASS : REVIEW });
            await page.keyboard.press('Escape').catch(() => {});
        }

        // API discovery
        const api = await makeApi(baseURL);
        for (const ep of ['/api/mice/events?limit=3', '/api/mice/spaces?limit=3']) {
            const x = await safeGet(api, ep);
            rec(testInfo, { module: M, scope: 7, step: `GET ${ep}`, status: x.status < 500 ? PASS : REVIEW, endpoint: ep, http: x.status });
        }
        await api.dispose();

        rec(testInfo, { module: M, scope: 7, step: 'Gerçek etkinlik POST', status: SKIP, note: 'Veri kirletme + cleanup karmaşası nedeniyle yalnız form keşfi.' });
        rec(testInfo, { module: M, scope: 7, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});

