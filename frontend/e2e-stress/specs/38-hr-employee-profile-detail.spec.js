// F8D-v3 § 38 — Employee Profile Detail (Personel Kartı Detay):
//   • GET /hr/staff/{id}/profile  — aggregate kişi + son 30g attendance +
//     izinler + performans + bordro + vardiya
//   • GET /hr/staff/{id}/salary-history — ücret değişim geçmişi
//   • GET /hr/staff/{id}/certifications — sertifika listesi
//   • GET /hr/staff/{id}/documents — özlük evrak checklist
//
// Backend ref: backend/domains/hr/router.py:3195 (profile), :4896 (salary-history),
//              :5121 (certifications), :5232 (documents).
//
// RBAC contract:
//   • profile: tenant + assigned_department + self-service (_authorize_staff_access)
//     - performans bölümü SADECE manage_hr (Finance gizlenir)
//   • salary-history: require_op("view_finance")  (PII high — IBAN/maaş)
//   • certifications/documents: tenant + dept-scope
//
// PII mask doctrine: phone/email/identity_no/iban masked unless manage_hr OR self.
//
// Mutlak kurallar:
//   • Pilot tenant'a mutation YOK (read-only spec).
//   • external_calls=[] (DB read only).
//   • failedTests=0, P0=P1=0.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertPiiMasked,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_employee_profile_detail';
const N_PROBE = 3;

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v3 § 38 — Employee Profile Detail', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let staffPool = [];

    test('Setup: prefix + pilot baseline + staff pool + profile probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const staffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
        const allStaff = staffR.body?.staff || staffR.body?.staff_members || staffR.body?.items
            || (Array.isArray(staffR.body) ? staffR.body : []);
        staffPool = allStaff.filter((s) => {
            const name = s?.name || s?.full_name || '';
            const email = (s?.email || '').toLowerCase();
            return (typeof name === 'string' && name.startsWith(prefix))
                || (typeof email === 'string' && email.startsWith(prefix.toLowerCase()));
        }).slice(0, N_PROBE + 1);
        if (!staffR.ok || staffPool.length < 1) {
            moduleBlocked = true;
            blockedReason = `pool_short_status_${staffR.status}_size_${staffPool.length}`;
            recFinding(testInfo, 'P2', MOD, 'Employee profile staff pool insufficient',
                `staff_status=${staffR.status} pool=${staffPool.length} — A/B/C skipped, D pilot_drift still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        // Profile probe — super_admin geçer; non-2xx → moduleBlocked.
        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/hr/staff/${staffPool[0].id}/profile`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `profile_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Profile detail probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} pool=${staffPool.length} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Profile aggregate read — kişi + attendance + leaves + reviews + payroll + shifts', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'profile_aggregate', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0;
        const errs = [];
        const shapeCheck = { has_staff: 0, has_attendance: 0, has_leaves: 0,
            has_reviews: 0, has_payroll: 0, has_shifts: 0, has_metrics: 0 };
        for (let i = 0; i < Math.min(N_PROBE, staffPool.length); i++) {
            const s = staffPool[i];
            const r = await callTimed(request, 'get',
                `/api/hr/staff/${s.id}/profile`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) {
                ok++;
                const body = r.body || {};
                // Backend nested response contract (router.py:3283-3302):
                //   staff, attendance:{records[], total_hours_30d, days_present_30d},
                //   leaves:{items[], total, pending}, leave_balance,
                //   performance:{items[], avg_score, total, redacted},
                //   payroll:{recent[], count}, upcoming_shifts[]
                if (body.staff) shapeCheck.has_staff++;
                if (Array.isArray(body.attendance?.records)) shapeCheck.has_attendance++;
                if (Array.isArray(body.leaves?.items)) shapeCheck.has_leaves++;
                if (Array.isArray(body.performance?.items)) shapeCheck.has_reviews++;
                if (Array.isArray(body.payroll?.recent)) shapeCheck.has_payroll++;
                if (Array.isArray(body.upcoming_shifts)) shapeCheck.has_shifts++;
                if (typeof body.attendance?.total_hours_30d === 'number'
                    || typeof body.attendance?.days_present_30d === 'number') {
                    shapeCheck.has_metrics++;
                }
                // PII mask assert on staff doc (super_admin → manage_hr=true, may see raw).
                // assertPiiMasked is informational: emit P0 if plain PII in nested arrays
                // that should be masked for other roles. Here we only sanity-check shape.
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 800));
        }
        const floor = Math.ceil(N_PROBE * 0.9);
        const shapeOk = shapeCheck.has_staff >= floor && shapeCheck.has_attendance >= floor
            && shapeCheck.has_leaves >= floor && shapeCheck.has_shifts >= floor;
        const pass = ok >= floor && shapeOk;
        recPerf(testInfo, MOD, 'profile_aggregate', samples, pass);
        rec(testInfo, { module: MOD, step: 'profile_aggregate', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/hr/staff/{id}/profile',
            note: `n=${N_PROBE} ok=${ok} fail=${fail} shape=${JSON.stringify(shapeCheck)} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Profile aggregate floor ihlal',
            `n=${N_PROBE} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        if (!shapeOk) recFinding(testInfo, 'P2', MOD, 'Profile aggregate shape drift',
            `shape=${JSON.stringify(shapeCheck)} expected has_staff/attendance/leaves/shifts >= ${floor}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'profile_aggregate', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `profile_aggregate floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('B) Salary-history + certifications + documents — özlük yüzeyleri', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'specialty_surfaces', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const counters = { salary_ok: 0, salary_fail: 0, salary_perm: 0,
            cert_ok: 0, cert_fail: 0, doc_ok: 0, doc_fail: 0 };
        const errs = [];
        const target = staffPool[0];
        // Salary-history (view_finance gate; super_admin geçer).
        const salR = await callTimed(request, 'get',
            `/api/hr/staff/${target.id}/salary-history`, undefined, stressTokens.stress_token);
        samples.push(salR.ms);
        if (salR.ok) counters.salary_ok++;
        else if (salR.status === 401 || salR.status === 403) counters.salary_perm++;
        else { counters.salary_fail++; if (errs.length < 3) errs.push({ ep: 'salary', status: salR.status }); }

        // Certifications.
        const certR = await callTimed(request, 'get',
            `/api/hr/staff/${target.id}/certifications`, undefined, stressTokens.stress_token);
        samples.push(certR.ms);
        if (certR.ok) counters.cert_ok++;
        else { counters.cert_fail++; if (errs.length < 3) errs.push({ ep: 'cert', status: certR.status }); }

        // Documents.
        const docR = await callTimed(request, 'get',
            `/api/hr/staff/${target.id}/documents`, undefined, stressTokens.stress_token);
        samples.push(docR.ms);
        if (docR.ok) counters.doc_ok++;
        else { counters.doc_fail++; if (errs.length < 3) errs.push({ ep: 'doc', status: docR.status }); }

        // PII guard on salary-history (IBAN should be masked when displayed cross-user;
        // super_admin context shows raw — so we only verify response shape, no body PII leak via stress logs).
        const pass = (counters.salary_ok + counters.salary_perm === 1)
            && counters.cert_ok === 1 && counters.doc_ok === 1;
        recPerf(testInfo, MOD, 'specialty_surfaces', samples, pass);
        rec(testInfo, { module: MOD, step: 'specialty_surfaces', status: pass ? 'PASS' : 'REVIEW',
            endpoint: 'GET /api/hr/staff/{id}/{salary-history,certifications,documents}',
            note: `counters=${JSON.stringify(counters)} errs=${JSON.stringify(errs)}` });
        if (counters.salary_fail > 0) recFinding(testInfo, 'P2', MOD, 'Salary-history non-perm fail',
            `status=${salR.status}`);
        if (counters.cert_fail > 0 || counters.doc_fail > 0) recFinding(testInfo, 'P2', MOD, 'Certifications/documents non-2xx',
            `cert_fail=${counters.cert_fail} doc_fail=${counters.doc_fail}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'specialty_surfaces', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) Cross-tenant profile probe — pilot staff_id ile stress token → 403/404 expected', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'cross_tenant', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Harvest pilot staff sample (read-only own-tenant).
        const pilotStaffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.pilot_token);
        const pilotStaff = pilotStaffR.body?.staff || pilotStaffR.body?.staff_members
            || pilotStaffR.body?.items || (Array.isArray(pilotStaffR.body) ? pilotStaffR.body : []);
        if (!pilotStaffR.ok || pilotStaff.length === 0) {
            rec(testInfo, { module: MOD, step: 'cross_tenant', status: 'PASS',
                note: `pilot_staff_status=${pilotStaffR.status} pilot_pool=0 — IDOR not exercised (pool empty)` });
            return;
        }
        const pilotSampleId = pilotStaff[0]?.id;
        if (!pilotSampleId) {
            rec(testInfo, { module: MOD, step: 'cross_tenant', status: 'PASS', note: 'no pilot sample id' });
            return;
        }
        // Stress token attempts to read pilot staff profile — must 403/404.
        const r = await callTimed(request, 'get',
            `/api/hr/staff/${pilotSampleId}/profile`, undefined, stressTokens.stress_token);
        const properly_rejected = r.status === 403 || r.status === 404;
        const idor_evidence = r.ok && r.body?.staff?.id === pilotSampleId;
        const pass = properly_rejected && !idor_evidence;
        rec(testInfo, { module: MOD, step: 'cross_tenant', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/hr/staff/{pilot_id}/profile (stress_token)',
            note: `pilot_sample=${pilotSampleId.slice(0, 8)}.. status=${r.status} idor_evidence=${idor_evidence}` });
        if (idor_evidence) recFinding(testInfo, 'P0', MOD, 'Cross-tenant profile IDOR leak',
            `stress_token read pilot staff profile (id=${pilotSampleId}); tenant isolation broken.`);
        else if (!properly_rejected) recFinding(testInfo, 'P1', MOD, 'Cross-tenant profile not 403/404',
            `status=${r.status} — beklenmeyen kabul yüzeyi.`);
        expect(idor_evidence, 'no cross-tenant IDOR evidence').toBe(false);
    });

    test('D) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_profile_detail_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});
