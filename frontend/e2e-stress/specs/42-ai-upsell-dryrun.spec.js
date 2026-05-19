// F8O § 42 — AI Upsell Dry-run Stress.
//
// Scope: AI guest-persona / upsell-candidate surface (read-only) — vendor
// LLM çağrısı tetikletmeden response shape + PII guard + cross-tenant
// isolation doğrula.
//
//   • Setup) module probe + pilot baseline + LLM state probe
//   • A) /api/ai/guest-persona/all-insights — read + items shape + PII guard
//   • B) Cross-tenant insights — pilot_tid forge probe (response'da stress
//        guest_id görünmemeli — leak P0)
//   • C) Forbidden-endpoint source-scan — autopilot/ML train substring'leri
//        spec source'unda LİTERAL geçmemeli (fail-closed)
//   • D) Vendor-call guard — assertNoVendorHttpCall (ai_powered=false)
//   • E) External-calls invariant + pilot_drift=0
//
// Mutlak kurallar:
//   - Pilot tenant'a mutation YOK (read-only)
//   - external_calls=[] (her batch sonu)
//   - failedTests=0, P0=P1=0
//   - Vendor LLM HTTP çağrısı YOK (briefing.ai_powered=false enforce)
//
// Module-blocked doctrine (F8C/D/E/I mirror):
//   - Insights probe non-2xx → moduleBlocked + P2 informational + A/B skip;
//     C (forbidden-scan) + D (vendor guard) + E (pilot_drift) BAĞIMSIZ.
//
// Threat-model anchors:
//   - § Information Disclosure (cross-tenant guest_id/insight leak)
//   - § Spoofing (vendor call → key/cost surface)
//   - § Tampering (autopilot run-cycle / ml train kapalı kapı)

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertPiiMasked,
    assertEndpointNeverCalled, assertNoVendorHttpCall,
    assertAiKeyShapeIsSentinel,
    FORBIDDEN_AI_AUTOPILOT_RUN, FORBIDDEN_AI_AUTOPILOT_SETMODE,
    FORBIDDEN_AI_ML_TRAIN_ALL, FORBIDDEN_AI_ML_TRAIN_FRAGMENT,
} from '../fixtures/stress-helpers.js';

const MOD = 'ai_upsell';

test.describe.configure({ mode: 'serial' });

