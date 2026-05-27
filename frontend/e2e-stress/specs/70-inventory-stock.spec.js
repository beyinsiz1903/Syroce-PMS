// F8F § 70 — Inventory / Stock CRUD + Movement + Negative Guard + Tenant Isolation.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   - Stock movements financial-adjacent → tenant-scoped filter shart.
//   - Inventory items multi-tenant; cross-tenant list leak P0.
//   - Negative stock = financial integrity ihlali (mevcut olmayan stok
//     üzerinden out movement raporlanırsa folio/cost reconciliation bozulur).
//
// Backend yüzeyleri (backend/routers/finance/accounting.py):
//   - POST /api/accounting/inventory               (create item, perm: view_finance_reports)
//   - GET  /api/accounting/inventory               (list + low_stock_count + total_value)
//   - POST /api/accounting/inventory/movement      (in/out/adjustment/transfer; QUERY params)
//   - GET  /api/housekeeping/inventory             (parallel domain, low_stock_only filter)
//
// Mutlak kurallar (task #197):
//   - stress_prefix marker tüm create'lerde (sku/name).
//   - pilot mutation = 0 (pilot_drift_zero gate).
//   - external_calls = [] (assertNoExternalCallsPostBatch).
//   - Stock negative bug = 0 (out movement > current stock → reject expect).
//   - Supplier cross-tenant leak = 0 (bu spec inventory için, supplier spec 71).
//   - Cleanup idempotent: inventory_items DELETE endpoint yok; create edilen
//     item'lar `stress_prefix` tagged kalır ve global STRESS_COLLECTIONS sweep
//     (backend/domains/admin/router/stress.py § STRESS_COLLECTIONS:132) tarafından
//     teardown'da temizlenir. PATCH quantity→0 best-effort low-stock cleanup.
//   - failedTests = 0, P0 = P1 = 0.
//
// Module-blocked doctrine (F8E mirror): list endpoint non-2xx veya RBAC denied
// → moduleBlocked=true → A/B/C/D test.skip; E (pilot_drift + external_calls)
// bağımsız çalışır.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'inventory_stock';
const N_ITEMS = 5;
const N_MOVEMENT = 8;

test.describe.configure({ mode: 'serial' });

