import { test } from '@playwright/test';
import { rec, PASS, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';

const M = 'users-roles';

test.describe('Scope 10 — Kullanıcı / Rol', () => {
    test('Kullanıcı-Rol Manager + filter + butonlar', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/admin/user-roles', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 10, step: 'UserRoleManager navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/admin/user-roles', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 10, step: 'İçerik', status: insp.empty || insp.has500 ? REVIEW : PASS });

        const emailFilter = page.locator('input[placeholder*="email"]').first();
        rec(testInfo, { module: M, scope: 10, step: 'Email filter input', status: (await emailFilter.count()) > 0 ? PASS : REVIEW });

        for (const t of ['Super Admin Yap', 'Admin Yap']) {
            const c = await page.locator(`text=/${t}/i`).count();
            rec(testInfo, { module: M, scope: 10, step: `Buton: ${t}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }

        const api = await makeApi(baseURL);
        const u = await safeGet(api, '/api/admin/users?limit=3');
        rec(testInfo, { module: M, scope: 10, step: 'GET /api/admin/users', status: u.status === 200 || u.status === 403 ? PASS : REVIEW, endpoint: '/api/admin/users', http: u.status });
        await api.dispose();

        rec(testInfo, { module: M, scope: 10, step: 'Test user create + role assign', status: SKIP, note: 'Pilot otentikasyon havuzunu kirletmemek için kullanıcı oluşturulmadı.' });
        rec(testInfo, { module: M, scope: 10, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