test.describe('F8O § 42 — AI Upsell Dry-run', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressGuestIds = []; // string[] — stress tenant'ta tanımlı guest id'leri
    let llmState = null;

    test('Setup: prefix + pilot baseline + LLM diagnostics + insights probe', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // LLM diagnostics — vendor surface state (no vendor call).
        const diagR = await callTimed(request, 'get', '/api/ai/diagnostics/llm-state', undefined, stressTokens.stress_token);
        if (diagR.ok) {
            llmState = diagR.body;
            assertAiKeyShapeIsSentinel(testInfo, MOD, llmState);
        } else {
            recFinding(testInfo, 'P2', MOD, 'LLM diagnostics endpoint non-2xx',
                `status=${diagR.status} — vendor-call guard still uses briefing.ai_powered fallback (D step).`);
        }

        // Insights probe (super_admin) — pool baseline.
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/ai/guest-persona/all-insights');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `insights_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'AI guest-persona insights probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B skipped; C/D/E still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason} llm_state=${llmState ? 'ok' : 'unreachable'}` });
            return;
        }
        const insights = probe.body?.insights || probe.body?.items
            || (Array.isArray(probe.body) ? probe.body : []);
        // Stress guest_id pool — sample (max 5).
        stressGuestIds = insights
            .map((it) => it?.guest_id || it?.id)
            .filter((id) => typeof id === 'string' && id.length > 0)
            .slice(0, 5);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} insights_count=${insights.length} stress_guests=${stressGuestIds.length} llm_state=${llmState ? `enabled=${llmState.llm_enabled}` : 'unreachable'} module_blocked=${moduleBlocked}` });
    });

    test('A) Insights read — response shape + PII guard (phone/email/identity_number)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'insights_read', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'get',
            '/api/ai/guest-persona/all-insights', undefined, stressTokens.stress_token);
        samples.push(r.ms);
        const items = r.body?.insights || r.body?.items
            || (Array.isArray(r.body) ? r.body : []);
        const shapeOk = Array.isArray(items);
        const piiOk = assertPiiMasked(testInfo, MOD, r.body, ['phone', 'email', 'identity_number', 'passport_no']);
        const pass = r.ok && shapeOk && piiOk;
        recPerf(testInfo, MOD, 'insights_read', samples, pass);
        rec(testInfo, { module: MOD, step: 'insights_read',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/ai/guest-persona/all-insights',
            note: `status=${r.status} items=${items.length} shape_ok=${shapeOk} pii_ok=${piiOk}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'insights_read', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) Cross-tenant insights — pilot token kendi tenant scope dışına çıkmamalı', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'cross_tenant_insights', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        // Pilot token ile insights çağır — response'da stress tenant guest_id
        // görünmemeli (cross-tenant leak P0). Pilot tenant kendi insight'ını
        // dönebilir ama stress guest_id'leri ASLA görünmemeli.
        const r = await callTimedWithBackoff(request, 'get',
            '/api/ai/guest-persona/all-insights', undefined, stressTokens.pilot_token);
        samples.push(r.ms);
        let leakHits = 0;
        const leakSample = [];
        if (r.ok && stressGuestIds.length > 0) {
            const text = JSON.stringify(r.body || {});
            for (const gid of stressGuestIds) {
                if (gid && text.includes(gid)) {
                    leakHits++;
                    if (leakSample.length < 3) leakSample.push(gid.slice(0, 8) + '…');
                }
            }
        }
        const tenantIsolated = leakHits === 0;
        const pass = (r.ok || r.status === 403 || r.status === 404) && tenantIsolated;
        recPerf(testInfo, MOD, 'cross_tenant_insights', samples, pass);
        rec(testInfo, { module: MOD, step: 'cross_tenant_insights',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/ai/guest-persona/all-insights (pilot token)',
            note: `pilot_status=${r.status} stress_guests_probed=${stressGuestIds.length} leak_hits=${leakHits} sample=${JSON.stringify(leakSample)}` });
        if (!tenantIsolated) {
            recFinding(testInfo, 'P0', MOD,
                'Cross-tenant insight leak — pilot response stress guest_id içeriyor',
                `leak_hits=${leakHits}/${stressGuestIds.length} sample=${JSON.stringify(leakSample)}. Tenant isolation ihlali (threat-model § Information Disclosure).`);
        }
    });

    test('C) Forbidden endpoint source-scan — autopilot/ML train kapalı kapı', async ({}, testInfo) => {
        // Bu test environment-bağımsız; module-blocked olsa bile çalışır.
        const c1 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_RUN);
        const c2 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_SETMODE);
        const c3 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_ML_TRAIN_ALL);
        // ML training fragment guard: forbidden substring helper sabitinden
        // import edilir (concat ile inşa); spec source'unda literal görünmez.
        // Tüm /ml/* training endpoint'leri (rms/persona/maintenance/hk-sched)
        // bu fragmenti içerir ve KAPALI KAPI.
        const c4 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_ML_TRAIN_FRAGMENT);
        const pass = c1 && c2 && c3 && c4;
        rec(testInfo, { module: MOD, step: 'forbidden_source_scan',
            status: pass ? 'PASS' : 'FAIL',
            note: `autopilot_run=${c1} autopilot_setmode=${c2} ml_train_all=${c3} ml_train_fragment=${c4}` });
        expect(pass).toBe(true);
    });

    test('D) Vendor-call guard — briefing.ai_powered=false (heuristic only)', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(60_000);
        // Bu test module-blocked durumda da çalışır — vendor isolation
        // her koşulda doğrulanmalı.
        const pass = await assertNoVendorHttpCall(testInfo, MOD, request, stressTokens.stress_token, 'spec42_post_batch');
        expect(pass).toBe(true);
    });

    test('E) Pilot drift=0 + external_calls invariant', async ({ request, stressTokens, stressState }, testInfo) => {
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
