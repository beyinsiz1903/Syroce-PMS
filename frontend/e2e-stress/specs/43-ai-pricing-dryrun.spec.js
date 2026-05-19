// F8O § 43 — AI Dynamic Pricing Dry-run Stress.
//
// Scope: AI rate recommendation surface (read-only) — autopilot run-cycle /
// set-mode / ML training KAPALI KAPI (forbidden source-scan). Recommend-rates
// response shape + cross-tenant guard + vendor-call isolation.
//
//   • Setup) prefix + pilot baseline + autopilot/status probe + recommend probe
//   • A) /api/ai/recommend-rates — 14-day window, shape + invariants
//   • B) /api/autopilot/status — read-only mode bilgisi (mutation YOK)
//   • C) Cross-tenant pricing — pilot token rec drift guard (response'ta
//        stress tenant room_type leak P0 değil ama drift > 0 ise REVIEW)
//   • D) Forbidden source-scan (run-cycle / set-mode / ML train)
//   • E) Vendor-call guard
//   • F) Pilot drift=0 + external_calls=[]
//
// Mutlak kurallar (F8O):
//   - Pilot mutation YOK
//   - Autopilot run-cycle / set-mode / ML train ASLA çağrılmaz (source-scan)
//   - Vendor LLM HTTP çağrısı YOK
//   - external_calls=[], failedTests=0, P0=P1=0
//
// Module-blocked doctrine:
//   - recommend-rates POST 403/404 → moduleBlocked + A/B/C skip;
//     D (forbidden-scan) + E (vendor guard) + F (pilot_drift) BAĞIMSIZ.
//
// Threat-model anchors:
//   - § Tampering (autopilot mode değiştirme → rate publish riski)
//   - § Information Disclosure (cross-tenant rate insight leak)
//   - § DoS (recommend-rates uzun period — perf gözlem)

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
    assertEndpointNeverCalled, assertNoVendorHttpCall,
    assertAiKeyShapeIsSentinel, assertAiDryRunEnvGuards,
    snapshotAiCallCount,
    FORBIDDEN_AI_AUTOPILOT_RUN, FORBIDDEN_AI_AUTOPILOT_SETMODE,
    FORBIDDEN_AI_ML_TRAIN_ALL, FORBIDDEN_AI_ML_TRAIN_FRAGMENT,
    FORBIDDEN_AI_RATE_APPLY, FORBIDDEN_AI_AUTOPILOT_EXECUTE,
    FORBIDDEN_AI_PRICING_PUBLISH,
} from '../fixtures/stress-helpers.js';

const MOD = 'ai_pricing';

function isoDate(d) { return d.toISOString().slice(0, 10); }
function pricingWindow(days = 14) {
    const start = new Date();
    start.setUTCDate(start.getUTCDate() + 7); // future-only, seed çakışmasından kaçın
    const end = new Date(start);
    end.setUTCDate(end.getUTCDate() + days);
    return { start: isoDate(start), end: isoDate(end) };
}

test.describe.configure({ mode: 'serial' });

