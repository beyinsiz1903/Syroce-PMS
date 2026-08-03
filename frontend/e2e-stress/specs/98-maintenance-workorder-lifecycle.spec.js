// ─────────────────────────────────────────────────────────────────────────
// F9C § 98 — Maintenance Work Order Lifecycle Deep Stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Scope (rapor §3.1 — maintenance modülü ZERO coverage idi):
//   Backend: backend/domains/pms/maintenance_router.py (prefix=/api)
//   Yüzey:
//     A) POST   /api/maintenance/work-orders          (create)
//     B) GET    /api/maintenance/work-orders          (list + filters)
//     C) PATCH  /api/maintenance/work-orders/{id}     (status / priority)
//     D) Lifecycle: open → in_progress → completed
//     E) GET    /api/maintenance/tasks                (read-only)
//     F) POST/GET /api/maintenance/assets             (asset register)
//     G) POST/GET /api/maintenance/plans              (preventive plan)
//     H) GET    /api/maintenance/repeat-issues        (read-only)
//     I) GET    /api/maintenance/sla-metrics          (read-only)
//     J) IDOR   PATCH work-order with cross-tenant id (must fail / no-op)
//     K) Anon   GET list (must be 401/403, no leak)
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []   (assertNoExternalCallsPostBatch)
//   - pilot mutation = 0    (assertPilotDriftZero — best effort, WO yok ise SKIP)
//   - P0 = P1 = 0; 5xx = 0; PII leak = 0
//   - Tüm mutasyonlar stress-tenant scope; tüm WO description'ları
//     `${prefix}` ile tag'lenir ki cleanup yakalasın (no hard delete).
//   - PATCH status=cancelled idempotent, afterAll soft-cleanup.
//   - Module-blocked doctrine: GET list non-2xx → A-G skip + REVIEW;
//     J/K (security probes) BAĞIMSIZ çalışır.
//
// Reporter satırı: `maintenance_workorder`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'maintenance_workorder';
const SUB_PREFIX = 'F9C_MAINT';
const GAP_MS = 1500;

test.describe.configure({ mode: 'serial' });

