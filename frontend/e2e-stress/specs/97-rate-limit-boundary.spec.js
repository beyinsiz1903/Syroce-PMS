// F8Q § 97 — Per-endpoint rate-limit boundary push.
//
// Surface: `backend/apm_middleware.py` EnhancedRateLimitMiddleware + per-route
// guards (room_qr_requests._rl_check, auth burst guard, B2B per-key, etc.).
//
// Doctrine:
//   - Burst N requests/endpoint; expect 429 (or documented throttle), no 5xx.
//   - Per-endpoint ceiling: public QR submit, login, B2B api-key probe,
//     webhook ingestion, GraphQL, reports export.
//   - Tenant/IP isolation: stress burst rate-limited → pilot probe NOT
//     affected (separate scope).
//   - 5xx=0 hard assert (DoS sentinel).
//   - external_calls=[], pilot_drift=0.
//
// Skip semantics (F8M/F8I doctrine): endpoint module-blocked → SKIP, NOT pass
// with 0 effective coverage.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'rate_limit_boundary';
const BURST_N = 60; // beyond typical per-minute ceiling for public surfaces.

test.describe.configure({ mode: 'serial' });

// Burst helper: N istek paralel atar, 429 sayar, 5xx sentinel.
// Task #34: bu spec RL davranışını ölçmek için kasıtlı olarak limiti
// zorluyor → `noPacer` + `noBackoff` ile client-side pacer ve 429 retry'ı
// devre dışı bırakıyoruz. Aksi takdirde 429 sinyali helper tarafından
// retry'lanır ve burst counter throttled=0 görür (false PASS).
async function burst(request, method, url, body, token, n) {
    const promises = [];
    for (let i = 0; i < n; i++) {
        promises.push(callTimed(request, method, url, body, token, { noPacer: true, noBackoff: true })
            .catch((e) => ({ status: 0, body: null, ok: false, err: e?.message })));
    }
    const results = await Promise.all(promises);
    let ok = 0, throttled = 0, clientErr = 0, serverErr = 0, network = 0;
    let retryAfterSeen = false;
    for (const r of results) {
        if (r.status === 429) {
            throttled++;
            // retry-after header check (callTimed proxies headers if available)
            if (r.headers && (r.headers['retry-after'] || r.headers['Retry-After'])) retryAfterSeen = true;
        } else if (r.status === 0) network++;
        else if (r.status >= 500) serverErr++;
        else if (r.status >= 400) clientErr++;
        else if (r.status >= 200 && r.status < 300) ok++;
    }
    return { n, ok, throttled, clientErr, serverErr, network, retryAfterSeen };
}

