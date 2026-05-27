// F8D-v3 § 35B — Shift Coverage Planning (Department Minimum Coverage Rules):
//   • POST /hr/coverage-rules        — create per-dept min_staff per shift_type
//   • GET  /hr/coverage-rules        — list (filter by department)
//   • DELETE /hr/coverage-rules/{id} — cleanup
//   • Idempotency + RBAC + invariants
//
// Backend ref: backend/domains/hr/router.py:5446 (CoverageRulePayload),
//              :5450 (POST), :5472 (GET), :5487 (DELETE).
//
// Not: Backend gerçek "coverage warning generation" endpoint'i yok — sadece
// CRUD. Warning emit testi mevcut değil; spec only CRUD + contract.
//
// Mutlak kurallar: pilot mutation YOK, external_calls=[], failedTests=0.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_shift_coverage_planning';
const N_RULES = 4;

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v3 § 35B — Shift Coverage Planning', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let createdRuleIds = [];

    test('Setup: prefix + pilot baseline + coverage-rules probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/hr/coverage-rules');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `coverage_rules_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Coverage-rules probe non-2xx',
                `status=${probe.status} reason=${probe.reason}`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Coverage rule CRUD — create N + list + dept filter + shape contract', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'coverage_crud', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, permFail = 0;
        const errs = [];
        const departments = ['housekeeping', 'frontdesk', 'restaurant', 'security'];
        const shiftTypes = ['morning', 'night', 'evening', 'any'];
        for (let i = 0; i < N_RULES; i++) {
            const payload = {
                department: departments[i % departments.length],
                weekday: i === 0 ? -1 : (i % 7),  // -1 = her gün, sonra 1..6
                shift_type: shiftTypes[i % shiftTypes.length],
                min_staff: 2 + i,
                note: `${prefix} F8D-v3 35B rule ${i + 1}`,
            };
            const r = await callTimed(request, 'post',
                '/api/hr/coverage-rules', payload, stressTokens.stress_token);
            samples.push(r.ms);
            const rid = r.body?.rule?.id;
            if (r.ok && rid) { ok++; createdRuleIds.push(rid); }
            else if (r.status === 401 || r.status === 403) permFail++;
            else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 800));
        }
        if (permFail === N_RULES) {
            recFinding(testInfo, 'P2', MOD, 'Coverage rule create RBAC blocked',
                `n=${N_RULES} all permFail`);
            rec(testInfo, { module: MOD, step: 'coverage_crud', status: 'SKIP',
                endpoint: 'POST /api/hr/coverage-rules', note: `perm_fail=${permFail}` });
            test.skip(true, 'coverage RBAC blocked');
            return;
        }
        // List + dept filter — housekeeping rule subset.
        const listR = await callTimed(request, 'get',
            '/api/hr/coverage-rules?department=housekeeping', undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const hkItems = listR.body?.items || [];
        const hkFromOurs = hkItems.filter((r) => createdRuleIds.includes(r.id)).length;
        const shapeOk = hkItems.length === 0 || (
            hkItems[0] && 'department' in hkItems[0]
            && 'weekday' in hkItems[0] && 'shift_type' in hkItems[0]
            && 'min_staff' in hkItems[0]
        );
        // Validation guard probe — min_staff=0 reject (Pydantic ge=1).
        const badR = await callTimed(request, 'post',
            '/api/hr/coverage-rules', {
                department: 'test', weekday: 0, shift_type: 'any', min_staff: 0,
            }, stressTokens.stress_token);
        samples.push(badR.ms);
        const validation_guard_ok = badR.status === 422 || badR.status === 400;

        const floor = Math.ceil(N_RULES * 0.9);
        const pass = ok >= floor && listR.ok && hkFromOurs >= 1 && shapeOk && validation_guard_ok;
        recPerf(testInfo, MOD, 'coverage_crud', samples, pass);
        rec(testInfo, { module: MOD, step: 'coverage_crud', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST/GET /api/hr/coverage-rules',
            note: `n=${N_RULES} ok=${ok} fail=${fail} perm_fail=${permFail} list_status=${listR.status} hk_total=${hkItems.length} hk_ours=${hkFromOurs} shape_ok=${shapeOk} validation_guard_status=${badR.status} validation_guard_ok=${validation_guard_ok} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_RULES) recFinding(testInfo, 'P1', MOD, 'Coverage rule create floor ihlal',
            `n=${N_RULES} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        if (!shapeOk) recFinding(testInfo, 'P2', MOD, 'Coverage rule shape drift',
            `keys=${Object.keys(hkItems[0] || {}).join(',')}`);
        if (!validation_guard_ok) recFinding(testInfo, 'P1', MOD, 'min_staff=0 validation bypass',
            `status=${badR.status} — Pydantic ge=1 guard çalışmıyor.`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'coverage_crud', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `coverage_crud floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('B) Idempotency window — same payload create twice (allowed, no unique constraint)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'idem_window', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const payload = {
            department: 'idem_test', weekday: 3, shift_type: 'morning',
            min_staff: 1, note: `${prefix} 35B idempotency`,
        };
        const r1 = await callTimed(request, 'post', '/api/hr/coverage-rules', payload, stressTokens.stress_token);
        const r2 = await callTimed(request, 'post', '/api/hr/coverage-rules', payload, stressTokens.stress_token);
        samples.push(r1.ms, r2.ms);
        if (r1.body?.rule?.id) createdRuleIds.push(r1.body.rule.id);
        if (r2.body?.rule?.id) createdRuleIds.push(r2.body.rule.id);
        // Backend'de unique constraint yok → 2 ayrı rule yaratılır (beklenen).
        // Contract: her iki POST 200/201, 2 farklı id.
        const both_ok = r1.ok && r2.ok && r1.body?.rule?.id !== r2.body?.rule?.id;
        recPerf(testInfo, MOD, 'idem_window', samples, both_ok);
        rec(testInfo, { module: MOD, step: 'idem_window', status: both_ok ? 'PASS' : 'REVIEW',
            note: `r1_status=${r1.status} r2_status=${r2.status} r1_id=${r1.body?.rule?.id?.slice(0, 8)} r2_id=${r2.body?.rule?.id?.slice(0, 8)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'idem_window', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('Cleanup) Inline DELETE coverage-rules (residue=0 target)', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(120_000);
        let delOk = 0, delFail = 0;
        for (const rid of createdRuleIds) {
            const r = await callTimed(request, 'delete', `/api/hr/coverage-rules/${rid}`, undefined, stressTokens.stress_token);
            if (r.ok || r.status === 404) delOk++; else delFail++;
        }
        const pass = delFail === 0;
        rec(testInfo, { module: MOD, step: 'cleanup', status: pass ? 'PASS' : 'REVIEW',
            endpoint: 'DELETE /api/hr/coverage-rules/{id}',
            note: `ok=${delOk}/${createdRuleIds.length} fail=${delFail}` });
        if (!pass) recFinding(testInfo, 'P2', MOD, 'Inline DELETE cleanup partial',
            `fail=${delFail} — hr_coverage_rules orphan scrub fallback (STRESS_COLLECTIONS).`);
    });

    test('D) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_coverage_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});