test.describe('F9C § 98 — Maintenance Work Order Lifecycle', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBookingBaseline = null;
    let pilotKnownWoId = null;
    const createdWoIds = [];
    const createdAssetIds = [];
    const createdPlanIds = [];

    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }
    function taggedDescription(label) {
        return `${prefix}_${SUB_PREFIX}_${label}`;
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: stress token + module probe + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        // Pilot baseline — assertPilotDriftZero için bookings count snapshot.
        // Pilot token yoksa null (helper SKIP eder).
        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBookingBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;

            // Best-effort: known pilot WO id capture for IDOR probe (J).
            // Pilot maintenance list 200 ise sample id alıp stress_token ile
            // PATCH dene (cross-tenant). non-2xx ise pilot module yok → bogus id fallback.
            try {
                const pilotMaint = await callTimed(
                    request, 'get', '/api/maintenance/work-orders', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (pilotMaint.status === 200 && Array.isArray(pilotMaint.body?.items) && pilotMaint.body.items.length > 0) {
                    pilotKnownWoId = pilotMaint.body.items[0].id || null;
                }
            } catch { /* ignore — J falls back to bogus id */ }
        }

        // Module probe: GET list
        const probe = await callTimed(
            request, 'get', '/api/maintenance/work-orders', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (probe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Maintenance module 5xx on setup probe',
                `GET /api/maintenance/work-orders → ${probe.status}; body=${JSON.stringify(probe.body || {}).slice(0, 200)}`);
            expect(probe.status, 'Maintenance setup 5xx').toBeLessThan(500);
        }
        if (probe.status === 401 || probe.status === 403 || probe.status === 404 || probe.status === 501) {
            moduleBlocked = true;
            blockedReason = `setup_probe_${probe.status}`;
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'REVIEW',
                http: probe.status, note: 'Module blocked / not deployed — A-G SKIP, J/K independent.',
            });
            recFinding(testInfo, 'P2', MOD,
                `Maintenance module blocked at setup (${probe.status})`,
                'A-G lifecycle SKIP; security probes (J/K) bağımsız çalışır.');
            return;
        }
        rec(testInfo, {
            module: MOD, step: 'module_probe', status: 'PASS',
            http: probe.status, note: 'GET list 2xx — lifecycle aktif.',
        });
    });

    // ──────────────────────────────────────────────────────────────
    // A) CREATE
    test('A) Create work order — stress-tenant scoped', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'A_create', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const payload = {
            room_number: '9001',
            issue_type: 'plumbing',
            priority: 'normal',
            source: 'staff',
            description: taggedDescription('A_create'),
        };
        const r = await callTimed(
            request, 'post', '/api/maintenance/work-orders', payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('A_create') } },
        );
        recPerf(testInfo, MOD, 'A_create', [r.ms], r.status >= 200 && r.status < 300);

        if (r.status === 404 || r.status === 403 || r.status === 501) {
            rec(testInfo, { module: MOD, step: 'A_create', status: 'REVIEW', http: r.status, note: 'create endpoint not deployed' });
            recFinding(testInfo, 'P2', MOD, 'POST /api/maintenance/work-orders not deployed', `status=${r.status}`);
            return;
        }
        expect(r.status, `A_create unexpected status=${r.status}`).toBeLessThan(500);
        expect(r.status, `A_create non-2xx status=${r.status}`).toBeGreaterThanOrEqual(200);
        expect(r.status).toBeLessThan(300);

        const wo = r.body || {};
        expect(wo.id, 'created WO id yok').toBeTruthy();
        expect(wo.tenant_id, 'WO tenant_id yok').toBeTruthy();
        createdWoIds.push(wo.id);

        rec(testInfo, {
            module: MOD, step: 'A_create', status: 'PASS',
            http: r.status, note: `created wo_id=${wo.id}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // B) LIST + FILTER
    test('B) List + filter by status=open', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'B_list', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/maintenance/work-orders?status=open', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `B_list 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `B_list non-200 status=${r.status}`, `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'B_list', status: 'REVIEW', http: r.status });
            return;
        }
        const items = (r.body && r.body.items) || [];
        expect(Array.isArray(items), 'B_list items array değil').toBe(true);

        // Tenant scoping invariant: hiçbir item başka tenant'a ait olmamalı
        for (const it of items) {
            expect(it.tenant_id, `B_list item tenant_id yok: ${JSON.stringify(it).slice(0, 100)}`).toBeTruthy();
        }
        rec(testInfo, {
            module: MOD, step: 'B_list', status: 'PASS',
            http: r.status, note: `items=${items.length}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // C+D) PATCH status lifecycle: open → in_progress → completed
    test('C+D) Lifecycle: open → in_progress → completed', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdWoIds.length === 0 ? 'no_wo_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'CD_lifecycle', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const woId = createdWoIds[0];
        const transitions = [
            { to: 'in_progress', op: 'C_in_progress' },
            { to: 'completed', op: 'D_completed' },
        ];
        for (const t of transitions) {
            const r = await callTimed(
                request, 'patch',
                `/api/maintenance/work-orders/${woId}?status=${t.to}`,
                null,
                stressTokens.stress_token,
                { timeout: 10_000, headers: { 'Idempotency-Key': idemKey(t.op) } },
            );
            expect(r.status, `${t.op} 5xx status=${r.status}`).toBeLessThan(500);
            if (r.status !== 200) {
                recFinding(testInfo, 'P2', MOD,
                    `Lifecycle transition ${t.to} non-200`,
                    `wo_id=${woId} status=${r.status} body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
                rec(testInfo, { module: MOD, step: t.op, status: 'REVIEW', http: r.status });
                continue;
            }
            expect(r.body?.updated, `${t.op} response updated flag yok`).toBe(true);
            rec(testInfo, { module: MOD, step: t.op, status: 'PASS', http: r.status });
            await gap(500);
        }
    });

    // ──────────────────────────────────────────────────────────────
    // E) Read-only: tasks
    test('E) GET /api/maintenance/tasks read-only', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'E_tasks', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/maintenance/tasks', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `E_tasks 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `tasks endpoint non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'E_tasks', status: 'REVIEW', http: r.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'E_tasks', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // F) Assets create+list
    test('F) POST+GET /api/maintenance/assets', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'F_assets', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        // Payload contract: MaintenanceAsset (backend/models/schemas/rooms.py)
        // requires name + asset_type; frontend MaintenanceAssets.jsx aynı
        // alanları gönderir. Önceki asset_tag/category alanları şema dışıydı
        // (extra=ignore → name/asset_type missing → 422).
        const post = await callTimed(
            request, 'post', '/api/maintenance/assets',
            {
                name: taggedDescription('F_asset'),
                asset_type: 'hvac',
                location: 'Stress Test Lab',
            },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('F_asset') } },
        );
        expect(post.status, `F_asset POST 5xx status=${post.status}`).toBeLessThan(500);
        if (post.status >= 200 && post.status < 300 && post.body?.id) {
            createdAssetIds.push(post.body.id);
            rec(testInfo, { module: MOD, step: 'F_asset_post', status: 'PASS', http: post.status });
        } else if ([404, 422, 501].includes(post.status)) {
            recFinding(testInfo, 'P2', MOD, `assets POST non-2xx status=${post.status}`,
                `body=${JSON.stringify(post.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'F_asset_post', status: 'REVIEW', http: post.status });
        } else {
            rec(testInfo, { module: MOD, step: 'F_asset_post', status: 'REVIEW', http: post.status });
        }

        const get = await callTimed(
            request, 'get', '/api/maintenance/assets', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(get.status, `F_asset GET 5xx`).toBeLessThan(500);
        rec(testInfo, { module: MOD, step: 'F_asset_get', status: get.status === 200 ? 'PASS' : 'REVIEW', http: get.status });
    });

    // ──────────────────────────────────────────────────────────────
    // G) Plans create+list
    test('G) POST+GET /api/maintenance/plans', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'G_plans', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        // Payload contract: PreventiveMaintenancePlan requires
        // frequency_type (days/weeks/months) + frequency_value + next_due_date;
        // frontend MaintenancePlans.jsx aynı alanları gönderir. Önceki
        // frequency:'monthly' alanı şema dışıydı → 422.
        const post = await callTimed(
            request, 'post', '/api/maintenance/plans',
            {
                frequency_type: 'months',
                frequency_value: 1,
                next_due_date: new Date(Date.now() + 30 * 86_400_000).toISOString(),
                description: taggedDescription('G_plan'),
            },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('G_plan') } },
        );
        expect(post.status, `G_plan POST 5xx`).toBeLessThan(500);
        if (post.status >= 200 && post.status < 300 && post.body?.id) {
            createdPlanIds.push(post.body.id);
            rec(testInfo, { module: MOD, step: 'G_plan_post', status: 'PASS', http: post.status });
        } else if ([404, 422, 501].includes(post.status)) {
            recFinding(testInfo, 'P2', MOD, `plans POST non-2xx status=${post.status}`, '');
            rec(testInfo, { module: MOD, step: 'G_plan_post', status: 'REVIEW', http: post.status });
        } else {
            rec(testInfo, { module: MOD, step: 'G_plan_post', status: 'REVIEW', http: post.status });
        }

        const get = await callTimed(
            request, 'get', '/api/maintenance/plans', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(get.status, `G_plan GET 5xx`).toBeLessThan(500);
        rec(testInfo, { module: MOD, step: 'G_plan_get', status: get.status === 200 ? 'PASS' : 'REVIEW', http: get.status });
    });

    // ──────────────────────────────────────────────────────────────
    // H) Repeat issues
    test('H) GET /api/maintenance/repeat-issues read-only', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'H_repeat', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/maintenance/repeat-issues', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `H_repeat 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `repeat-issues non-200 status=${r.status}`, '');
        }
        rec(testInfo, { module: MOD, step: 'H_repeat', status: r.status === 200 ? 'PASS' : 'REVIEW', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // I) SLA metrics
    test('I) GET /api/maintenance/sla-metrics read-only', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'I_sla', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/maintenance/sla-metrics', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `I_sla 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `sla-metrics non-200 status=${r.status}`, '');
        }
        rec(testInfo, { module: MOD, step: 'I_sla', status: r.status === 200 ? 'PASS' : 'REVIEW', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // J) SECURITY: IDOR — cross-tenant PATCH (must be no-op or 404)
    // Always-on; module-blocked durumda da çalışır.
    test('J) IDOR: cross-tenant PATCH → no mutation', async ({ request, stressTokens }, testInfo) => {
        // Round-2 (architect): tercihen REAL pilot WO id ile dene (gerçek IDOR
        // boundary'sini test eder). Setup'ta pilotKnownWoId varsa onu kullan;
        // yoksa bogus UUID fallback (en azından "nonexistent → no-op" doğrular).
        const targetId = pilotKnownWoId || `cross-tenant-${cryptoRandomUUID()}`;
        const probeKind = pilotKnownWoId ? 'real_pilot_wo_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'patch',
            `/api/maintenance/work-orders/${targetId}?status=completed`,
            null,
            stressTokens.stress_token,
            { timeout: 10_000 },
        );
        expect(r.status, `J_idor 5xx`).toBeLessThan(500);
        // Doctrine: 200+updated=false VEYA 404/403/401. ASLA 200+updated=true.
        if (r.status === 200) {
            const updated = r.body?.updated;
            if (updated === true) {
                recFinding(testInfo, 'P0', MOD,
                    `IDOR boundary breach: cross-tenant PATCH succeeded (${probeKind})`,
                    `target_id=${targetId} response=${JSON.stringify(r.body).slice(0, 200)}`);
            }
            expect(updated, `J_idor: PATCH with ${probeKind}=${targetId} returned updated=true → cross-tenant tampering`).toBe(false);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'PASS', http: r.status, note: `${probeKind} → updated=false` });
        } else if ([404, 403, 401].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'PASS', http: r.status, note: `${probeKind} rejected ${r.status}` });
        } else {
            recFinding(testInfo, 'P2', MOD, `IDOR probe unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // K) SECURITY: Anonymous list — must be blocked
    // Round-2 (architect): raw request.get + NO Authorization header
    // (callTimed token=null "Bearer null" gönderir — invalid token probe olur,
    // strict anonymous değil). Burada gerçek headerless probe yapıyoruz.
    test('K) Anonymous (headerless) GET → 401/403', async ({ request }, testInfo) => {
        let status = 0;
        let bodySnippet = '';
        try {
            const r = await request.get('/api/maintenance/work-orders', {
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
                `Anonymous GET maintenance work-orders not blocked (status=${status})`,
                `PUBLIC SURFACE LEAK — tenant data may be reachable without auth. body=${bodySnippet}`);
        }
        expect(blocked, `K_anon: headerless request returned ${status} (expected 401/403)`).toBe(true);
        rec(testInfo, { module: MOD, step: 'K_anon', status: 'PASS', http: status, note: 'headerless probe' });
    });

    // ──────────────────────────────────────────────────────────────
    // INVARIANTS
    test('M) Invariant: external_calls=[] for this module batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(
            testInfo, MOD, 'F9C_MAINT_full',
            stressState, request, stressTokens.pilot_token,
        );
        expect(ok, 'external_calls invariant failed').toBe(true);
    });

    test('N) Invariant: pilot drift — booking-count baseline + prefix scan', async ({ request, stressTokens }, testInfo) => {
        // Round-2 (architect): primary gate = assertPilotDriftZero (booking count
        // baseline vs after). Stress maintenance suite pilot bookings'i hiç
        // değiştirmemeli. Secondary supplemental = pilot maint list prefix scan.
        const primaryOk = await assertPilotDriftZero(
            testInfo, MOD, request, stressTokens.pilot_token, pilotBookingBaseline,
        );
        expect(primaryOk, 'pilot bookings drift detected → suite mutated pilot').toBe(true);

        // Supplemental: pilot maintenance list prefix scan (best-effort).
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefix_scan', status: 'SKIP', note: 'pilot_token yok' });
            return;
        }
        const r = await callTimed(
            request, 'get', '/api/maintenance/work-orders', null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        expect(r.status, 'pilot maintenance list 5xx').toBeLessThan(500);
        if (r.status === 200 && Array.isArray(r.body?.items)) {
            const leaked = r.body.items.filter(it =>
                typeof it.description === 'string' && it.description.includes(prefix || '__nope__'),
            );
            if (leaked.length > 0) {
                recFinding(testInfo, 'P0', MOD,
                    'PILOT DRIFT (supplemental): stress-prefixed WO found in pilot tenant',
                    `count=${leaked.length} sample_id=${leaked[0].id}`);
            }
            expect(leaked.length, 'pilot drift (supplemental): stress-prefixed WO leaked to pilot').toBe(0);
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefix_scan', status: 'PASS',
                http: r.status, note: `pilot maint count=${r.body.items.length} leaked=0` });
        } else {
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefix_scan', status: 'REVIEW',
                http: r.status, note: 'pilot maint list non-200 — supplemental unverifiable; primary gate authoritative' });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // CLEANUP — idempotent soft cancel (no hard DELETE endpoint)
    test.afterAll(async ({}, testInfo) => {
        const cleanupRec = {
            module: MOD,
            step: 'cleanup',
            wo_attempted: createdWoIds.length,
            assets_left: createdAssetIds.length,
            plans_left: createdPlanIds.length,
            note: 'soft-cancel via PATCH; assets/plans tagged with data_prefix for external cleanup script',
        };
        // PATCH-based cancel idempotent: aynı id'ye birden çok kez çalsa da DB'de
        // tek bir state'e yakınsar. afterAll içinde ayrı request fixture yok →
        // global Playwright request kullan.
        try {
            const { request: globalRequest } = await import('@playwright/test');
            const TOKEN_FILE = (await import('node:path')).default.join(
                process.cwd(), 'e2e-stress', '.auth', 'stress-token.json');
            const fs = await import('node:fs');
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
            let cancelled = 0;
            for (const id of createdWoIds) {
                try {
                    const r = await ctx.patch(
                        `/api/maintenance/work-orders/${id}?status=cancelled`,
                        { timeout: 10_000, failOnStatusCode: false },
                    );
                    if (r.status() < 500) cancelled += 1;
                } catch { /* idempotent best-effort */ }
            }
            await ctx.dispose();
            cleanupRec.cancelled = cancelled;
            cleanupRec.status = 'PASS';
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        } catch (e) {
            cleanupRec.status = 'REVIEW';
            cleanupRec.error = String(e?.message || e).slice(0, 200);
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        }
    });
});