test.describe('F8Q § 97 — Per-endpoint rate-limit boundary', () => {
    let pilotBefore = null;
    let prefix = null;
    let stressTid = null;
    let stressRoomId = null;

    test('Setup: prefix + pilot baseline + stress sample harvest', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tenant_id || process.env.E2E_STRESS_TENANT_ID || null;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const rooms = await callTimed(request, 'get', '/api/rooms?limit=1',
            undefined, stressTokens.stress_token);
        if (rooms.ok) {
            const arr = Array.isArray(rooms.body?.items) ? rooms.body.items : Array.isArray(rooms.body) ? rooms.body : [];
            stressRoomId = arr[0]?.id || arr[0]?._id || null;
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} burst_n=${BURST_N} room=${stressRoomId?.slice(0, 8) || 'none'}` });
        expect(true).toBe(true);
    });

    test('A) Public surface burst — QR submit + login (anonymous)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        const surfaces = [];

        // 1) Public QR submit — anonymous, expect 403 (invalid token) or
        // 429 if RL hits first. Either way, 5xx=0.
        if (stressRoomId) {
            const qr = await burst(request, 'post',
                `/api/public/room-qr/${stressTid}/${stressRoomId}/submit?t=garbage`,
                { category: 'housekeeping', description: 'rl_burst', priority: 'normal', language: 'tr' },
                null, BURST_N);
            surfaces.push({ key: 'qr_submit', ...qr });
        } else {
            surfaces.push({ key: 'qr_submit', skipped: 'no_room' });
        }

        // 2) Login burst with wrong creds — expect 401 or 429, 5xx=0.
        // WATCH E#11: the email MUST be a syntactically-VALID address that
        // simply doesn't exist. A `.invalid` TLD (RFC 6761 special-use) is
        // rejected by Pydantic `EmailStr` with a 422 *before* the login
        // handler runs, so the per-IP/per-account throttle (`enforce` in
        // `_record_failure_and_raise`) is never reached and the burst can
        // NEVER observe a 429 — the throttled=0 was a vacuous validation
        // bounce, not evidence of a missing rate limit. `@example.com`
        // (RFC 2606 doc domain) parses as a real address yet resolves to no
        // account, so every attempt reaches the handler, fails creds (401),
        // records a throttle hit, and the cap (LOGIN_IP=20/60s) trips 429.
        const login = await burst(request, 'post', '/api/auth/login',
            { email: `${prefix}_rl@example.com`, password: 'wrong_pw_burst' },
            null, BURST_N);
        surfaces.push({ key: 'auth_login', ...login });

        const serverErrAny = surfaces.some((s) => (s.serverErr || 0) > 0);
        const throttledAny = surfaces.some((s) => (s.throttled || 0) > 0);
        if (serverErrAny) {
            const offenders = surfaces.filter((s) => (s.serverErr || 0) > 0).map((s) => `${s.key}:${s.serverErr}`).join(',');
            recFinding(testInfo, 'P0', MOD, 'public burst → 5xx',
                `DoS sentinel — ${offenders}. Public surface should never 5xx under burst.`);
        }
        if (!throttledAny) {
            recFinding(testInfo, 'P2', MOD, 'no 429 observed on public burst',
                `BURST_N=${BURST_N} — RL middleware ya threshold yüksek, ya inactive. surfaces=${JSON.stringify(surfaces)}`);
        }
        rec(testInfo, { module: MOD, step: 'public_burst', status: !serverErrAny ? 'PASS' : 'FAIL',
            note: `surfaces=${JSON.stringify(surfaces)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'public_burst', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(serverErrAny, '5xx under burst is DoS surface').toBe(false);
    });

    test('B) Authenticated surface burst — GraphQL + B2B + reports export', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        const surfaces = [];
        // GraphQL trivial query burst
        const gql = await burst(request, 'post', '/api/graphql',
            { query: '{ __typename }' }, stressTokens.stress_token, BURST_N);
        surfaces.push({ key: 'graphql', ...gql });

        // B2B api-keys list burst (super_admin / view_system_diagnostics gated;
        // 401/403 normal, 429 if RL hits; 5xx hard fail)
        const b2b = await burst(request, 'get', '/api/b2b/agencies?limit=1',
            undefined, stressTokens.stress_token, BURST_N);
        surfaces.push({ key: 'b2b_agencies', ...b2b });

        // Reports export burst (heavier surface)
        const rep = await burst(request, 'get', '/api/reports/occupancy?days=7',
            undefined, stressTokens.stress_token, BURST_N);
        surfaces.push({ key: 'reports_occupancy', ...rep });

        const serverErrAny = surfaces.some((s) => (s.serverErr || 0) > 0);
        if (serverErrAny) {
            const offenders = surfaces.filter((s) => (s.serverErr || 0) > 0).map((s) => `${s.key}:${s.serverErr}`).join(',');
            recFinding(testInfo, 'P0', MOD, 'auth burst → 5xx',
                `DoS sentinel — ${offenders}.`);
        }
        rec(testInfo, { module: MOD, step: 'auth_burst', status: !serverErrAny ? 'PASS' : 'FAIL',
            note: `surfaces=${JSON.stringify(surfaces)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'auth_burst', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(serverErrAny, '5xx under auth burst').toBe(false);
    });

    test('C) Tenant/IP isolation — pilot probe MUST remain healthy after stress burst', async ({ request, stressTokens, stressState }, testInfo) => {
        // Stress tenant'a burst gönderiminden hemen sonra pilot tenant
        // healthcheck — eğer pilot RL'e takılırsa isolation broken (P0).
        // Pilot read-only — no mutation.
        const samples = [];
        for (let i = 0; i < 5; i++) {
            const r = await callTimed(request, 'get', '/api/pms/bookings?limit=1',
                undefined, stressTokens.pilot_token);
            samples.push({ status: r.status, ms: r.ms });
        }
        const allHealthy = samples.every((s) => s.status >= 200 && s.status < 300);
        const any429 = samples.some((s) => s.status === 429);
        const any5xx = samples.some((s) => s.status >= 500);
        if (any429) {
            recFinding(testInfo, 'P0', MOD, 'tenant isolation broken — pilot rate-limited after stress burst',
                `samples=${JSON.stringify(samples)} — RL scope should be per-tenant/IP, pilot must not bleed.`);
        }
        if (any5xx) {
            recFinding(testInfo, 'P0', MOD, 'pilot 5xx after stress burst',
                `samples=${JSON.stringify(samples)} — DoS sentinel.`);
        }
        rec(testInfo, { module: MOD, step: 'tenant_isolation', status: allHealthy ? 'PASS' : 'FAIL',
            note: `samples=${JSON.stringify(samples)} all_healthy=${allHealthy}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'tenant_isolation', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(any429, 'pilot 429 after stress burst (isolation broken)').toBe(false);
        expect(any5xx, 'pilot 5xx after stress burst').toBe(false);
    });

    test('D) Pilot drift = 0 + external_calls = [] (final invariants)', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants', status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});
