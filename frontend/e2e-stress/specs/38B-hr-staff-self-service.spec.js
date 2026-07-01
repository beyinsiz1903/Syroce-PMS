// F8D-v3 § 38B — Staff Self-Service Scope:
//   • /hr/payroll/me?month=YYYY-MM      — kendi locked payroll satırı
//   • /hr/staff/{self_id}/profile        — _authorize_staff_access self bypass
//   • /hr/leave-balance/{self_id}        — kendi izin bakiyesi
//   • /hr/attendance/records?staff_id=self — kendi attendance
//
// Backend ref: /hr/payroll/me (router.py:1947) — _PAYROLL_ME_ALLOWED_ROLES
//              fail-closed allow-list; super_admin geçer ama gerçek staff
//              self-service için staff/front_desk/housekeeping/finance role
//              token gerekir.
//
// Stress not'u: stress admin super_admin → self-service guard geçer ama gerçek
// "staff token cross-staff read" yapamayız (staff role JWT token oluşturma path'i
// yok). Bu yüzden spec module-blocked doctrine ile çalışır:
//   • super_admin /payroll/me → kendi satırı (boş veya locked-only)
//   • cross-staff probe = pilot staff_id ile attempt → 403/404 expect (F8D-v3
//     § 38 ile overlap, F8P § 96 IDOR doctrine mirror)
//
// Mutlak kurallar: read-only spec, pilot mutation YOK, external_calls=[].
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_staff_self_service';

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v3 § 38B — Staff Self-Service Scope', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let selfId = null;

    test('Setup: prefix + pilot baseline + self-service probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        // /payroll/me probe — super_admin role _PAYROLL_ME_ALLOWED_ROLES'da
        // değilse 403 döner (post-review round 6 fail-closed). super_admin
        // genelde geçer; geçmiyorsa module-blocked.
        const today = new Date();
        const month = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/hr/payroll/me?month=${month}`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `payroll_me_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Self-service /payroll/me probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped (super_admin not in _PAYROLL_ME_ALLOWED_ROLES?).`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        // Stress token self_id — JWT'den staff_id veya user_id türü.
        selfId = probe.body?.staff_id || probe.body?.self_id || null;
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} self_id_present=${!!selfId} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) /payroll/me — self-only contract (locked-only doctrine + no cross-staff)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'payroll_me', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const months = ['2025-12', '2026-01', '2026-02'];
        let ok = 0, fail = 0;
        const lockedOnlyViolations = [];
        for (const m of months) {
            const r = await callTimed(request, 'get',
                `/api/hr/payroll/me?month=${m}`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) {
                ok++;
                // Locked-only: returned row (if any) must have status='locked'.
                const row = r.body?.row || r.body?.payroll || null;
                if (row && row.status && row.status !== 'locked') {
                    lockedOnlyViolations.push({ month: m, status: row.status });
                }
            } else fail++;
            await new Promise((res) => setTimeout(res, 500));
        }
        const pass = ok >= 2 && lockedOnlyViolations.length === 0;
        recPerf(testInfo, MOD, 'payroll_me', samples, pass);
        rec(testInfo, { module: MOD, step: 'payroll_me', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/hr/payroll/me?month=...',
            note: `n=${months.length} ok=${ok} fail=${fail} locked_only_violations=${JSON.stringify(lockedOnlyViolations)}` });
        if (lockedOnlyViolations.length > 0) recFinding(testInfo, 'P0', MOD,
            'Self-service /payroll/me returned non-locked row (KVKK + iş hukuku ihlal)',
            `violations=${JSON.stringify(lockedOnlyViolations)} — taslak satır self-service'te asla görünmemeli.`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'payroll_me', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) Cross-staff IDOR probe — pilot staff_id ile self-service surface', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'cross_staff_idor', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Harvest pilot staff_id (read-only own-tenant).
        const pilotStaffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.pilot_token);
        const pilotStaff = pilotStaffR.body?.staff || pilotStaffR.body?.staff_members
            || pilotStaffR.body?.items || (Array.isArray(pilotStaffR.body) ? pilotStaffR.body : []);
        if (pilotStaff.length === 0) {
            rec(testInfo, { module: MOD, step: 'cross_staff_idor', status: 'PASS',
                note: 'pilot_pool=0 — IDOR not exercised' });
            return;
        }
        const pilotSampleId = pilotStaff[0]?.id;
        const probes = [
            { ep: `/api/hr/staff/${pilotSampleId}/profile`, name: 'profile' },
            { ep: `/api/hr/leave-balance/${pilotSampleId}`, name: 'leave_balance' },
            { ep: `/api/hr/staff/${pilotSampleId}/salary-history`, name: 'salary_history' },
        ];
        const samples = [];
        const violations = [];
        for (const p of probes) {
            const r = await callTimed(request, 'get', p.ep, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            const properly_rejected = r.status === 403 || r.status === 404;
            const idor_evidence = r.ok && (
                (r.body?.staff?.id === pilotSampleId) ||
                (r.body?.balance?.staff_id === pilotSampleId) ||
                (r.body?.history && Array.isArray(r.body.history) && r.body.history.length > 0)
            );
            if (idor_evidence) violations.push({ name: p.name, status: r.status });
            else if (!properly_rejected) violations.push({ name: p.name, status: r.status, suspicious: true });
            await new Promise((res) => setTimeout(res, 500));
        }
        const hasP0 = violations.some((v) => !v.suspicious);
        const pass = violations.length === 0;
        recPerf(testInfo, MOD, 'cross_staff_idor', samples, pass);
        rec(testInfo, { module: MOD, step: 'cross_staff_idor', status: pass ? 'PASS' : (hasP0 ? 'FAIL' : 'REVIEW'),
            endpoint: 'GET /api/hr/staff/{pilot_id}/{profile,leave-balance,salary-history}',
            note: `pilot_sample=${pilotSampleId.slice(0, 8)}.. violations=${JSON.stringify(violations)}` });
        if (hasP0) recFinding(testInfo, 'P0', MOD, 'Cross-staff IDOR — pilot staff self-service okundu',
            `violations=${JSON.stringify(violations)} — object-level RBAC bypassed.`);
        else if (violations.length > 0) recFinding(testInfo, 'P1', MOD, 'Cross-staff probe non-403/404',
            `violations=${JSON.stringify(violations)} — beklenmeyen yüzey.`);
        expect(hasP0, 'no cross-staff IDOR P0').toBe(false);
    });

    test('C) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_self_service_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});