test.describe('F8O § 43 — AI Dynamic Pricing Dry-run', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressRoomTypes = [];
    let aiCallBaseline = null;

    test('Setup: prefix + pilot baseline + LLM diagnostics + env guards + recommend probe', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        // Snapshot authoritative ledger baseline + run env/key guards.
        const snap = await snapshotAiCallCount(request, stressTokens.pilot_token);
        if (!snap.ok) {
            recFinding(testInfo, 'P0', MOD, 'LLM diagnostics endpoint non-2xx — ledger baseline alınamadı',
                `status=${snap.status} — F8O mutlak kuralı: authoritative ledger zorunlu.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
                note: `ledger_baseline_unavailable status=${snap.status}` });
            expect(snap.ok, `LLM diagnostics endpoint must be reachable (got status=${snap.status})`).toBe(true);
            return;
        }
        aiCallBaseline = snap.count;
        const envOk = assertAiDryRunEnvGuards(testInfo, MOD, snap.body);
        const keyOk = assertAiKeyShapeIsSentinel(testInfo, MOD, snap.body);
        expect(envOk, 'E2E_AI_DRY_RUN / E2E_EXTERNAL_DRY_RUN env guards must pass').toBe(true);
        expect(keyOk, 'API key shape must be sentinel').toBe(true);
        const win = pricingWindow(14);
        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/ai/recommend-rates?start_date=${win.start}&end_date=${win.end}`,
            { method: 'post' });
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `recommend_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'AI recommend-rates probe non-2xx',
                `status=${probe.status} reason=${probe.reason} window=${win.start}..${win.end} — A/B/C skipped; D/E/F enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        const recs = probe.body?.recommendations
            || (Array.isArray(probe.body) ? probe.body : []);
        stressRoomTypes = [...new Set(recs.map((r) => r?.room_type).filter(Boolean))].slice(0, 5);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} recs=${recs.length} room_types=${stressRoomTypes.length} window=${win.start}..${win.end}` });
    });

    test('A) recommend-rates — 14-day window shape + invariants (no apply)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'recommend_rates', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const win = pricingWindow(14);
        const samples = [];
        const r = await callTimedWithBackoff(request, 'post',
            `/api/ai/recommend-rates?start_date=${win.start}&end_date=${win.end}`,
            undefined, stressTokens.stress_token, { timeout: 60_000 });
        samples.push(r.ms);
        const recs = r.body?.recommendations
            || (Array.isArray(r.body) ? r.body : []);
        const summary = r.body?.summary || {};
        // Shape invariants: array + her item'da room_type + recommended_rate.
        let invariantViolations = 0;
        for (const rec of recs.slice(0, 50)) {
            if (!rec || typeof rec !== 'object') { invariantViolations++; continue; }
            if (!rec.room_type) invariantViolations++;
            if (typeof rec.recommended_rate !== 'number' && typeof rec.recommended_rate !== 'string') invariantViolations++;
            // Confidence 0..1 range.
            if (rec.confidence != null && (rec.confidence < 0 || rec.confidence > 1)) invariantViolations++;
        }
        const pass = r.ok && Array.isArray(recs) && invariantViolations === 0;
        recPerf(testInfo, MOD, 'recommend_rates', samples, pass);
        rec(testInfo, { module: MOD, step: 'recommend_rates',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/ai/recommend-rates',
            note: `status=${r.status} recs=${recs.length} invariant_viol=${invariantViolations} summary=${JSON.stringify(summary).slice(0, 120)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'recommend_rates', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) autopilot/status — read-only mode bilgisi (mutation YOK)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'autopilot_status_read', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimed(request, 'get', '/api/autopilot/status', undefined, stressTokens.stress_token);
        samples.push(r.ms);
        const modeOk = r.ok && r.body && typeof r.body === 'object' && 'mode' in r.body;
        recPerf(testInfo, MOD, 'autopilot_status_read', samples, r.ok);
        rec(testInfo, { module: MOD, step: 'autopilot_status_read',
            status: (r.ok && modeOk) ? 'PASS' : 'REVIEW',
            endpoint: '/api/autopilot/status',
            note: `status=${r.status} mode=${r.body?.mode || 'n/a'} active=${r.body?.active}` });
    });

    test('C) Cross-tenant pricing — pilot token kendi tenant scope dışına taşmamalı', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked || stressRoomTypes.length === 0) {
            rec(testInfo, { module: MOD, step: 'cross_tenant_pricing', status: 'SKIP', note: 'module blocked or no room types' });
            test.skip(true, 'module blocked or empty pool');
            return;
        }
        const win = pricingWindow(7);
        const r = await callTimedWithBackoff(request, 'post',
            `/api/ai/recommend-rates?start_date=${win.start}&end_date=${win.end}`,
            undefined, stressTokens.pilot_token, { timeout: 30_000 });
        // Pilot response stress room_type isim leak içermemeli — eğer
        // room_type adlandırma scheme'i tenant-spesifik (prefix'li) ise
        // leak yakalanır. Generic adlar ("standard", "deluxe") false-positive
        // olur — bu yüzden sadece prefix'li adları kontrol et.
        let leakHits = 0;
        const leakSample = [];
        if (r.ok && prefix) {
            const text = JSON.stringify(r.body || {});
            for (const rt of stressRoomTypes) {
                if (rt && typeof rt === 'string' && rt.startsWith(prefix) && text.includes(rt)) {
                    leakHits++;
                    if (leakSample.length < 3) leakSample.push(rt);
                }
            }
        }
        const tenantIsolated = leakHits === 0;
        const pass = (r.ok || r.status === 403 || r.status === 404) && tenantIsolated;
        rec(testInfo, { module: MOD, step: 'cross_tenant_pricing',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/ai/recommend-rates (pilot token)',
            note: `pilot_status=${r.status} prefix=${prefix} probed_room_types=${stressRoomTypes.length} leak_hits=${leakHits} sample=${JSON.stringify(leakSample)}` });
        if (!tenantIsolated) {
            recFinding(testInfo, 'P0', MOD,
                'Cross-tenant pricing leak — pilot response stress prefix\'li room_type içeriyor',
                `leak_hits=${leakHits} sample=${JSON.stringify(leakSample)}. Tenant isolation ihlali (threat-model § Information Disclosure).`);
        }
    });

    test('D) Forbidden endpoint source-scan — autopilot/ML/pricing/rate kapalı kapı', async ({}, testInfo) => {
        const c1 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_RUN);
        const c2 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_SETMODE);
        const c3 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_ML_TRAIN_ALL);
        const c4 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_ML_TRAIN_FRAGMENT);
        // Task #206 — rate/apply, autopilot/execute, pricing/publish ASLA.
        const c5 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_RATE_APPLY);
        const c6 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_EXECUTE);
        const c7 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_PRICING_PUBLISH);
        const pass = c1 && c2 && c3 && c4 && c5 && c6 && c7;
        rec(testInfo, { module: MOD, step: 'forbidden_source_scan',
            status: pass ? 'PASS' : 'FAIL',
            note: `autopilot_run=${c1} autopilot_setmode=${c2} ml_train_all=${c3} ml_train_fragment=${c4} rate_apply=${c5} autopilot_execute=${c6} pricing_publish=${c7}` });
        expect(pass).toBe(true);
    });

    test('E) Vendor-call guard — authoritative ledger delta + briefing.ai_powered=false', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(60_000);
        const pass = await assertNoVendorHttpCall(testInfo, MOD, request, stressTokens.pilot_token, aiCallBaseline, 'spec43_post_batch');
        expect(pass).toBe(true);
    });

    test('F) Pilot drift=0 + external_calls invariant', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(30_000);
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants',
            status: (driftOk && extOk) ? 'PASS' : 'FAIL',
            note: `drift_ok=${driftOk} external_calls_ok=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});
