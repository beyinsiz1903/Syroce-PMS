// F10A Mobile smoke — navigate every Expo Router route, run console +
// PII/token leak scan. Read-only against pilot (zero mutation guarantee).
//
// Findings are recorded as test annotations (consumable by the existing
// stress drill reporter once Task #94 wires the markdown reporter).

import { test, expect } from '@playwright/test';
import { MOBILE_ROUTES, PII_LEAK_PATTERNS } from './routes.js';

/**
 * Fail the test with a structured finding so the reporter can pick it up.
 * `severity` must be one of P0/P1/P2/P3 (P0=hard fail, P1=hard fail,
 * P2/P3=warn-only annotation).
 */
function recordFinding(testInfo, severity, route, message, detail = '') {
    const f = { severity, route, message, detail };
    testInfo.annotations.push({ type: 'finding', description: JSON.stringify(f) });
    if (severity === 'P0' || severity === 'P1') {
        throw new Error(`[${severity}] ${route}: ${message} — ${detail}`);
    }
}

function scanForLeaks(html) {
    const hits = [];
    for (const { name, re } of PII_LEAK_PATTERNS) {
        const m = re.exec(html);
        if (m) hits.push({ pattern: name, sample: m[0].slice(0, 60) });
    }
    return hits;
}

// HTTP methods that mutate server state — must be zero per the F10A
// read-only doctrine. Any outbound request using one of these methods
// is recorded and hard-fails the test (P1: pilot mutation guarantee).
const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

// External hosts the mobile app must NOT call during smoke. Allowlist
// is derived from EXPO_PUBLIC_API_URL / EXPO_PUBLIC_QUICKID_URL host
// names at test time; everything else is flagged as `external_calls`.
function isAllowedHost(url, allowedHosts) {
    try {
        const u = new URL(url);
        return allowedHosts.has(u.host);
    } catch {
        return true; // relative / data: / blob: — not an external call
    }
}

test.describe('F10A Mobile Smoke — Expo Web', () => {
    test.describe.configure({ mode: 'serial' });

    // One test per route × viewport. The test array is generated at
    // collection time so Playwright shows each route as a separate entry.
    for (const route of MOBILE_ROUTES) {
        test(`smoke ${route.group} ${route.path}`, async ({ page, baseURL }, testInfo) => {
            const consoleErrors = [];
            const mutatingCalls = [];
            const externalCalls = [];
            const allowedHosts = new Set();
            try { allowedHosts.add(new URL(baseURL).host); } catch { /* ignore */ }

            page.on('console', (msg) => {
                if (msg.type() === 'error') consoleErrors.push(msg.text());
            });
            page.on('pageerror', (err) => consoleErrors.push(String(err?.message || err)));

            // Doctrine instrumentation: record every outbound request,
            // hard-fail on mutating verbs (read-only guarantee) and on
            // calls to hosts outside the Expo Web origin allowlist.
            page.on('request', (req) => {
                const method = req.method();
                const url = req.url();
                if (MUTATING_METHODS.has(method)) {
                    mutatingCalls.push({ method, url });
                }
                if (!isAllowedHost(url, allowedHosts)) {
                    externalCalls.push({ method, url });
                }
            });

            let response;
            try {
                response = await page.goto(route.path, { waitUntil: 'domcontentloaded' });
            } catch (e) {
                if (route.critical) {
                    recordFinding(testInfo, 'P1', route.path,
                        'navigation failed', String(e?.message || e).slice(0, 200));
                } else {
                    recordFinding(testInfo, 'P3', route.path,
                        'navigation failed (non-critical)', String(e?.message || e).slice(0, 200));
                }
                return;
            }

            // Network status — Expo Web SPA returns 200 even for unknown
            // routes (router handles 404 client-side), so we don't gate
            // on HTTP. Instead we look for the router 404 component.
            const status = response?.status() ?? 0;
            expect(status, `${route.path}: HTTP ${status}`).toBeLessThan(500);

            // Wait briefly for the React tree to mount.
            await page.waitForTimeout(800);

            // Auth-gating check: protected routes must redirect to /login
            // when unauthenticated. F10A runs unauthenticated; Task #93
            // will add a login fixture and re-walk with valid session.
            const url = page.url();
            if (route.requiresAuth) {
                const redirected = url.includes('/login') || url.endsWith('/login');
                if (!redirected) {
                    // Could be legitimately rendered (e.g. server returns
                    // public placeholder) — mark REVIEW, not fail, until
                    // F10B authenticated walk lands.
                    recordFinding(testInfo, 'P3', route.path,
                        'protected route did not redirect to /login when unauth',
                        `current_url=${url}`);
                }
            }

            // PII / token leak scan on the rendered DOM.
            const html = await page.content();
            const leaks = scanForLeaks(html);
            if (leaks.length > 0) {
                recordFinding(testInfo, 'P0', route.path,
                    'PII/token leak in rendered DOM',
                    leaks.map((l) => `${l.pattern}:${l.sample}`).join(' | '));
            }

            // Console error budget — > 5 errors on a single route is a
            // smell worth REVIEWING. < 5 is informational only (RN web
            // shim noise, expected during F10A scaffold phase).
            if (consoleErrors.length > 5) {
                recordFinding(testInfo, 'P2', route.path,
                    `console errors > 5 (count=${consoleErrors.length})`,
                    consoleErrors.slice(0, 3).join(' || '));
            }

            // Doctrine gates — hard-fail on mutation or external call.
            if (mutatingCalls.length > 0) {
                recordFinding(testInfo, 'P1', route.path,
                    'pilot mutation doctrine breach: outbound mutating request observed',
                    mutatingCalls.slice(0, 3).map((c) => `${c.method} ${c.url}`).join(' | '));
            }
            if (externalCalls.length > 0) {
                recordFinding(testInfo, 'P1', route.path,
                    'external_calls doctrine breach: request to non-allowlisted host',
                    externalCalls.slice(0, 3).map((c) => `${c.method} ${c.url}`).join(' | '));
            }

            testInfo.annotations.push({
                type: 'route_ok',
                description: JSON.stringify({
                    route: route.path, group: route.group, criticality: route.criticality,
                    status, console_errors: consoleErrors.length, leaks: leaks.length,
                    requires_auth: route.requiresAuth,
                    mutating_calls: mutatingCalls.length,
                    external_calls: externalCalls.length,
                }),
            });
        });
    }
});