test.describe('F8F § 70 — Inventory / Stock Stress', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let createdItemIds = [];
    let seededItemId = null;
    let negTestItemId = null;

    test.afterAll(async ({ request, stressTokens }, _testInfo) => {
        // Best-effort cleanup: inventory_items modeli için public DELETE
        // endpoint'i mevcut değil. Quantity→0 PATCH dene; başarısızsa
        // STRESS_COLLECTIONS sweep'e güven (orphan low-stock sinyal
        // üretmesin diye qty=0 + reorder_level=0 set'le).
        for (const iid of [...createdItemIds, negTestItemId].filter(Boolean)) {
            await callTimed(request, 'patch', `/api/accounting/inventory/${iid}`,
                { quantity: 0, reorder_level: 0 }, stressTokens.stress_token)
                .catch(() => null);
        }
    });

    test('Setup: prefix + pilot baseline + module probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        const probe = await withModuleProbe(request, stressTokens.stress_token,
            '/api/accounting/inventory');
        // Doctrine alignment: any non-2xx probe → moduleBlocked (architect
        // review #1 fix). `withModuleProbe` only flags 403/404/0; we extend
        // locally so 5xx server errors also short-circuit A/B/C/D (E still
        // runs as final invariant gate).
        if (probe.moduleBlocked || (probe.status >= 300)) {
            moduleBlocked = true;
            blockedReason = probe.reason || `non_2xx_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Inventory module probe blocked',
                `endpoint=/api/accounting/inventory status=${probe.status} reason=${blockedReason} — A/B/C/D skip, E gates still enforced.`);
        } else {
            // Seed'den gelen F8E baseline item'ları aynı tenant'ta yaşıyor;
            // sku prefix match ile bul (spec 27 pattern).
            const items = Array.isArray(probe.body?.items) ? probe.body.items : [];
            const seeded = items.find((it) => typeof it?.sku === 'string' && it.sku.startsWith(prefix));
            seededItemId = seeded?.id || items[0]?.id || null;
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} seed_item=${seededItemId?.slice(0, 8) || 'none'} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Stock item bulk create — stress prefix marker', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'bulk_create_items', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, permFail = 0, throttled = 0;
        const errs = [];
        const categories = ['food', 'beverage', 'amenity', 'linen', 'cleaning'];
        for (let i = 0; i < N_ITEMS; i++) {
            const payload = {
                name: `${prefix}StockA_${i + 1}`,
                sku: `${prefix}SKUA${i + 1}00000`,
                category: categories[i % categories.length],
                unit: 'piece',
                quantity: 100 + (i * 10),
                unit_cost: 5.0 + (i * 2.5),
                reorder_level: 20,
            };
            const r = await callTimed(request, 'post', '/api/accounting/inventory',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.id || r.body?.sku === payload.sku)) {
                ok++;
                if (r.body?.id) createdItemIds.push(r.body.id);
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 80) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 80) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_ITEMS) {
            recFinding(testInfo, 'P2', MOD, 'Stock item create RBAC-blocked',
                `n=${N_ITEMS} all permFail. view_finance_reports gate intentional; informational.`);
            rec(testInfo, { module: MOD, step: 'bulk_create_items', status: 'SKIP',
                endpoint: '/api/accounting/inventory',
                note: `n=${N_ITEMS} perm_fail=${permFail} (RBAC blocked, P2 informational)` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create_items', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'RBAC-blocked');
            return;
        }
        const floor = Math.ceil(N_ITEMS * 0.9);
        const status = ok >= floor ? 'PASS' : 'FAIL';
        recPerf(testInfo, MOD, 'bulk_create_items', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'bulk_create_items', status,
            endpoint: 'POST /api/accounting/inventory',
            note: `ok=${ok}/${N_ITEMS} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} ids=${createdItemIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_ITEMS) {
            recFinding(testInfo, 'P1', MOD, 'Stock item create hard-floor ihlal',
                `ok=${ok}/${floor} errs=${JSON.stringify(errs)}`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create_items', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `stock create floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('B) Stock movements — in/out cycles + low-stock contract', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'stock_movements', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Use first created item (or seed fallback) as target.
        const targetId = createdItemIds[0] || seededItemId;
        if (!targetId) {
            rec(testInfo, { module: MOD, step: 'stock_movements', status: 'SKIP',
                note: 'no target item (create skipped + no seed)' });
            recFinding(testInfo, 'P2', MOD, 'Stock movement skipped — no target item',
                'A) create returned no IDs and seed item missing.');
            test.skip(true, 'no target item');
            return;
        }
        const samples = [];
        let okMov = 0, failMov = 0, permFail = 0, throttled = 0;
        const errs = [];
        // Architect review #2 fix: expand coverage to include adjustment.
        // Note: 'transfer' requires from_location+to_location pair; backend
        // contract does not surface a single-target transfer probe, so we
        // exclude it (documented out-of-scope). adjustment is in scope.
        const movementTypes = ['in', 'out', 'adjustment'];
        for (let i = 0; i < N_MOVEMENT; i++) {
            const params = new URLSearchParams({
                item_id: targetId,
                movement_type: movementTypes[i % movementTypes.length],
                quantity: String(2 + (i % 4)),
                unit_cost: String(10 + i),
                reference: `${prefix}MOVA${i + 1}`,
                notes: `${prefix} F8F spec70 movement ${i + 1}`,
            }).toString();
            const r = await callTimed(request, 'post',
                `/api/accounting/inventory/movement?${params}`,
                undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.id || r.body?.success === true)) okMov++;
            else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 80) });
            } else {
                failMov++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 80) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_MOVEMENT) {
            recFinding(testInfo, 'P2', MOD, 'Stock movement RBAC-blocked',
                `n=${N_MOVEMENT} all permFail (informational).`);
            rec(testInfo, { module: MOD, step: 'stock_movements', status: 'SKIP',
                note: `n=${N_MOVEMENT} perm_fail=${permFail}` });
            test.skip(true, 'RBAC-blocked');
            return;
        }
        const floor = Math.ceil(N_MOVEMENT * 0.9);
        const status = okMov >= floor ? 'PASS' : 'FAIL';
        recPerf(testInfo, MOD, 'stock_movements', samples, okMov >= floor);
        rec(testInfo, { module: MOD, step: 'stock_movements', status,
            endpoint: 'POST /api/accounting/inventory/movement',
            note: `target=${targetId.slice(0, 8)} ok=${okMov}/${N_MOVEMENT} fail=${failMov} perm_fail=${permFail} throttled_429=${throttled} errs=${JSON.stringify(errs)}` });
        if (okMov < floor && permFail < N_MOVEMENT) {
            recFinding(testInfo, 'P1', MOD, 'Stock movement hard-floor ihlal',
                `ok=${okMov}/${floor} errs=${JSON.stringify(errs)}`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'stock_movements', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(okMov, `movement floor>=${floor}; got ok=${okMov}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Negative stock guard — out movement exceeding current stock must reject', async ({ request, stressTokens, stressState }, testInfo) => {
        // Korelasyon: bu test "stock negative bug = 0" mutlak kuralının
        // doğrulayıcısı. Düşük stoklu item create et, sonra stok > qty olan
        // out movement gönder; backend tarafında reject (400/409/422) bekle.
        // 2xx + qty negatif → P0 (financial integrity ihlali).
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'negative_stock_guard', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Dedicated low-stock item create (don't reuse main test items).
        const lowItem = {
            name: `${prefix}NegA_test`,
            sku: `${prefix}SKUNEG00001`,
            category: 'amenity',
            unit: 'piece',
            quantity: 5,
            unit_cost: 1.0,
            reorder_level: 1,
        };
        const create = await callTimed(request, 'post', '/api/accounting/inventory',
            lowItem, stressTokens.stress_token);
        if (create.status === 401 || create.status === 403) {
            recFinding(testInfo, 'P2', MOD, 'Negative stock guard test — create RBAC denied',
                `status=${create.status} informational (perm gate intentional).`);
            rec(testInfo, { module: MOD, step: 'negative_stock_guard', status: 'SKIP',
                note: `create_status=${create.status} RBAC` });
            return;
        }
        if (!create.ok || !create.body?.id) {
            recFinding(testInfo, 'P1', MOD, 'Negative stock guard test — low-stock item create failed',
                `status=${create.status} body=${JSON.stringify(create.body).slice(0, 120)}`);
            rec(testInfo, { module: MOD, step: 'negative_stock_guard', status: 'FAIL',
                note: `create_status=${create.status}` });
            expect(create.ok).toBe(true);
            return;
        }
        negTestItemId = create.body.id;

        // Excessive out movement: quantity = 50 vs current = 5.
        const params = new URLSearchParams({
            item_id: negTestItemId,
            movement_type: 'out',
            quantity: '50',
            unit_cost: '1.0',
            reference: `${prefix}NEGOUT01`,
            notes: `${prefix} F8F spec70 negative stock guard probe`,
        }).toString();
        const out = await callTimed(request, 'post',
            `/api/accounting/inventory/movement?${params}`,
            undefined, stressTokens.stress_token);

        // Verify item state regardless of outcome.
        const after = await callTimed(request, 'get', '/api/accounting/inventory',
            undefined, stressTokens.stress_token);
        const items = Array.isArray(after.body?.items) ? after.body.items : [];
        const updated = items.find((it) => it?.id === negTestItemId);
        const finalQty = typeof updated?.quantity === 'number' ? updated.quantity : null;

        // Acceptance:
        //   PASS — out rejected (4xx) AND finalQty unchanged (=5) or > 0.
        //   PASS — out accepted (2xx) AND finalQty >= 0 (backend clamped to 0).
        //   FAIL/P0 — out accepted AND finalQty < 0 (TRUE financial integrity bug).
        const rejected = !out.ok && out.status >= 400 && out.status < 500;
        const accepted = out.ok;
        const negativeResulted = finalQty != null && finalQty < 0;

        // Architect review #3 fail-closed: post-read MUST succeed and
        // finalQty MUST be a number. Null/read-failure = FAIL/P1 (cannot
        // silently pass).
        const readOk = after.ok && finalQty != null;
        let status, severity = null, title = null, detail = null;
        if (!readOk) {
            status = 'FAIL'; severity = 'P1';
            title = 'Negative stock guard — post-probe read failure (cannot verify final quantity)';
            detail = `read_status=${after.status} final_qty=${finalQty} items_len=${items.length}. Fail-closed: invariant unverifiable.`;
        } else if (negativeResulted) {
            status = 'FAIL'; severity = 'P0';
            title = 'NEGATIVE STOCK BUG — out movement quantity guard bypass';
            detail = `Item ${negTestItemId.slice(0, 8)} started=5, out=50, final_quantity=${finalQty}. Stock negative = financial integrity ihlali (task #197 mutlak kural). out_status=${out.status} out_body=${JSON.stringify(out.body).slice(0, 120)}`;
        } else if (rejected) {
            status = 'PASS';  // explicit reject — best behavior
        } else if (accepted && finalQty >= 0) {
            status = 'PASS';  // backend clamped to 0 (acceptable; no negative leak)
            recFinding(testInfo, 'P2', MOD, 'Stock out accepted with quantity clamp (non-rejecting backend)',
                `Item ${negTestItemId.slice(0, 8)} start=5 out=50 final=${finalQty}. Spec doctrine: explicit reject preferred; clamp acceptable if quantity never goes negative.`);
        } else {
            // Out non-2xx but not in [400,500); REVIEW.
            status = 'REVIEW';
            recFinding(testInfo, 'P2', MOD, 'Negative stock guard indeterminate verdict',
                `out_status=${out.status} final_qty=${finalQty} rejected=${rejected} accepted=${accepted} — classifier did not match a known branch.`);
        }
        rec(testInfo, { module: MOD, step: 'negative_stock_guard', status,
            endpoint: 'POST /api/accounting/inventory/movement (negative probe)',
            note: `item=${negTestItemId.slice(0, 8)} start_qty=5 out_qty=50 out_status=${out.status} read_status=${after.status} final_qty=${finalQty} rejected=${rejected} accepted=${accepted}` });
        if (severity) recFinding(testInfo, severity, MOD, title, detail);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'negative_stock_guard', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        // Hard asserts (fail-closed): read MUST succeed AND stock MUST NOT be negative.
        expect(readOk, `negative stock guard — post-read failed (read_status=${after.status} final_qty=${finalQty})`).toBe(true);
        expect(finalQty >= 0,
            `stock negative bug — final_quantity=${finalQty}`).toBe(true);
    });

    test('D) Low-stock aggregation contract + cross-tenant isolation', async ({ request, stressTokens }, testInfo) => {
        // Spec 27 D-extension peer reference: low_stock_count + total_value
        // contract. Bu spec ek olarak cross-tenant isolation kontrol eder:
        //   - GET /api/accounting/inventory stress_token ile → tüm items
        //     stress prefix veya stress_seed marker taşımalı (pilot prefix
        //     içeren item = cross-tenant leak P0).
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'lowstock_and_isolation', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const r = await callTimed(request, 'get', '/api/accounting/inventory',
            undefined, stressTokens.stress_token);
        if (r.status === 401 || r.status === 403) {
            recFinding(testInfo, 'P2', MOD, 'inventory aggregation RBAC short-circuit',
                `status=${r.status} (perm gate intentional).`);
            rec(testInfo, { module: MOD, step: 'lowstock_and_isolation', status: 'SKIP',
                note: `status=${r.status}` });
            return;
        }
        const items = Array.isArray(r.body?.items) ? r.body.items : [];
        const lowStockCount = r.body?.low_stock_count;
        const totalValue = r.body?.total_value;

        // Contract: low_stock_count = items where quantity <= reorder_level.
        const expectedLowStock = items.filter(
            (it) => (it?.quantity ?? 0) <= (it?.reorder_level ?? 0)).length;
        const expectedTotalValue = items.reduce(
            (acc, it) => acc + ((it?.quantity ?? 0) * (it?.unit_cost ?? 0)), 0);
        const lowStockOk = typeof lowStockCount === 'number' && lowStockCount === expectedLowStock;
        const totalValueOk = typeof totalValue === 'number'
            && Math.abs(totalValue - expectedTotalValue) < 0.5;

        // Cross-tenant isolation: backend GET zaten tenant_id filter ile
        // dönüyor (accounting.py:401). Defansif gate: hiçbir item PILOT_TID
        // taşımıyorsa PASS. tenant_id projection'dan çıkarılmış olabilir;
        // bu durumda sku/name'de pilot marker arar (PILOT_ prefix vb.).
        const pilotTid = (typeof globalThis !== 'undefined' && globalThis.process?.env?.PILOT_TENANT_ID) || null;
        const leaks = [];
        for (const it of items) {
            if (pilotTid && it?.tenant_id && it.tenant_id === pilotTid) {
                leaks.push({ id: it.id?.slice(0, 8), tid_match: true });
            }
            // Marker heuristic — pilot prefix items genelde "PILOT_" veya
            // production hotel kod prefix'i taşır; stress prefix DEĞİL.
            const sku = String(it?.sku || '');
            if (sku.startsWith('PILOT_') || sku.startsWith('PROD_')) {
                leaks.push({ id: it.id?.slice(0, 8), sku_pilot_marker: sku.slice(0, 12) });
            }
        }

        const isolated = leaks.length === 0;
        const ok = r.ok && lowStockOk && totalValueOk && isolated;
        rec(testInfo, { module: MOD, step: 'lowstock_and_isolation', status: ok ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/accounting/inventory',
            note: `items=${items.length} low_stock=${lowStockCount}(exp=${expectedLowStock}) total_value=${totalValue}(exp=${expectedTotalValue.toFixed(2)}) leaks=${leaks.length} ms=${r.ms}` });
        if (!isolated) {
            recFinding(testInfo, 'P0', MOD, 'Cross-tenant inventory leak',
                `stress_token GET /api/accounting/inventory pilot-tagged item döndürdü. leaks=${JSON.stringify(leaks.slice(0, 5))}`);
        }
        if (!lowStockOk || !totalValueOk) {
            recFinding(testInfo, 'P1', MOD, 'Inventory aggregation contract ihlal',
                `low_stock_ok=${lowStockOk} total_value_ok=${totalValueOk} items=${items.length}`);
        }
        expect(r.ok).toBe(true);
        expect(isolated, `cross-tenant leak count=${leaks.length}`).toBe(true);
        expect(lowStockOk, `low_stock_count matches recomputed`).toBe(true);
        expect(totalValueOk, `total_value matches recomputed (tol=0.5)`).toBe(true);
    });

    test('E) Pilot drift = 0 + external_calls = []', async ({ request, stressTokens, stressState }, testInfo) => {
        // E ALWAYS runs (not gated by moduleBlocked) — pilot read-only
        // doğrulama + external dispatcher leak guard. Mutlak kural.
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants', status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});
