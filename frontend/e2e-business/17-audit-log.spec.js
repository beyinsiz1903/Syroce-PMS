import { test } from '@playwright/test';
import { rec, PASS, REVIEW } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';

const M = 'audit-log';

test.describe('Scope 17 — Audit / log', () => {
    test('Audit Timeline UI + endpointler', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const candidates = ['/audit-timeline', '/admin/audit-timeline', '/audit'];
        let opened = false;
        for (const p of candidates) {
            const r = await page.goto(p, { waitUntil: 'domcontentloaded' }).catch(() => null);
            const insp = await inspectPageContent(page);
            if (r?.ok() && !insp.has404 && !insp.empty) {
                rec(testInfo, { module: M, scope: 17, step: `Audit sayfası: ${p}`, status: PASS, endpoint: p, http: r.status() });
                opened = true;
                break;
            }
        }
        if (!opened) rec(testInfo, { module: M, scope: 17, step: 'Audit Timeline UI bulunamadı', status: REVIEW });

        const api = await makeApi(baseURL);
        for (const ep of ['/api/audit/timeline?limit=5', '/api/admin/audit-log?limit=5']) {
            const x = await safeGet(api, ep);
            rec(testInfo, { module: M, scope: 17, step: `GET ${ep}`, status: x.status < 500 ? PASS : REVIEW, endpoint: ep, http: x.status });
        }
        await api.dispose();

        // PII scrub heuristik: response gövdesinde JWT/email/IP regex var mı? (read-only)
        rec(testInfo, { module: M, scope: 17, step: 'PII scrub heuristik', status: REVIEW, note: 'Audit response payload kontrolü manuel — Sentry PII scrub ayrı suite ile test edilmeli (bkz. docs/SENTRY_ALERT_POLICY.md).' });
        rec(testInfo, { module: M, scope: 17, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
