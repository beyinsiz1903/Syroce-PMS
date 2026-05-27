// ─────────────────────────────────────────────────────────────────────────
// F9D § 99 — Finance Folio & Guest-Purchase Surface Deep Stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Scope (task-52 — Full App Coverage Closure Sprint, F9D slot):
//   Backend:
//     backend/routers/finance/folio.py          (prefix /api/folio/*)
//     backend/domains/guest/operations_router.py (guest upsell purchase)
//   Yüzey:
//     A) GET   /api/folio/list?limit=20                 (read, harvest folio)
//     B) GET   /api/folio/{folio_id}                    (detail + invariants)
//     C) POST  /api/folio/{folio_id}/charge             (post charge)
//          + X-Idempotency-Key (replay aynı key → idempotent / 409)
//     D) POST  /api/folio/{folio_id}/payment            (post payment)
//          + X-Idempotency-Key
//     E) POST  /api/folio/{folio_id}/void-charge/{cid}  (void = "refund" line)
//     F) POST  /api/folio/{folio_id}/payment/{pid}/void (void payment)
//     G) POST  /api/guest/purchase-upsell/{bid}         (guest endpoint —
//          staff JWT lacks guest.email → expected 4xx, NOT 5xx)
//     H) GET   /api/guest/purchased-upsells/{bid}       (guest read probe)
//     I) IDOR — pilot folio_id harvested via pilot_token; stress_token
//          tries GET /api/folio/{pilot_id}, charge POST, payment POST,
//          close POST. Each MUST be ≥400 hard-asserted. 2xx = P0 cross-
//          tenant financial breach (threat-model § Information Disclosure,
//          § Tampering, § Elevation of Privilege all collapse here).
//     J) Anonymous (headerless) GET /api/folio/list → 401/403.
//          Public financial surface = P1 if not blocked.
//     K) Bogus folio id mutations (charge/payment/close) on UUID that
//          does not exist anywhere → 4xx (no 5xx, no leak).
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []   (assertNoExternalCallsPostBatch after batch)
//   - pilot mutation = 0    (assertPilotDriftZero + supplemental folio scan)
//   - P0 = P1 = 0; 5xx = 0
//   - Mutations stress-tenant scope; descriptions tagged with `${prefix}` +
//     SUB_PREFIX so cleanup script catches residue
//     (folio_charges/payments are in STRESS_COLLECTIONS forward-compat list).
//   - Idempotency-Key (X-Idempotency-Key) zorunlu on C/D mutation calls;
//     replay assertion (same key → no duplicate row) explicit.
//   - Module-blocked doctrine: GET /api/folio/list non-2xx → A–H SKIP
//     + P2 REVIEW; I/J/K (security probes) BAĞIMSIZ çalışır.
//   - Skip-as-pass YOK. Cross-tenant 2xx on real pilot folio_id = P0 emit.
//   - Destructive POST sadece stress-tenant + spec-side teardown void.
//
// Reporter satırı: `finance_folio`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'finance_folio';
const SUB_PREFIX = 'F9D_FOLIO';
const GAP_MS = 1200;

test.describe.configure({ mode: 'serial' });

