// F8F v2 § 72 — Warehouse Transfer + Procurement Hardening Stress.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   - Warehouse-to-warehouse transfer = real money/operational movement;
//     contract MUST be explicit (multi-target probe) or NOT exist (422).
//     Silent "transfer" acceptance → P0 (stock magicked between locations).
//   - Partial GRN lifecycle: receive < ordered → `partially_received`;
//     subsequent GRN reaching ordered qty → `received`; overage → 422.
//     Rejected qc_status MUST NOT increment stock (`_grn_apply` guard).
//   - PO cancellation guard: cancelled PO cannot accept further GRN (409).
//     Empty/short `reason` → 422 (POStatusIn `_reason_for_cancel`).
//     Terminal states (closed) cannot transition back to cancelled (409).
//   - Supplier `credit_limit` field NOT in SupplierIn model (Task #9 probe):
//     create with extra field is silently dropped by Pydantic → P2 REVIEW
//     (feature gap, not a security bug; documented for product backlog).
//   - Supplier delete-when-used guard: open PO (sent/partially_received) →
//     409 (procurement.py:211). Cancelled/closed PO → allows delete.
//   - P0 cross-tenant IDOR: pilot bearer must never mutate or read
//     stress-tenant supplier/PO/GRN (write probes → 4xx mandatory).
//
// Backend yüzeyleri:
//   - POST /api/accounting/inventory/movement?movement_type=transfer (← 422 expected)
//   - POST /api/procurement/suppliers
//   - DELETE /api/procurement/suppliers/{id}                           (409 in-use)
//   - POST /api/procurement/purchase-orders                            (standalone PO)
//   - POST /api/procurement/purchase-orders/{id}/status                (sent/cancelled/closed)
//   - POST /api/procurement/purchase-orders/{id}/grn                   (partial → full)
//   - GET  /api/procurement/purchase-orders/{id}                       (detail + grns[])
//
// Mutlak kurallar (F8F v2 task #9):
//   - stress_prefix marker tüm create'lerde (supplier name/code, PO notes,
//     GRN notes).
//   - pilot mutation = 0 (assertPilotDriftZero her test'te try/finally).
//   - external_calls = [] (assertNoExternalCallsPostBatch her batch sonu).
//   - inventory_item_id = null PO lines'ta — housekeeping_inventory'ye
//     yan etki üretme (spec 71 doctrine).
//   - cleanup idempotent: PO cancel → supplier delete; 404/409 absorb.
//   - failedTests = 0, P0 = P1 = 0; module-blocked → P2 + skip (no fake PASS).
//
// Module-blocked doctrine:
//   - suppliers GET probe non-2xx (403/404/5xx) → A/B/C/D skip + P2; final
//     invariant gate (E) bağımsız çalışır.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'inventory_transfer_procurement';

test.describe.configure({ mode: 'serial' });

