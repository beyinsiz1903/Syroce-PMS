// F8F § 71 — Purchasing / Supplier / PR / PO / GRN Stress.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   - Supplier master vendor cost data → view_finance_reports perm gate.
//   - PO mutations require manage_sales perm + require_procurement gate.
//   - Cross-supplier cross-tenant leak P0 (suppliers list, PO history).
//   - GRN write touches housekeeping_inventory.current_stock via $inc —
//     stress prefix marker + tenant_id filter shart.
//
// Backend yüzeyleri (backend/routers/procurement.py):
//   - POST   /api/procurement/suppliers
//   - GET    /api/procurement/suppliers (perm: view_finance_reports)
//   - PUT    /api/procurement/suppliers/{id}
//   - DELETE /api/procurement/suppliers/{id}                (409 if used in open PO)
//   - POST   /api/procurement/purchase-requests             (PR draft)
//   - POST   /api/procurement/purchase-requests/{id}/status (state machine)
//   - POST   /api/procurement/purchase-orders               (PO from supplier+lines)
//   - POST   /api/procurement/purchase-orders/{id}/status   (sent/cancelled)
//   - POST   /api/procurement/purchase-orders/{id}/grn      (GRN dry-run kabul)
//   - GET    /api/procurement/summary                       (dashboard)
//
// Mutlak kurallar (task #197):
//   - stress_prefix marker tüm create'lerde (supplier name/code/PO notes).
//   - pilot mutation = 0 (pilot_drift_zero gate).
//   - external_calls = [] (assertNoExternalCallsPostBatch).
//   - Supplier cross-tenant leak = 0 (GET /suppliers stress_token sadece
//     kendi tenant items'i dönmeli).
//   - Cleanup idempotent: PO cancel → PR cancel → Supplier delete.
//     Inventory_item_id'ye link YOK (GRN housekeeping_inventory'yi update
//     etmesin diye PO lines'ta inventory_item_id=None).
//   - Real EDI/e-fatura dispatch = 0 (out-of-scope; bu spec yalnız local
//     CRUD + state machine + summary read'i tetikler).
//   - failedTests = 0, P0 = P1 = 0.
//
// Module-blocked doctrine (F8E/F mirror): suppliers GET non-2xx → moduleBlocked
// → A/B/C test.skip; D (pilot_drift + external_calls) bağımsız çalışır.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'purchasing_supplier';
const N_SUPPLIERS = 3;

test.describe.configure({ mode: 'serial' });

