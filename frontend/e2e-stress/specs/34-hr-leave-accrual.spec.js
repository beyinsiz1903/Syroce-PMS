// F8D-v2 § 34 — HR Leave Balance Accrual + Carryover Stress.
//
// Scope: backlog items "Leave balance accrual / carry-over smoke" — F8D v1
// spec 22 only tested request→decision; balance probe vardı ama monthly
// accrual + year-end carry-over hesap path'i test edilmedi.
//
// Covered endpoints:
//   • GET  /api/hr/leave-balance/{staff_id}?year=YYYY  — current balance
//   • POST /api/hr/leave-balance                       — upsert (carry/ent)
//   • POST /api/hr/leave-request                       — fresh request (idempot)
//   • POST /api/hr/leave-request/{id}/decision         — approve (decrement)
//
// Dry-run safety: leave decision approve → in-app notification only
// (DB write). Email/Resend not invoked here (F8B § 11/12 doctrine).
//
// Mutlak kurallar:
//   - pilot mutation YOK (E baseline diff)
//   - external_calls=[] (in-app notification only)
//   - failedTests=0, P0=P1=0
//   - Spec-created leave_requests stress_seed/prefix tagged'i değil ama
//     stress tenant scope'unda; cleanup loop bu rows'u tenant_id eşleştirir.
//     Yine de spec içinde idempotent re-decision attempt cleanup-ish: request
//     rejected/approved sonra immutable.

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_leave_accrual';

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v2 § 34 — HR Leave Balance Accrual + Carryover', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let staffPool = [];
    let savedBalances = []; // {staff_id, year, before}  — restore-on-cleanup
    let createdLeaveIds = []; // fresh leave_requests created in step B

    test('Setup: prefix + pilot baseline + staff pool + leave-balance probe', async ({ request, stressTokens, stressState }, testInfo) => {
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
        }).slice(0, 5);
        if (staffPool.length === 0) {
            moduleBlocked = true;
            blockedReason = 'no_stress_staff';
            recFinding(testInfo, 'P2', MOD, 'No stress-tagged staff in pool',
                `total=${allStaff.length} prefix=${prefix} pool=0 — A/B/C/D skipped, E enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS', note: `module_blocked=true` });
            return;
        }
        // Probe one balance to verify endpoint reachable
        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/hr/leave-balance/${staffPool[0].id}`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `leave_balance_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Leave-balance probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C/D skipped.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} staff_total=${allStaff.length} pool=${staffPool.length} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
    });

    test('A) GET leave-balance baseline — read shape sanity', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'baseline_read', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0;
        for (const s of staffPool) {
            const r = await callTimed(request, 'get',
                `/api/hr/leave-balance/${s.id}`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            const shapeOk = r.ok && r.body && r.body.annual
                && typeof r.body.annual.entitlement === 'number'
                && typeof r.body.annual.remaining === 'number';
            if (shapeOk) {
                ok++;
                savedBalances.push({
                    staff_id: s.id,
                    year: r.body.year,
                    annual_entitlement: r.body.annual.entitlement,
                    carry_over: r.body.annual.carry_over,
                    sick_entitlement: r.body.sick.entitlement,
                    used_before: r.body.annual.used,
                });
            } else fail++;
            await new Promise((res) => setTimeout(res, 200));
        }
        const pass = fail === 0 && ok === staffPool.length;
        recPerf(testInfo, MOD, 'baseline_read', samples, pass);
        rec(testInfo, { module: MOD, step: 'baseline_read', status: pass ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/leave-balance/{staff_id}',
            note: `n=${staffPool.length} ok=${ok} fail=${fail}` });
        if (!pass) recFinding(testInfo, 'P2', MOD, 'Baseline leave-balance read fail',
            `n=${staffPool.length} ok=${ok} fail=${fail}`);
    });

    test('B) Approve fresh leave_request → balance decrement check', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked || savedBalances.length === 0) {
            rec(testInfo, { module: MOD, step: 'approve_decrement', status: 'SKIP', note: `module blocked or empty baseline` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let createOk = 0, decisionOk = 0, decrementOk = 0, fail = 0, permFail = 0;
        const errs = [];
        // Tek bir staff için end-to-end: create leave_request → approve → re-read balance.
        const target = savedBalances[0];
        // Future dates within current year (kalan gün varsa kullan)
        const today = new Date();
        const start = new Date(today.getTime() + 21 * 86_400_000);
        const end = new Date(start.getTime() + 1 * 86_400_000);
        const fmt = (d) => `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
        // Yıl ortasında 2 günlük annual leave; days_requested=2.
        const createR = await callTimedWithBackoff(request, 'post', '/api/hr/leave-request', {
            staff_id: target.staff_id,
            leave_type: 'annual',
            start_date: fmt(start),
            end_date: fmt(end),
            reason: `${prefix} F8D-v2 34-B leave dry-run`,
        }, stressTokens.stress_token);
        samples.push(createR.ms);
        const lid = createR.body?.request?.id || createR.body?.id || createR.body?.leave_id;
        if (createR.ok && lid) {
            createOk++;
            createdLeaveIds.push(lid);
        } else if (createR.status === 401 || createR.status === 403) {
            permFail++;
            errs.push({ phase: 'create', status: createR.status, body: JSON.stringify(createR.body).slice(0, 120) });
        } else {
            fail++;
            errs.push({ phase: 'create', status: createR.status, body: JSON.stringify(createR.body).slice(0, 120) });
        }
        if (createOk === 0 && permFail >= 1) {
            recFinding(testInfo, 'P2', MOD, 'Leave-request create RBAC blocked',
                `status=${createR.status} — A/B/C/D skipped from here, E enforced.`);
            rec(testInfo, { module: MOD, step: 'approve_decrement', status: 'SKIP',
                note: `perm_fail=${permFail} errs=${JSON.stringify(errs)}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'approve_decrement', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'RBAC blocked');
            return;
        }
        if (createOk === 0) {
            recPerf(testInfo, MOD, 'approve_decrement', samples, false);
            rec(testInfo, { module: MOD, step: 'approve_decrement', status: 'FAIL',
                note: `create failed: ${JSON.stringify(errs)}` });
            recFinding(testInfo, 'P1', MOD, 'Leave-request create failed',
                `errs=${JSON.stringify(errs)}`);
            expect(createOk).toBeGreaterThan(0);
            return;
        }
        // Approve decision — router contract: { decision: 'approve'|'reject', note? }
        // (backend/domains/hr/router.py:112-114 LeaveDecision). NOT `action`.
        const decR = await callTimedWithBackoff(request, 'post',
            `/api/hr/leave-request/${lid}/decision`,
            { decision: 'approve', note: `${prefix} F8D-v2 34-B approve` },
            stressTokens.stress_token);
        samples.push(decR.ms);
        if (decR.ok) decisionOk++;
        else if (decR.status === 401 || decR.status === 403) permFail++;
        else { fail++; errs.push({ phase: 'decision', status: decR.status, body: JSON.stringify(decR.body).slice(0, 120) }); }
        // Re-read balance — used should be ≥ before+2 (router computes from approved leaves)
        await new Promise((res) => setTimeout(res, 600));
        const afterR = await callTimed(request, 'get',
            `/api/hr/leave-balance/${target.staff_id}`, undefined, stressTokens.stress_token);
        samples.push(afterR.ms);
        const usedAfter = afterR.body?.annual?.used;
        const decremented = decisionOk > 0 && typeof usedAfter === 'number' && usedAfter >= target.used_before + 2;
        if (decremented) decrementOk++;

        const pass = createOk > 0 && decisionOk > 0 && decrementOk > 0;
        recPerf(testInfo, MOD, 'approve_decrement', samples, pass);
        rec(testInfo, { module: MOD, step: 'approve_decrement',
            status: pass ? 'PASS' : (permFail > 0 ? 'REVIEW' : 'FAIL'),
            endpoint: 'POST /api/hr/leave-request + .../decision',
            note: `create_ok=${createOk} decision_ok=${decisionOk} used_before=${target.used_before} used_after=${usedAfter} decrement_ok=${decrementOk} perm_fail=${permFail} errs=${JSON.stringify(errs)}` });
        if (!pass && permFail === 0) recFinding(testInfo, 'P1', MOD,
            'Leave decrement contract ihlal — approve sonrası used artmadı',
            `before=${target.used_before} after=${usedAfter} decision_ok=${decisionOk}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'approve_decrement', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) Year-end carryover upsert — POST /hr/leave-balance set carry_over', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || savedBalances.length === 0) {
            rec(testInfo, { module: MOD, step: 'carryover_upsert', status: 'SKIP', note: 'module blocked' });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let upsertOk = 0, readbackOk = 0, restoreOk = 0, permFail = 0;
        const errs = [];
        const target = savedBalances[0];
        const TEST_CARRY = 3; // 3 gün carry-over set
        // Upsert: carry_over set
        const upR = await callTimedWithBackoff(request, 'post', '/api/hr/leave-balance', {
            staff_id: target.staff_id,
            year: target.year,
            annual_entitlement: target.annual_entitlement,
            carry_over: TEST_CARRY,
            sick_entitlement: target.sick_entitlement,
        }, stressTokens.stress_token);
        samples.push(upR.ms);
        if (upR.ok) upsertOk++;
        else if (upR.status === 401 || upR.status === 403) permFail++;
        else { errs.push({ phase: 'upsert', status: upR.status, body: JSON.stringify(upR.body).slice(0, 120) }); }
        // Read back
        const rbR = await callTimed(request, 'get',
            `/api/hr/leave-balance/${target.staff_id}?year=${target.year}`, undefined, stressTokens.stress_token);
        samples.push(rbR.ms);
        if (rbR.ok && rbR.body?.annual?.carry_over === TEST_CARRY) readbackOk++;
        // Restore: carry_over original değerine geri al (idempotent upsert)
        const restoreR = await callTimedWithBackoff(request, 'post', '/api/hr/leave-balance', {
            staff_id: target.staff_id,
            year: target.year,
            annual_entitlement: target.annual_entitlement,
            carry_over: target.carry_over || 0,
            sick_entitlement: target.sick_entitlement,
        }, stressTokens.stress_token);
        if (restoreR.ok) restoreOk++;

        if (permFail >= 1) {
            recFinding(testInfo, 'P2', MOD, 'Leave-balance upsert RBAC blocked',
                `status=${upR.status} — require_op(view_executive_reports) gate; super_admin normalde bypass eder.`);
            rec(testInfo, { module: MOD, step: 'carryover_upsert', status: 'SKIP',
                note: `perm_fail=${permFail} errs=${JSON.stringify(errs)}` });
            test.skip(true, 'RBAC blocked');
            return;
        }
        const pass = upsertOk > 0 && readbackOk > 0 && restoreOk > 0;
        recPerf(testInfo, MOD, 'carryover_upsert', samples, pass);
        rec(testInfo, { module: MOD, step: 'carryover_upsert',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/leave-balance',
            note: `upsert_ok=${upsertOk} readback_ok=${readbackOk} restore_ok=${restoreOk} test_carry=${TEST_CARRY} original_carry=${target.carry_over || 0} errs=${JSON.stringify(errs)}` });
        if (!pass) recFinding(testInfo, 'P1', MOD, 'Carryover upsert/readback contract ihlal',
            `upsert=${upsertOk} readback=${readbackOk} restore=${restoreOk} errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'carryover_upsert', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(pass, `carryover lifecycle contract`).toBe(true);
    });

    test('D) Future-year accrual probe — READ-only default behavior (no upsert)', async ({ request, stressTokens }, testInfo) => {
        // Architect-iter-1 fix: D adımı RESIDUE bırakmamak için artık POST upsert
        // YAPMAZ; backend router default behavior'ı (line 1571 — annual=14 fallback
        // when balance not configured) doğrular. Future-year leave_balances row
        // yazılmaz → stress-tenant residue + restore karmaşası engellenir.
        if (moduleBlocked || savedBalances.length === 0) {
            rec(testInfo, { module: MOD, step: 'future_accrual_readonly', status: 'SKIP', note: 'module blocked' });
            return;
        }
        const samples = [];
        const target = savedBalances[0];
        const nextYear = target.year + 1;
        const rbR = await callTimed(request, 'get',
            `/api/hr/leave-balance/${target.staff_id}?year=${nextYear}`, undefined, stressTokens.stress_token);
        samples.push(rbR.ms);
        // Backend default: configured=false → annual.entitlement=14 (İş K. m.53)
        const defaultOk = rbR.ok && rbR.body?.year === nextYear
            && rbR.body?.configured === false
            && typeof rbR.body?.annual?.entitlement === 'number'
            && rbR.body.annual.entitlement >= 14;
        recPerf(testInfo, MOD, 'future_accrual_readonly', samples, rbR.ok);
        rec(testInfo, { module: MOD, step: 'future_accrual_readonly',
            status: defaultOk ? 'PASS' : 'REVIEW',
            endpoint: 'GET /api/hr/leave-balance/{id}?year=Y+1 (read-only)',
            note: `next_year=${nextYear} readback_status=${rbR.status} configured=${rbR.body?.configured} entitlement=${rbR.body?.annual?.entitlement} default_ok=${defaultOk}` });
        if (rbR.ok && !defaultOk) recFinding(testInfo, 'P2', MOD,
            'Future-year default leave-balance contract drift',
            `expected configured=false + annual.entitlement>=14; got configured=${rbR.body?.configured} entitlement=${rbR.body?.annual?.entitlement}`);
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_leave_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});
