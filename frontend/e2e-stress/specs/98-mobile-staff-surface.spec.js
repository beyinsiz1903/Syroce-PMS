// ─────────────────────────────────────────────────────────────────────────
// F9C § 98 — Mobile Staff Surface Deep Stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Scope (TEST_COVERAGE_GAP_MAP_20260527.md §2.1 G2 — mobile staff
// app + push + handover yüzeyi ZERO coverage idi):
//   Backend:
//     - backend/domains/pms/notification_router.py
//         POST   /api/notifications/push/register
//         POST   /api/notifications/push/unregister
//         GET    /api/notifications/preferences
//         PUT    /api/notifications/preferences
//         GET    /api/notifications/list
//     - backend/routers/shift_handover.py  (prefix=/api/pms/shift-handover)
//         POST   /api/pms/shift-handover
//         GET    /api/pms/shift-handover
//         GET    /api/pms/shift-handover/open-count
//         PATCH  /api/pms/shift-handover/{id}/acknowledge
//         DELETE /api/pms/shift-handover/{id}   (cleanup)
//
//   Yüzey haritası:
//     A) POST   /api/notifications/push/register          (push token register)
//     B) GET    /api/notifications/preferences            (read prefs)
//     C) PUT    /api/notifications/preferences            (update prefs)
//     D) POST   /api/pms/shift-handover                   (create handover note)
//     E) GET    /api/pms/shift-handover                   (list — tenant-scoped)
//     F) GET    /api/pms/shift-handover/open-count        (counter read-only)
//     G) PATCH  /api/pms/shift-handover/{id}/acknowledge  (task ack lifecycle)
//     H) GET    /api/notifications/list                   (inbox read-only)
//     I) POST   /api/notifications/push/unregister        (cleanup-adjacent)
//     J) IDOR   PATCH ack with cross-tenant handover id   (must fail / no-op)
//     K) Anon   GET handover list (must be 401/403, no leak)
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []   (assertNoExternalCallsPostBatch)
//   - pilot mutation = 0    (assertPilotDriftZero — booking baseline + pilot push
//                            token prefix scan supplemental)
//   - P0 = P1 = 0; 5xx = 0; PII leak = 0
//   - DISABLE_EXPO_PUSH=1  test env mutlak (gerçek delivery YOK; backend bunu
//     env'den kendi okur — burada sadece doğrulanır).
//   - Tüm push token / handover note değerleri `${prefix}` ile tag'lenir
//     (cleanup yakalasın).
//   - Module-blocked doctrine: handover list non-2xx → A-I skip + REVIEW;
//     J/K (security probes) BAĞIMSIZ çalışır.
//   - Skip-as-pass YOK → `test.skip(true, reason)` kullanılır.
//
// Reporter satırı: `mobile_staff`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'mobile_staff';
const SUB_PREFIX = 'F9C_MSTAFF';
const GAP_MS = 1500;

test.describe.configure({ mode: 'serial' });

