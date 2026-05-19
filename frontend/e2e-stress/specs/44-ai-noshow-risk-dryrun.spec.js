// F8O § 44 — AI No-Show Risk Dry-run Stress.
//
// Scope: No-show prediction surface (GET /api/predictions/no-shows + POST
// /api/ai/predict-no-shows) — read-only risk scoring + PII guard +
// cross-tenant isolation. ML training KAPALI KAPI.
//
//   • Setup) prefix + pilot baseline + predictions probe
//   • A) GET /api/predictions/no-shows — read + shape
//   • B) POST /api/ai/predict-no-shows — risk scoring + PII guard
//        (guest_name maskeli olmayabilir — sadece phone/email/identity sahası
//        kontrol edilir; guest_name informational)
//   • C) Cross-tenant — pilot token stress booking_id leak guard
//   • D) Forbidden source-scan (autopilot + ML train)
//   • E) Vendor-call guard
//   • F) Pilot drift=0 + external_calls=[]
//
// Mutlak kurallar (F8O):
//   - Pilot mutation YOK
//   - ML training endpoint'leri ASLA çağrılmaz (forbidden source-scan,
//     helper sabitleri concat ile inşa edilir)
//   - Vendor LLM HTTP çağrısı YOK
//   - external_calls=[], failedTests=0, P0=P1=0
//
// Module-blocked doctrine:
//   - GET no-shows probe non-2xx → moduleBlocked + A/B/C skip;
//     D/E/F BAĞIMSIZ çalışır.
//
// Threat-model anchors:
//   - § Information Disclosure (cross-tenant booking_id / guest_name leak)
//   - § Spoofing (vendor call)
//   - § Tampering (ML train kapalı kapı — model integrity riski)

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertPiiMasked,
    assertEndpointNeverCalled, assertNoVendorHttpCall,
    FORBIDDEN_AI_AUTOPILOT_RUN, FORBIDDEN_AI_AUTOPILOT_SETMODE,
    FORBIDDEN_AI_ML_TRAIN_ALL, FORBIDDEN_AI_ML_TRAIN_FRAGMENT,
} from '../fixtures/stress-helpers.js';

const MOD = 'ai_noshow_risk';

function targetDate(daysAhead = 1) {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + daysAhead);
    return d.toISOString().slice(0, 10);
}

test.describe.configure({ mode: 'serial' });