test.describe('F8F v2 § 72 — Warehouse Transfer + Procurement Hardening', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    const createdSupplierIds = [];
    const createdPOIds = [];
    // POs we deliberately leave un-cancelled so D can attempt to delete
    // supplier and verify the 409 guard. Tracked separately so afterAll
    // cancels them last.

    test.afterAll(async ({ request, stressTokens }, _testInfo) => {
        // Idempotent teardown — PO cancel → supplier delete; 404/409 absorb.
        // Cancelled/closed PO unblocks supplier delete (procurement.py:213
        // filter excludes cancelled/closed from in-use check).
        for (const poId of createdPOIds) {
            await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/status`,
                { status: 'cancelled',
                  reason: `${prefix || 'STRESS_F8Fv2_'} teardown cancel` },
                stressTokens.stress_token).catch(() => null);
        }
        for (const sid of createdSupplierIds) {
            await callTimed(request, 'delete',
                `/api/procurement/suppliers/${sid}`,
                undefined, stressTokens.stress_token).catch(() => null);
        }
    });

    test('Setup: probe procurement + prefix + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix || `STRESS_F8Fv2_${Date.now()}_`;
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO',
            note: `count=${pilotBefore?.count} prefix=${prefix}` });

        try {
            const probe = await withModuleProbe(request, sToken,
                '/api/procurement/suppliers?active_only=false');
            if (probe.moduleBlocked || probe.status >= 300) {
                moduleBlocked = true;
                blockedReason = probe.reason || `non_2xx_${probe.status}`;
                recFinding(testInfo, 'P2', MOD, 'Procurement module probe blocked',
                    `endpoint=/api/procurement/suppliers status=${probe.status} reason=${blockedReason} — A/B/C/D skip, E final invariants still enforced.`);
            }
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `prefix=${prefix} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
            expect(typeof probe.status).toBe('number');
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_batch',
                stressState, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('A) Warehouse transfer endpoint — happy path + insufficient-source-stock 409', async ({ request, stressTokens, stressState }, testInfo) => {
        // Task #20 — `POST /api/accounting/inventory/transfer` performs an
        // atomic source→destination stock move. Source decrement is guarded
        // by `quantity >= requested` (409 on insufficient stock); destination
        // increment is compensated on failure. Two stock_movements rows are
        // written sharing the same `transfer_id` for reconciliation.
        // Legacy probe also retained: movement_type=transfer on the OLD
        // /movement endpoint MUST still 4xx — it has no destination contract.
        if (moduleBlocked) { test.skip(true, 'procurement module blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        const createdItemIds = [];
        try {
            // A0) Seed two inventory items representing two warehouses (the
            // InventoryItem.location field is the warehouse label).
            const srcCreate = await callTimed(request, 'post',
                '/api/accounting/inventory', {
                    name: `${prefix}TransferItemSrc`,
                    category: 'general',
                    unit: 'adet',
                    quantity: 20,
                    unit_cost: 5.0,
                    reorder_level: 0,
                    location: `${prefix}MainStore`,
                    notes: `${prefix} spec72 A source warehouse`,
                }, sToken);
            if (srcCreate.status === 401 || srcCreate.status === 403) {
                recFinding(testInfo, 'P2', MOD, 'Inventory create RBAC-blocked',
                    `status=${srcCreate.status} — A transfer chain skipped.`);
                test.skip(true, 'inventory create RBAC');
                return;
            }
            expect(srcCreate.ok, `src inventory http=${srcCreate.status} body=${JSON.stringify(srcCreate.body).slice(0, 160)}`).toBe(true);
            const srcId = srcCreate.body?.id;
            createdItemIds.push(srcId);

            const dstCreate = await callTimed(request, 'post',
                '/api/accounting/inventory', {
                    name: `${prefix}TransferItemDst`,
                    category: 'general',
                    unit: 'adet',
                    quantity: 3,
                    unit_cost: 5.0,
                    reorder_level: 0,
                    location: `${prefix}FloorBar`,
                    notes: `${prefix} spec72 A destination warehouse`,
                }, sToken);
            expect(dstCreate.ok, `dst inventory http=${dstCreate.status}`).toBe(true);
            const dstId = dstCreate.body?.id;
            createdItemIds.push(dstId);

            // A1) Happy path — transfer 8 units. Expected source=12, dst=11.
            const ok = await callTimed(request, 'post',
                '/api/accounting/inventory/transfer', {
                    source_item_id: srcId,
                    destination_item_id: dstId,
                    quantity: 8,
                    unit_cost: 5.0,
                    reference: `${prefix}TRANSFER_A1`,
                    notes: `${prefix} happy path 8 units`,
                }, sToken);
            expect(ok.ok, `transfer happy http=${ok.status} body=${JSON.stringify(ok.body).slice(0, 240)}`).toBe(true);
            expect(typeof ok.body?.transfer_id, 'transfer_id must be returned').toBe('string');
            expect(Array.isArray(ok.body?.legs)).toBe(true);
            expect(ok.body?.legs?.length).toBe(2);
            const transferId = ok.body.transfer_id;
            const legs = ok.body.legs;
            const outLeg = legs.find(l => l.movement_type === 'transfer_out');
            const inLeg = legs.find(l => l.movement_type === 'transfer_in');
            expect(outLeg, 'transfer_out leg must exist').toBeTruthy();
            expect(inLeg, 'transfer_in leg must exist').toBeTruthy();
            expect(outLeg.transfer_id, 'out leg transfer_id must match').toBe(transferId);
            expect(inLeg.transfer_id, 'in leg transfer_id must match').toBe(transferId);
            expect(outLeg.counterpart_item_id).toBe(dstId);
            expect(inLeg.counterpart_item_id).toBe(srcId);

            // Verify balances via inventory read.
            const inv = await callTimed(request, 'get', '/api/accounting/inventory', undefined, sToken);
            expect(inv.ok).toBe(true);
            const items = inv.body?.items || [];
            const srcAfter = items.find(i => i.id === srcId);
            const dstAfter = items.find(i => i.id === dstId);
            expect(srcAfter?.quantity, `src qty after transfer should be 12, got ${srcAfter?.quantity}`).toBe(12);
            expect(dstAfter?.quantity, `dst qty after transfer should be 11, got ${dstAfter?.quantity}`).toBe(11);

            // A2) Insufficient source stock — request 9999 → 409, balances unchanged.
            const short = await callTimed(request, 'post',
                '/api/accounting/inventory/transfer', {
                    source_item_id: srcId,
                    destination_item_id: dstId,
                    quantity: 9999,
                    unit_cost: 5.0,
                    reference: `${prefix}TRANSFER_A2_SHORT`,
                    notes: `${prefix} insufficient stock probe`,
                }, sToken);
            expect(short.status, `insufficient-stock must 409 http=${short.status}`).toBe(409);
            if (short.status >= 200 && short.status < 300) {
                recFinding(testInfo, 'P0', MOD, 'Warehouse transfer overdraws source',
                    `http=${short.status} — backend allowed transfer beyond available source qty; financial integrity broken.`);
            }
            // Balances must not have shifted.
            const inv2 = await callTimed(request, 'get', '/api/accounting/inventory', undefined, sToken);
            const items2 = inv2.body?.items || [];
            const srcAfter2 = items2.find(i => i.id === srcId);
            const dstAfter2 = items2.find(i => i.id === dstId);
            expect(srcAfter2?.quantity, 'src qty must be unchanged after rejected transfer').toBe(12);
            expect(dstAfter2?.quantity, 'dst qty must be unchanged after rejected transfer').toBe(11);

            // A3) Same-source/destination → 422 (no-op rejection).
            const same = await callTimed(request, 'post',
                '/api/accounting/inventory/transfer', {
                    source_item_id: srcId,
                    destination_item_id: srcId,
                    quantity: 1,
                    unit_cost: 5.0,
                }, sToken);
            expect(same.status, `same src/dst must 422 http=${same.status}`).toBeGreaterThanOrEqual(400);
            expect(same.status).toBeLessThan(500);

            // A4) Legacy fail-closed — movement_type=transfer on old endpoint
            // still 4xx (no destination contract there).
            const legacyPath = `/api/accounting/inventory/movement?item_id=${srcId}&movement_type=transfer&quantity=1&unit_cost=1`;
            const legacy = await callTimed(request, 'post', legacyPath, {}, sToken);
            expect(legacy.status, `legacy /movement transfer must still 4xx http=${legacy.status}`).toBeGreaterThanOrEqual(400);
            if (legacy.status >= 200 && legacy.status < 300) {
                recFinding(testInfo, 'P0', MOD, 'Legacy movement endpoint silently accepts transfer',
                    `POST /api/accounting/inventory/movement?movement_type=transfer http=${legacy.status} — legacy endpoint must keep {in,out,adjustment} whitelist; multi-target moves only via /inventory/transfer.`);
            }

            // A5) Cross-tenant IDOR — pilot bearer must NOT transfer stress
            // tenant stock.
            if (pToken) {
                const x = await callTimed(request, 'post',
                    '/api/accounting/inventory/transfer', {
                        source_item_id: srcId,
                        destination_item_id: dstId,
                        quantity: 1,
                        unit_cost: 5.0,
                        notes: `${prefix} pilot hijack`,
                    }, pToken);
                expect(x.status, `pilot cross-tenant transfer must 4xx http=${x.status}`).toBeGreaterThanOrEqual(400);
                if (x.status >= 200 && x.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant inventory transfer',
                        `pilot bearer moved stress tenant stock http=${x.status}.`);
                }
            }

            rec(testInfo, { module: MOD, step: 'warehouse_transfer_endpoint',
                status: 'PASS',
                note: `happy=${ok.status} transfer_id=${transferId?.slice(0, 8)} src_after=${srcAfter?.quantity} dst_after=${dstAfter?.quantity} short=${short.status} same=${same.status} legacy=${legacy.status}` });
        } finally {
            // Idempotent cleanup — adjust both items back to 0; ignore errors.
            for (const id of createdItemIds) {
                await callTimed(request, 'post',
                    `/api/accounting/inventory/movement?item_id=${id}&movement_type=adjustment&quantity=0&unit_cost=0`,
                    {}, stressTokens.stress_token).catch(() => null);
            }
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'transfer_probe_batch',
                stressState, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('B) Partial GRN lifecycle: sent → partially_received → received + rejected-no-stock + duplicate grn_no', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'procurement module blocked'); return; }
        test.setTimeout(180_000);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // B0) Seed supplier.
            const sup = await callTimed(request, 'post', '/api/procurement/suppliers', {
                name: `${prefix}SupF8Fv2_B`,
                code: `${prefix}SUPB`,
                tax_no: `${prefix}TAXB1`,
                contact_name: `${prefix}ContactB`,
                payment_terms_days: 30,
                categories: ['general'],
                notes: `${prefix} F8Fv2 spec72 B supplier`,
                active: true,
            }, sToken);
            if (sup.status === 401 || sup.status === 403) {
                recFinding(testInfo, 'P2', MOD, 'Supplier create RBAC-blocked',
                    `status=${sup.status} (manage_sales + require_procurement). B chain skipped.`);
                rec(testInfo, { module: MOD, step: 'partial_grn_lifecycle',
                    status: 'SKIP', note: `supplier_perm_fail` });
                test.skip(true, 'RBAC');
                return;
            }
            expect(sup.ok, `supplier create http=${sup.status} body=${JSON.stringify(sup.body).slice(0, 160)}`).toBe(true);
            const supplierId = sup.body?.id;
            createdSupplierIds.push(supplierId);

            // B1) Create PO (standalone) — inventory_item_id=null to skip
            // housekeeping_inventory side-effect (spec 71 doctrine).
            const po = await callTimed(request, 'post', '/api/procurement/purchase-orders', {
                supplier_id: supplierId,
                source_pr_id: null,
                expected_delivery: null,
                currency: 'TRY',
                tax_rate: 20.0,
                notes: `${prefix} F8Fv2 spec72 B PO`,
                lines: [
                    { item_name: `${prefix}ItemB1`, quantity: 10, unit: 'adet', unit_cost: 10.0 },
                    { item_name: `${prefix}ItemB2`, quantity: 4,  unit: 'adet', unit_cost: 25.0 },
                ],
            }, sToken);
            expect(po.ok, `PO create http=${po.status} body=${JSON.stringify(po.body).slice(0, 160)}`).toBe(true);
            const poId = po.body?.id;
            createdPOIds.push(poId);

            // B2) PO → sent (required for GRN).
            const send = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/status`,
                { status: 'sent' }, sToken);
            expect(send.ok, `PO send http=${send.status}`).toBe(true);

            // B3) Partial GRN — line 0 qty 4 of 10. PO must flip to
            // partially_received.
            const grn1 = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/grn`, {
                    received_at: null,
                    notes: `${prefix} GRN partial #1`,
                    lines: [
                        { po_line_idx: 0, received_qty: 4, qc_status: 'accepted',
                          notes: `${prefix} partial qty B3` },
                    ],
                }, sToken);
            expect(grn1.ok, `partial GRN #1 http=${grn1.status} body=${JSON.stringify(grn1.body).slice(0, 160)}`).toBe(true);
            expect(grn1.body?.po_status, 'PO must be partially_received after partial GRN').toBe('partially_received');

            // B4) Rejected qc_status — MUST NOT increment received_qty
            // (_grn_apply skip on qc_status='rejected').
            const grn2 = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/grn`, {
                    received_at: null,
                    notes: `${prefix} GRN rejected QC`,
                    lines: [
                        { po_line_idx: 1, received_qty: 4, qc_status: 'rejected',
                          notes: `${prefix} reject QC B4` },
                    ],
                }, sToken);
            // rejected GRN insert succeeds (record kept for audit) but PO
            // status stays partially_received (no qty bump on line 1).
            if (grn2.ok) {
                expect(grn2.body?.po_status, 'rejected QC must NOT promote to received').toBe('partially_received');
                // Verify via detail read that line 1 received_qty is still 0.
                const det = await callTimed(request, 'get',
                    `/api/procurement/purchase-orders/${poId}`, undefined, sToken);
                const line1 = det.body?.lines?.[1];
                if (line1 && (line1.received_qty ?? 0) > 0) {
                    recFinding(testInfo, 'P0', MOD, 'Rejected GRN incremented stock',
                        `line[1].received_qty=${line1.received_qty} after rejected qc_status — _grn_apply skip-rejected guard broken (financial integrity).`);
                    expect(line1.received_qty).toBe(0);
                }
            }

            // B5) Final GRN — complete line 0 (remaining 6) + line 1 (4) →
            // PO flips to received.
            const grn3 = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/grn`, {
                    received_at: null,
                    notes: `${prefix} GRN final`,
                    lines: [
                        { po_line_idx: 0, received_qty: 6, qc_status: 'accepted' },
                        { po_line_idx: 1, received_qty: 4, qc_status: 'accepted' },
                    ],
                }, sToken);
            expect(grn3.ok, `final GRN http=${grn3.status} body=${JSON.stringify(grn3.body).slice(0, 160)}`).toBe(true);
            expect(grn3.body?.po_status, 'PO must flip to received after full receipt').toBe('received');

            // B6) Overage attempt — receive more than ordered on a now-full
            // line → 422 (procurement.py:609 "kabul ... sipariş miktarını aşıyor").
            const over = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/grn`, {
                    received_at: null,
                    notes: `${prefix} GRN overage`,
                    lines: [
                        { po_line_idx: 0, received_qty: 1, qc_status: 'accepted' },
                    ],
                }, sToken);
            // Once PO is `received`, further GRN is blocked by status guard
            // (procurement.py:592 "Mal kabul yalnızca gönderilmiş veya kısmi
            // alınmış POlar için") → 409. Either 409 or 422 is a defensive
            // rejection; only 2xx is the breach.
            expect(over.status, `overage/post-complete GRN must reject http=${over.status}`).toBeGreaterThanOrEqual(400);
            if (over.status >= 200 && over.status < 300) {
                recFinding(testInfo, 'P0', MOD, 'GRN overage / post-complete accepted',
                    `PO already received; further GRN http=${over.status} body=${JSON.stringify(over.body).slice(0, 160)} — quantity overage guard broken.`);
            }

            // B7) PO received → closed transition (state machine).
            const close = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/status`,
                { status: 'closed' }, sToken);
            if (!close.ok) {
                recFinding(testInfo, 'P2', MOD, 'PO received→closed not accepted',
                    `http=${close.status} body=${JSON.stringify(close.body).slice(0, 160)} — informational (state machine variance).`);
            }

            rec(testInfo, { module: MOD, step: 'partial_grn_lifecycle',
                status: 'PASS',
                note: `po=${po.body?.po_no} grn1=${grn1.status}/${grn1.body?.po_status} grn2_rejected=${grn2.status} grn3=${grn3.status}/${grn3.body?.po_status} overage=${over.status} close=${close.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'partial_grn_batch',
                stressState, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('C) PO cancellation guard: cancel+GRN blocked, empty reason 422, closed→cancelled 409', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'procurement module blocked'); return; }
        test.setTimeout(180_000);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // C0) Reuse a fresh supplier (avoid C state leaking into B).
            const sup = await callTimed(request, 'post', '/api/procurement/suppliers', {
                name: `${prefix}SupF8Fv2_C`,
                code: `${prefix}SUPC`,
                tax_no: `${prefix}TAXC1`,
                payment_terms_days: 30,
                categories: ['general'],
                notes: `${prefix} F8Fv2 spec72 C supplier`,
                active: true,
            }, sToken);
            if (sup.status === 401 || sup.status === 403) {
                test.skip(true, 'supplier RBAC');
                return;
            }
            expect(sup.ok, `C supplier http=${sup.status}`).toBe(true);
            createdSupplierIds.push(sup.body?.id);

            // C1) Create PO (sent state) for cancel test.
            const po = await callTimed(request, 'post', '/api/procurement/purchase-orders', {
                supplier_id: sup.body?.id,
                source_pr_id: null,
                currency: 'TRY', tax_rate: 20.0,
                notes: `${prefix} F8Fv2 spec72 C PO cancel`,
                lines: [{ item_name: `${prefix}ItemC1`, quantity: 5, unit: 'adet', unit_cost: 10.0 }],
            }, sToken);
            expect(po.ok, `C PO create http=${po.status}`).toBe(true);
            const poId = po.body?.id;
            createdPOIds.push(poId);
            const send = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/status`,
                { status: 'sent' }, sToken);
            expect(send.ok, `C PO send http=${send.status}`).toBe(true);

            // C2) Empty cancel reason → 422 (POStatusIn._reason_for_cancel
            // requires >= 5 chars; pydantic ValueError → 422).
            const empty = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/status`,
                { status: 'cancelled', reason: '' }, sToken);
            expect(empty.status, `empty cancel reason http=${empty.status}`).toBeGreaterThanOrEqual(400);
            expect(empty.status).toBeLessThan(500);
            if (empty.status >= 200 && empty.status < 300) {
                recFinding(testInfo, 'P1', MOD, 'PO cancel accepted without reason',
                    `http=${empty.status} — _reason_for_cancel validator bypass (audit gap).`);
            }

            // C3) Cancel with proper reason → 200; subsequent GRN → 409
            // (procurement.py:592 "Mal kabul yalnızca gönderilmiş veya
            // kısmi alınmış POlar için" — cancelled excluded).
            const cancel = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/status`,
                { status: 'cancelled',
                  reason: `${prefix} F8Fv2 C cancel reason for audit` },
                sToken);
            expect(cancel.ok, `cancel http=${cancel.status}`).toBe(true);

            const grnOnCancelled = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/grn`, {
                    received_at: null,
                    notes: `${prefix} GRN on cancelled PO`,
                    lines: [{ po_line_idx: 0, received_qty: 1, qc_status: 'accepted' }],
                }, sToken);
            expect(grnOnCancelled.status, `GRN on cancelled PO must 4xx http=${grnOnCancelled.status}`).toBeGreaterThanOrEqual(400);
            if (grnOnCancelled.status >= 200 && grnOnCancelled.status < 300) {
                recFinding(testInfo, 'P0', MOD, 'GRN accepted on cancelled PO',
                    `poId=${poId?.slice(0, 8)} http=${grnOnCancelled.status} body=${JSON.stringify(grnOnCancelled.body).slice(0, 160)} — _grn_apply status guard bypass (cancelled PO mutated; financial referential integrity).`);
            }

            // C4) Closed → cancelled invalid transition. Build a second PO,
            // walk it draft→sent→full GRN→received→closed, then attempt to
            // cancel from closed. Allowed map: closed→{} (procurement.py:541)
            // so 409 expected.
            const po2 = await callTimed(request, 'post', '/api/procurement/purchase-orders', {
                supplier_id: sup.body?.id,
                source_pr_id: null,
                currency: 'TRY', tax_rate: 20.0,
                notes: `${prefix} F8Fv2 spec72 C PO closed`,
                lines: [{ item_name: `${prefix}ItemC2`, quantity: 2, unit: 'adet', unit_cost: 5.0 }],
            }, sToken);
            if (po2.ok && po2.body?.id) {
                createdPOIds.push(po2.body.id);
                const s2 = await callTimed(request, 'post',
                    `/api/procurement/purchase-orders/${po2.body.id}/status`,
                    { status: 'sent' }, sToken);
                const g2 = await callTimed(request, 'post',
                    `/api/procurement/purchase-orders/${po2.body.id}/grn`, {
                        received_at: null,
                        notes: `${prefix} full GRN for closed test`,
                        lines: [{ po_line_idx: 0, received_qty: 2, qc_status: 'accepted' }],
                    }, sToken);
                const c2 = await callTimed(request, 'post',
                    `/api/procurement/purchase-orders/${po2.body.id}/status`,
                    { status: 'closed' }, sToken);
                if (s2.ok && g2.ok && c2.ok) {
                    const badCancel = await callTimed(request, 'post',
                        `/api/procurement/purchase-orders/${po2.body.id}/status`,
                        { status: 'cancelled',
                          reason: `${prefix} attempt cancel from closed` },
                        sToken);
                    expect(badCancel.status, `closed→cancelled must 4xx http=${badCancel.status}`).toBeGreaterThanOrEqual(400);
                    if (badCancel.status >= 200 && badCancel.status < 300) {
                        recFinding(testInfo, 'P0', MOD, 'closed→cancelled transition accepted',
                            `http=${badCancel.status} — state machine bypass (closed is terminal; cancel after close re-opens financial obligation).`);
                    }
                } else {
                    rec(testInfo, { module: MOD, step: 'closed_cancel_chain',
                        status: 'REVIEW',
                        note: `chain incomplete s2=${s2.status} g2=${g2.status} c2=${c2.status}` });
                }
            }

            rec(testInfo, { module: MOD, step: 'po_cancel_guard',
                status: 'PASS',
                note: `empty_reason=${empty.status} cancel=${cancel.status} grn_on_cancel=${grnOnCancelled.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'cancel_guard_batch',
                stressState, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('D) Supplier credit_limit probe + delete-when-used guard + cross-tenant IDOR', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'procurement module blocked'); return; }
        test.setTimeout(180_000);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // D1) credit_limit enforcement (Task #19): SupplierIn now
            // accepts credit_limit; create_purchase_order sums open PO
            // grand_totals (draft + sent + partially_received) for the
            // supplier and rejects with 409 when the new PO would push
            // running commitment past the limit. First PO at exactly the
            // limit must succeed (2xx); a follow-up PO that breaches it
            // must 409. Override path (manage_credit_limit) is exercised
            // by sending override_credit_limit=true on the breach attempt.
            const CL_LIMIT = 1000;
            const credSup = await callTimed(request, 'post', '/api/procurement/suppliers', {
                name: `${prefix}SupF8Fv2_D_CL`,
                code: `${prefix}SUPDCL`,
                tax_no: `${prefix}TAXDCL`,
                payment_terms_days: 30,
                categories: ['general'],
                notes: `${prefix} F8Fv2 credit_limit probe`,
                active: true,
                credit_limit: CL_LIMIT,
            }, sToken);
            if (credSup.status === 401 || credSup.status === 403) {
                test.skip(true, 'D supplier RBAC');
                return;
            }
            expect(credSup.ok, `D credit supplier http=${credSup.status}`).toBe(true);
            createdSupplierIds.push(credSup.body?.id);
            const credSupId = credSup.body?.id;
            const hasCreditLimit = credSup.body
                && Object.prototype.hasOwnProperty.call(credSup.body, 'credit_limit');
            if (!hasCreditLimit) {
                recFinding(testInfo, 'P1', MOD, 'Supplier credit_limit not persisted',
                    `Task #19 expected SupplierIn to accept credit_limit; field absent from create response. PO-creation guard cannot enforce without it.`);
            }
            expect(hasCreditLimit, 'SupplierIn must persist credit_limit (Task #19)').toBe(true);
            expect(credSup.body.credit_limit).toBe(CL_LIMIT);

            // D1a) First PO at exactly the limit: subtotal 833.33, tax 20%
            // → grand_total 999.996 ≈ 1000.00 (= CL_LIMIT). 2xx expected.
            // Use tax_rate=0 to keep arithmetic crisp.
            const poUnderLimit = await callTimed(request, 'post', '/api/procurement/purchase-orders', {
                supplier_id: credSupId,
                source_pr_id: null,
                currency: 'TRY', tax_rate: 0,
                notes: `${prefix} F8Fv2 D PO under credit limit`,
                lines: [{ item_name: `${prefix}ItemDCL1`, quantity: 1, unit: 'adet', unit_cost: CL_LIMIT }],
            }, sToken);
            expect(poUnderLimit.ok, `D PO at-limit http=${poUnderLimit.status} body=${JSON.stringify(poUnderLimit.body).slice(0, 160)}`).toBe(true);
            createdPOIds.push(poUnderLimit.body?.id);

            // D1b) Second PO that breaches credit limit must be rejected
            // with 409. 2xx here = P0 (vendor credit governance bypass).
            const poOverLimit = await callTimed(request, 'post', '/api/procurement/purchase-orders', {
                supplier_id: credSupId,
                source_pr_id: null,
                currency: 'TRY', tax_rate: 0,
                notes: `${prefix} F8Fv2 D PO over credit limit`,
                lines: [{ item_name: `${prefix}ItemDCL2`, quantity: 1, unit: 'adet', unit_cost: 1 }],
            }, sToken);
            if (poOverLimit.ok) {
                createdPOIds.push(poOverLimit.body?.id);
                recFinding(testInfo, 'P0', MOD, 'Supplier credit_limit not enforced on PO create',
                    `supplier credit_limit=${CL_LIMIT}; first PO consumed full limit yet second PO grand_total=${poOverLimit.body?.grand_total} accepted http=${poOverLimit.status}. Task #19 enforcement bypass — vendor over-extension risk.`);
            }
            expect(poOverLimit.status, `breach PO must reject http=${poOverLimit.status}`).toBe(409);

            // D1c) Override path: admin/finance user with
            // manage_credit_limit may opt-in via override_credit_limit=true.
            // The stress token is provisioned as admin → override should
            // succeed (200). For non-privileged users the backend would
            // 403 instead; we accept either 2xx or 403 here as proof the
            // override gate is wired, while a 409 means override was
            // ignored (still failed-closed, which is acceptable too).
            const poOverride = await callTimed(request, 'post', '/api/procurement/purchase-orders', {
                supplier_id: credSupId,
                source_pr_id: null,
                currency: 'TRY', tax_rate: 0,
                notes: `${prefix} F8Fv2 D PO credit override`,
                lines: [{ item_name: `${prefix}ItemDCL3`, quantity: 1, unit: 'adet', unit_cost: 1 }],
                override_credit_limit: true,
            }, sToken);
            if (poOverride.ok) {
                createdPOIds.push(poOverride.body?.id);
            }
            expect([200, 201, 403, 409]).toContain(poOverride.status);
            rec(testInfo, { module: MOD, step: 'credit_limit_probe',
                status: 'PASS',
                note: `limit=${CL_LIMIT} at_limit=${poUnderLimit.status} breach=${poOverLimit.status} override=${poOverride.status}` });

            // D2) Delete-when-used guard. Seed supplier + sent PO; DELETE
            // /suppliers/{id} → 409 (procurement.py:215). 200 = P0.
            const sup = await callTimed(request, 'post', '/api/procurement/suppliers', {
                name: `${prefix}SupF8Fv2_D_USE`,
                code: `${prefix}SUPDUSE`,
                tax_no: `${prefix}TAXDUSE`,
                payment_terms_days: 30,
                categories: ['general'],
                notes: `${prefix} F8Fv2 D in-use supplier`,
                active: true,
            }, sToken);
            expect(sup.ok, `D in-use supplier http=${sup.status}`).toBe(true);
            const supId = sup.body?.id;
            createdSupplierIds.push(supId);

            const po = await callTimed(request, 'post', '/api/procurement/purchase-orders', {
                supplier_id: supId,
                source_pr_id: null,
                currency: 'TRY', tax_rate: 20.0,
                notes: `${prefix} F8Fv2 D PO for delete guard`,
                lines: [{ item_name: `${prefix}ItemD1`, quantity: 2, unit: 'adet', unit_cost: 7.5 }],
            }, sToken);
            expect(po.ok, `D PO http=${po.status}`).toBe(true);
            const poId = po.body?.id;
            createdPOIds.push(poId);
            const sent = await callTimed(request, 'post',
                `/api/procurement/purchase-orders/${poId}/status`,
                { status: 'sent' }, sToken);
            expect(sent.ok, `D PO sent http=${sent.status}`).toBe(true);

            const del = await callTimed(request, 'delete',
                `/api/procurement/suppliers/${supId}`, undefined, sToken);
            if (del.ok) {
                recFinding(testInfo, 'P0', MOD, 'Supplier delete guard bypass — açık PO içeren tedarikçi silindi',
                    `DELETE /api/procurement/suppliers/${supId?.slice(0, 8)} http=${del.status} — procurement.py:211 in_use check bypass; financial referential integrity broken.`);
                // remove from teardown set to avoid double-404 noise
                const idx = createdSupplierIds.indexOf(supId);
                if (idx >= 0) createdSupplierIds.splice(idx, 1);
                expect(del.ok, 'supplier delete-when-used must 409').toBe(false);
            } else {
                expect([409, 401, 403]).toContain(del.status);
                rec(testInfo, { module: MOD, step: 'delete_when_used_guard',
                    status: 'PASS',
                    note: `delete http=${del.status} (expected 409 in-use guard fired)` });
            }

            // D3) P0 cross-tenant IDOR — pilot bearer must NOT mutate stress
            // supplier/PO. PUT supplier, DELETE supplier, POST /status,
            // POST /grn → all 4xx mandatory.
            if (pToken) {
                const xPut = await callTimed(request, 'put',
                    `/api/procurement/suppliers/${supId}`, {
                        name: `${prefix}PILOT_HIJACK`,
                        code: `${prefix}SUPDUSE`,
                        payment_terms_days: 30,
                        categories: ['general'],
                        active: false,
                    }, pToken);
                expect(xPut.status, `pilot cross-tenant supplier PUT must 4xx; got ${xPut.status}`).toBeGreaterThanOrEqual(400);
                if (xPut.status >= 200 && xPut.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant supplier PUT',
                        `pilot bearer mutated stress supplier ${supId?.slice(0, 8)} → http=${xPut.status}. Tenant guard breach.`);
                }
                const xDel = await callTimed(request, 'delete',
                    `/api/procurement/suppliers/${supId}`, undefined, pToken);
                expect(xDel.status, `pilot cross-tenant supplier DELETE must 4xx; got ${xDel.status}`).toBeGreaterThanOrEqual(400);
                if (xDel.status >= 200 && xDel.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant supplier DELETE',
                        `pilot bearer deleted stress supplier ${supId?.slice(0, 8)} → http=${xDel.status}.`);
                }
                const xStatus = await callTimed(request, 'post',
                    `/api/procurement/purchase-orders/${poId}/status`,
                    { status: 'cancelled',
                      reason: `${prefix} pilot hijack attempt cancel` },
                    pToken);
                expect(xStatus.status, `pilot cross-tenant PO status must 4xx; got ${xStatus.status}`).toBeGreaterThanOrEqual(400);
                if (xStatus.status >= 200 && xStatus.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant PO status mutation',
                        `pilot bearer cancelled stress PO ${poId?.slice(0, 8)} → http=${xStatus.status}.`);
                }
                const xGrn = await callTimed(request, 'post',
                    `/api/procurement/purchase-orders/${poId}/grn`, {
                        received_at: null,
                        notes: `${prefix} pilot hijack GRN`,
                        lines: [{ po_line_idx: 0, received_qty: 1, qc_status: 'accepted' }],
                    }, pToken);
                expect(xGrn.status, `pilot cross-tenant GRN must 4xx; got ${xGrn.status}`).toBeGreaterThanOrEqual(400);
                if (xGrn.status >= 200 && xGrn.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant GRN insert',
                        `pilot bearer inserted GRN on stress PO ${poId?.slice(0, 8)} → http=${xGrn.status}.`);
                }
                rec(testInfo, { module: MOD, step: 'cross_tenant_idor',
                    status: 'PASS',
                    note: `pilot probes: put=${xPut.status} del=${xDel.status} status=${xStatus.status} grn=${xGrn.status} (all 4xx)` });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'credit_idor_batch',
                stressState, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('E) Final invariants + cleanup idempotency', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Idempotent cleanup pass: PO cancel → supplier delete. Second
            // pass on suppliers should be 404 (idempotency contract).
            let poCancelOk = 0, poCancelOther = 0;
            for (const poId of new Set(createdPOIds.filter(Boolean))) {
                const r = await callTimed(request, 'post',
                    `/api/procurement/purchase-orders/${poId}/status`,
                    { status: 'cancelled',
                      reason: `${prefix || 'STRESS_F8Fv2_'} E cleanup cancel` },
                    sToken);
                if (r.ok || r.status === 409) poCancelOk++;
                else poCancelOther++;
            }
            let supDel = 0, supMissing = 0, supOther = 0;
            for (const sid of new Set(createdSupplierIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete',
                    `/api/procurement/suppliers/${sid}`, undefined, sToken);
                if (r.ok) supDel++;
                else if (r.status === 404) supMissing++;
                else supOther++;
            }
            // Second-pass idempotency check.
            let secondPassNon404 = 0;
            for (const sid of new Set(createdSupplierIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete',
                    `/api/procurement/suppliers/${sid}`, undefined, sToken);
                if (r.status !== 404) secondPassNon404++;
            }
            if (secondPassNon404 > 0) {
                recFinding(testInfo, 'P1', MOD, 'Supplier delete NOT idempotent',
                    `Second-pass returned non-404 for ${secondPassNon404} supplier id(s).`);
            }
            rec(testInfo, { module: MOD, step: 'cleanup',
                status: secondPassNon404 === 0 ? 'PASS' : 'FAIL',
                note: `po_cancel_ok=${poCancelOk} po_other=${poCancelOther} sup_del=${supDel} sup_missing=${supMissing} sup_other=${supOther} second_pass_bad=${secondPassNon404}` });
            expect(secondPassNon404, 'supplier cleanup must be idempotent').toBe(0);
        } finally {
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD,
                'final_batch', stressState, request, pToken);
            const driftOk = await assertPilotDriftZero(testInfo, MOD, request,
                pToken, pilotBefore);
            rec(testInfo, { module: MOD, step: 'final_invariants',
                status: extOk && driftOk ? 'PASS' : 'FAIL',
                note: `external_calls_empty=${extOk} pilot_drift_zero=${driftOk}` });
            expect(extOk).toBe(true);
            expect(driftOk).toBe(true);
        }
    });
});
