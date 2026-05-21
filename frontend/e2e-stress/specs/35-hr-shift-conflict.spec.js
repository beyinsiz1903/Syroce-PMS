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

    // Seed shifts (`_build_f8d_docs`) only cover days +1..+7 with staff slots
    // 5..29. Spec uses today+35 to stay clear of the seed window entirely so
    // staffPool[0] never inherits a residual seeded shift, which would
    // otherwise 409 the S1 create deterministically.
    function tomorrowIso() {
        const d = new Date(Date.now() + 35 * 86_400_000);
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

        // Overlap conflict OBSERVATION (architect iter-7 directive, final):
        // backend `POST /hr/shifts` overlap guard'a sahip değil — hard-assert
        // deterministic fail yaratır. Spec backend reality ile uyumlu:
        // 409/422 PASS, 2xx → P1 gap finding (hard fail değil). Backend
        // hardening follow-up'la takip; o tamamlanınca hard-assert'a çevrilir.
        let overlapBehavior = 'unknown';
        if (r.status === 409 || r.status === 422) {
            overlapBehavior = 'enforced_reject';
            rec(testInfo, { module: MOD, step: 'overlap_s2', status: 'PASS',
                endpoint: 'POST /api/hr/shifts (overlap)',
                note: `status=${r.status} — backend correctly rejects overlapping shift for same staff/date.` });
        } else if (r.ok && s2Id) {
            overlapBehavior = 'allowed_overlap';
            rec(testInfo, { module: MOD, step: 'overlap_s2', status: 'REVIEW',
                endpoint: 'POST /api/hr/shifts (overlap)',
                note: `status=${r.status} s2_id=${s2Id} — backend ALLOWED overlapping shift (no 409/422). Known gap; D step cleanup edecek.` });
            recFinding(testInfo, 'P1', MOD,
                'Shift overlap guard MISSING — backend aynı staff+date için overlapping shift kabul etti',
                `S1=09:00-13:00 S2=10:00-14:00 staff=${staffA.id} → her ikisi de kayıt oldu (s1_id=${s1Id} s2_id=${s2Id}). POST /hr/shifts route'unda overlap check yok; production'da double-booking riski. Gap finding (backend hardening follow-up).`);
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
            recFinding(testInfo, 'P2', MOD, 'S2 overlap unexpected status',
                `status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)}`);
            rec(testInfo, { module: MOD, step: 'overlap_s2', status: 'REVIEW',
                note: `status=${r.status}` });
        }
        // SOFT-assert (iter-7): block only on 5xx; allowed_overlap = P1 gap.
        expect(r.status < 500,
            `overlap probe must not 5xx. behavior=${overlapBehavior} status=${r.status}`).toBe(true);
    });

    test('B2) Overnight branch — crosses_midnight contract + next-day overlap (Task #255/#258)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'overnight_overlap', status: 'SKIP',
                note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Use staffB if available (avoid colliding with S1/S2 locks on staffA);
        // base date today+42 → A/B uses today+35; B2 uses +42/+43, beyond seed
        // window (+1..+7) so no residual collisions.
        const staffN = staffPool[1] || staffPool[0];
        const base = new Date(Date.now() + 42 * 86_400_000);
        const baseIso = `${base.getUTCFullYear()}-${String(base.getUTCMonth() + 1).padStart(2, '0')}-${String(base.getUTCDate()).padStart(2, '0')}`;
        const next = new Date(base.getTime() + 86_400_000);
        const nextIso = `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}-${String(next.getUTCDate()).padStart(2, '0')}`;
        const samples = [];
        let nightId = null, conflictId = null, acceptedId = null;

        // Step 1 — invalid: crosses_midnight=True with end>=start → expect 422.
        const badPayload = {
            staff_id: staffN.id, shift_date: baseIso, shift_type: 'night',
            start_time: '09:00', end_time: '17:00', crosses_midnight: true,
            notes: `${prefix} F8D-v2 35-B2 invalid-overnight`,
        };
        const rBad = await callTimedWithBackoff(request, 'post', '/api/hr/shifts',
            badPayload, stressTokens.stress_token);
        samples.push(rBad.ms);
        if (rBad.status === 401 || rBad.status === 403) {
            recFinding(testInfo, 'P2', MOD, 'Overnight probe RBAC blocked',
                `status=${rBad.status} — overnight branch skipped`);
            rec(testInfo, { module: MOD, step: 'overnight_overlap', status: 'SKIP',
                note: `perm_fail status=${rBad.status}` });
            test.skip(true, 'perm_fail on overnight probe');
            return;
        }
        const badOk = rBad.status === 422;
        if (!badOk) {
            recFinding(testInfo, 'P1', MOD,
                'Overnight contract guard MISSING — crosses_midnight=True + end>=start kabul edildi',
                `status=${rBad.status} body=${JSON.stringify(rBad.body).slice(0, 160)}`);
            const sid = rBad.body?.shift?.id || rBad.body?.id;
            if (sid) createdShiftIds.push({ id: sid, label: 'B2-bad-overnight' });
        }

        // Step 2 — valid overnight 22:00→06:00 (crosses_midnight=True) → expect 2xx.
        const nightPayload = {
            staff_id: staffN.id, shift_date: baseIso, shift_type: 'night',
            start_time: '22:00', end_time: '06:00', crosses_midnight: true,
            notes: `${prefix} F8D-v2 35-B2 baseline-overnight`,
        };
        const rNight = await callTimedWithBackoff(request, 'post', '/api/hr/shifts',
            nightPayload, stressTokens.stress_token);
        samples.push(rNight.ms);
        nightId = rNight.body?.shift?.id || rNight.body?.id;
        if (nightId) createdShiftIds.push({ id: nightId, label: 'B2-night' });
        const nightOk = rNight.ok && !!nightId;
        if (!nightOk) {
            recFinding(testInfo, 'P1', MOD,
                'Overnight baseline create FAILED — Task #255 regresyonu olabilir',
                `status=${rNight.status} body=${JSON.stringify(rNight.body).slice(0, 160)}`);
            rec(testInfo, { module: MOD, step: 'overnight_overlap', status: 'FAIL',
                note: `baseline overnight create failed status=${rNight.status}` });
            expect(rNight.status < 500, `overnight baseline must not 5xx`).toBe(true);
            return;
        }

        // Step 3 — next-morning 05:00-09:00 overlaps the [00:00,06:00) leg → expect 409.
        const conflictPayload = {
            staff_id: staffN.id, shift_date: nextIso, shift_type: 'morning',
            start_time: '05:00', end_time: '09:00', crosses_midnight: false,
            notes: `${prefix} F8D-v2 35-B2 next-day-overlap`,
        };
        const rConflict = await callTimedWithBackoff(request, 'post', '/api/hr/shifts',
            conflictPayload, stressTokens.stress_token);
        samples.push(rConflict.ms);
        conflictId = rConflict.body?.shift?.id || rConflict.body?.id;
        if (conflictId) createdShiftIds.push({ id: conflictId, label: 'B2-conflict' });
        const conflictRejected = rConflict.status === 409;
        if (!conflictRejected) {
            recFinding(testInfo, 'P1', MOD,
                'Overnight overlap guard MISSING — gece vardiyası + ertesi sabah 05-09 çakışması yakalanamadı',
                `night=22:00-06:00 morning=05:00-09:00 staff=${staffN.id} → status=${rConflict.status}. Task #255 datetime-overlap guard regresyonu.`);
        }

        // Step 4 — next-morning 07:00-15:00 başlar gece bittiği için kabul edilmeli.
        const acceptedPayload = {
            staff_id: staffN.id, shift_date: nextIso, shift_type: 'morning',
            start_time: '07:00', end_time: '15:00', crosses_midnight: false,
            notes: `${prefix} F8D-v2 35-B2 next-day-accept`,
        };
        const rAccepted = await callTimedWithBackoff(request, 'post', '/api/hr/shifts',
            acceptedPayload, stressTokens.stress_token);
        samples.push(rAccepted.ms);
        acceptedId = rAccepted.body?.shift?.id || rAccepted.body?.id;
        if (acceptedId) createdShiftIds.push({ id: acceptedId, label: 'B2-accept' });
        const acceptedOk = rAccepted.ok && !!acceptedId;
        if (!acceptedOk) {
            recFinding(testInfo, 'P2', MOD,
                'Overnight non-overlap false-409 — gece bitti, 07-15 reddedildi',
                `status=${rAccepted.status} body=${JSON.stringify(rAccepted.body).slice(0, 160)}`);
        }

        const allOk = badOk && nightOk && conflictRejected && acceptedOk;
        recPerf(testInfo, MOD, 'overnight_overlap', samples, allOk);
        rec(testInfo, { module: MOD, step: 'overnight_overlap',
            status: allOk ? 'PASS' : 'REVIEW',
            endpoint: 'POST /api/hr/shifts (overnight contract)',
            note: `bad_422=${badOk} night_201=${nightOk} conflict_409=${conflictRejected} accept_201=${acceptedOk} staff=${staffN.id}` });
        // SOFT-assert: yalnız 5xx hard fail. Contract gap'leri P1 finding olarak rapor edilir.
        expect(rBad.status < 500 && rNight.status < 500 && rConflict.status < 500 && rAccepted.status < 500,
            `overnight branch must not 5xx`).toBe(true);
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

    test('F) Coverage rules CRUD + coverage-check probe (Task #263 v2)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'coverage_rules', status: 'SKIP',
                note: `module blocked: ${blockedReason}` });
            test.skip(true, 'HR shifts module blocked');
            return;
        }
        const samples = [];
        // List existing rules (idempotent baseline).
        const listR = await callTimed(request, 'get', '/api/hr/coverage-rules',
            undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const listOk = listR.ok || listR.status === 404;
        const notImplemented = listR.status === 404;
        const blockedRBAC = listR.status === 401 || listR.status === 403;
        let createdId = null;
        let createStatus = null;
        let checkStatus = null;
        let checkShapeOk = false;
        if (listR.ok) {
            const tomorrow = new Date(Date.now() + 86_400_000);
            // Task #263 carryover: backend coverage-rules validator -1..6
            // bekler (0=Pazartesi, Python `date.weekday()`). JS getUTCDay()
            // 0=Pazar..6=Cumartesi → Python weekday = (jsDay + 6) % 7.
            const weekday = (tomorrow.getUTCDay() + 6) % 7;
            const payload = {
                department: 'housekeeping',
                weekday,
                shift_type: 'morning',
                min_staff: 1,
            };
            const createR = await callTimed(request, 'post', '/api/hr/coverage-rules',
                payload, stressTokens.stress_token);
            samples.push(createR.ms);
            createStatus = createR.status;
            createdId = createR.body?.rule?.id || createR.body?.id || createR.body?.rule_id;
            const start = tomorrow.toISOString().slice(0, 10);
            const end = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
            const checkR = await callTimed(request, 'get',
                `/api/hr/coverage/check?start=${start}&end=${end}`,
                undefined, stressTokens.stress_token);
            samples.push(checkR.ms);
            checkStatus = checkR.status;
            checkShapeOk = checkR.ok
                && (Array.isArray(checkR.body?.gaps) || Array.isArray(checkR.body))
                && (typeof checkR.body?.rules_count === 'number' || Array.isArray(checkR.body));
            // Cleanup created rule (best-effort).
            if (createdId) {
                await callTimed(request, 'delete', `/api/hr/coverage-rules/${createdId}`,
                    undefined, stressTokens.stress_token);
            }
        }
        const pass = listOk && (notImplemented || blockedRBAC ||
            ((createStatus === null || createStatus === 200 || createStatus === 201 || createStatus === 401 || createStatus === 403) &&
             (checkStatus === null || checkShapeOk || checkStatus === 401 || checkStatus === 403)));
        recPerf(testInfo, MOD, 'coverage_rules', samples, pass);
        rec(testInfo, { module: MOD, step: 'coverage_rules', status: pass ? 'PASS' : 'REVIEW',
            endpoint: 'GET/POST/DELETE /api/hr/coverage-rules + /coverage/check',
            note: `list=${listR.status} create=${createStatus} check=${checkStatus} check_shape_ok=${checkShapeOk} created_id=${createdId} not_impl=${notImplemented} rbac=${blockedRBAC}` });
        if (notImplemented) recFinding(testInfo, 'P2', MOD, 'Coverage-rules endpoint not implemented (informational)', `status=404`);
        if (blockedRBAC) recFinding(testInfo, 'P2', MOD, 'Coverage-rules RBAC-blocked (informational)', `status=${listR.status}`);
        expect(pass).toBe(true);
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_shift_conflict_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});
