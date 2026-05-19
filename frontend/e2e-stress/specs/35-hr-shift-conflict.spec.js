// F8D-v2 § 35 — HR Shift Conflict + Coverage Stress.
//
// Scope: backlog items "Shift conflict reject" + "Shift coverage minimum check".
// v1 spec 23 sadece swap lifecycle test etti; conflict guard + coverage check
// hiç yapılmadı.
//
// Test contract:
//   A) Create shift S1 for staffA tomorrow morning (09:00-13:00)
//   B) Create shift S2 OVERLAPPING (10:00-14:00) for same staffA same date.
//      Expected: 409 conflict. If 200/201 → backend overlap guard missing → P1 finding.
//      Both shifts deleted in D regardless.
//   C) Coverage check — GET /api/hr/shifts for date range; group by dept,
//      assert Housekeeping dept has ≥ MIN_COVERAGE scheduled staff (P2 if not).
//   D) Cleanup — DELETE /api/hr/shifts/{id} both S1+S2 (idempotent residue=0)
//   E) pilot_drift=0 + external_calls=[]
//
// Mutlak kurallar:
//   - pilot mutation YOK
//   - external_calls=[] (shifts in-app, no provider call)
//   - failedTests=0, P0=P1=0 (conflict gap finding = P1 only if create succeeded
//     without reject; we still cleanup to keep residue=0)

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_shift_conflict';
const MIN_COVERAGE_HK = 2; // doctrine: HK has 10 seeded staff; min 2 across 7-day window

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v2 § 35 — HR Shift Conflict + Coverage', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let staffPool = [];
    let createdShiftIds = []; // {id, note}
    let s1Id = null, s2Id = null;
    let s2Status = null;

    function tomorrowIso() {
        const d = new Date(Date.now() + 86_400_000);
        return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
    }

    test('Setup: prefix + pilot baseline + staff pool + shifts probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/hr/shifts');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `shifts_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'HR shifts probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C/D skipped.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        const staffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
        const allStaff = staffR.body?.staff || staffR.body?.staff_members || staffR.body?.items
            || (Array.isArray(staffR.body) ? staffR.body : []);
        staffPool = allStaff.filter((s) => {
            const name = s?.name || s?.full_name || '';
            return typeof name === 'string' && name.startsWith(prefix);
        });
        if (staffPool.length < 2) {
            moduleBlocked = true;
            blockedReason = `staff_pool_insufficient (${staffPool.length})`;
            recFinding(testInfo, 'P2', MOD, 'Stress staff pool insufficient for conflict probe',
                `pool=${staffPool.length} need>=2 — A/B/C/D skipped.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} staff_total=${allStaff.length} pool=${staffPool.length} module_blocked=${moduleBlocked}` });
    });

    test('A) Create initial shift S1 — staffA tomorrow morning 09-13', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'create_s1', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const staffA = staffPool[0];
        const payload = {
            staff_id: staffA.id,
            shift_date: tomorrowIso(),
            shift_type: 'morning',
            start_time: '09:00',
            end_time: '13:00',
            notes: `${prefix} F8D-v2 35-A baseline shift`,
        };
        const r = await callTimedWithBackoff(request, 'post', '/api/hr/shifts', payload, stressTokens.stress_token);
        samples.push(r.ms);
        s1Id = r.body?.shift?.id || r.body?.id;
        if (s1Id) createdShiftIds.push({ id: s1Id, label: 'S1' });
        const permFail = r.status === 401 || r.status === 403;
        if (permFail) {
            moduleBlocked = true;
            blockedReason = `shift_create_rbac_${r.status}`;
            recFinding(testInfo, 'P2', MOD, 'Shift create RBAC blocked',
                `status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)} — B/C/D skipped.`);
            rec(testInfo, { module: MOD, step: 'create_s1', status: 'SKIP',
                note: `perm_fail status=${r.status}` });
            return;
        }
        recPerf(testInfo, MOD, 'create_s1', samples, r.ok && !!s1Id);
        rec(testInfo, { module: MOD, step: 'create_s1', status: (r.ok && s1Id) ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/shifts',
            note: `status=${r.status} shift_id=${s1Id} staff=${staffA.id}` });
        if (!r.ok || !s1Id) recFinding(testInfo, 'P1', MOD, 'S1 shift create failed',
            `status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)}`);
        expect(r.ok && !!s1Id, `S1 must be created`).toBe(true);
    });

    test('B) Create overlapping shift S2 — expect 409 conflict OR document P1 gap', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !s1Id) {
            rec(testInfo, { module: MOD, step: 'overlap_s2', status: 'SKIP', note: 'module blocked or no S1' });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const staffA = staffPool[0];
        const payload = {
            staff_id: staffA.id,
            shift_date: tomorrowIso(),
            shift_type: 'morning',
            start_time: '10:00',
            end_time: '14:00',
            notes: `${prefix} F8D-v2 35-B overlapping shift`,
        };
        const r = await callTimedWithBackoff(request, 'post', '/api/hr/shifts', payload, stressTokens.stress_token);
        samples.push(r.ms);
        s2Status = r.status;
        s2Id = r.body?.shift?.id || r.body?.id;
        if (s2Id) createdShiftIds.push({ id: s2Id, label: 'S2-overlap' });

        recPerf(testInfo, MOD, 'overlap_s2', samples, true); // perf çağrı başarısı (status-bağımsız)

        // Overlap conflict contract HARD-ASSERT: aynı staff+date için
        // çakışan time-window POST → 409 veya 422 BEKLENIR. 2xx kabul
        // edilemez (production double-booking riski). Architect iter-3
        // directive: contract checks must hard-fail when violated.
        let overlapBehavior = 'unknown';
        if (r.status === 409 || r.status === 422) {
            overlapBehavior = 'enforced_reject';
            rec(testInfo, { module: MOD, step: 'overlap_s2', status: 'PASS',
                endpoint: 'POST /api/hr/shifts (overlap)',
                note: `status=${r.status} — backend correctly rejects overlapping shift for same staff/date.` });
        } else if (r.ok && s2Id) {
            overlapBehavior = 'allowed_overlap';
            rec(testInfo, { module: MOD, step: 'overlap_s2', status: 'FAIL',
                endpoint: 'POST /api/hr/shifts (overlap)',
                note: `status=${r.status} s2_id=${s2Id} — backend ALLOWED overlapping shift (no 409/422). CONTRACT VIOLATION; D step cleanup edecek.` });
            recFinding(testInfo, 'P0', MOD,
                'Shift overlap guard MISSING — backend aynı staff+date için overlapping shift kabul etti',
                `S1=09:00-13:00 S2=10:00-14:00 staff=${staffA.id} → her ikisi de kayıt oldu (s1_id=${s1Id} s2_id=${s2Id}). POST /hr/shifts route'unda overlap check yok; production'da double-booking riski. CONTRACT VIOLATION.`);
        } else if (r.status === 401 || r.status === 403) {
            overlapBehavior = 'perm_fail';
            recFinding(testInfo, 'P2', MOD, 'S2 overlap probe RBAC blocked',
                `status=${r.status} — A1 başarılı ama A2 perm fail; tutarsız gate beklenmedik.`);
            rec(testInfo, { module: MOD, step: 'overlap_s2', status: 'SKIP',
                note: `perm_fail status=${r.status}` });
            test.skip(true, 'perm_fail mid-flight (inconsistent gate)');
            return;
        } else {
            overlapBehavior = `unexpected_${r.status}`;
            recFinding(testInfo, 'P1', MOD, 'S2 overlap unexpected status',
                `status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)}`);
            rec(testInfo, { module: MOD, step: 'overlap_s2', status: 'FAIL',
                note: `status=${r.status}` });
        }
        // HARD-ASSERT (architect iter-3): overlap must be rejected by backend.
        expect(overlapBehavior,
            `overlap contract: aynı staff+date çakışan shift için 409/422 BEKLENIR. behavior=${overlapBehavior} status=${r.status}`)
            .toBe('enforced_reject');
    });

    test('C) Coverage check — HK dept ≥ MIN_COVERAGE_HK scheduled staff', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'coverage', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const today = new Date();
        const start = `${today.getUTCFullYear()}-${String(today.getUTCMonth() + 1).padStart(2, '0')}-${String(today.getUTCDate()).padStart(2, '0')}`;
        const endDt = new Date(today.getTime() + 7 * 86_400_000);
        const end = `${endDt.getUTCFullYear()}-${String(endDt.getUTCMonth() + 1).padStart(2, '0')}-${String(endDt.getUTCDate()).padStart(2, '0')}`;
        const r = await callTimed(request, 'get',
            `/api/hr/shifts?start=${start}&end=${end}`, undefined, stressTokens.stress_token);
        samples.push(r.ms);
        const shifts = r.body?.items || (Array.isArray(r.body) ? r.body : []);
        // Build dept→unique staff_id set from shifts intersected with stress staff pool
        const stressStaffIds = new Set(staffPool.map((s) => s.id));
        const deptStaffSet = new Map(); // dept(string) → Set(staff_id)
        for (const sh of shifts) {
            if (!stressStaffIds.has(sh.staff_id)) continue;
            const staff = staffPool.find((s) => s.id === sh.staff_id);
            const dept = staff?.department || 'unknown';
            if (!deptStaffSet.has(dept)) deptStaffSet.set(dept, new Set());
            deptStaffSet.get(dept).add(sh.staff_id);
        }
        const hkCount = (deptStaffSet.get('Housekeeping') || new Set()).size;
        const coverageOk = hkCount >= MIN_COVERAGE_HK;
        const deptSummary = Array.from(deptStaffSet.entries()).map(([d, set]) => `${d}=${set.size}`).join(',');
        recPerf(testInfo, MOD, 'coverage', samples, r.ok);
        rec(testInfo, { module: MOD, step: 'coverage',
            status: coverageOk ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/shifts?start&end (coverage rollup)',
            note: `range=${start}..${end} shifts=${shifts.length} hk_unique_staff=${hkCount} min=${MIN_COVERAGE_HK} dept_breakdown=${deptSummary}` });
        if (!coverageOk) recFinding(testInfo, 'P2', MOD,
            'HK department coverage minimum altında',
            `hk_unique_staff=${hkCount} min=${MIN_COVERAGE_HK} dept_breakdown=${deptSummary} — seed 10 HK staff sağlıyor; coverage gap operasyonel risk (shift planlama eksikliği).`);
    });

    test('D) Cleanup — DELETE all created shifts (idempotent residue=0)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || createdShiftIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'cleanup_shifts', status: 'SKIP',
                note: `module blocked or nothing to clean (created=${createdShiftIds.length})` });
            return;
        }
        const samples = [];
        let delOk = 0, delFail = 0, idemOk = 0, idemFail = 0;
        for (const sh of createdShiftIds) {
            const r = await callTimedWithBackoff(request, 'delete',
                `/api/hr/shifts/${sh.id}`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok || r.status === 404) delOk++; else delFail++;
            await new Promise((res) => setTimeout(res, 400));
        }
        // Idempotent re-DELETE — hepsi 404 olmalı
        for (const sh of createdShiftIds) {
            const r2 = await callTimed(request, 'delete',
                `/api/hr/shifts/${sh.id}`, undefined, stressTokens.stress_token);
            if (r2.status === 404) idemOk++; else idemFail++;
        }
        const pass = delFail === 0 && idemFail === 0;
        recPerf(testInfo, MOD, 'cleanup_shifts', samples, pass);
        rec(testInfo, { module: MOD, step: 'cleanup_shifts',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: 'DELETE /api/hr/shifts/{id}',
            note: `created=${createdShiftIds.length} del_ok=${delOk} del_fail=${delFail} idem_ok=${idemOk} idem_fail=${idemFail} labels=${createdShiftIds.map(x => x.label).join(',')}` });
        if (!pass) recFinding(testInfo, 'P1', MOD, 'Shift cleanup residue ihlal',
            `del_fail=${delFail} idem_fail=${idemFail} created=${createdShiftIds.length}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'cleanup_shifts', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(pass, `shift cleanup idempotent`).toBe(true);
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_shift_conflict_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});
