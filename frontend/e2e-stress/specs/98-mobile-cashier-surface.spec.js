// ─────────────────────────────────────────────────────────────────────────
// F9C § 98 — Mobile Cashier Surface Deep Stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Scope (rapor §3.1 — finance/mobile + cashier_router PARTIAL/ZERO idi;
// task-43 deep stress).
//   Backend:
//     backend/domains/pms/cashier_router.py (prefix=/api, tags=PMS/Cashier)
//     backend/routers/finance/mobile.py     (prefix=/api/finance/mobile/*)
//     backend/routers/finance/folio.py      (folio charge/void/refund yan etki)
//   Yüzey:
//     A) GET   /api/cashier/current-shift              (settlement read)
//     B) POST  /api/cashier/open-shift                 (settlement open)
//     C) POST  /api/cashier/manual-transaction         (CHARGE — direction=in)
//          + X-Idempotency-Key zorunlu mutation header
//     D) POST  /api/cashier/manual-transaction         (REFUND — direction=out)
//     E) GET   /api/cashier/x-report                   (in-shift EoS preview)
//     F) GET   /api/cashier/shift/{shift_id}/transactions  (txn detail)
//     G) POST  /api/cashier/close-shift                (settlement close)
//     H) GET   /api/cashier/z-report/{shift_id}        (final EoS report)
//     I) GET   /api/finance/mobile/daily-collections   (mobile cashier read)
//     J) IDOR — GET /api/cashier/shift/{pilot_shift_id}/transactions
//          stress_token + pilot shift id → 404 / [] (tenant scoped).
//          200 + pilot txns → P0 financial breach.
//     K) Anonymous (headerless) GET /api/cashier/current-shift → 401/403.
//     L) "PIN" brute-force throttle probe — /api/cashier/handover-shift
//          (target_email + target_password gate = financial PIN equivalent).
//          6 wrong-password attempts; 7th expects 429 (throttle present).
//          7th still 401 → P1 finding: brute-force unprotected.
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []   (assertNoExternalCallsPostBatch)
//   - pilot mutation = 0    (assertPilotDriftZero primary + supplemental scan)
//   - P0 = P1 = 0; 5xx = 0; PII leak = 0
//   - Mutations stress-tenant scope; descriptions tagged with `${prefix}` so
//     cleanup script catches residue.
//   - Idempotency-Key (X-Idempotency-Key) zorunlu on C/D/G mutation calls.
//   - Module-blocked doctrine: GET current-shift non-2xx → A-I SKIP +
//     REVIEW; J/K/L (security probes) BAĞIMSIZ çalışır.
//   - Skip-as-pass YOK. Financial-critical IDOR breach = P0 emit.
//
// Reporter satırı: `mobile_cashier`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'mobile_cashier';
const SUB_PREFIX = 'F9C_MCASH';
const GAP_MS = 1500;

test.describe.configure({ mode: 'serial' });

