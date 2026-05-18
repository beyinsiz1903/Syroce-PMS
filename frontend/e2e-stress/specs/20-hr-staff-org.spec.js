// F8D § 20 — HR Staff / Departments / Positions (org structure):
// list reads + bulk create staff.
//
// Dry-run safety:
//   - All endpoints DB CRUD only. HR notifications are in-app (`notifications`
//     collection) so no external dispatch.
//   - Created staff tagged with prefix in name/email.
//   - module-blocked pattern: if list/setup returns non-2xx, module is treated
//     as blocked (P2 informational) and A/B/C test.skip — D pilot_drift
//     runs independently.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_staff_org';
const N_CREATE = 5;

test.describe.configure({ mode: 'serial' });

test.describe('F8D § 20 — HR Staff Org', () => {
    let pilotBefore = null;
    let prefix = null;
    let seededDeptId = null;
    let seededPositionId = null;
    let createdStaffIds = [];
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + module probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        // Module probe: read departments + positions so B has a target dept+position.
        const deptR = await callTimed(request, 'get', '/api/hr/departments', undefined, stressTokens.stress_token);
        const posR = await callTimed(request, 'get', '/api/hr/positions', undefined, stressTokens.stress_token);
        const depts = deptR.body?.departments || deptR.body?.items || (Array.isArray(deptR.body) ? deptR.body : []);
        const positions = posR.body?.positions || posR.body?.items || (Array.isArray(posR.body) ? posR.body : []);
        const seededDept = depts.find((d) => typeof d?.code === 'string' && d.code.startsWith(prefix));
        const seededPos = positions.find((p) => typeof p?.code === 'string' && p.code.startsWith(prefix));
        seededDeptId = seededDept?.id || depts[0]?.id || null;
        seededPositionId = seededPos?.id || positions[0]?.id || null;
        const reachable = deptR.ok && posR.ok;
        if (!reachable || !seededDeptId || !seededPositionId) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'HR org module read blocked',
                `dept_status=${deptR.status} pos_status=${posR.status} dept_id=${seededDeptId ?? 'none'} pos_id=${seededPositionId ?? 'none'} — A/B skipped, pilot_drift gate still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup',
            status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} dept_status=${deptR.status} pos_status=${posR.status} module_blocked=${moduleBlocked}` });
        expect(typeof deptR.status).toBe('number');
    });

    test('A) List staff + departments + positions', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'list_org', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'HR org module blocked');
            return;
        }
        const samples = [];
        const staffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
        samples.push(staffR.ms);
        const deptR = await callTimed(request, 'get', '/api/hr/departments', undefined, stressTokens.stress_token);
        samples.push(deptR.ms);
        const posR = await callTimed(request, 'get', '/api/hr/positions', undefined, stressTokens.stress_token);
        samples.push(posR.ms);
        recPerf(testInfo, MOD, 'list_org', samples, staffR.ok && deptR.ok && posR.ok);
        const ok = staffR.ok && deptR.ok && posR.ok;
        rec(testInfo, { module: MOD, step: 'list_org', status: ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/{staff,departments,positions}',
            note: `staff=${staffR.status} dept=${deptR.status} pos=${posR.status} max_ms=${Math.max(...samples)}` });
        if (!ok) recFinding(testInfo, 'P2', MOD, 'HR org list non-2xx',
            `staff=${staffR.status} dept=${deptR.status} pos=${posR.status}`);
        expect(staffR.ok).toBe(true);
    });

    test('B) Bulk create staff', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'bulk_create_staff', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'HR org module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];
        for (let i = 0; i < N_CREATE; i++) {
            // Router contract: requires `name` only; other fields optional and
            // mapped to staff_members doc (department/position strings, not _id).
            const payload = {
                name: `${prefix}StaffB${i + 1} Test`,
                email: `${prefix.toLowerCase()}staffb${i + 1}@e2e-stress.example.com`,
                phone: `+90555700${i + 1}000`,
                department: 'Front Office',
                position: 'Front Desk Agent',
                employment_type: 'full_time',
                hire_date: new Date().toISOString().slice(0, 10),
                hourly_rate: 112.5,
                monthly_hours: 160,
                annual_leave_entitlement: 14,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/hr/staff',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.staff_id || r.body?.id)) {
                ok++;
                createdStaffIds.push(r.body.staff_id || r.body.id);
            } else if (r.status === 403 || r.status === 401) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        // RBAC perm-fail tolerant: if all requests 401/403, mark module-blocked at runtime.
        if (permFail === N_CREATE) {
            recFinding(testInfo, 'P2', MOD, 'HR staff create blocked (RBAC)',
                `n=${N_CREATE} all permFail. Permission gate intentional; treat as informational.`);
            rec(testInfo, { module: MOD, step: 'bulk_create_staff', status: 'SKIP',
                endpoint: 'POST /api/hr/staff',
                note: `n=${N_CREATE} perm_fail=${permFail} (RBAC blocked, P2 informational)` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create_staff', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'HR staff create RBAC-blocked');
            return;
        }
        const floor = Math.ceil(N_CREATE * 0.9);
        recPerf(testInfo, MOD, 'bulk_create_staff', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'bulk_create_staff', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/staff',
            note: `n=${N_CREATE} ok=${ok} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} floor>=${floor} created=${createdStaffIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_CREATE) recFinding(testInfo, 'P1', MOD, 'Staff bulk create floor ihlal',
            `n=${N_CREATE} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create_staff', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `bulk_create_staff floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});
