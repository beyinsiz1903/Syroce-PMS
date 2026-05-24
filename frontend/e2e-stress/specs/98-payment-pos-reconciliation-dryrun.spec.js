// F8Z § 98 — Payment / POS reconciliation dry-run.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   Para hareketi en yüksek risk yüzeyi. Gerçek Iyzico/Stripe/POS provider
//   HTTP çağrısı testte ASLA tetiklenmemeli. Bu spec; folio payment, cashier
//   shift state, POS read-only yüzeyini + tenant-isolation + external-call
//   gate ile doğrular.
//
// Architect fix notes (2026-05-24 NO-GO → revised):
//   - `PaymentCreate` zorunlu alan: `amount` (>0), `method` (PaymentMethod
//     enum: cash|card|bank_transfer|online), `payment_type` (PaymentType
//     enum: prepayment|deposit|interim|final|refund). Eski payload
//     `payment_type` göndermediği için 422 ile düşüyordu → tenant guard
//     ölçülmüyordu. Şimdi schema-valid payload ile cross-tenant IDOR
//     yüzeyi gerçekten test edilir.
//   - `/api/cashier/current-shift` yanıtı `{ shift: {...} }` (nested).
//     Open-shift tespiti artık `body?.shift?.shift_id || body?.shift?.id`.
//   - `/api/cashier/manual-transaction` header alias `X-Idempotency-Key`
//     (test eski `Idempotency-Key` gönderiyordu). Payload `direction:
//     'in'|'out'` + `description` (boş kabul edilmez) + `method` (default
//     cash) + `amount` (>0). Eski `transaction_type` field'ı silindi.
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = [] (gerçek payment provider HTTP yok)
//   - failedTests = 0, P0 = P1 = 0
//   - REAL money mutation tetiklenmez — bogus folio + cross-tenant probe
//     yalnız 4xx yüzeyine girer; idempotency probe sadece stress tenant'ta
//     açık vardiya varsa minimum 1.00 TL ile çalışır.
//   - try/finally ile final invariants her path'te zorunlu.
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, fetchSingle,
} from '../fixtures/stress-helpers.js';
import { randomUUID } from 'node:crypto';

const MOD = 'payment_pos_reconciliation';

// PaymentCreate schema-valid base payload (sadece amount/folio_id IDOR/validation
// için değişir). Real POST surfaces stress tenant'a tetiklenmez — bogus id +
// cross-tenant id kullanılır.
const PAYMENT_BASE = {
    amount: 1.00,
    method: 'cash',
    payment_type: 'deposit',
    reference: 'STRESS_F8Z',
    notes: 'STRESS_F8Z dry-run probe',
};

