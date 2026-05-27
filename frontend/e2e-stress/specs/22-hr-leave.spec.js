// F8D § 22 — HR Leave (balance / requests / decision):
// balance read + leave-request create + decision approve/reject + balance recalc.
//
// Dry-run safety:
//   - All endpoints DB-only. Notification on decision is in-app
//     (`notifications` collection) — no Resend/SMS/push dispatch.
//   - Created leave-requests tagged with prefix in `reason`.
//   - module-blocked pattern: 403/non-2xx Setup → A/B/C skip + P2.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_leave';
const N_REQ = 5;

test.describe.configure({ mode: 'serial' });

test.describe('F8D § 22 — HR Leave', () => {
    let pilotBefore = null;
    let prefix = null;
    let staffPool = [];
    let createdRequestIds = [];
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + staff pool + balance probe', async ({ request, stressTokens, stressState }, testInfo) => {
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
        }).slice(0, N_REQ + 2);
        let balanceProbe = null;
        if (staffPool.length > 0) {
            balanceProbe = await callTimed(request, 'get', `/api/hr/leave-balance/${staffPool[0].id}`,
                undefined, stressTokens.stress_token);
        }
        const reachable = staffR.ok && (balanceProbe?.ok ?? false);
        if (!reachable || staffPool.length < N_REQ) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'HR leave module read blocked',
                `staff_status=${staffR.status} balance_status=${balanceProbe?.status ?? 'n/a'} pool=${staffPool.length} — A/B/C skipped, pilot_drift gate still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} staff_status=${staffR.status} balance_status=${balanceProbe?.status ?? 'n/a'} pool=${staffPool.length} module_blocked=${moduleBlocked}` });
        expect(typeof staffR.status).toBe('number');
    });

    test('A) Leave requests list', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'list_requests', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'HR leave module blocked');
            return;
        }
        const samples = [];
        const listR = await callTimed(request, 'get', '/api/hr/leave-requests', undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        recPerf(testInfo, MOD, 'list_requests', samples, listR.ok);
        const list = listR.body?.leave_requests || listR.body?.items || (Array.isArray(listR.body) ? listR.body : []);
        rec(testInfo, { module: MOD, step: 'list_requests', status: listR.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/leave-requests',
            note: `status=${listR.status} count=${list.length} max_ms=${Math.max(...samples)}` });
        if (!listR.ok) recFinding(testInfo, 'P2', MOD, 'Leave list non-2xx', `status=${listR.status}`);
        expect(listR.ok).toBe(true);
    });

    test('B) Create N=5 leave requests', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'create_requests', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'HR leave module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];
        for (let i = 0; i < N_REQ; i++) {
            const s = staffPool[i];
            const startD = new Date();
            startD.setDate(startD.getDate() + 30 + i);
            const endD = new Date(startD);
            endD.setDate(endD.getDate() + 2);
            const payload = {
                staff_id: s.id,
                leave_type: 'annual',
                start_date: startD.toISOString().slice(0, 10),
                end_date: endD.toISOString().slice(0, 10),
                reason: `${prefix} F8D 22-B leave req ${i + 1}`,
            };
            const r = await callTimed(request, 'post', '/api/hr/leave-request',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            // Router response: { success, leave_id, total_days, status }
            if (r.ok && (r.body?.leave_id || r.body?.id)) {
                ok++;
                createdRequestIds.push(r.body.leave_id || r.body.id);
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_REQ) {
            recFinding(testInfo, 'P2', MOD, 'Leave create RBAC blocked', `n=${N_REQ} all permFail.`);
            rec(testInfo, { module: MOD, step: 'create_requests', status: 'SKIP',
                endpoint: 'POST /api/hr/leave-request', note: `perm_fail=${permFail}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'create_requests', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'Leave create RBAC-blocked');
            return;
        }
        const floor = Math.ceil(N_REQ * 0.9);
        recPerf(testInfo, MOD, 'create_requests', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'create_requests', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/leave-request',
            note: `n=${N_REQ} ok=${ok} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} floor>=${floor} created=${createdRequestIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_REQ) recFinding(testInfo, 'P1', MOD, 'Leave request create floor ihlal',
            `n=${N_REQ} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'create_requests', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `create_requests floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Decision (approve/reject)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked || createdRequestIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'decision', status: 'SKIP',
                note: moduleBlocked ? 'module blocked' : 'no created requests' });
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        // Task #263: backend 2-aşamalı state machine — pending → dept_approve →
        // dept_approved → approve → approved. Reject pending'den de olur.
        // Spec her i için: i%2==0 → dept_approve sonra approve (chained ok),
        //                   i%2==1 → reject (single-step). ok floor=N.
        for (let i = 0; i < createdRequestIds.length; i++) {
            const rid = createdRequestIds[i];
            if (i % 2 === 0) {
                // Aşama 1: dept_approve
                const r1 = await callTimed(request, 'post', `/api/hr/leave-request/${rid}/decision`,
                    { decision: 'dept_approve', note: `${prefix} 22-C dept` }, stressTokens.stress_token);
                samples.push(r1.ms);
                if (r1.throttled) throttled++;
                if (!r1.ok) {
                    fail++;
                    if (errs.length < 3) errs.push({ phase: 'dept_approve', status: r1.status, body: JSON.stringify(r1.body).slice(0, 120) });
                    await new Promise((res) => setTimeout(res, 1500));
                    continue;
                }
                await new Promise((res) => setTimeout(res, 600));
                // Aşama 2: approve (final HR)
                const r2 = await callTimed(request, 'post', `/api/hr/leave-request/${rid}/decision`,
                    { decision: 'approve', note: `${prefix} 22-C final` }, stressTokens.stress_token);
                samples.push(r2.ms);
                if (r2.throttled) throttled++;
                if (r2.ok) ok++;
                else { fail++; if (errs.length < 3) errs.push({ phase: 'approve', status: r2.status, body: JSON.stringify(r2.body).slice(0, 120) }); }
            } else {
                // Reject — pending'den direkt geçer
                const r = await callTimed(request, 'post', `/api/hr/leave-request/${rid}/decision`,
                    { decision: 'reject', note: `${prefix} 22-C reject reason` }, stressTokens.stress_token);
                samples.push(r.ms);
                if (r.throttled) throttled++;
                if (r.ok) ok++;
                else { fail++; if (errs.length < 3) errs.push({ phase: 'reject', status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const total = createdRequestIds.length;
        const floor = Math.ceil(total * 0.9);
        recPerf(testInfo, MOD, 'decision', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'decision', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/leave-request/{id}/decision',
            note: `n=${total} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Leave decision floor ihlal',
            `n=${total} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'decision', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});