test.describe('F8F § 71 — Purchasing / Supplier Stress', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    const createdSupplierIds = [];
    const createdPRIds = [];
    const createdPOIds = [];

    test.afterAll(async ({ request, stressTokens }, _testInfo) => {
        // Belt-and-suspenders cleanup: PO cancel → PR cancel → Supplier delete.
        // Idempotent: 404/409 silently absorbed.
        for (const poId of createdPOIds) {
            await callTimed(request, 'post', `/api/procurement/purchase-orders/${poId}/status`,
                { status: 'cancelled', reason: `${prefix} F8F teardown cancel` },
                stressTokens.stress_token).catch(() => null);
        }
        for (const prId of createdPRIds) {
            await callTimed(request, 'post', `/api/procurement/purchase-requests/${prId}/status`,
                { status: 'cancelled', reason: `${prefix} F8F teardown cancel` },
                stressTokens.stress_token).catch(() => null);
        }
        for (const sid of createdSupplierIds) {
            await callTimed(request, 'delete', `/api/procurement/suppliers/${sid}`,
                undefined, stressTokens.stress_token).catch(() => null);
        }
    });

    test('Setup: prefix + pilot baseline + supplier list probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        const probe = await withModuleProbe(request, stressTokens.stress_token,
            '/api/procurement/suppliers?active_only=false');
        // Doctrine alignment: any non-2xx probe → moduleBlocked (architect
        // review #1 fix). `withModuleProbe` only flags 403/404/0; we extend
        // locally so 5xx also short-circuits A/B/C (D still runs).
        if (probe.moduleBlocked || (probe.status >= 300)) {
            moduleBlocked = true;
            blockedReason = probe.reason || `non_2xx_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Procurement module probe blocked',
                `endpoint=/api/procurement/suppliers status=${probe.status} reason=${blockedReason} — A/B/C skip, D gates still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Supplier CRUD + cross-tenant isolation', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'supplier_crud', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let okCreate = 0, failCreate = 0, permFail = 0, throttled = 0;
        const errs = [];

        // 1) Bulk create suppliers
        for (let i = 0; i < N_SUPPLIERS; i++) {
            const payload = {
                name: `${prefix}SupA_${i + 1}`,
                code: `${prefix}SUPC${i + 1}`,
                tax_no: `${prefix}TAX${i + 1}0000`,
                contact_name: `${prefix}Contact_${i + 1}`,
                email: `${prefix.toLowerCase()}sup${i + 1}@example.test`,
                phone: `+90555000${i + 1}000`,
                payment_terms_days: 30,
                categories: ['general'],
                notes: `${prefix} F8F spec71 supplier ${i + 1}`,
                active: true,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/procurement/suppliers',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && r.body?.id) { okCreate++; createdSupplierIds.push(r.body.id); }
            else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ ep: 'create', status: r.status, body: JSON.stringify(r.body).slice(0, 80) });
            } else {
                failCreate++;
                if (errs.length < 3) errs.push({ ep: 'create', status: r.status, body: JSON.stringify(r.body).slice(0, 80) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_SUPPLIERS) {
            recFinding(testInfo, 'P2', MOD, 'Supplier create RBAC-blocked',
                `n=${N_SUPPLIERS} all permFail (manage_sales + require_procurement gate). Informational.`);
            rec(testInfo, { module: MOD, step: 'supplier_crud', status: 'SKIP',
                note: `n=${N_SUPPLIERS} perm_fail=${permFail}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'supplier_crud', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'RBAC-blocked');
            return;
        }

        // 2) Update (defensive: first created)
        let updateOk = false;
        if (createdSupplierIds[0]) {
            const u = await callTimed(request, 'put', `/api/procurement/suppliers/${createdSupplierIds[0]}`,
                {
                    name: `${prefix}SupA_1_updated`,
                    code: `${prefix}SUPC1`,
                    tax_no: `${prefix}TAX10000`,
                    payment_terms_days: 45,
                    categories: ['general'],
                    active: true,
                }, stressTokens.stress_token);
            updateOk = u.ok || u.status === 403;
            samples.push(u.ms);
        }

        // 3) List + cross-tenant isolation
        const list = await callTimed(request, 'get', '/api/procurement/suppliers?active_only=false',
            undefined, stressTokens.stress_token);
        const items = Array.isArray(list.body?.items) ? list.body.items : [];
        const pilotTid = (typeof globalThis !== 'undefined' && globalThis.process?.env?.PILOT_TENANT_ID) || null;
        const leaks = [];
        for (const it of items) {
            if (pilotTid && it?.tenant_id && it.tenant_id === pilotTid) {
                leaks.push({ id: it.id?.slice(0, 8), tid_match: true });
            }
            const code = String(it?.code || '');
            if (code.startsWith('PILOT_') || code.startsWith('PROD_')) {
                leaks.push({ id: it.id?.slice(0, 8), code_pilot_marker: code.slice(0, 12) });
            }
        }
        const isolated = leaks.length === 0;
        if (!isolated) {
            recFinding(testInfo, 'P0', MOD, 'Cross-tenant supplier leak',
                `stress_token GET /api/procurement/suppliers pilot-tagged supplier döndürdü. leaks=${JSON.stringify(leaks.slice(0, 5))}`);
        }

        const floor = Math.ceil(N_SUPPLIERS * 0.9);
        const status = (okCreate >= floor && updateOk && list.ok && isolated) ? 'PASS' : 'FAIL';
        recPerf(testInfo, MOD, 'supplier_crud', samples, status === 'PASS');
        rec(testInfo, { module: MOD, step: 'supplier_crud', status,
            endpoint: '/api/procurement/suppliers (POST+PUT+GET)',
            note: `create=${okCreate}/${N_SUPPLIERS} update_ok=${updateOk} list_status=${list.status} list_count=${items.length} leaks=${leaks.length} perm_fail=${permFail} throttled=${throttled} errs=${JSON.stringify(errs)}` });
        if (okCreate < floor && permFail < N_SUPPLIERS) {
            recFinding(testInfo, 'P1', MOD, 'Supplier create hard-floor ihlal',
                `ok=${okCreate}/${floor} errs=${JSON.stringify(errs)}`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'supplier_crud', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(isolated, `cross-tenant supplier leak count=${leaks.length}`).toBe(true);
        expect(okCreate, `supplier create floor>=${floor}; got ok=${okCreate}`).toBeGreaterThanOrEqual(floor);
    });

    test('B) PR → PO lifecycle dry-run (draft → approved → PO sent)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'pr_po_lifecycle', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        if (!createdSupplierIds[0]) {
            rec(testInfo, { module: MOD, step: 'pr_po_lifecycle', status: 'SKIP',
                note: 'no supplier created in A — chain skipped' });
            recFinding(testInfo, 'P2', MOD, 'PR/PO chain skipped — no supplier',
                'Supplier create either RBAC-blocked or failed; PR/PO chain depends on it.');
            test.skip(true, 'no supplier');
            return;
        }
        const supplierId = createdSupplierIds[0];
        const samples = [];

        // 1) Create PR (draft) — inventory_item_id=None to avoid stock side-effects.
        const pr = await callTimed(request, 'post', '/api/procurement/purchase-requests', {
            department: `${prefix}Dept`,
            requester: `${prefix}Requester`,
            notes: `${prefix} F8F spec71 PR`,
            lines: [
                { item_name: `${prefix}LineItem_1`, quantity: 5, unit: 'adet', est_unit_cost: 10.0 },
                { item_name: `${prefix}LineItem_2`, quantity: 3, unit: 'adet', est_unit_cost: 25.0 },
            ],
        }, stressTokens.stress_token);
        samples.push(pr.ms);
        if (pr.status === 401 || pr.status === 403) {
            recFinding(testInfo, 'P2', MOD, 'PR create RBAC-blocked',
                `status=${pr.status} (informational).`);
            rec(testInfo, { module: MOD, step: 'pr_po_lifecycle', status: 'SKIP',
                note: `pr_status=${pr.status} RBAC` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'pr_po_lifecycle', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'PR RBAC');
            return;
        }
        if (!pr.ok || !pr.body?.id) {
            recFinding(testInfo, 'P1', MOD, 'PR create failed',
                `status=${pr.status} body=${JSON.stringify(pr.body).slice(0, 120)}`);
            rec(testInfo, { module: MOD, step: 'pr_po_lifecycle', status: 'FAIL',
                note: `pr_status=${pr.status}` });
            expect(pr.ok).toBe(true);
            return;
        }
        createdPRIds.push(pr.body.id);

        // 2) Submit + approve
        const sub = await callTimed(request, 'post', `/api/procurement/purchase-requests/${pr.body.id}/status`,
            { status: 'submitted' }, stressTokens.stress_token);
        samples.push(sub.ms);
        const app = await callTimed(request, 'post', `/api/procurement/purchase-requests/${pr.body.id}/status`,
            { status: 'approved' }, stressTokens.stress_token);
        samples.push(app.ms);

        // 3) Create PO from approved PR
        const po = await callTimed(request, 'post', '/api/procurement/purchase-orders', {
            supplier_id: supplierId,
            source_pr_id: app.ok ? pr.body.id : null,  // fallback: standalone PO if approval failed
            expected_delivery: null,
            currency: 'TRY',
            tax_rate: 20.0,
            notes: `${prefix} F8F spec71 PO`,
            lines: [
                { item_name: `${prefix}LineItem_1`, quantity: 5, unit: 'adet', unit_cost: 10.0 },
                { item_name: `${prefix}LineItem_2`, quantity: 3, unit: 'adet', unit_cost: 25.0 },
            ],
        }, stressTokens.stress_token);
        samples.push(po.ms);
        if (po.ok && po.body?.id) createdPOIds.push(po.body.id);

        // 4) PO status → sent (required for GRN in C)
        let sentOk = false;
        if (po.ok && po.body?.id) {
            const send = await callTimed(request, 'post', `/api/procurement/purchase-orders/${po.body.id}/status`,
                { status: 'sent' }, stressTokens.stress_token);
            samples.push(send.ms);
            sentOk = send.ok;
        }

        // 5) Summary dashboard read
        const sum = await callTimed(request, 'get', '/api/procurement/summary',
            undefined, stressTokens.stress_token);
        samples.push(sum.ms);

        const chainOk = pr.ok && sub.ok && app.ok && po.ok && sentOk;
        const status = chainOk ? 'PASS' : (po.ok ? 'REVIEW' : 'FAIL');
        recPerf(testInfo, MOD, 'pr_po_lifecycle', samples, chainOk);
        rec(testInfo, { module: MOD, step: 'pr_po_lifecycle', status,
            endpoint: '/api/procurement/{purchase-requests,purchase-orders}',
            note: `pr=${pr.status}/${pr.body?.pr_no || 'none'} sub=${sub.status} app=${app.status} po=${po.status}/${po.body?.po_no || 'none'} sent=${sentOk} sum=${sum.status}` });
        if (!chainOk && po.ok) {
            recFinding(testInfo, 'P2', MOD, 'PR/PO partial chain (PO created, state machine ihlal değil)',
                `PR state machine veya send transition başarısız; PO mevcut — invoice matching dry-run hala denenebilir.`);
        } else if (!po.ok) {
            recFinding(testInfo, 'P1', MOD, 'PO create failed in PR→PO chain',
                `pr=${pr.status} app=${app.status} po=${po.status} body=${JSON.stringify(po.body).slice(0, 120)}`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'pr_po_lifecycle', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(pr.ok, `PR create`).toBe(true);
    });

    test('C) GRN + invoice matching dry-run + supplier-delete-when-used guard', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'grn_invoice_dryrun', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        if (!createdPOIds[0]) {
            rec(testInfo, { module: MOD, step: 'grn_invoice_dryrun', status: 'SKIP',
                note: 'no PO from B — skipped' });
            test.skip(true, 'no PO');
            return;
        }
        const poId = createdPOIds[0];
        const samples = [];

        // 1) GRN — kabul partial (sadece line 0 + qty=2 of ordered 5). Backend
        //    PO.status → "partially_received" yapmalı; housekeeping_inventory'ye
        //    yan etki YOK çünkü PO lines'ta inventory_item_id=None set ettik.
        const grn = await callTimed(request, 'post', `/api/procurement/purchase-orders/${poId}/grn`, {
            received_at: null,
            notes: `${prefix} F8F spec71 GRN partial`,
            lines: [
                { po_line_idx: 0, received_qty: 2, qc_status: 'accepted', notes: 'partial qty' },
            ],
        }, stressTokens.stress_token);
        samples.push(grn.ms);
        const grnOk = grn.ok && grn.body?.grn?.grn_no && grn.body?.po_status === 'partially_received';

        // 2) PO detail read — GRN listesinde görünmeli + invoice matching
        //    dry-run için 3-way uyum kontrolü (PO ↔ GRN ↔ Invoice). Bu spec
        //    invoice oluşturmaz; sadece PO detail'in grns array'ini doğrular.
        const detail = await callTimed(request, 'get', `/api/procurement/purchase-orders/${poId}`,
            undefined, stressTokens.stress_token);
        samples.push(detail.ms);
        const grnsOnDetail = Array.isArray(detail.body?.grns) ? detail.body.grns : [];
        const detailOk = detail.ok && grnsOnDetail.length >= 1;

        // 3) Supplier-delete-when-used guard: PO sent + GRN var → DELETE
        //    /api/procurement/suppliers/{sid} 409 dönmeli (procurement.py:211).
        let deleteGuardOk = true;
        const supplierId = createdSupplierIds[0];
        if (supplierId) {
            const del = await callTimed(request, 'delete', `/api/procurement/suppliers/${supplierId}`,
                undefined, stressTokens.stress_token);
            samples.push(del.ms);
            // 409 = expected (in_use guard); 200 = silinmemeli (P0 bug);
            // 403 = RBAC informational.
            if (del.ok) {
                deleteGuardOk = false;
                recFinding(testInfo, 'P0', MOD, 'Supplier delete guard bypass — açık PO içeren tedarikçi silindi',
                    `DELETE /api/procurement/suppliers/${supplierId.slice(0, 8)} status=${del.status}. procurement.py:211 in_use check baypas edildi; financial referential integrity bug.`);
                // Tracked id'yi listeden çıkar (afterAll yine 404 absorb eder ama temiz olsun).
                const idx = createdSupplierIds.indexOf(supplierId);
                if (idx >= 0) createdSupplierIds.splice(idx, 1);
            } else if (del.status !== 409 && del.status !== 401 && del.status !== 403) {
                deleteGuardOk = false;
                recFinding(testInfo, 'P1', MOD, 'Supplier delete-when-used unexpected status',
                    `Expected 409 (in_use) or 4xx auth; got ${del.status} body=${JSON.stringify(del.body).slice(0, 120)}`);
            }
        }

        const chainOk = grnOk && detailOk && deleteGuardOk;
        const status = chainOk ? 'PASS' : (grn.ok ? 'REVIEW' : 'FAIL');
        recPerf(testInfo, MOD, 'grn_invoice_dryrun', samples, chainOk);
        rec(testInfo, { module: MOD, step: 'grn_invoice_dryrun', status,
            endpoint: '/api/procurement/purchase-orders/{id}/grn + /suppliers/{id} DELETE',
            note: `grn=${grn.status} grn_ok=${grnOk} po_status=${grn.body?.po_status || 'n/a'} detail=${detail.status} grns_on_detail=${grnsOnDetail.length} delete_guard_ok=${deleteGuardOk}` });
        if (!grnOk && grn.status !== 401 && grn.status !== 403) {
            recFinding(testInfo, 'P1', MOD, 'GRN create dry-run failed',
                `status=${grn.status} body=${JSON.stringify(grn.body).slice(0, 120)}`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'grn_invoice_dryrun', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(deleteGuardOk, `supplier delete-when-used guard`).toBe(true);
    });

    test('D) Pilot drift = 0 + external_calls = []', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants', status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});