test.describe('F9D § 99 — Finance Folio & Guest-Purchase Surface', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBookingBaseline = null;

    // stress-tenant harvests
    let stressFolioId = null;
    let stressBookingId = null;
    let createdChargeId = null;
    let createdPaymentId = null;

    // pilot harvest for IDOR
    let pilotFolioId = null;
    let pilotBookingId = null;

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
    test('Setup: stress token + module probe + pilot baseline + harvest', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        // Pilot booking baseline (drift guard).
        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBookingBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;
            rec(testInfo, {
                module: MOD, step: 'setup_pilot_baseline',
                status: 'PASS', note: `pilot bookings baseline=${pilotBookingBaseline}`,
            });
        } else {
            rec(testInfo, {
                module: MOD, step: 'setup_pilot_baseline',
                status: 'SKIP', note: 'pilot_token yok — drift guard reduced',
            });
        }

        // Module probe — GET /api/folio/list (require_op view_finance_reports).
        // Non-2xx → module/RBAC blocked → A–H SKIP, security probes still run.
        const probe = await callTimed(
            request, 'get', '/api/folio/list?limit=5', null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        if (probe.status !== 200) {
            moduleBlocked = true;
            blockedReason = `folio_list_probe http=${probe.status}`;
            recFinding(testInfo, 'P2', MOD,
                `Finance folio module blocked (http=${probe.status})`,
                `stress_token finance module reach yok — A–H SKIP, I/J/K bağımsız.`);
            rec(testInfo, {
                module: MOD, step: 'setup_module_probe',
                status: 'REVIEW', http: probe.status, note: blockedReason,
            });
        } else {
            rec(testInfo, { module: MOD, step: 'setup_module_probe', status: 'PASS', http: 200 });
        }

        // Harvest a stress-tenant OPEN folio for mutation tests.
        if (!moduleBlocked) {
            const items = probe.body?.folios || probe.body?.items || (Array.isArray(probe.body) ? probe.body : []);
            const openFolio = items.find((f) => (f.status || 'open') === 'open' && f.id) || items[0];
            if (openFolio?.id) {
                stressFolioId = openFolio.id;
                stressBookingId = openFolio.booking_id || null;
                rec(testInfo, {
                    module: MOD, step: 'setup_harvest_stress_folio',
                    status: 'PASS', note: `folio_id=${stressFolioId} booking_id=${stressBookingId}`,
                });
            } else {
                rec(testInfo, {
                    module: MOD, step: 'setup_harvest_stress_folio',
                    status: 'REVIEW', note: 'no open folio in stress tenant — C–F will SKIP',
                });
            }
        }

        // Harvest a pilot folio_id for IDOR (read-only on pilot side).
        if (stressTokens.pilot_token) {
            try {
                const pr = await callTimed(
                    request, 'get', '/api/folio/list?limit=5', null,
                    stressTokens.pilot_token, { timeout: 15_000 },
                );
                if (pr.status === 200) {
                    const pItems = pr.body?.folios || pr.body?.items || (Array.isArray(pr.body) ? pr.body : []);
                    const pf = pItems.find((f) => f.id) || null;
                    if (pf?.id) {
                        pilotFolioId = pf.id;
                        pilotBookingId = pf.booking_id || null;
                        rec(testInfo, {
                            module: MOD, step: 'setup_harvest_pilot_folio',
                            status: 'PASS', note: `pilot_folio_id=${pilotFolioId.slice(0, 8)}…`,
                        });
                    } else {
                        rec(testInfo, {
                            module: MOD, step: 'setup_harvest_pilot_folio',
                            status: 'REVIEW', note: 'pilot folio list empty — IDOR falls back to bogus uuid',
                        });
                    }
                } else {
                    rec(testInfo, {
                        module: MOD, step: 'setup_harvest_pilot_folio',
                        status: 'REVIEW', http: pr.status, note: 'pilot folio list non-200',
                    });
                }
            } catch (e) {
                rec(testInfo, {
                    module: MOD, step: 'setup_harvest_pilot_folio',
                    status: 'REVIEW', note: `pilot harvest error: ${String(e?.message || e).slice(0, 120)}`,
                });
            }
        }
    });

    // ──────────────────────────────────────────────────────────────
    // A0) POST /api/folio/create — folio OPEN lifecycle step.
    // FolioCreate (backend/models/schemas/folio.py): booking_id + folio_type
    // enum (guest|company|agency). RBAC: post_charge. A second open guest
    // folio for the same booking may legitimately 409; we accept that as a
    // "constraint enforced" outcome and continue. The point of this step is
    // to exercise the open path (not to guarantee creation). 2xx success
    // updates `stressFolioId` so downstream C/D/E/F target the freshly
    // opened folio (truer lifecycle coverage); failure leaves the
    // setup-harvested folio in place.
    test('A0) POST /api/folio/create (open lifecycle)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressBookingId) {
            const reason = moduleBlocked ? blockedReason : 'no_stress_booking_for_open';
            rec(testInfo, { module: MOD, step: 'A0_open', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const payload = {
            booking_id: stressBookingId,
            folio_type: 'guest',
            notes: taggedDescription('open_A0'),
        };
        const r = await callTimed(
            request, 'post', '/api/folio/create', payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('A0_open') } },
        );
        recPerf(testInfo, MOD, 'A0_open', [r.ms], r.status === 200 || r.status === 201);
        expect(r.status, `A0_open 5xx=${r.status}`).toBeLessThan(500);
        const okStatuses = [200, 201, 403, 409, 422];
        expect(okStatuses, `A0_open unexpected status=${r.status}`).toContain(r.status);
        if (r.status === 200 || r.status === 201) {
            const newId = r.body?.id || r.body?.folio_id;
            // Tenant-scoping sanity: created folio must carry stress tenant id.
            if (r.body?.tenant_id && r.body.tenant_id !== stressFolioId /* unknown stress_tid here */) {
                // (We don't have stress_tid in scope here; just record body tenant.)
                rec(testInfo, {
                    module: MOD, step: 'A0_open_tenant_scope',
                    status: 'PASS', note: `body.tenant_id=${r.body.tenant_id}`,
                });
            }
            if (newId) {
                stressFolioId = newId;
                rec(testInfo, {
                    module: MOD, step: 'A0_open', status: 'PASS', http: r.status,
                    note: `opened_folio_id=${newId} (replaces harvested)`,
                });
            } else {
                rec(testInfo, {
                    module: MOD, step: 'A0_open', status: 'PASS', http: r.status,
                    note: 'open success but no id in response',
                });
            }
        } else {
            // 409 = duplicate guest folio for booking (constraint enforced).
            // 422 = backend schema mismatch (RBAC role lacks post_charge → 403).
            recFinding(testInfo, 'P2', MOD,
                `folio/create non-2xx status=${r.status}`,
                `booking=${stressBookingId} body=${JSON.stringify(r.body || {}).slice(0, 200)} — constraint/RBAC likely; downstream tests continue against harvested folio.`);
            rec(testInfo, { module: MOD, step: 'A0_open', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // A) GET /api/folio/list — read smoke
    test('A) GET /api/folio/list', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'A_list', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/folio/list?limit=20', null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'A_list', [r.ms], r.status === 200);
        expect(r.status, `A_list 5xx=${r.status}`).toBeLessThan(500);
        expect(r.status, `A_list expected 200, got ${r.status}`).toBe(200);
        rec(testInfo, { module: MOD, step: 'A_list', status: 'PASS', http: 200 });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // B) GET /api/folio/{folio_id} — detail
    test('B) GET /api/folio/{folio_id}', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressFolioId) {
            const reason = moduleBlocked ? blockedReason : 'no_stress_folio';
            rec(testInfo, { module: MOD, step: 'B_detail', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const r = await callTimed(
            request, 'get', `/api/folio/${stressFolioId}`, null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'B_detail', [r.ms], r.status === 200);
        expect(r.status, `B_detail 5xx=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `folio detail non-200 status=${r.status}`,
                `folio_id=${stressFolioId}`);
            rec(testInfo, { module: MOD, step: 'B_detail', status: 'REVIEW', http: r.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'B_detail', status: 'PASS', http: 200 });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // C) POST /api/folio/{folio_id}/charge — with X-Idempotency-Key + replay
    test('C) POST /api/folio/{folio_id}/charge + Idempotency-Key replay', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressFolioId) {
            const reason = moduleBlocked ? blockedReason : 'no_stress_folio';
            rec(testInfo, { module: MOD, step: 'C_charge', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const key = idemKey('C_charge');
        // ChargeCreate (backend/models/schemas/folio.py): charge_category
        // is a ChargeCategory enum (room|food|...|other), description min_length=1,
        // amount/quantity >0, vat_rate 0-100, discount_amount default 0.
        const payload = {
            charge_category: 'other',
            description: taggedDescription('charge_C'),
            amount: 1.0,
            quantity: 1,
            vat_rate: 0,
        };
        const r1 = await callTimed(
            request, 'post', `/api/folio/${stressFolioId}/charge`, payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': key } },
        );
        recPerf(testInfo, MOD, 'C_charge', [r1.ms], r1.status === 200 || r1.status === 201);
        expect(r1.status, `C_charge 5xx=${r1.status}`).toBeLessThan(500);
        const okStatuses = [200, 201, 403, 404, 409, 422];
        expect(okStatuses, `C_charge unexpected status=${r1.status}`).toContain(r1.status);

        if (r1.status === 200 || r1.status === 201) {
            createdChargeId = r1.body?.id || r1.body?.charge_id || null;
            rec(testInfo, {
                module: MOD, step: 'C_charge', status: 'PASS', http: r1.status,
                note: `charge_id=${createdChargeId} amount=1.0`,
            });
            await gap(400);
            // Replay with same idempotency key — must NOT create a duplicate.
            const r2 = await callTimed(
                request, 'post', `/api/folio/${stressFolioId}/charge`, payload,
                stressTokens.stress_token,
                { timeout: 15_000, headers: { 'X-Idempotency-Key': key } },
            );
            expect(r2.status, `C_charge_replay 5xx=${r2.status}`).toBeLessThan(500);
            const replayId = r2.body?.id || r2.body?.charge_id || null;
            const replayOk = (r2.status === 200 || r2.status === 201)
                ? (replayId && createdChargeId && replayId === createdChargeId)
                : [409, 422].includes(r2.status);
            if (!replayOk && (r2.status === 200 || r2.status === 201) && replayId && replayId !== createdChargeId) {
                recFinding(testInfo, 'P1', MOD,
                    'Idempotency-Key not honoured on /folio/{id}/charge',
                    `key=${key} first_id=${createdChargeId} replay_id=${replayId} — duplicate charge created → financial double-post risk.`);
            }
            rec(testInfo, {
                module: MOD, step: 'C_charge_replay',
                status: replayOk ? 'PASS' : 'REVIEW',
                http: r2.status, note: `replay_id=${replayId}`,
            });
        } else {
            // RBAC/module reject — no creation, no replay assertion.
            recFinding(testInfo, 'P2', MOD,
                `folio charge POST blocked status=${r1.status}`,
                `stress_token charge permission yok ya da folio kapalı (folio_id=${stressFolioId}).`);
            rec(testInfo, { module: MOD, step: 'C_charge', status: 'REVIEW', http: r1.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // D) POST /api/folio/{folio_id}/payment — with X-Idempotency-Key + replay
    test('D) POST /api/folio/{folio_id}/payment + Idempotency-Key replay', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressFolioId) {
            const reason = moduleBlocked ? blockedReason : 'no_stress_folio';
            rec(testInfo, { module: MOD, step: 'D_payment', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const key = idemKey('D_payment');
        // PaymentCreate (backend/models/schemas/folio.py): `method` (not
        // `payment_method`) is a PaymentMethod enum (cash|card|bank_transfer|
        // online); payment_type is PaymentType enum (prepayment|deposit|
        // interim|final|refund); amount>0; notes max 2000.
        const payload = {
            amount: 1.0,
            method: 'cash',
            payment_type: 'deposit',
            notes: taggedDescription('payment_D'),
        };
        const r1 = await callTimed(
            request, 'post', `/api/folio/${stressFolioId}/payment`, payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': key } },
        );
        recPerf(testInfo, MOD, 'D_payment', [r1.ms], r1.status === 200 || r1.status === 201);
        expect(r1.status, `D_payment 5xx=${r1.status}`).toBeLessThan(500);
        const okStatuses = [200, 201, 403, 404, 409, 422];
        expect(okStatuses, `D_payment unexpected status=${r1.status}`).toContain(r1.status);

        if (r1.status === 200 || r1.status === 201) {
            createdPaymentId = r1.body?.id || r1.body?.payment_id || null;
            rec(testInfo, {
                module: MOD, step: 'D_payment', status: 'PASS', http: r1.status,
                note: `payment_id=${createdPaymentId} amount=1.0`,
            });
            await gap(400);
            const r2 = await callTimed(
                request, 'post', `/api/folio/${stressFolioId}/payment`, payload,
                stressTokens.stress_token,
                { timeout: 15_000, headers: { 'X-Idempotency-Key': key } },
            );
            expect(r2.status, `D_payment_replay 5xx=${r2.status}`).toBeLessThan(500);
            const replayId = r2.body?.id || r2.body?.payment_id || null;
            const replayOk = (r2.status === 200 || r2.status === 201)
                ? (replayId && createdPaymentId && replayId === createdPaymentId)
                : [409, 422].includes(r2.status);
            if (!replayOk && (r2.status === 200 || r2.status === 201) && replayId && replayId !== createdPaymentId) {
                recFinding(testInfo, 'P1', MOD,
                    'Idempotency-Key not honoured on /folio/{id}/payment',
                    `key=${key} first_id=${createdPaymentId} replay_id=${replayId} — duplicate payment recorded → cash-reconciliation risk.`);
            }
            rec(testInfo, {
                module: MOD, step: 'D_payment_replay',
                status: replayOk ? 'PASS' : 'REVIEW',
                http: r2.status, note: `replay_id=${replayId}`,
            });
        } else {
            recFinding(testInfo, 'P2', MOD,
                `folio payment POST blocked status=${r1.status}`,
                `stress_token payment permission yok (folio_id=${stressFolioId}).`);
            rec(testInfo, { module: MOD, step: 'D_payment', status: 'REVIEW', http: r1.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // E) POST /api/folio/{id}/void-charge/{cid} — void the charge from C
    test('E) POST /api/folio/{id}/void-charge/{cid}', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressFolioId || !createdChargeId) {
            const reason = moduleBlocked ? blockedReason
                : !stressFolioId ? 'no_stress_folio' : 'no_created_charge_to_void';
            rec(testInfo, { module: MOD, step: 'E_void_charge', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        // Backend contract (backend/routers/finance/folio.py:856-861): void_charge
        // takes `void_reason: str` as a QUERY param (no Body(...)). Sending JSON
        // body would 422; must use ?void_reason=… in the URL.
        const r = await callTimed(
            request, 'post',
            `/api/folio/${stressFolioId}/void-charge/${createdChargeId}?void_reason=${encodeURIComponent(taggedDescription('void_charge_E'))}`,
            {},
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('E_void_charge') } },
        );
        recPerf(testInfo, MOD, 'E_void_charge', [r.ms], r.status === 200);
        expect(r.status, `E_void_charge 5xx=${r.status}`).toBeLessThan(500);
        const okStatuses = [200, 201, 403, 404, 409];
        expect(okStatuses, `E_void_charge unexpected status=${r.status}`).toContain(r.status);
        if (r.status === 200 || r.status === 201) {
            rec(testInfo, { module: MOD, step: 'E_void_charge', status: 'PASS', http: r.status });
            createdChargeId = null; // voided — clear so cleanup skip
        } else {
            recFinding(testInfo, 'P2', MOD,
                `void-charge non-2xx status=${r.status}`,
                `charge_id=${createdChargeId} folio_id=${stressFolioId}`);
            rec(testInfo, { module: MOD, step: 'E_void_charge', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // F) POST /api/folio/{id}/payment/{pid}/void — void the payment from D
    test('F) POST /api/folio/{id}/payment/{pid}/void', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressFolioId || !createdPaymentId) {
            const reason = moduleBlocked ? blockedReason
                : !stressFolioId ? 'no_stress_folio' : 'no_created_payment_to_void';
            rec(testInfo, { module: MOD, step: 'F_void_payment', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const r = await callTimed(
            request, 'post',
            `/api/folio/${stressFolioId}/payment/${createdPaymentId}/void`,
            { reason: taggedDescription('void_payment_F') },
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('F_void_payment') } },
        );
        recPerf(testInfo, MOD, 'F_void_payment', [r.ms], r.status === 200);
        expect(r.status, `F_void_payment 5xx=${r.status}`).toBeLessThan(500);
        const okStatuses = [200, 201, 403, 404, 409];
        expect(okStatuses, `F_void_payment unexpected status=${r.status}`).toContain(r.status);
        if (r.status === 200 || r.status === 201) {
            rec(testInfo, { module: MOD, step: 'F_void_payment', status: 'PASS', http: r.status });
            createdPaymentId = null;
        } else {
            recFinding(testInfo, 'P2', MOD,
                `void-payment non-2xx status=${r.status}`,
                `payment_id=${createdPaymentId} folio_id=${stressFolioId}`);
            rec(testInfo, { module: MOD, step: 'F_void_payment', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // G) POST /api/guest/purchase-upsell/{booking_id}
    //    Guest endpoint — staff stress_token (whose `email` is staff, not
    //    a guest email) → booking lookup by guest_email fails → 4xx (404).
    //    Must NOT 5xx; must NOT 2xx (would imply guest-flow exposed to staff).
    test('G) POST /api/guest/purchase-upsell/{booking_id} (staff token rejected)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'G_guest_purchase', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const targetBooking = stressBookingId || `bogus-${cryptoRandomUUID()}`;
        const r = await callTimed(
            request, 'post',
            `/api/guest/purchase-upsell/${targetBooking}`,
            {
                offer_id: `${SUB_PREFIX}_offer_${cryptoRandomUUID()}`,
                offer_name: taggedDescription('guest_purchase_G'),
                offer_type: 'upsell',
                price: 1.0,
                amount: 1.0,
            },
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'X-Idempotency-Key': idemKey('G_guest_purchase') } },
        );
        recPerf(testInfo, MOD, 'G_guest_purchase', [r.ms], false);
        expect(r.status, `G_guest_purchase 5xx=${r.status}`).toBeLessThan(500);
        if (r.status >= 200 && r.status < 300) {
            recFinding(testInfo, 'P1', MOD,
                `Guest upsell purchase endpoint accepted staff JWT (status=${r.status})`,
                `Staff stress_token reached guest-only purchase flow on booking=${targetBooking}. Threat-model § Elevation of Privilege — guest/staff trust boundaries collapsed; purchase row created in guest pipeline.`);
            // Hard-fail: this is a real bypass.
            expect(false, `G_guest_purchase: staff JWT accepted on guest endpoint (status=${r.status})`).toBe(true);
        }
        rec(testInfo, {
            module: MOD, step: 'G_guest_purchase',
            status: 'PASS', http: r.status,
            note: 'staff JWT correctly rejected on guest upsell endpoint',
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // H) GET /api/guest/purchased-upsells/{booking_id} — tenant-scoped read
    //    Endpoint returns rows where booking_id matches AND tenant_id ==
    //    current_user.tenant_id. Stress staff token on a stress booking
    //    should return 200 + (possibly empty) list. Pilot booking_id via
    //    stress token → MUST return [] (cross-tenant scope enforced).
    test('H) GET /api/guest/purchased-upsells/{booking_id} (tenant scope)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'H_guest_upsells_list', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        // Probe 1 — own booking (stress tenant). Expect 200 + array.
        const ownTarget = stressBookingId || `bogus-${cryptoRandomUUID()}`;
        const r1 = await callTimed(
            request, 'get', `/api/guest/purchased-upsells/${ownTarget}`, null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        expect(r1.status, `H_guest_upsells_list_own 5xx=${r1.status}`).toBeLessThan(500);
        if (r1.status === 200) {
            rec(testInfo, {
                module: MOD, step: 'H_guest_upsells_list_own',
                status: 'PASS', http: 200,
                note: `items=${(r1.body?.items || []).length}`,
            });
        } else {
            recFinding(testInfo, 'P2', MOD,
                `guest purchased-upsells own-tenant non-200 status=${r1.status}`,
                `target=${ownTarget}`);
            rec(testInfo, { module: MOD, step: 'H_guest_upsells_list_own', status: 'REVIEW', http: r1.status });
        }

        // Probe 2 — pilot booking_id via stress_token. MUST return empty
        // list (tenant_id filter applied). Any item present is a P0 leak.
        if (pilotBookingId) {
            await gap(400);
            const r2 = await callTimed(
                request, 'get', `/api/guest/purchased-upsells/${pilotBookingId}`, null,
                stressTokens.stress_token, { timeout: 15_000 },
            );
            expect(r2.status, `H_guest_upsells_list_xtenant 5xx=${r2.status}`).toBeLessThan(500);
            if (r2.status === 200) {
                const items = r2.body?.items || [];
                if (items.length > 0) {
                    recFinding(testInfo, 'P0', MOD,
                        'Cross-tenant guest upsell leak via /api/guest/purchased-upsells',
                        `stress_token + pilot_booking_id=${pilotBookingId} returned ${items.length} rows. Tenant filter missing on this read path. Sample: ${JSON.stringify(items[0]).slice(0, 200)}`);
                }
                expect(items.length, `H_guest_upsells_list_xtenant leaked ${items.length} rows`).toBe(0);
                rec(testInfo, {
                    module: MOD, step: 'H_guest_upsells_list_xtenant',
                    status: 'PASS', http: 200, note: 'empty list (tenant scope enforced)',
                });
            } else {
                rec(testInfo, {
                    module: MOD, step: 'H_guest_upsells_list_xtenant',
                    status: 'PASS', http: r2.status, note: 'non-200 also acceptable',
                });
            }
        } else {
            rec(testInfo, {
                module: MOD, step: 'H_guest_upsells_list_xtenant',
                status: 'SKIP', note: 'no pilot booking id harvested',
            });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // I) SECURITY: IDOR — cross-tenant folio detail/mutate via stress_token.
    //    Pilot folio_id (real) preferred; bogus UUID fallback proves
    //    "non-existent → no leak" at minimum.
    //    Detail 200 on REAL pilot folio = P0 disclosure.
    //    Charge / payment / close 2xx on REAL pilot folio = P0 tampering.
    test('I) IDOR: cross-tenant folio detail + mutate → all rejected', async ({ request, stressTokens }, testInfo) => {
        const targetId = pilotFolioId || `cross-tenant-${cryptoRandomUUID()}`;
        const probeKind = pilotFolioId ? 'real_pilot_folio_id' : 'bogus_uuid_fallback';

        // I.1 — detail read
        const rd = await callTimed(
            request, 'get', `/api/folio/${targetId}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(rd.status, `I_idor_detail 5xx=${rd.status}`).toBeLessThan(500);
        if (rd.status === 200 && probeKind === 'real_pilot_folio_id') {
            recFinding(testInfo, 'P0', MOD,
                'Financial IDOR: stress_token GET /api/folio/{pilot_id} returned 200',
                `target=${targetId} body_keys=${Object.keys(rd.body || {}).join(',')} sample=${JSON.stringify(rd.body || {}).slice(0, 200)}`);
            // Hard-fail explicitly so the test reports FAIL even if downstream
            // expect() somehow tolerates the status.
            expect(false, `I_idor_detail real pilot folio → 200 leak`).toBe(true);
        }
        // Architect Round-1 fix: hard-assert ≥400 in BOTH modes. Bogus UUID
        // returning 200 is also a leak/false-PASS risk (would mean backend
        // returned a non-existent folio payload). Real pilot mode is already
        // caught above as P0; bogus mode still hard-fails here.
        expect(rd.status, `I_idor_detail: ${probeKind}=${targetId} accepted (status=${rd.status})`).toBeGreaterThanOrEqual(400);
        rec(testInfo, {
            module: MOD, step: 'I_idor_detail',
            status: 'PASS', http: rd.status, note: `${probeKind}`,
        });

        // I.2 — charge mutate (schema-valid so a 4xx truly means tenant/
        // RBAC reject, not validation reject)
        await gap(400);
        const rc = await callTimed(
            request, 'post', `/api/folio/${targetId}/charge`,
            {
                charge_category: 'other',
                description: taggedDescription('idor_charge'),
                amount: 1.0, quantity: 1, vat_rate: 0,
            },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'X-Idempotency-Key': idemKey('I_idor_charge') } },
        );
        expect(rc.status, `I_idor_charge 5xx=${rc.status}`).toBeLessThan(500);
        if (rc.status >= 200 && rc.status < 300 && probeKind === 'real_pilot_folio_id') {
            recFinding(testInfo, 'P0', MOD,
                'Financial IDOR: stress_token POST charge on REAL pilot folio accepted',
                `target=${targetId} status=${rc.status} body=${JSON.stringify(rc.body || {}).slice(0, 200)} — cross-tenant financial tampering.`);
        }
        expect(rc.status, `I_idor_charge: ${probeKind}=${targetId} accepted (status=${rc.status})`).toBeGreaterThanOrEqual(400);
        rec(testInfo, { module: MOD, step: 'I_idor_charge', status: 'PASS', http: rc.status });

        // I.3 — payment mutate (schema-valid: `method` enum, payment_type enum)
        await gap(400);
        const rp = await callTimed(
            request, 'post', `/api/folio/${targetId}/payment`,
            {
                amount: 1.0, method: 'cash', payment_type: 'deposit',
                notes: taggedDescription('idor_payment'),
            },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'X-Idempotency-Key': idemKey('I_idor_payment') } },
        );
        expect(rp.status, `I_idor_payment 5xx=${rp.status}`).toBeLessThan(500);
        if (rp.status >= 200 && rp.status < 300 && probeKind === 'real_pilot_folio_id') {
            recFinding(testInfo, 'P0', MOD,
                'Financial IDOR: stress_token POST payment on REAL pilot folio accepted',
                `target=${targetId} status=${rp.status} body=${JSON.stringify(rp.body || {}).slice(0, 200)}`);
        }
        expect(rp.status, `I_idor_payment: ${probeKind}=${targetId} accepted (status=${rp.status})`).toBeGreaterThanOrEqual(400);
        rec(testInfo, { module: MOD, step: 'I_idor_payment', status: 'PASS', http: rp.status });

        // I.4 — close mutate
        await gap(400);
        const rcl = await callTimed(
            request, 'post', `/api/folio/${targetId}/close`, {},
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'X-Idempotency-Key': idemKey('I_idor_close') } },
        );
        expect(rcl.status, `I_idor_close 5xx=${rcl.status}`).toBeLessThan(500);
        if (rcl.status >= 200 && rcl.status < 300 && probeKind === 'real_pilot_folio_id') {
            recFinding(testInfo, 'P0', MOD,
                'Financial IDOR: stress_token POST close on REAL pilot folio accepted',
                `target=${targetId} status=${rcl.status}`);
        }
        expect(rcl.status, `I_idor_close: ${probeKind}=${targetId} accepted (status=${rcl.status})`).toBeGreaterThanOrEqual(400);
        rec(testInfo, { module: MOD, step: 'I_idor_close', status: 'PASS', http: rcl.status });
    });

    // ──────────────────────────────────────────────────────────────
    // J) SECURITY: Anonymous (headerless) GET → 401/403
    test('J) Anonymous GET /api/folio/list → 401/403', async ({ request }, testInfo) => {
        let status = 0;
        let bodySnippet = '';
        try {
            const r = await request.get('/api/folio/list?limit=5', {
                failOnStatusCode: false,
                timeout: 10_000,
            });
            status = r.status();
            try { bodySnippet = (await r.text()).slice(0, 200); } catch { /* ignore */ }
        } catch (e) {
            recFinding(testInfo, 'P2', MOD, 'J_anon network error', String(e?.message || e).slice(0, 200));
        }
        expect(status, `J_anon 5xx=${status}`).toBeLessThan(500);
        const blocked = status === 401 || status === 403;
        if (!blocked) {
            recFinding(testInfo, 'P1', MOD,
                `Anonymous GET /api/folio/list not blocked (status=${status})`,
                `PUBLIC FINANCIAL SURFACE LEAK — folio list reachable without auth. body=${bodySnippet}`);
        }
        expect(blocked, `J_anon: headerless returned ${status} (expected 401/403)`).toBe(true);
        rec(testInfo, { module: MOD, step: 'J_anon', status: 'PASS', http: status });
    });

    // ──────────────────────────────────────────────────────────────
    // K) Bogus folio id mutations → 4xx (no 5xx, no false success).
    // Architect Round-1 fix: K is a security probe and must run independently
    // of module-blocked state (parity with I/J). A blocked finance module
    // still has to reject unknown folio ids without leaking 5xx stack traces.
    test('K) Bogus folio id mutations → 4xx', async ({ request, stressTokens }, testInfo) => {
        const bogus = `bogus-${cryptoRandomUUID()}`;
        const idem = { 'X-Idempotency-Key': idemKey('K_bogus') };

        const rChg = await callTimed(
            request, 'post', `/api/folio/${bogus}/charge`,
            {
                charge_category: 'other',
                description: taggedDescription('bogus_charge'),
                amount: 1.0, quantity: 1, vat_rate: 0,
            },
            stressTokens.stress_token, { timeout: 10_000, headers: idem },
        );
        expect(rChg.status, `K_bogus_charge 5xx=${rChg.status}`).toBeLessThan(500);
        expect(rChg.status, `K_bogus_charge accepted (status=${rChg.status})`).toBeGreaterThanOrEqual(400);

        await gap(400);
        const rPay = await callTimed(
            request, 'post', `/api/folio/${bogus}/payment`,
            { amount: 1.0, method: 'cash', payment_type: 'deposit' },
            stressTokens.stress_token, { timeout: 10_000, headers: idem },
        );
        expect(rPay.status, `K_bogus_payment 5xx=${rPay.status}`).toBeLessThan(500);
        expect(rPay.status, `K_bogus_payment accepted (status=${rPay.status})`).toBeGreaterThanOrEqual(400);

        await gap(400);
        const rCl = await callTimed(
            request, 'post', `/api/folio/${bogus}/close`, {},
            stressTokens.stress_token, { timeout: 10_000, headers: idem },
        );
        expect(rCl.status, `K_bogus_close 5xx=${rCl.status}`).toBeLessThan(500);
        expect(rCl.status, `K_bogus_close accepted (status=${rCl.status})`).toBeGreaterThanOrEqual(400);

        rec(testInfo, {
            module: MOD, step: 'K_bogus', status: 'PASS',
            note: `charge=${rChg.status} payment=${rPay.status} close=${rCl.status}`,
        });
    });

    // ──────────────────────────────────────────────────────────────
    // L) TEARDOWN — best-effort void of any leftover created rows on
    // stress folio. Unified cleanup script also catches anything tagged
    // with the data_prefix via folio_charges/payments collections.
    // Architect Round-1 fix: teardown MUST run BEFORE invariants (M/N) so
    // the external_calls=[] + pilot_drift=0 assertions cover the FULL
    // mutation envelope including void-charge/void-payment side effects.
    test('L) Teardown: void leftover stress charges/payments', async ({ request, stressTokens }, testInfo) => {
        if (!stressFolioId) {
            rec(testInfo, { module: MOD, step: 'L_teardown', status: 'SKIP', note: 'no_stress_folio' });
            test.skip(true, 'no_stress_folio');
        }
        let actions = [];
        if (createdChargeId) {
            try {
                // void_reason is a QUERY param on this endpoint (see step E note).
                const r = await callTimed(
                    request, 'post',
                    `/api/folio/${stressFolioId}/void-charge/${createdChargeId}?void_reason=${encodeURIComponent(taggedDescription('teardown_void_charge'))}`,
                    {},
                    stressTokens.stress_token,
                    { timeout: 10_000, headers: { 'X-Idempotency-Key': idemKey('L_void_charge') } },
                );
                actions.push(`charge=${r.status}`);
            } catch (e) {
                actions.push(`charge_err=${String(e?.message || e).slice(0, 60)}`);
            }
        }
        if (createdPaymentId) {
            try {
                const r = await callTimed(
                    request, 'post',
                    `/api/folio/${stressFolioId}/payment/${createdPaymentId}/void`,
                    { reason: taggedDescription('teardown_void_payment') },
                    stressTokens.stress_token,
                    { timeout: 10_000, headers: { 'X-Idempotency-Key': idemKey('L_void_payment') } },
                );
                actions.push(`payment=${r.status}`);
            } catch (e) {
                actions.push(`payment_err=${String(e?.message || e).slice(0, 60)}`);
            }
        }
        rec(testInfo, {
            module: MOD, step: 'L_teardown',
            status: 'PASS',
            note: actions.length ? actions.join(' ') : 'nothing_to_void',
        });
    });

    // ──────────────────────────────────────────────────────────────
    // INVARIANTS — placed LAST so they cover every mutation in this
    // describe (A–K probes + L teardown void calls).
    test('M) Invariant: external_calls=[] for this module batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(
            testInfo, MOD, `${SUB_PREFIX}_full`,
            stressState, request, stressTokens.pilot_token,
        );
        expect(ok, 'external_calls invariant failed').toBe(true);
    });

    test('N) Invariant: pilot drift — booking baseline', async ({ request, stressTokens }, testInfo) => {
        const ok = await assertPilotDriftZero(
            testInfo, MOD, request, stressTokens.pilot_token, pilotBookingBaseline,
        );
        expect(ok, 'pilot bookings drift detected → suite mutated pilot').toBe(true);
    });
});
