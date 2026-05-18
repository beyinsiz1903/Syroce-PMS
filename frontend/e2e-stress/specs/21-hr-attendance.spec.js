// F8D § 21 — HR Attendance (clock-in / clock-out / records / summary):
// read records + clock-in flow + clock-out same staff + summary aggregate.
//
// Dry-run safety:
//   - clock-in/out endpoints are pure DB writes; no SMS/email/push.
//   - Each iteration uses a distinct seeded staff_id; seeded attendance rows
//     are CLOSED so the staff has no open shift collision.
//   - module-blocked pattern: 403/non-2xx Setup → A/B/C skip + P2.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_attendance';
const N_CLOCK = 5;

test.describe.configure({ mode: 'serial' });

test.describe('F8D § 21 — HR Attendance', () => {
    let pilotBefore = null;
    let prefix = null;
    let staffPool = [];
    let clockedInStaff = [];
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + staff pool', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const staffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
        const allStaff = staffR.body?.staff || staffR.body?.staff_members || staffR.body?.items
            || (Array.isArray(staffR.body) ? staffR.body : []);
        // Filter to seeded stress-prefixed staff who don't have an open attendance row.
        // Router returns staff with `name`/`email`; filter by prefix-tagged
        // identity. Offset 20-30 avoids the first 10 used in 60-row attendance seed.
        staffPool = allStaff.filter((s) => {
            const name = s?.name || s?.full_name || '';
            const email = (s?.email || '').toLowerCase();
            return (typeof name === 'string' && name.startsWith(prefix))
                || (typeof email === 'string' && email.startsWith(prefix.toLowerCase()));
        }).slice(20, 30);
        const reachable = staffR.ok;
        if (!reachable || staffPool.length < N_CLOCK) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'HR attendance module read blocked',
                `staff_status=${staffR.status} pool_size=${staffPool.length} need>=${N_CLOCK} — A/B/C skipped, pilot_drift gate still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} staff_status=${staffR.status} pool=${staffPool.length} module_blocked=${moduleBlocked}` });
        expect(typeof staffR.status).toBe('number');
    });

    test('A) Attendance records list + summary read', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'records_summary', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'HR attendance module blocked');
            return;
        }
        const samples = [];
        const recsR = await callTimed(request, 'get', '/api/hr/attendance/records', undefined, stressTokens.stress_token);
        samples.push(recsR.ms);
        const sumR = await callTimed(request, 'get', '/api/hr/attendance/summary', undefined, stressTokens.stress_token);
        samples.push(sumR.ms);
        recPerf(testInfo, MOD, 'records_summary', samples, recsR.ok && sumR.ok);
        const ok = recsR.ok && sumR.ok;
        rec(testInfo, { module: MOD, step: 'records_summary', status: ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/attendance/{records,summary}',
            note: `records=${recsR.status} summary=${sumR.status} max_ms=${Math.max(...samples)}` });
        if (!ok) recFinding(testInfo, 'P2', MOD, 'Attendance read non-2xx',
            `records=${recsR.status} summary=${sumR.status}`);
        expect(recsR.ok).toBe(true);
    });

    test('B) Clock-in N=5 staff', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'clock_in', status: 'SKIP', note: 'module blocked (see Setup)' });
            test.skip(true, 'HR attendance module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];
        const targets = staffPool.slice(0, N_CLOCK);
        for (const s of targets) {
            // ClockInRequest router contract: { staff_id } only.
            const payload = { staff_id: s.id };
            const r = await callTimedWithBackoff(request, 'post', '/api/hr/clock-in',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) { ok++; clockedInStaff.push(s.id); }
            else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_CLOCK) {
            recFinding(testInfo, 'P2', MOD, 'Clock-in RBAC blocked', `n=${N_CLOCK} all permFail.`);
            rec(testInfo, { module: MOD, step: 'clock_in', status: 'SKIP',
                endpoint: 'POST /api/hr/clock-in', note: `perm_fail=${permFail}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'clock_in', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'Clock-in RBAC-blocked');
            return;
        }
        const floor = Math.ceil(N_CLOCK * 0.9);
        recPerf(testInfo, MOD, 'clock_in', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'clock_in', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/clock-in',
            note: `n=${N_CLOCK} ok=${ok} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_CLOCK) recFinding(testInfo, 'P1', MOD, 'Clock-in floor ihlal',
            `n=${N_CLOCK} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'clock_in', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `clock_in floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Clock-out same staff', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked || clockedInStaff.length === 0) {
            rec(testInfo, { module: MOD, step: 'clock_out', status: 'SKIP',
                note: moduleBlocked ? 'module blocked' : 'no clocked-in staff' });
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        for (const sid of clockedInStaff) {
            const payload = { staff_id: sid };
            const r = await callTimedWithBackoff(request, 'post', '/api/hr/clock-out',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) ok++;
            else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const total = clockedInStaff.length;
        const floor = Math.ceil(total * 0.9);
        recPerf(testInfo, MOD, 'clock_out', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'clock_out', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/clock-out',
            note: `n=${total} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Clock-out floor ihlal',
            `n=${total} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'clock_out', stressState, request, stressTokens.pilot_token);
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