test.describe('F9C § 98 — Mobile Staff Surface', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBookingBaseline = null;
    let pilotKnownHandoverId = null;
    const createdHandoverIds = [];
    const registeredDeviceIds = [];

    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }
    function todayYmd() {
        const d = new Date();
        const y = d.getUTCFullYear();
        const m = String(d.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(d.getUTCDate()).padStart(2, '0');
        return `${y}-${m}-${dd}`;
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: stress token + module probe + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        // Doctrine self-check: DISABLE_EXPO_PUSH=1 test env zorunlu (fail-closed).
        // Architect Round-1: runner-side REVIEW only was too permissive; bir
        // runner DISABLE_EXPO_PUSH unset state'iyle koşarsa register edilen
        // ExponentPushToken[...] payload'ı backend real-delivery yapma riski
        // doğar (backend env yanlış config'liyse). Hard fail: A-I lifecycle
        // tamamen SKIP, J/K bağımsız çalışır (security probes push delivery
        // tetiklemez).
        if (process.env.DISABLE_EXPO_PUSH !== '1') {
            moduleBlocked = true;
            blockedReason = 'DISABLE_EXPO_PUSH_not_1';
            rec(testInfo, {
                module: MOD, step: 'env_check', status: 'REVIEW',
                note: 'DISABLE_EXPO_PUSH != "1" — A-I SKIP (real-delivery guard), J/K independent.',
            });
            recFinding(testInfo, 'P1', MOD,
                'Mobile staff stress requires DISABLE_EXPO_PUSH=1',
                'Runner env not set; lifecycle batch SKIPped to prevent real Expo delivery.');
            // Note: don't return — let module probe still run so we capture
            // baseline state. moduleBlocked already flips A-I to SKIP.
        }

        // Pilot baseline — assertPilotDriftZero için bookings count snapshot.
        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBookingBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;

            // Best-effort: real pilot handover id for IDOR probe (J).
            try {
                const pilotHv = await callTimed(
                    request, 'get', '/api/pms/shift-handover', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (pilotHv.status === 200 && Array.isArray(pilotHv.body?.items) && pilotHv.body.items.length > 0) {
                    pilotKnownHandoverId = pilotHv.body.items[0].id || null;
                }
            } catch { /* ignore — J falls back to bogus id */ }
        }

        // Module probe: GET handover list (mobile-staff core surface).
        const probe = await callTimed(
            request, 'get', '/api/pms/shift-handover', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (probe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Mobile staff module 5xx on setup probe',
                `GET /api/pms/shift-handover → ${probe.status}; body=${JSON.stringify(probe.body || {}).slice(0, 200)}`);
            expect(probe.status, 'Mobile staff setup 5xx').toBeLessThan(500);
        }
        if ([401, 403, 404, 501].includes(probe.status)) {
            moduleBlocked = true;
            blockedReason = `setup_probe_${probe.status}`;
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'REVIEW',
                http: probe.status, note: 'Module blocked / not deployed — A-I SKIP, J/K independent.',
            });
            recFinding(testInfo, 'P2', MOD,
                `Mobile staff module blocked at setup (${probe.status})`,
                'A-I lifecycle SKIP; security probes (J/K) bağımsız çalışır.');
            return;
        }
        rec(testInfo, {
            module: MOD, step: 'module_probe', status: 'PASS',
            http: probe.status, note: 'GET handover list 2xx — lifecycle aktif.',
        });
    });

    // ──────────────────────────────────────────────────────────────
    // A) Push token register
    test('A) Register push device token — stress-tenant scoped', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'A_push_register', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const deviceId = `${prefix}-DEV-${cryptoRandomUUID()}`;
        // Prefix tag in push_token so afterAll / external cleanup script can
        // identify rows; backend DISABLE_EXPO_PUSH=1 means this never reaches
        // Expo. ExponentPushToken[...] prefix used so server-side validators
        // (if any) accept the shape; suffix carries our prefix.
        const pushToken = `ExponentPushToken[${prefix}_${SUB_PREFIX}_${cryptoRandomUUID().slice(0, 8)}]`;
        const r = await callTimed(
            request, 'post', '/api/notifications/push/register',
            {
                device_id: deviceId,
                push_token: pushToken,
                device_name: `${prefix}-stress-device`,
                platform: 'ios',
                app_version: '1.0.0-stress',
                os_version: '17.0',
                subscriptions: ['operations', 'vip_alerts'],
                departments: ['front_office'],
            },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('A_push_register') } },
        );
        recPerf(testInfo, MOD, 'A_push_register', [r.ms], r.status >= 200 && r.status < 300);

        if ([404, 403, 501].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'A_push_register', status: 'REVIEW', http: r.status,
                note: 'push register endpoint not deployed' });
            recFinding(testInfo, 'P2', MOD, 'POST /api/notifications/push/register not deployed',
                `status=${r.status}`);
            return;
        }
        expect(r.status, `A_push_register 5xx status=${r.status}`).toBeLessThan(500);
        expect(r.status, `A_push_register non-2xx status=${r.status}`).toBeGreaterThanOrEqual(200);
        expect(r.status).toBeLessThan(300);
        expect(r.body?.success, 'A_push_register success flag yok').toBe(true);
        registeredDeviceIds.push(deviceId);
        rec(testInfo, { module: MOD, step: 'A_push_register', status: 'PASS', http: r.status,
            note: `device_id=${deviceId}` });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // B) GET notification preferences
    test('B) GET /api/notifications/preferences read', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'B_prefs_get', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/notifications/preferences', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `B_prefs_get 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `prefs GET non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'B_prefs_get', status: 'REVIEW', http: r.status });
            return;
        }
        expect(r.body, 'B_prefs_get body yok').toBeTruthy();
        rec(testInfo, { module: MOD, step: 'B_prefs_get', status: 'PASS', http: r.status });
        await gap(500);
    });

    // ──────────────────────────────────────────────────────────────
    // C) PUT notification preferences
    test('C) PUT /api/notifications/preferences update', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'C_prefs_put', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'put', '/api/notifications/preferences',
            { notification_type: `${SUB_PREFIX}_stress_alert`, enabled: true, channels: ['in_app'] },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('C_prefs_put') } },
        );
        expect(r.status, `C_prefs_put 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `prefs PUT non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'C_prefs_put', status: 'REVIEW', http: r.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'C_prefs_put', status: 'PASS', http: r.status });
        await gap(500);
    });

    // ──────────────────────────────────────────────────────────────
    // D) Create shift handover note
    test('D) POST /api/pms/shift-handover create note', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'D_hv_create', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const payload = {
            business_date: todayYmd(),
            shift: 'morning',
            note: `${prefix} ${SUB_PREFIX} D_create stress handover note`,
            priority: 'normal',
            to_shift: 'afternoon',
        };
        const r = await callTimed(
            request, 'post', '/api/pms/shift-handover', payload,
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('D_hv_create') } },
        );
        recPerf(testInfo, MOD, 'D_hv_create', [r.ms], r.status >= 200 && r.status < 300);

        if ([404, 403, 501].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'D_hv_create', status: 'REVIEW', http: r.status,
                note: 'handover create not deployed' });
            recFinding(testInfo, 'P2', MOD, 'POST /api/pms/shift-handover not deployed',
                `status=${r.status}`);
            return;
        }
        expect(r.status, `D_hv_create 5xx status=${r.status}`).toBeLessThan(500);
        expect(r.status, `D_hv_create non-2xx status=${r.status}`).toBeGreaterThanOrEqual(200);
        expect(r.status).toBeLessThan(300);

        const hv = r.body || {};
        expect(hv.id, 'created handover id yok').toBeTruthy();
        expect(hv.tenant_id, 'handover tenant_id yok').toBeTruthy();
        expect(hv.acknowledged, 'handover yeni iken acknowledged=false olmalı').toBe(false);
        createdHandoverIds.push(hv.id);

        rec(testInfo, { module: MOD, step: 'D_hv_create', status: 'PASS', http: r.status,
            note: `handover_id=${hv.id}` });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // E) List handovers — tenant scoping invariant
    test('E) GET /api/pms/shift-handover list + tenant scope', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'E_hv_list', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', `/api/pms/shift-handover?business_date=${todayYmd()}&status=open`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `E_hv_list 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `handover list non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'E_hv_list', status: 'REVIEW', http: r.status });
            return;
        }
        const items = (r.body && r.body.items) || [];
        expect(Array.isArray(items), 'E_hv_list items array değil').toBe(true);
        // Architect Round-1: strict tenant equality, not "truthy". Bir cross-tenant
        // leak'te response item populated `tenant_id` ile gelebilir; sadece
        // truthy kontrolü false-PASS yaratır. stress_tid ile birebir eşleşme şart.
        const expectedTid = stressState.stress_tid;
        expect(expectedTid, 'stressState.stress_tid yok').toBeTruthy();
        for (const it of items) {
            expect(it.tenant_id, `E_hv_list item tenant_id yok: ${JSON.stringify(it).slice(0, 100)}`).toBeTruthy();
            expect(it.tenant_id, `E_hv_list item cross-tenant: expected=${expectedTid} got=${it.tenant_id}`).toBe(expectedTid);
        }
        rec(testInfo, { module: MOD, step: 'E_hv_list', status: 'PASS', http: r.status,
            note: `items=${items.length}` });
        await gap(500);
    });

    // ──────────────────────────────────────────────────────────────
    // F) Open-count read-only
    test('F) GET /api/pms/shift-handover/open-count', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'F_hv_open_count', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/pms/shift-handover/open-count', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `F_hv_open_count 5xx`).toBeLessThan(500);
        if (r.status === 200) {
            expect(typeof r.body?.open, 'F_hv_open_count open numeric').toBe('number');
        } else {
            recFinding(testInfo, 'P2', MOD, `open-count non-200 status=${r.status}`, '');
        }
        rec(testInfo, { module: MOD, step: 'F_hv_open_count', status: r.status === 200 ? 'PASS' : 'REVIEW',
            http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // G) Acknowledge handover (task ack lifecycle)
    test('G) PATCH /api/pms/shift-handover/{id}/acknowledge', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdHandoverIds.length === 0 ? 'no_handover_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'G_hv_ack', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const hvId = createdHandoverIds[0];
        const r = await callTimed(
            request, 'patch', `/api/pms/shift-handover/${hvId}/acknowledge`,
            { note: `${SUB_PREFIX} ack` },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('G_hv_ack') } },
        );
        expect(r.status, `G_hv_ack 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `handover ack non-200 status=${r.status}`,
                `hv_id=${hvId} body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'G_hv_ack', status: 'REVIEW', http: r.status });
            return;
        }
        expect(r.body?.acknowledged, 'G_hv_ack acknowledged flag true olmalı').toBe(true);
        expect(r.body?.id, 'G_hv_ack response id yok').toBe(hvId);
        rec(testInfo, { module: MOD, step: 'G_hv_ack', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // H) Inbox list read-only
    test('H) GET /api/notifications/list read-only', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'H_inbox_list', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/notifications/list?limit=25', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `H_inbox_list 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `inbox list non-200 status=${r.status}`, '');
        }
        rec(testInfo, { module: MOD, step: 'H_inbox_list', status: r.status === 200 ? 'PASS' : 'REVIEW',
            http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // I) Push unregister (cleanup-adjacent positive flow)
    test('I) POST /api/notifications/push/unregister', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (registeredDeviceIds.length === 0 ? 'no_device_registered' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'I_push_unregister', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const deviceId = registeredDeviceIds[0];
        const r = await callTimed(
            request, 'post', '/api/notifications/push/unregister',
            { device_id: deviceId },
            stressTokens.stress_token,
            { timeout: 10_000 },
        );
        expect(r.status, `I_push_unregister 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status === 200 && r.body?.success === true) {
            // Mark as already-cleaned so afterAll skips it.
            registeredDeviceIds.shift();
            rec(testInfo, { module: MOD, step: 'I_push_unregister', status: 'PASS', http: r.status,
                note: `removed=${r.body?.removed ?? 0}` });
        } else {
            recFinding(testInfo, 'P2', MOD, `push unregister non-2xx status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'I_push_unregister', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // J) SECURITY: IDOR — cross-tenant PATCH ack (must be no-op or 404)
    // Always-on; module-blocked durumda da çalışır.
    test('J) IDOR: cross-tenant PATCH ack → no mutation', async ({ request, stressTokens }, testInfo) => {
        // Architect Round-1: bogus fallback must be a pure UUID (not prefixed)
        // so backend ObjectId/UUID validators don't 422 the path param before
        // tenant filter even runs (which would make K probe meaningless).
        const targetId = pilotKnownHandoverId || cryptoRandomUUID();
        const probeKind = pilotKnownHandoverId ? 'real_pilot_handover_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'patch', `/api/pms/shift-handover/${targetId}/acknowledge`,
            { note: `${SUB_PREFIX} idor_probe` },
            stressTokens.stress_token,
            { timeout: 10_000 },
        );
        expect(r.status, `J_idor 5xx status=${r.status}`).toBeLessThan(500);
        // Doctrine: 404 / 403 / 401 PASS. 200 with this id MUST NOT happen
        // (backend filters by tenant_id; cross-tenant id → find_one_and_update
        // returns None → 404).
        if ([404, 403, 401].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'PASS', http: r.status,
                note: `${probeKind} rejected ${r.status}` });
        } else if (r.status === 200) {
            const ackedTenant = r.body?.tenant_id;
            // 200 ile dönerse: kendi tenant'ından gerçek bir handover'a denk
            // gelmiş olabilir (zayıf ihtimal, pilot id collision). Eğer
            // response tenant_id stress tenant değilse P0 IDOR.
            recFinding(testInfo, 'P0', MOD,
                `IDOR boundary breach: cross-tenant PATCH ack succeeded (${probeKind})`,
                `target_id=${targetId} response_tenant=${ackedTenant} body=${JSON.stringify(r.body).slice(0, 200)}`);
            expect(r.status, `J_idor: PATCH ack with ${probeKind}=${targetId} returned 200 → cross-tenant tampering`).not.toBe(200);
        } else {
            recFinding(testInfo, 'P2', MOD, `IDOR probe unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // K) SECURITY: Anonymous (headerless) list — must be blocked
    // Round-2 doctrine: raw request.get + NO Authorization header
    // (callTimed token=null "Bearer null" gönderir — invalid-token probe olur,
    // strict anonymous değil). Burada gerçek headerless probe yapıyoruz.
    test('K) Anonymous (headerless) GET handover list → 401/403', async ({ request }, testInfo) => {
        let status = 0;
        let bodySnippet = '';
        try {
            const r = await request.get('/api/pms/shift-handover', {
                failOnStatusCode: false,
                timeout: 10_000,
                // Intentionally headerless — no Authorization header at all.
            });
            status = r.status();
            try { bodySnippet = (await r.text()).slice(0, 200); } catch { /* ignore */ }
        } catch (e) {
            recFinding(testInfo, 'P2', MOD, 'K_anon network error', String(e?.message || e).slice(0, 200));
        }
        expect(status, `K_anon 5xx status=${status}`).toBeLessThan(500);
        const blocked = status === 401 || status === 403 || status === 429;
        if (!blocked) {
            recFinding(testInfo, 'P1', MOD,
                `Anonymous GET shift-handover not blocked (status=${status})`,
                `PUBLIC SURFACE LEAK — tenant data may be reachable without auth. body=${bodySnippet}`);
        }
        expect(blocked, `K_anon: headerless request returned ${status} (expected 401/403)`).toBe(true);
        rec(testInfo, { module: MOD, step: 'K_anon', status: 'PASS', http: status, note: 'headerless probe' });
    });

    // ──────────────────────────────────────────────────────────────
    // INVARIANTS
    test('M) Invariant: external_calls=[] for this module batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(
            testInfo, MOD, 'F9C_MSTAFF_full',
            stressState, request, stressTokens.pilot_token,
        );
        expect(ok, 'external_calls invariant failed').toBe(true);
    });

    test('N) Invariant: pilot drift — booking baseline + push token prefix scan', async ({ request, stressTokens }, testInfo) => {
        // Primary gate: pilot bookings drift = 0 (this suite touches NO booking
        // surface, so any mutation = bug).
        const primaryOk = await assertPilotDriftZero(
            testInfo, MOD, request, stressTokens.pilot_token, pilotBookingBaseline,
        );
        expect(primaryOk, 'pilot bookings drift detected → suite mutated pilot').toBe(true);

        // Supplemental: pilot handover list scan — no stress-prefix note should
        // leak into pilot tenant.
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefix_scan', status: 'SKIP', note: 'pilot_token yok' });
            return;
        }
        const r = await callTimed(
            request, 'get', '/api/pms/shift-handover', null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        expect(r.status, 'pilot handover list 5xx').toBeLessThan(500);
        if (r.status === 200 && Array.isArray(r.body?.items)) {
            const leaked = r.body.items.filter(it =>
                typeof it.note === 'string' && it.note.includes(prefix || '__nope__'),
            );
            if (leaked.length > 0) {
                recFinding(testInfo, 'P0', MOD,
                    'PILOT DRIFT (supplemental): stress-prefixed handover found in pilot tenant',
                    `count=${leaked.length} sample_id=${leaked[0].id}`);
            }
            expect(leaked.length, 'pilot drift (supplemental): stress-prefixed handover leaked to pilot').toBe(0);
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefix_scan', status: 'PASS',
                http: r.status, note: `pilot handover count=${r.body.items.length} leaked=0` });
        } else {
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefix_scan', status: 'REVIEW',
                http: r.status, note: 'pilot handover list non-200 — supplemental unverifiable; primary gate authoritative' });
        }

        // Architect Round-1 add: pilot push-subscription channel scan.
        // Stress suite registers push tokens with subscriptions=['operations',
        // 'vip_alerts'] and updates prefs with notification_type='${SUB_PREFIX}_*'.
        // Bunlar pilot tenant'a sızmış olsa pilot user'ın subscription channels
        // listesinde SUB_PREFIX yer alırdı. Backend `push_device_tokens` admin
        // list endpoint expose etmiyor, ancak per-user subscriptions endpoint
        // pilot user'ın kanal listesini döner → supplemental sızıntı dedektörü.
        const sub = await callTimed(
            request, 'get', '/api/notifications/push/subscriptions', null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        if (sub.status === 200 && Array.isArray(sub.body?.channels)) {
            const tainted = sub.body.channels.filter(c =>
                typeof c === 'string' && (c.includes(SUB_PREFIX) || c.includes(prefix || '__nope__')),
            );
            if (tainted.length > 0) {
                recFinding(testInfo, 'P0', MOD,
                    'PILOT DRIFT (push subs): stress-prefixed channel found in pilot user subscriptions',
                    `count=${tainted.length} sample=${tainted[0]}`);
            }
            expect(tainted.length, 'pilot drift (push subs): stress-prefixed channel leaked').toBe(0);
            rec(testInfo, { module: MOD, step: 'N_supplemental_push_sub_scan', status: 'PASS',
                http: sub.status, note: `pilot channels=${sub.body.channels.length} tainted=0` });
        } else {
            rec(testInfo, { module: MOD, step: 'N_supplemental_push_sub_scan', status: 'REVIEW',
                http: sub.status, note: 'pilot push subs non-200 — supplemental unverifiable; primary gate authoritative' });
        }

        // Architect Round-1 add: pilot notification preferences scan.
        // C) PUT prefs writes notification_type=`${SUB_PREFIX}_stress_alert` for
        // stress user — pilot user prefs'inde aynı key görünürse cross-tenant /
        // cross-user mutation söz konusudur (backend prefs collection user_id
        // scoped; tenant_id filter yok — bu ekstra önemli).
        const prefs = await callTimed(
            request, 'get', '/api/notifications/preferences', null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        if (prefs.status === 200 && prefs.body) {
            const blob = JSON.stringify(prefs.body);
            const tainted = blob.includes(SUB_PREFIX);
            if (tainted) {
                recFinding(testInfo, 'P0', MOD,
                    'PILOT DRIFT (prefs): stress SUB_PREFIX found in pilot user notification preferences',
                    `body_snippet=${blob.slice(0, 200)}`);
            }
            expect(tainted, 'pilot drift (prefs): stress-prefixed notification_type leaked').toBe(false);
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefs_scan', status: 'PASS',
                http: prefs.status, note: 'pilot prefs clean of SUB_PREFIX' });
        } else {
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefs_scan', status: 'REVIEW',
                http: prefs.status, note: 'pilot prefs non-200 — supplemental unverifiable; primary gate authoritative' });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // CLEANUP — DELETE handovers (hard delete endpoint exists) +
    //          POST push unregister (idempotent best-effort).
    test.afterAll(async ({}, testInfo) => {
        const cleanupRec = {
            module: MOD,
            step: 'cleanup',
            handovers_attempted: createdHandoverIds.length,
            devices_attempted: registeredDeviceIds.length,
            note: 'DELETE handover + POST push/unregister; idempotent best-effort.',
        };
        try {
            const { request: globalRequest } = await import('@playwright/test');
            const path = (await import('node:path')).default;
            const fs = await import('node:fs');
            const TOKEN_FILE = path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-token.json');
            if (!fs.existsSync(TOKEN_FILE)) {
                cleanupRec.status = 'SKIP';
                cleanupRec.note += ' | token cache yok';
                testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
                return;
            }
            const tok = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf-8')).stress_token;
            const ctx = await globalRequest.newContext({
                extraHTTPHeaders: { Authorization: `Bearer ${tok}` },
            });
            let hvDeleted = 0;
            for (const id of createdHandoverIds) {
                try {
                    const r = await ctx.delete(`/api/pms/shift-handover/${id}`,
                        { timeout: 10_000, failOnStatusCode: false });
                    if (r.status() < 500) hvDeleted += 1;
                } catch { /* idempotent best-effort */ }
            }
            let devUnreg = 0;
            for (const did of registeredDeviceIds) {
                try {
                    const r = await ctx.post('/api/notifications/push/unregister', {
                        data: { device_id: did },
                        timeout: 10_000, failOnStatusCode: false,
                    });
                    if (r.status() < 500) devUnreg += 1;
                } catch { /* idempotent best-effort */ }
            }
            await ctx.dispose();
            cleanupRec.handovers_deleted = hvDeleted;
            cleanupRec.devices_unregistered = devUnreg;
            cleanupRec.status = 'PASS';
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        } catch (e) {
            cleanupRec.status = 'REVIEW';
            cleanupRec.error = String(e?.message || e).slice(0, 200);
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        }
    });
});
