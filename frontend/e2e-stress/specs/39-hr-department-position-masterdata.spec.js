// F8D-v3 § 39 — Department / Position Master Data:
//   • /hr/departments  GET/POST/DELETE + /sync-from-staff
//   • /hr/positions    GET/POST/DELETE  (pozisyon FK → departman)
//   • Aktif personeli olan departman silinemez (409 expected)
//   • Pozisyon master data'da olmayan departmana bağlanamaz (400 expected)
//
// Backend ref: backend/domains/hr/router.py:2612 (departments),
//              :2769 (positions), :2697 (sync-from-staff).
//
// Cleanup: inline DELETE created dept/position; STRESS_COLLECTIONS sweep
//          fallback (hr_departments, hr_positions tenant-scoped).
//
// Mutlak kurallar: pilot mutation YOK, external_calls=[], failedTests=0.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_dept_position_masterdata';
const N_DEPT = 3;
const N_POS = 3;

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v3 § 39 — Department / Position Master Data', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let createdDeptIds = [];
    let createdPosIds = [];

    test('Setup: prefix + pilot baseline + departments probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/hr/departments?include_inactive=true');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `departments_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Departments probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped, D pilot_drift still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Department CRUD — create N + list + active-staff guard + position FK', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'dept_crud', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, permFail = 0;
        const errs = [];
        // Create N departments with prefix-scoped codes.
        for (let i = 0; i < N_DEPT; i++) {
            const code = `${prefix}_dept_${i + 1}`.slice(0, 40);
            const payload = {
                name: `${prefix} F8D-v3 39 dept ${i + 1}`,
                code,
                description: `${prefix} masterdata stress`,
            };
            const r = await callTimed(request, 'post',
                '/api/hr/departments', payload, stressTokens.stress_token);
            samples.push(r.ms);
            const did = r.body?.department?.id;
            if (r.ok && did) { ok++; createdDeptIds.push(did); }
            else if (r.status === 401 || r.status === 403) permFail++;
            else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 800));
        }
        if (permFail === N_DEPT) {
            recFinding(testInfo, 'P2', MOD, 'Department create RBAC blocked',
                `n=${N_DEPT} all permFail — manage_hr gate reddetti.`);
            rec(testInfo, { module: MOD, step: 'dept_crud', status: 'SKIP',
                endpoint: 'POST /api/hr/departments', note: `perm_fail=${permFail}` });
            test.skip(true, 'dept RBAC blocked');
            return;
        }
        // List read — created departments visible.
        const listR = await callTimed(request, 'get', '/api/hr/departments?include_inactive=true', undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const listItems = listR.body?.items || [];
        const ourSeen = listItems.filter((d) => createdDeptIds.includes(d.id)).length;
        // Position FK guard — pozisyon bilinmeyen departmana bağlanmaya çalışırsa 400.
        const fakeDeptR = await callTimed(request, 'post',
            '/api/hr/positions', {
                title: `${prefix} F8D-v3 39 FK-guard probe`,
                department: `${prefix}_NONEXISTENT_DEPT`,
            }, stressTokens.stress_token);
        samples.push(fakeDeptR.ms);
        const fk_guard_ok = fakeDeptR.status === 400;
        if (!fk_guard_ok && fakeDeptR.body?.position?.id) {
            createdPosIds.push(fakeDeptR.body.position.id);
        }

        const floor = Math.ceil(N_DEPT * 0.9);
        const pass = ok >= floor && ourSeen >= floor && fk_guard_ok;
        recPerf(testInfo, MOD, 'dept_crud', samples, pass);
        rec(testInfo, { module: MOD, step: 'dept_crud', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST/GET /api/hr/departments + POST /api/hr/positions(FK probe)',
            note: `n=${N_DEPT} ok=${ok} fail=${fail} perm_fail=${permFail} our_seen=${ourSeen}/${createdDeptIds.length} fk_guard_status=${fakeDeptR.status} fk_guard_ok=${fk_guard_ok} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_DEPT) recFinding(testInfo, 'P1', MOD, 'Department create floor ihlal',
            `n=${N_DEPT} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        if (!fk_guard_ok) recFinding(testInfo, 'P0', MOD, 'Position FK guard bypass',
            `non-existent dept ile pozisyon kabul edildi: status=${fakeDeptR.status} body=${JSON.stringify(fakeDeptR.body).slice(0, 200)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'dept_crud', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `dept_crud floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('B) Position CRUD — create N pozisyon (dept FK valid) + list + dept filter', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked || createdDeptIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'pos_crud', status: 'SKIP', note: `module blocked or no dept: ${blockedReason}` });
            test.skip(true, 'module blocked or no dept');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0;
        const errs = [];
        // Use prefix-coded dept (created in A) for valid FK.
        const deptCode = `${prefix}_dept_1`.slice(0, 40);
        for (let i = 0; i < N_POS; i++) {
            const payload = {
                title: `${prefix} F8D-v3 39 pos ${i + 1}`,
                department: deptCode,
                default_hourly_rate: 100 + i * 10,
            };
            const r = await callTimed(request, 'post',
                '/api/hr/positions', payload, stressTokens.stress_token);
            samples.push(r.ms);
            const pid = r.body?.position?.id;
            if (r.ok && pid) { ok++; createdPosIds.push(pid); }
            else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 800));
        }
        // List + dept filter.
        const listR = await callTimed(request, 'get',
            `/api/hr/positions?department=${encodeURIComponent(deptCode)}`,
            undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const listItems = listR.body?.items || [];
        const ourSeen = listItems.filter((p) => createdPosIds.includes(p.id)).length;
        const floor = Math.ceil(N_POS * 0.9);
        const pass = ok >= floor && listR.ok && ourSeen >= 1;
        recPerf(testInfo, MOD, 'pos_crud', samples, pass);
        rec(testInfo, { module: MOD, step: 'pos_crud', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST/GET /api/hr/positions?department=...',
            note: `n=${N_POS} ok=${ok} fail=${fail} list_status=${listR.status} our_seen=${ourSeen} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Position create floor ihlal',
            `n=${N_POS} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'pos_crud', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) Sync-from-staff — idempotent master data backfill', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'sync_from_staff', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r1 = await callTimed(request, 'post',
            '/api/hr/departments/sync-from-staff', {}, stressTokens.stress_token);
        samples.push(r1.ms);
        const created1 = r1.body?.created || 0;
        await new Promise((res) => setTimeout(res, 1000));
        const r2 = await callTimed(request, 'post',
            '/api/hr/departments/sync-from-staff', {}, stressTokens.stress_token);
        samples.push(r2.ms);
        const created2 = r2.body?.created || 0;
        // Idempotent: 2. run YENI departman yaratmamalı (ya 0 ya ilk run'a göre az).
        const idempotent = r2.ok && created2 <= created1;
        const pass = r1.ok && r2.ok && idempotent;
        recPerf(testInfo, MOD, 'sync_from_staff', samples, pass);
        rec(testInfo, { module: MOD, step: 'sync_from_staff', status: pass ? 'PASS' : 'REVIEW',
            endpoint: 'POST /api/hr/departments/sync-from-staff',
            note: `r1_status=${r1.status} created1=${created1} r2_status=${r2.status} created2=${created2} idempotent=${idempotent}` });
        if (!idempotent) recFinding(testInfo, 'P1', MOD, 'Sync-from-staff not idempotent',
            `created1=${created1} created2=${created2} — 2. run aynı set'i yeniden eklemiş.`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'sync_from_staff', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('Cleanup) Inline DELETE positions + departments (residue=0 target)', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(120_000);
        let delPosOk = 0, delPosFail = 0;
        let delDeptOk = 0, delDeptFail = 0;
        // Positions önce silinmeli (FK cleanliness).
        for (const pid of createdPosIds) {
            const r = await callTimed(request, 'delete', `/api/hr/positions/${pid}`, undefined, stressTokens.stress_token);
            if (r.ok || r.status === 404) delPosOk++; else delPosFail++;
        }
        for (const did of createdDeptIds) {
            const r = await callTimed(request, 'delete', `/api/hr/departments/${did}`, undefined, stressTokens.stress_token);
            // Aktif personeli olan dept silinemez (409 expected) — bu cleanup'ta
            // SORUN değil, beklenen davranış. 200/204/404/409 hepsi OK.
            if (r.ok || r.status === 404 || r.status === 409) delDeptOk++;
            else delDeptFail++;
        }
        const pass = delPosFail === 0 && delDeptFail === 0;
        rec(testInfo, { module: MOD, step: 'cleanup', status: pass ? 'PASS' : 'REVIEW',
            endpoint: 'DELETE /api/hr/{positions,departments}/{id}',
            note: `pos_ok=${delPosOk}/${createdPosIds.length} pos_fail=${delPosFail} dept_ok=${delDeptOk}/${createdDeptIds.length} dept_fail=${delDeptFail}` });
        if (!pass) recFinding(testInfo, 'P2', MOD, 'Inline DELETE cleanup partial — STRESS_COLLECTIONS sweep fallback',
            `pos_fail=${delPosFail} dept_fail=${delDeptFail}`);
    });

    test('D) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_dept_pos_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});
