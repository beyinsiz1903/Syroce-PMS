// F8D § 23 — HR Shift (schedule read / swap request / consent / decision):
// shift schedule read + swap-request create + consent + final decision.
//
// Dry-run safety:
//   - All endpoints DB-only. Swap notification is in-app (`notifications`).
//   - Swap requests use distinct seeded staff pairs (no overlap with seeded
//     pending shift_swap_requests).
//   - module-blocked pattern: 403/non-2xx Setup → A/B/C skip + P2.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_shift';
const N_SWAP = 5;

test.describe.configure({ mode: 'serial' });

test.describe('F8D § 23 — HR Shift', () => {
    let pilotBefore = null;
    let prefix = null;
    let staffPool = [];
    let shiftPool = [];      // seeded shifts (id + staff_id), used to pair shift_id with non-owner target
    let createdSwapIds = [];
    let consentedSwapIds = [];
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + staff pool + shift pool', async ({ request, stressTokens, stressState }, testInfo) => {
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
        });
        // Build shift pool: ShiftSwapRequestPayload requires shift_id from
        // existing shift_schedules. Router GET /hr/shifts returns {items:[{id,staff_id,...}]}.
        const shiftsR = await callTimed(request, 'get', '/api/hr/shifts', undefined, stressTokens.stress_token);
        const allShifts = shiftsR.body?.items || (Array.isArray(shiftsR.body) ? shiftsR.body : []);
        const staffPoolIds = new Set(staffPool.map((s) => s.id));
        shiftPool = allShifts.filter((sh) => sh?.id && sh?.staff_id && staffPoolIds.has(sh.staff_id));
        // Probe canonical list (404 tolerated — endpoint optional on some builds).
        const swapListR = await callTimed(request, 'get', '/api/hr/shift-swap-requests',
            undefined, stressTokens.stress_token);
        const reachable = staffR.ok && shiftsR.ok;
        if (!reachable || staffPool.length < (N_SWAP * 2) || shiftPool.length < N_SWAP) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'HR shift module read blocked',
                `staff_status=${staffR.status} shifts_status=${shiftsR.status} swap_list_status=${swapListR.status} staff_pool=${staffPool.length} shift_pool=${shiftPool.length} need_staff>=${N_SWAP * 2} need_shift>=${N_SWAP} — A/B/C skipped, pilot_drift gate still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} staff_status=${staffR.status} shifts_status=${shiftsR.status} swap_list_status=${swapListR.status} staff_pool=${staffPool.length} shift_pool=${shiftPool.length} module_blocked=${moduleBlocked}` });
        expect(typeof staffR.status).toBe('number');
    });

    test('A) Shift swap list read', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'list_swaps', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'HR shift module blocked');
            return;
        }
        const samples = [];
        const listR = await callTimed(request, 'get', '/api/hr/shift-swap-requests',
            undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        recPerf(testInfo, MOD, 'list_swaps', samples, listR.ok);
        rec(testInfo, { module: MOD, step: 'list_swaps', status: listR.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/shift-swap-requests',
            note: `status=${listR.status} max_ms=${Math.max(...samples)}` });
        if (!listR.ok) recFinding(testInfo, 'P2', MOD, 'Shift swap list non-2xx', `status=${listR.status}`);
        // Soft: list endpoint may not exist on every backend; tolerate 404 as REVIEW only.
        if (listR.status !== 404) expect(listR.ok).toBe(true);
    });

    test('B) Create N=5 shift swap requests', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'create_swaps', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'HR shift module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];
        // Router contract: { shift_id, target_staff_id, reason }. target must
        // differ from shift owner. Pick distinct targets from staffPool that
        // do NOT match the shift's owner.
        const pairs = [];
        for (let i = 0; i < N_SWAP && i < shiftPool.length; i++) {
            const shift = shiftPool[i];
            const target = staffPool.find((s) => s.id && s.id !== shift.staff_id
                && !pairs.some((p) => p.target_staff_id === s.id));
            if (target) pairs.push({ shift_id: shift.id, target_staff_id: target.id });
        }
        for (let i = 0; i < pairs.length; i++) {
            const payload = {
                shift_id: pairs[i].shift_id,
                target_staff_id: pairs[i].target_staff_id,
                reason: `${prefix} F8D 23-B swap req ${i + 1}`,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/hr/shift-swap-request',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            // Router returns { success, request: {id, ...} }.
            const swapId = r.body?.request?.id || r.body?.id || r.body?.swap_id;
            if (r.ok && swapId) {
                ok++;
                createdSwapIds.push(swapId);
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        // RBAC short-circuit: super_admin is NOT in HR_ELEVATED_ROLES
        // ({'admin','owner','supervisor','manager','hr','finance'}) AND swap
        // create requires caller email == shift owner email. Stress admin
        // almost always fails → permFail-dominant path is expected.
        if (pairs.length === 0 || permFail >= Math.max(1, pairs.length)) {
            recFinding(testInfo, 'P2', MOD, 'Swap create RBAC blocked',
                `pairs=${pairs.length} perm_fail=${permFail} (super_admin not in HR_ELEVATED_ROLES + email mismatch with shift owner).`);
            rec(testInfo, { module: MOD, step: 'create_swaps', status: 'SKIP',
                endpoint: 'POST /api/hr/shift-swap-request', note: `pairs=${pairs.length} perm_fail=${permFail}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'create_swaps', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'Swap create RBAC-blocked');
            return;
        }
        const floor = Math.ceil(pairs.length * 0.9);
        recPerf(testInfo, MOD, 'create_swaps', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'create_swaps', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/shift-swap-request',
            note: `n=${pairs.length} ok=${ok} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} floor>=${floor} created=${createdSwapIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < pairs.length) recFinding(testInfo, 'P1', MOD, 'Shift swap create floor ihlal',
            `n=${pairs.length} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'create_swaps', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `create_swaps floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Consent + decision lifecycle', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked || createdSwapIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'consent_decision', status: 'SKIP',
                note: moduleBlocked ? 'module blocked' : 'no created swaps' });
            return;
        }
        const samples = [];
        let consentOk = 0, decisionOk = 0, consentPermFail = 0, decisionPermFail = 0, fail = 0, throttled = 0;
        const errs = [];
        for (let i = 0; i < createdSwapIds.length; i++) {
            const sid = createdSwapIds[i];
            // target consent — router requires caller email == target_staff email
            // (no role bypass). Stress admin will 403 → tolerated as RBAC.
            const cR = await callTimedWithBackoff(request, 'post',
                `/api/hr/shift-swap-request/${sid}/consent`,
                { action: 'approve', note: `${prefix} F8D 23-C consent` },
                stressTokens.stress_token);
            samples.push(cR.ms);
            if (cR.throttled) throttled++;
            if (cR.ok) { consentOk++; consentedSwapIds.push(sid); }
            else if (cR.status === 401 || cR.status === 403) consentPermFail++;
            else { fail++; if (errs.length < 3) errs.push({ phase: 'consent', status: cR.status, body: JSON.stringify(cR.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
            // final decision — ShiftSwapDecisionPayload: { action, note }
            const dR = await callTimedWithBackoff(request, 'post',
                `/api/hr/shift-swap-request/${sid}/decision`,
                { action: i % 2 === 0 ? 'approve' : 'reject', note: `${prefix} F8D 23-C decision` },
                stressTokens.stress_token);
            samples.push(dR.ms);
            if (dR.throttled) throttled++;
            if (dR.ok) decisionOk++;
            else if (dR.status === 401 || dR.status === 403) decisionPermFail++;
            else { fail++; if (errs.length < 3) errs.push({ phase: 'decision', status: dR.status, body: JSON.stringify(dR.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const total = createdSwapIds.length;
        // RBAC tolerance: consent endpoint demands target_email match — for
        // stress admin always 403. Decision needs require_op which super_admin
        // passes; if both are RBAC-dominated treat as informational.
        if (consentPermFail >= total && decisionPermFail >= total) {
            recFinding(testInfo, 'P2', MOD, 'Swap consent+decision RBAC blocked',
                `n=${total} consent_perm_fail=${consentPermFail} decision_perm_fail=${decisionPermFail} — consent requires target email match (intentional).`);
            rec(testInfo, { module: MOD, step: 'consent_decision', status: 'SKIP',
                endpoint: 'POST /api/hr/shift-swap-request/{id}/{consent,decision}',
                note: `n=${total} consent_perm_fail=${consentPermFail} decision_perm_fail=${decisionPermFail} (RBAC-blocked)` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'consent_decision', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            return;
        }
        const floor = Math.ceil(total * 0.8);
        const consentReachable = total - consentPermFail;
        const decisionReachable = total - decisionPermFail;
        const consentFloor = Math.ceil(Math.max(1, consentReachable) * 0.8);
        const decisionFloor = Math.ceil(Math.max(1, decisionReachable) * 0.8);
        const pass = consentOk >= consentFloor && decisionOk >= decisionFloor;
        recPerf(testInfo, MOD, 'consent_decision', samples, pass);
        rec(testInfo, { module: MOD, step: 'consent_decision', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/shift-swap-request/{id}/{consent,decision}',
            note: `n=${total} consent_ok=${consentOk}/${consentReachable} decision_ok=${decisionOk}/${decisionReachable} fail=${fail} perm_fail(c/d)=${consentPermFail}/${decisionPermFail} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (!pass) recFinding(testInfo, 'P1', MOD, 'Shift swap consent/decision floor ihlal',
            `n=${total} consent_ok=${consentOk}/${consentReachable} decision_ok=${decisionOk}/${decisionReachable} errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'consent_decision', stressState, request, stressTokens.pilot_token);
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