test.describe.serial('F8Z payment/pos reconciliation dryrun', () => {
    test('cashier + POS read-only surface', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO', note: `count=${pilotBefore?.count}` });

        try {
            const surfaces = [
                { name: 'cashier_current_shift', path: '/api/cashier/current-shift' },
                { name: 'cashier_period_report', path: '/api/cashier/period-report' },
                { name: 'pos_orders_list', path: '/api/pos/orders?limit=5' },
                { name: 'pos_tables_list', path: '/api/pos/tables?limit=5' },
            ];
            for (const s of surfaces) {
                const probe = await withModuleProbe(request, sToken, s.path);
                if (probe.moduleBlocked) {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'SKIP',
                        note: `module_blocked:${probe.reason} http=${probe.status}` });
                    recFinding(testInfo, 'P2', MOD, `Payment ${s.name} surface module-blocked`,
                        `GET ${s.path} http=${probe.status} reason=${probe.reason}.`);
                } else {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'PASS',
                        note: `http=${probe.status}` });
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'payment_readonly_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('folio payment — schema enforcement + cross-tenant IDOR', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            // A. Schema enforcement: payment_type eksik → 422 PASS.
            const bogusFolio = '000000000000000000000000';
            const noType = await callTimed(request, 'post', `/api/folio/${bogusFolio}/payment`,
                { amount: 1.00, method: 'cash' }, sToken);
            const noTypeRejected = noType.status === 422 || noType.status === 400 ||
                noType.status === 403 || noType.status === 404;
            if (!noTypeRejected && noType.status >= 200 && noType.status < 300) {
                recFinding(testInfo, 'P1', MOD, 'Folio payment accepts payload missing payment_type',
                    `POST /api/folio/.../payment without payment_type → http=${noType.status}. PaymentCreate schema enforcement broken.`);
            }
            rec(testInfo, { module: MOD, step: 'folio_schema_enforcement',
                status: noTypeRejected ? 'PASS' : 'REVIEW',
                note: `http=${noType.status}` });

            // B. Schema-valid payload + bogus folio_id → 404 PASS (tenant guard /
            // folio lookup hard-fail).
            const bogusValid = await callTimed(request, 'post', `/api/folio/${bogusFolio}/payment`,
                PAYMENT_BASE, sToken);
            if (bogusValid.status === 403 || bogusValid.status === 404) {
                rec(testInfo, { module: MOD, step: 'folio_bogus_id', status: 'PASS',
                    note: `http=${bogusValid.status} (folio lookup guard)` });
            } else if (bogusValid.status >= 400 && bogusValid.status < 500) {
                // 400 (shift kapalı) veya 401 (RBAC) — yine non-2xx PASS.
                rec(testInfo, { module: MOD, step: 'folio_bogus_id', status: 'PASS',
                    note: `http=${bogusValid.status}` });
            } else if (bogusValid.status === 0) {
                recFinding(testInfo, 'P2', MOD, 'Folio payment endpoint unreachable',
                    `POST /api/folio/${bogusFolio}/payment http=0 — deploy/route gap.`);
            } else {
                recFinding(testInfo, 'P1', MOD, 'Folio payment accepted bogus folio id',
                    `POST /api/folio/${bogusFolio}/payment schema-valid → http=${bogusValid.status}. Backend must 404 on unknown folio.`);
            }

            // C. Negative amount → 422 PASS (PaymentCreate.amount gt=0).
            const negAmt = await callTimed(request, 'post', `/api/folio/${bogusFolio}/payment`,
                { ...PAYMENT_BASE, amount: -100.00 }, sToken);
            const negRejected = negAmt.status >= 400 && negAmt.status < 500;
            if (!negRejected) {
                recFinding(testInfo, 'P1', MOD, 'Folio payment accepts negative amount',
                    `POST /api/folio/.../payment amount=-100 → http=${negAmt.status}. PaymentCreate.amount gt=0 enforcement broken.`);
            }
            rec(testInfo, { module: MOD, step: 'folio_negative_amount',
                status: negRejected ? 'PASS' : 'REVIEW',
                note: `http=${negAmt.status}` });

            // D. Cross-tenant folio payment IDOR — schema-valid + pilot folio_id.
            if (pToken) {
                const pilotFolios = await fetchSingle(request, pToken, '/api/pms/folios?limit=5');
                const items = pilotFolios?.raw?.folios || pilotFolios?.raw?.items || pilotFolios?.list || [];
                const pilotFolioId = items[0]?.id || items[0]?._id || items[0]?.folio_id || null;
                if (pilotFolioId) {
                    const r = await callTimed(request, 'post', `/api/folio/${pilotFolioId}/payment`,
                        { ...PAYMENT_BASE, amount: 0.01 }, sToken);
                    if (r.status >= 200 && r.status < 300) {
                        recFinding(testInfo, 'P0', MOD, 'Cross-tenant folio payment IDOR',
                            `stress_token POST /api/folio/${pilotFolioId}/payment → ${r.status} (PILOT folio mutated with real money!). KESIN P0 breach.`);
                        expect(r.status, 'cross-tenant folio payment must be 403/404').toBeGreaterThanOrEqual(400);
                    } else {
                        rec(testInfo, { module: MOD, step: 'folio_cross_tenant_payment', status: 'PASS',
                            note: `http=${r.status} (tenant guard enforced)` });
                    }
                } else {
                    rec(testInfo, { module: MOD, step: 'folio_cross_tenant_payment', status: 'SKIP',
                        note: 'pilot folio harvest empty' });
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'folio_payment_validation',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('manual-transaction X-Idempotency-Key replay', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            // Open-shift detection — response shape: { shift: {...} } veya { shift: null }.
            const cur = await callTimed(request, 'get', '/api/cashier/current-shift', undefined, sToken);
            const shiftBody = cur.body?.shift ?? null;
            const hasOpenShift = cur.status === 200 && shiftBody && (shiftBody.id || shiftBody.shift_id);
            if (!hasOpenShift) {
                rec(testInfo, { module: MOD, step: 'manual_txn_idempotency', status: 'SKIP',
                    note: `no open cashier shift (http=${cur.status}, shift=${shiftBody ? 'closed' : 'null'}); idempotency probe requires active shift.` });
                recFinding(testInfo, 'P2', MOD, 'Manual transaction idempotency probe skipped',
                    `Cashier current-shift http=${cur.status} body.shift=${JSON.stringify(shiftBody).slice(0, 120)}; cannot exercise X-Idempotency-Key replay without active shift.`);
                return;
            }

            const idemKey = `STRESS_F8Z_${randomUUID()}`;
            const payload = {
                amount: 1.00,
                direction: 'in',
                method: 'cash',
                description: 'STRESS_F8Z dry-run idempotency probe',
                type: 'manual_in',
                currency: 'TRY',
            };
            const r1 = await callTimedWithBackoff(request, 'post', '/api/cashier/manual-transaction',
                payload, sToken, { headers: { 'X-Idempotency-Key': idemKey } });
            const r2 = await callTimedWithBackoff(request, 'post', '/api/cashier/manual-transaction',
                payload, sToken, { headers: { 'X-Idempotency-Key': idemKey } });

            // Backend returns `{ok: true, transaction: txn}` — read nested id.
            const extractTxnId = (body) =>
                body?.transaction?.id || body?.transaction?.transaction_id || body?.transaction?.txn_id ||
                body?.id || body?.transaction_id || body?.txn_id || null;
            const r1Id = extractTxnId(r1.body);
            const r2Id = extractTxnId(r2.body);
            const sameId = r1Id && r2Id && r1Id === r2Id;
            const conflictAccepted = r2.status === 409;
            const idempotent = sameId || conflictAccepted;
            const bothOk = r1.status >= 200 && r1.status < 300 && r2.status >= 200 && r2.status < 300;

            if (bothOk && !idempotent) {
                // Distinct ids OR null ids on 2xx replay — both are non-idempotent
                // signatures; escalate to P1 (don't hide as REVIEW).
                recFinding(testInfo, 'P1', MOD, 'Manual transaction NOT idempotent on X-Idempotency-Key replay',
                    `r1.id=${r1Id} r2.id=${r2Id} — same X-Idempotency-Key did NOT yield identical txn id and no 409 conflict. Money double-post risk. r1.body=${JSON.stringify(r1.body).slice(0, 200)} r2.body=${JSON.stringify(r2.body).slice(0, 200)}`);
            }
            rec(testInfo, { module: MOD, step: 'manual_txn_idempotency',
                status: idempotent ? 'PASS' : (bothOk ? 'FAIL' : (r1.status >= 400 ? 'SKIP' : 'REVIEW')),
                note: `r1.http=${r1.status} r2.http=${r2.status} r1.id=${r1Id} r2.id=${r2Id} sameId=${!!sameId} conflict=${conflictAccepted}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'manual_txn_idempotency_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});