test.describe('F9C § 98 — Mobile Cashier Surface', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBookingBaseline = null;
    let pilotKnownShiftId = null;
    let pilotInitialShift = false;   // was an open pilot shift observed at setup?
    let openedShiftId = null;
    let closedShiftId = null;  // captured at G success; H uses this for z-report
    let chargeTxnId = null;
    let refundTxnId = null;
    let preexistingStressShift = false; // stress tenant already had open shift

    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }
    function taggedDescription(label) {
        return `${prefix}_${SUB_PREFIX}_${label}`;
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: stress token + module probe + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBookingBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;

            // Best-effort: capture a REAL pilot shift id for the J IDOR probe.
            // Prefer the currently open shift (also needed for the supplemental
            // drift gate). If pilot has none open, fall back to the most recent
            // closed shift via shift-history — still a real cross-tenant id
            // (architect Round-1 fix: bogus UUID alone does NOT prove tenant
            // boundary). Only if both lookups fail does J use a bogus UUID.
            try {
                const pilotShift = await callTimed(
                    request, 'get', '/api/cashier/current-shift', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (pilotShift.status === 200 && pilotShift.body?.shift?.id) {
                    pilotKnownShiftId = pilotShift.body.shift.id;
                    pilotInitialShift = true;
                }
            } catch { /* ignore */ }
            if (!pilotKnownShiftId) {
                try {
                    const hist = await callTimed(
                        request, 'get', '/api/cashier/shift-history?limit=1', null,
                        stressTokens.pilot_token, { timeout: 10_000 },
                    );
                    const item = (hist.body?.shifts || hist.body?.items || [])[0];
                    const histId = item?.id || item?.shift_id || null;
                    if (histId) pilotKnownShiftId = histId;
                } catch { /* ignore — J final fallback = bogus UUID */ }
            }
        }

        // Module probe: GET current-shift
        const probe = await callTimed(
            request, 'get', '/api/cashier/current-shift', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (probe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Cashier module 5xx on setup probe',
                `GET /api/cashier/current-shift → ${probe.status}; body=${JSON.stringify(probe.body || {}).slice(0, 200)}`);
            expect(probe.status, 'Cashier setup 5xx').toBeLessThan(500);
        }
        if ([401, 403, 404, 501].includes(probe.status)) {
            moduleBlocked = true;
            blockedReason = `setup_probe_${probe.status}`;
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'REVIEW',
                http: probe.status, note: 'Module blocked / not deployed — A-I SKIP, J/K/L independent.',
            });
            recFinding(testInfo, 'P2', MOD,
                `Cashier module blocked at setup (${probe.status})`,
                'A-I lifecycle SKIP; security probes (J/K/L) bağımsız çalışır.');
            return;
        }
        // If stress tenant already has an open shift (residue from prior run),
        // adopt it instead of trying to open a fresh one — open-shift returns
        // 400 if one is already open.
        if (probe.status === 200 && probe.body?.shift?.id) {
            openedShiftId = probe.body.shift.id;
            preexistingStressShift = true;
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'PASS',
                http: probe.status, note: `adopted pre-existing open shift=${openedShiftId}`,
            });
        } else {
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'PASS',
                http: probe.status, note: 'GET current-shift 2xx — no open shift, will open fresh.',
            });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // A) READ current-shift (idempotent read)
    test('A) GET /api/cashier/current-shift', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'A_current_shift', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/cashier/current-shift', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        recPerf(testInfo, MOD, 'A_current_shift', [r.ms], r.status === 200);
        expect(r.status, `A_current_shift 5xx=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `current-shift non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'A_current_shift', status: 'REVIEW', http: r.status });
            return;
        }
        // Tenant scoping invariant
        if (r.body?.shift) {
            expect(r.body.shift.tenant_id, 'A_current_shift: shift tenant_id missing').toBeTruthy();
        }
        rec(testInfo, { module: MOD, step: 'A_current_shift', status: 'PASS', http: r.status });
        await gap(500);
    });

    // ──────────────────────────────────────────────────────────────
    // B) OPEN shift (settlement open)
    test('B) POST /api/cashier/open-shift', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'B_open_shift', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        if (preexistingStressShift && openedShiftId) {
            rec(testInfo, {
                module: MOD, step: 'B_open_shift', status: 'PASS',
                note: `adopted pre-existing shift=${openedShiftId} (open-shift would 400 — single-open invariant honored)`,
            });
            return;
        }
        const r = await callTimed(
            request, 'post', '/api/cashier/open-shift',
            { opening_amount: 1000, denomination_counts: { '100': 10 } },
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('B_open') } },
        );
        recPerf(testInfo, MOD, 'B_open_shift', [r.ms], r.status >= 200 && r.status < 300);
        expect(r.status, `B_open_shift 5xx=${r.status}`).toBeLessThan(500);

        if (r.status === 400 && /açık bir vardiya|already/i.test(JSON.stringify(r.body || ''))) {
            // Race: another concurrent worker opened a shift between probe and open.
            // Adopt it via a follow-up GET.
            const followup = await callTimed(
                request, 'get', '/api/cashier/current-shift', null,
                stressTokens.stress_token, { timeout: 10_000 },
            );
            if (followup.status === 200 && followup.body?.shift?.id) {
                openedShiftId = followup.body.shift.id;
                preexistingStressShift = true;
                rec(testInfo, {
                    module: MOD, step: 'B_open_shift', status: 'PASS',
                    http: r.status, note: `single-open invariant honored, adopted shift=${openedShiftId}`,
                });
                return;
            }
        }
        if (r.status >= 200 && r.status < 300) {
            expect(r.body?.shift?.id, 'B_open_shift: shift id missing').toBeTruthy();
            expect(r.body?.shift?.tenant_id, 'B_open_shift: tenant_id missing').toBeTruthy();
            openedShiftId = r.body.shift.id;
            rec(testInfo, { module: MOD, step: 'B_open_shift', status: 'PASS', http: r.status, note: `shift_id=${openedShiftId}` });
        } else {
            recFinding(testInfo, 'P2', MOD, `open-shift non-2xx status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'B_open_shift', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // C) CHARGE — manual cash transaction direction=in (Idempotency-Key)
    test('C) POST /api/cashier/manual-transaction (charge)', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (openedShiftId ? null : 'no_open_shift');
        if (reason) {
            rec(testInfo, { module: MOD, step: 'C_charge', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const r = await callTimed(
            request, 'post', '/api/cashier/manual-transaction',
            {
                amount: 250,
                direction: 'in',
                method: 'cash',
                type: 'manual_in',
                description: taggedDescription('C_charge'),
            },
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('C_charge') } },
        );
        recPerf(testInfo, MOD, 'C_charge', [r.ms], r.status >= 200 && r.status < 300);
        expect(r.status, `C_charge 5xx=${r.status}`).toBeLessThan(500);
        if (r.status >= 200 && r.status < 300 && r.body?.transaction) {
            chargeTxnId = r.body.transaction.id || r.body.transaction.transaction_id || null;
            rec(testInfo, { module: MOD, step: 'C_charge', status: 'PASS', http: r.status, note: `txn=${chargeTxnId}` });
        } else {
            recFinding(testInfo, 'P2', MOD, `charge non-2xx status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'C_charge', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // D) REFUND — manual cash transaction direction=out (Idempotency-Key)
    test('D) POST /api/cashier/manual-transaction (refund)', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (openedShiftId ? null : 'no_open_shift');
        if (reason) {
            rec(testInfo, { module: MOD, step: 'D_refund', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const r = await callTimed(
            request, 'post', '/api/cashier/manual-transaction',
            {
                amount: 75,
                direction: 'out',
                method: 'cash',
                type: 'paid_out',
                description: taggedDescription('D_refund'),
            },
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('D_refund') } },
        );
        recPerf(testInfo, MOD, 'D_refund', [r.ms], r.status >= 200 && r.status < 300);
        expect(r.status, `D_refund 5xx=${r.status}`).toBeLessThan(500);
        if (r.status >= 200 && r.status < 300 && r.body?.transaction) {
            refundTxnId = r.body.transaction.id || r.body.transaction.transaction_id || null;
            rec(testInfo, { module: MOD, step: 'D_refund', status: 'PASS', http: r.status, note: `txn=${refundTxnId}` });
        } else {
            recFinding(testInfo, 'P2', MOD, `refund non-2xx status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'D_refund', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // E) X-report (in-shift EoS preview)
    test('E) GET /api/cashier/x-report', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'E_x_report', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/cashier/x-report', null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'E_x_report', [r.ms], r.status === 200);
        expect(r.status, `E_x_report 5xx=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `x-report non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'E_x_report', status: 'REVIEW', http: r.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'E_x_report', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // F) shift transactions detail
    test('F) GET /api/cashier/shift/{id}/transactions', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (openedShiftId ? null : 'no_open_shift');
        if (reason) {
            rec(testInfo, { module: MOD, step: 'F_txns', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const r = await callTimed(
            request, 'get', `/api/cashier/shift/${openedShiftId}/transactions`, null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'F_txns', [r.ms], r.status === 200);
        expect(r.status, `F_txns 5xx=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `shift txns non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'F_txns', status: 'REVIEW', http: r.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'F_txns', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // L) SECURITY: PIN brute-force throttle probe (Task-120).
    // Mobile cashier `/api/cashier/peer-verify` is the PIN re-auth gate
    // used at the front-desk terminal every shift. Without a throttle an
    // unattended terminal can be brute-forced one tap at a time. Backend
    // wires CASHIER_PEER_VERIFY_USER + CASHIER_PEER_VERIFY_IP sliding
    // windows (cap=10/900s, always_on, Mongo-backed cross-instance) —
    // the 11th wrong PIN in the window must return 429.
    //
    // MODULE-BLOCKED: probe is independent of shift lifecycle; the
    // throttle layer applies regardless of whether a shift is open.
    //
    // If the 11th attempt is NOT 429, that's a P1 finding (unbounded
    // brute-force on a financial gate). Sequential — no Promise.all so
    // the throttle window applies cleanly.
    test('L) PIN brute-force throttle probe', async ({ request, stressTokens }, testInfo) => {
        // F8AH tur-4 fix (CI cold-boot regression): 11 sequential POSTs
        // with per-call timeout=10s + 200ms pacing ⇒ ~112s nominal, ~165s
        // worst-case (cold Mongo + throttle-enforce write per attempt on
        // a fresh-boot replica without warm caches). Playwright default
        // test budget is 180s which leaves no margin for the fixture
        // setup or the report-recording teardown. Bump only this test's
        // budget to 300s — the brute-force probe IS the test, can't
        // parallelise; this is the cheapest correct fix that preserves
        // the doctrine "no skip-as-pass, no coverage cut".
        test.setTimeout(300_000);
        // Independent of moduleBlocked.
        const statuses = [];
        for (let i = 1; i <= 11; i++) {
            const r = await callTimed(
                request, 'post', '/api/cashier/peer-verify',
                {
                    pin: `wrong_pin_${i}_${cryptoRandomUUID().slice(0, 8)}`,
                },
                stressTokens.stress_token,
                { timeout: 10_000 },
            );
            statuses.push(r.status);
            if (r.status === 429) break;
            // Light pacing so we don't trip global token rate-limit instead
            // of the per-gate throttle we're probing.
            await new Promise((res) => setTimeout(res, 200));
        }
        const last = statuses[statuses.length - 1];
        const throttled = statuses.includes(429);
        expect(last, `L_pin_throttle: 5xx=${last}`).toBeLessThan(500);

        if (throttled) {
            rec(testInfo, {
                module: MOD, step: 'L_pin_throttle', status: 'PASS',
                http: last, note: `throttle hit at attempt ${statuses.indexOf(429) + 1}; statuses=[${statuses.join(',')}]`,
            });
        } else {
            // All 11 attempts rejected only with 401 → gate validates
            // credentials but does NOT throttle. Financial brute-force
            // surface.
            recFinding(testInfo, 'P1', MOD,
                'Cashier peer-verify PIN gate has NO brute-force throttle',
                `11 wrong-PIN attempts produced statuses=[${statuses.join(',')}]; expected 429 by attempt 11. Financial gate must rate-limit.`);
            rec(testInfo, {
                module: MOD, step: 'L_pin_throttle', status: 'REVIEW',
                http: last, note: `no throttle observed; statuses=[${statuses.join(',')}]`,
            });
            // Doctrine: skip-as-pass YOK. This is a real finding, but it's
            // a P1 (no throttle), not a P0 (breach). recFinding surfaces it
            // for triage without failing the suite.
        }
    });

    // ──────────────────────────────────────────────────────────────
    // G) CLOSE shift (settlement close)
    test('G) POST /api/cashier/close-shift', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked
            ? blockedReason
            : (openedShiftId ? (preexistingStressShift ? 'preexisting_shift_skip_close_to_avoid_pilot_disruption' : null) : 'no_open_shift');
        if (reason) {
            rec(testInfo, { module: MOD, step: 'G_close_shift', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        // counted_amount = opening + cash_in - cash_out matches exactly
        // (1000 + 250 - 75 = 1175) so difference=0.
        const r = await callTimed(
            request, 'post', '/api/cashier/close-shift',
            { counted_amount: 1175, denomination_counts: { '50': 23, '25': 1 } },
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('G_close') } },
        );
        recPerf(testInfo, MOD, 'G_close_shift', [r.ms], r.status === 200);
        expect(r.status, `G_close_shift 5xx=${r.status}`).toBeLessThan(500);
        if (r.status === 200) {
            expect(r.body?.status, 'G_close_shift: status not closed').toBe('closed');
            rec(testInfo, {
                module: MOD, step: 'G_close_shift', status: 'PASS', http: r.status,
                note: `expected=${r.body?.expected_amount} counted=${r.body?.counted_amount} diff=${r.body?.difference}`,
            });
            // Stabilize H: stash the id BEFORE clearing openedShiftId so the
            // z-report test doesn't need a shift-history fallback (which can
            // pick an unrelated shift under concurrency).
            closedShiftId = openedShiftId;
            openedShiftId = null; // shift no longer open; cleanup skips re-close
        } else {
            recFinding(testInfo, 'P2', MOD, `close-shift non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'G_close_shift', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // H) Z-report (final EoS)
    test('H) GET /api/cashier/z-report/{shift_id}', async ({ request, stressTokens }, testInfo) => {
        // z-report needs a closed shift id; G might have skipped (preexisting)
        // or failed. Try the last known opened shift id either way.
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'H_z_report', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        // Prefer the deterministic id stashed at G success (closedShiftId).
        // openedShiftId is the fallback if G was skipped (pre-existing
        // adopted shift); shift-history is the final fallback if neither
        // was set. Architect Round-1 fix: shift-history's "latest" can pick
        // an unrelated shift under concurrency, so it's last-resort only.
        let zShiftId = closedShiftId || openedShiftId;
        if (!zShiftId) {
            try {
                const hist = await callTimed(
                    request, 'get', '/api/cashier/shift-history?limit=1', null,
                    stressTokens.stress_token, { timeout: 10_000 },
                );
                const item = (hist.body?.shifts || hist.body?.items || [])[0];
                if (item?.id || item?.shift_id) zShiftId = item.id || item.shift_id;
            } catch { /* ignore */ }
        }
        if (!zShiftId) {
            rec(testInfo, { module: MOD, step: 'H_z_report', status: 'SKIP', note: 'no_shift_id_available' });
            test.skip(true, 'no_shift_id_available');
        }
        const r = await callTimed(
            request, 'get', `/api/cashier/z-report/${zShiftId}`, null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'H_z_report', [r.ms], r.status === 200);
        expect(r.status, `H_z_report 5xx=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `z-report non-200 status=${r.status}`,
                `shift_id=${zShiftId} body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'H_z_report', status: 'REVIEW', http: r.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'H_z_report', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // I) Mobile cashier read endpoint
    test('I) GET /api/finance/mobile/daily-collections', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'I_mobile_daily', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/finance/mobile/daily-collections', null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'I_mobile_daily', [r.ms], r.status === 200);
        expect(r.status, `I_mobile_daily 5xx=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `mobile daily-collections non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'I_mobile_daily', status: 'REVIEW', http: r.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'I_mobile_daily', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // J) SECURITY: IDOR — cross-tenant shift txn read.
    // Financial-critical: stress_token reading pilot's shift transactions
    // would be a P0 cross-tenant breach. Real pilot shift id preferred;
    // bogus UUID fallback at minimum proves "non-existent → no leak".
    test('J) IDOR: cross-tenant shift txn read → no leak', async ({ request, stressTokens }, testInfo) => {
        const targetId = pilotKnownShiftId || `cross-tenant-${cryptoRandomUUID()}`;
        const probeKind = pilotKnownShiftId ? 'real_pilot_shift_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'get',
            `/api/cashier/shift/${targetId}/transactions`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `J_idor 5xx=${r.status}`).toBeLessThan(500);

        if (r.status === 200) {
            // Endpoint returns shift metadata (cashier_name, opened_at,
            // closed_at, status) on 200 in addition to transactions. For a
            // REAL pilot shift id, 200 ALONE is a cross-tenant disclosure of
            // shift metadata — even an empty `transactions[]` exposes that
            // the shift exists, who opened it, and when. Architect Round-1
            // gap: previous logic only flagged when txns.length>0, which
            // could false-PASS a metadata-only breach. Bogus UUID + 200 is
            // still suspect but doesn't prove cross-tenant access (could be
            // a backend bug returning empty shell), so we leave that path as
            // P2 REVIEW.
            const txns = r.body?.transactions || r.body?.items || (Array.isArray(r.body) ? r.body : []);
            const txnCount = Array.isArray(txns) ? txns.length : 0;
            if (probeKind === 'real_pilot_shift_id') {
                recFinding(testInfo, 'P0', MOD,
                    'Financial IDOR breach: stress_token returned 200 on REAL pilot shift id',
                    `target_id=${targetId} txn_count=${txnCount} body_keys=${Object.keys(r.body || {}).join(',')} sample=${JSON.stringify(r.body || {}).slice(0, 200)}`);
                expect(true, `J_idor: ${probeKind}=${targetId} returned 200 → cross-tenant financial breach (metadata disclosure regardless of txn count)`).toBe(false);
            }
            // bogus UUID path — 200 with content is also a leak (unlikely
            // but possible if a UUID collision exists)
            if (txnCount > 0) {
                recFinding(testInfo, 'P0', MOD,
                    `Financial IDOR breach: cross-tenant shift txns leaked (${probeKind})`,
                    `target_id=${targetId} leaked_count=${txnCount} sample=${JSON.stringify(txns[0]).slice(0, 200)}`);
            }
            expect(txnCount, `J_idor: ${probeKind}=${targetId} leaked ${txnCount} txns → cross-tenant financial breach`).toBe(0);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'REVIEW', http: r.status,
                note: `${probeKind} → 200 with empty txns (bogus path — backend returned empty shell, investigate)` });
        } else if ([404, 403, 401].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'PASS', http: r.status, note: `${probeKind} rejected ${r.status}` });
        } else {
            recFinding(testInfo, 'P2', MOD, `IDOR probe unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // K) SECURITY: Anonymous (headerless) GET → 401/403
    test('K) Anonymous (headerless) GET → 401/403', async ({ request }, testInfo) => {
        let status = 0;
        let bodySnippet = '';
        try {
            const r = await request.get('/api/cashier/current-shift', {
                failOnStatusCode: false,
                timeout: 10_000,
            });
            status = r.status();
            try { bodySnippet = (await r.text()).slice(0, 200); } catch { /* ignore */ }
        } catch (e) {
            recFinding(testInfo, 'P2', MOD, 'K_anon network error', String(e?.message || e).slice(0, 200));
        }
        expect(status, `K_anon 5xx=${status}`).toBeLessThan(500);
        const blocked = status === 401 || status === 403;
        if (!blocked) {
            recFinding(testInfo, 'P1', MOD,
                `Anonymous GET cashier current-shift not blocked (status=${status})`,
                `PUBLIC FINANCIAL SURFACE LEAK — tenant cashier state may be reachable without auth. body=${bodySnippet}`);
        }
        expect(blocked, `K_anon: headerless returned ${status} (expected 401/403)`).toBe(true);
        rec(testInfo, { module: MOD, step: 'K_anon', status: 'PASS', http: status, note: 'headerless probe' });
    });

    // ──────────────────────────────────────────────────────────────
    // INVARIANTS
    test('M) Invariant: external_calls=[] for this module batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(
            testInfo, MOD, 'F9C_MCASH_full',
            stressState, request, stressTokens.pilot_token,
        );
        expect(ok, 'external_calls invariant failed').toBe(true);
    });

    test('N) Invariant: pilot drift — booking baseline + cashier shift scan', async ({ request, stressTokens }, testInfo) => {
        const primaryOk = await assertPilotDriftZero(
            testInfo, MOD, request, stressTokens.pilot_token, pilotBookingBaseline,
        );
        expect(primaryOk, 'pilot bookings drift detected → suite mutated pilot').toBe(true);

        // Supplemental: ensure the pilot's open shift (if any) was NOT
        // touched. If pilot had an open shift at setup and now it's closed
        // OR if a new pilot shift appeared whose cashier email matches stress
        // mutations, that's a P0 cross-tenant breach.
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'N_supplemental_shift_scan', status: 'SKIP', note: 'pilot_token yok' });
            return;
        }
        const r = await callTimed(
            request, 'get', '/api/cashier/current-shift', null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        expect(r.status, 'pilot current-shift 5xx').toBeLessThan(500);
        if (r.status !== 200) {
            rec(testInfo, {
                module: MOD, step: 'N_supplemental_shift_scan', status: 'REVIEW',
                http: r.status, note: 'pilot current-shift non-200 — supplemental unverifiable; primary gate authoritative',
            });
            return;
        }
        const pilotShiftNow = r.body?.shift?.id || null;
        if (pilotInitialShift) {
            // The pilot HAD an open shift at setup; it MUST still be open with
            // the same id (we MUST NOT have closed/replaced it).
            if (pilotShiftNow !== pilotKnownShiftId) {
                recFinding(testInfo, 'P0', MOD,
                    'PILOT DRIFT (supplemental): pilot open shift mutated',
                    `before_id=${pilotKnownShiftId} after_id=${pilotShiftNow}`);
            }
            expect(pilotShiftNow, 'pilot drift (supplemental): pilot open shift id changed').toBe(pilotKnownShiftId);
        }
        // Also scan pilot's shift transactions for our prefix tag — if any
        // stress-prefixed description landed in pilot, that's a hard breach.
        if (pilotShiftNow) {
            const tx = await callTimed(
                request, 'get', `/api/cashier/shift/${pilotShiftNow}/transactions`, null,
                stressTokens.pilot_token, { timeout: 10_000 },
            );
            if (tx.status === 200) {
                const txns = tx.body?.transactions || tx.body?.items || (Array.isArray(tx.body) ? tx.body : []);
                const leaked = (Array.isArray(txns) ? txns : []).filter(t =>
                    typeof t?.description === 'string' && t.description.includes(prefix || '__nope__'),
                );
                if (leaked.length > 0) {
                    recFinding(testInfo, 'P0', MOD,
                        'PILOT DRIFT (supplemental): stress-prefixed cashier txn found in pilot shift',
                        `count=${leaked.length} sample=${JSON.stringify(leaked[0]).slice(0, 200)}`);
                }
                expect(leaked.length, 'pilot drift (supplemental): stress-prefixed cashier txn leaked').toBe(0);
            }
        }
        rec(testInfo, {
            module: MOD, step: 'N_supplemental_shift_scan', status: 'PASS', http: r.status,
            note: `pilot_shift_now=${pilotShiftNow} pilot_initial=${pilotInitialShift}`,
        });
    });

    // ──────────────────────────────────────────────────────────────
    // CLEANUP — idempotent best-effort close of any shift we left open.
    // We do NOT hard-delete cashier txns (no endpoint); they remain
    // tagged with `${prefix}` for the external cleanup script.
    test.afterAll(async ({}, testInfo) => {
        const cleanupRec = {
            module: MOD,
            step: 'cleanup',
            charge_txn: chargeTxnId,
            refund_txn: refundTxnId,
            shift_left_open: openedShiftId,
            preexisting_shift: preexistingStressShift,
            note: 'idempotent close of any leftover stress shift; txns retained tagged by data_prefix',
        };
        if (!openedShiftId || preexistingStressShift) {
            cleanupRec.status = 'PASS';
            cleanupRec.note += ' | nothing to close (already closed or pre-existing adopted)';
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
            return;
        }
        try {
            const { request: globalRequest } = await import('@playwright/test');
            const TOKEN_FILE = (await import('node:path')).default.join(
                process.cwd(), 'e2e-stress', '.auth', 'stress-token.json');
            const fs = await import('node:fs');
            if (!fs.existsSync(TOKEN_FILE)) {
                cleanupRec.status = 'SKIP';
                cleanupRec.note += ' | token cache yok';
                testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
                return;
            }
            const tok = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf-8')).stress_token;
            const ctx = await globalRequest.newContext({
                extraHTTPHeaders: { Authorization: `Bearer ${tok}` },
            });
            // Close with counted_amount=0 → backend records a difference but
            // closes the shift cleanly (idempotent if already closed → 404).
            let closeStatus = 0;
            try {
                const r = await ctx.post('/api/cashier/close-shift', {
                    data: { counted_amount: 0 },
                    headers: { 'X-Idempotency-Key': `${SUB_PREFIX}_cleanup_${Date.now()}_${cryptoRandomUUID()}` },
                    timeout: 10_000, failOnStatusCode: false,
                });
                closeStatus = r.status();
            } catch { /* idempotent best-effort */ }
            await ctx.dispose();
            cleanupRec.close_status = closeStatus;
            cleanupRec.status = 'PASS';
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        } catch (e) {
            cleanupRec.status = 'REVIEW';
            cleanupRec.error = String(e?.message || e).slice(0, 200);
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        }
    });
});