test.describe('F8O § 44 — AI No-Show Risk Dry-run', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressBookingIds = [];

    test('Setup: prefix + pilot baseline + no-show probe', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/predictions/no-shows?target_date=${targetDate(1)}`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `noshow_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'No-show predictions probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped; D/E/F enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        const preds = probe.body?.predictions || [];
        stressBookingIds = preds
            .map((p) => p?.booking_id)
            .filter((id) => typeof id === 'string' && id.length > 0)
            .slice(0, 5);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} preds=${preds.length} stress_bookings=${stressBookingIds.length}` });
    });

    test('A) GET /api/predictions/no-shows — read + shape', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'noshow_read', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'get',
            `/api/predictions/no-shows?target_date=${targetDate(1)}`,
            undefined, stressTokens.stress_token);
        samples.push(r.ms);
        const preds = r.body?.predictions || [];
        const shapeOk = Array.isArray(preds);
        const pass = r.ok && shapeOk;
        recPerf(testInfo, MOD, 'noshow_read', samples, pass);
        rec(testInfo, { module: MOD, step: 'noshow_read',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/predictions/no-shows',
            note: `status=${r.status} preds=${preds.length} shape_ok=${shapeOk} high_risk=${r.body?.high_risk_count}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'noshow_read', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) POST /api/ai/predict-no-shows — risk scoring + PII guard', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'noshow_detailed', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'post',
            `/api/ai/predict-no-shows?date=${targetDate(1)}`,
            undefined, stressTokens.stress_token, { timeout: 60_000 });
        samples.push(r.ms);
        if (r.status === 403 || r.status === 404) {
            recFinding(testInfo, 'P2', MOD, 'Detailed no-show prediction RBAC blocked',
                `status=${r.status} — require_op(view_reports) gate; super_admin normalde bypass eder.`);
            rec(testInfo, { module: MOD, step: 'noshow_detailed', status: 'SKIP',
                note: `rbac_blocked status=${r.status}` });
            test.skip(true, 'RBAC blocked');
            return;
        }
        const preds = r.body?.predictions || [];
        // Risk score invariants: 0..100 + risk_level ∈ {low,medium,high}.
        let invariantViolations = 0;
        const RISK_LEVELS = new Set(['low', 'medium', 'high']);
        for (const p of preds.slice(0, 50)) {
            if (!p || typeof p !== 'object') { invariantViolations++; continue; }
            if (typeof p.risk_score !== 'number' || p.risk_score < 0 || p.risk_score > 100) invariantViolations++;
            if (p.risk_level && !RISK_LEVELS.has(p.risk_level)) invariantViolations++;
        }
        // PII guard — predictions payload guest_name içerebilir (mock data),
        // ama phone/email/identity_number/passport_no plain dönmemeli.
        const piiOk = assertPiiMasked(testInfo, MOD, { items: preds }, ['phone', 'email', 'identity_number', 'passport_no']);
        const pass = r.ok && invariantViolations === 0 && piiOk;
        recPerf(testInfo, MOD, 'noshow_detailed', samples, pass);
        rec(testInfo, { module: MOD, step: 'noshow_detailed',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/ai/predict-no-shows',
            note: `status=${r.status} preds=${preds.length} invariant_viol=${invariantViolations} pii_ok=${piiOk} summary=${JSON.stringify(r.body?.summary || {}).slice(0, 120)}` });
    });

    test('C) Cross-tenant — pilot token stress booking_id leak guard', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked || stressBookingIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'cross_tenant_noshow', status: 'SKIP', note: 'module blocked or no stress bookings' });
            test.skip(true, 'module blocked or empty pool');
            return;
        }
        const r = await callTimedWithBackoff(request, 'get',
            `/api/predictions/no-shows?target_date=${targetDate(1)}`,
            undefined, stressTokens.pilot_token);
        let leakHits = 0;
        const leakSample = [];
        if (r.ok) {
            const text = JSON.stringify(r.body || {});
            for (const bid of stressBookingIds) {
                if (bid && text.includes(bid)) {
                    leakHits++;
                    if (leakSample.length < 3) leakSample.push(bid.slice(0, 8) + '…');
                }
            }
        }
        const tenantIsolated = leakHits === 0;
        const pass = (r.ok || r.status === 403 || r.status === 404) && tenantIsolated;
        rec(testInfo, { module: MOD, step: 'cross_tenant_noshow',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/predictions/no-shows (pilot token)',
            note: `pilot_status=${r.status} stress_bookings_probed=${stressBookingIds.length} leak_hits=${leakHits} sample=${JSON.stringify(leakSample)}` });
        if (!tenantIsolated) {
            recFinding(testInfo, 'P0', MOD,
                'Cross-tenant no-show leak — pilot response stress booking_id içeriyor',
                `leak_hits=${leakHits}/${stressBookingIds.length} sample=${JSON.stringify(leakSample)}. Tenant isolation ihlali.`);
        }
    });

    test('D) Forbidden endpoint source-scan — autopilot/ML train kapalı kapı', async ({}, testInfo) => {
        const c1 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_RUN);
        const c2 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_SETMODE);
        const c3 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_ML_TRAIN_ALL);
        const c4 = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_ML_TRAIN_FRAGMENT);
        const pass = c1 && c2 && c3 && c4;
        rec(testInfo, { module: MOD, step: 'forbidden_source_scan',
            status: pass ? 'PASS' : 'FAIL',
            note: `autopilot_run=${c1} autopilot_setmode=${c2} ml_train_all=${c3} ml_train_fragment=${c4}` });
        expect(pass).toBe(true);
    });

    test('E) Vendor-call guard — briefing.ai_powered=false', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(60_000);
        const pass = await assertNoVendorHttpCall(testInfo, MOD, request, stressTokens.stress_token, 'spec44_post_batch');
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
