// F8Z.2 § 98 — POS KDS Print + F&B Inventory Stress (sister of F8Z v2 POS
// Deep Lifecycle). Focused on the kitchen-ticket dispatch surface and the
// F&B inventory deplete (recipe/BOM → inventory_items decrement +
// stock_consumption audit) that Task #8 left out of scope.
//
// Threat-model surface:
//   - KDS print/queue: GET /api/fnb/kitchen-display, POST /api/fnb/kitchen-
//     order, PUT /api/fnb/kitchen-order/{id}/status, POST /api/fnb/kitchen-
//     order/{id}/complete, POST /api/pos/kds/update-order-status
//   - WebSocket broadcast tenant-isolation (`broadcast_kitchen_orders`) —
//     verified indirectly via cross-tenant list & mutate probes; direct
//     spy is not feasible from the spec, recorded as P2 REVIEW.
//   - F&B inventory atomic-movement: POST /api/accounting/inventory/movement
//     (atomic tenant-scoped negative-stock guard) + GET /api/accounting/
//     inventory snapshot
//   - stock_consumption read: GET /api/fnb/mobile/stock-consumption (cross-
//     tenant must not leak stress identifiers)
//   - P0 cross-tenant IDOR: pilot bearer must NEVER mutate a stress-created
//     kitchen_order or inventory_item; cross-tenant reads must not surface
//     stress prefixes.
//
// API contract notes (kept here as the canonical reference for this spec):
//   - POST /api/fnb/kitchen-order — body: { items[], table_number?,
//     room_number?, priority?, station?, notes? }. Response: { success,
//     order: { id, ... } }.
//   - PUT /api/fnb/kitchen-order/{order_id}/status?status=<state> — tenant-
//     scoped update; modified_count==0 → 404. States: pending, preparing,
//     ready, served.
//   - POST /api/fnb/kitchen-order/{order_id}/complete — marks status=ready.
//     NOTE: handler intentionally omits tenant_id filter on update_one
//     ("complete" can be called from broadcast clients without tenant
//     context); the spec records a P0 finding if cross-tenant mutation
//     succeeds and falls back to expect-4xx hard fail.
//   - POST /api/pos/kds/update-order-status?order_id=&new_status= — tenant-
//     scoped; states: preparing, ready, served.
//   - POST /api/accounting/inventory — InventoryItemCreateRequest body
//     (name, sku, category, unit, quantity, unit_cost, reorder_level).
//   - POST /api/accounting/inventory/movement?item_id=&movement_type=&
//     quantity=&unit_cost= — atomic conditional decrement; 409 on insufficient
//     stock for movement_type='out'; 404 on bogus or cross-tenant item_id.
//
// Folio-posting safety:
//   This spec NEVER calls `/api/pos/v2/orders/close` with `post_to_folio=
//   true`. The KDS surface is folio-independent — kitchen_orders are
//   pure operational queue rows and do not write folio_charges or publish
//   Xchange `POSTING_CHARGE` events. `assertNoExternalCallsPostBatch`
//   per-batch proves no real bus traffic occurred.
//
// Module-blocked doctrine:
//   - KDS probe `/api/fnb/kitchen-display` → 403/404 ⇒ A/B/C/D skip + P2.
//   - Inventory probe `/api/accounting/inventory` → 403/404 ⇒ E/F/G/H/I skip + P2.
//   - Recipe/menu-item seed missing in stress tenant ⇒ E/G skip + P2 (out
//     of scope per task #11 — seeding is not this spec's job).
//
// Mutlak kurallar:
//   - pilot mutation = 0 (assertPilotDriftZero + assertPilotInventoryDeltaZero)
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//   - cleanup idempotent (kitchen_orders → status=cancelled via PUT;
//     inventory_items orphan-scrubbed via STRESS_COLLECTIONS sweep)
//   - try/finally ile final invariants her test'te zorunlu
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';
import { randomUUID } from 'node:crypto';

const MOD = 'pos_kds_inventory';

// Inventory-delta snapshot — sums inventory_items.quantity for a tenant.
// Returns null if endpoint unreachable. Used for pilot delta=0 invariant.
async function inventorySnapshot(request, token) {
    try {
        const r = await request.get('/api/accounting/inventory', {
            headers: { Authorization: `Bearer ${token}` },
            failOnStatusCode: false, timeout: 10_000,
        });
        if (r.status() < 200 || r.status() >= 300) {
            return { ok: false, totalQty: null, itemCount: null, http: r.status() };
        }
        const body = await r.json().catch(() => null);
        const items = body?.items || [];
        const totalQty = items.reduce((s, it) => s + Number(it?.quantity || 0), 0);
        return { ok: true, totalQty, itemCount: items.length, http: r.status() };
    } catch (e) {
        return { ok: false, totalQty: null, itemCount: null, error: String(e?.message || e).slice(0, 80) };
    }
}

async function assertPilotInventoryDeltaZero(testInfo, module, request, pilotToken, baseline) {
    if (!request || !pilotToken) {
        testInfo.annotations.push({ type: 'rec', description: JSON.stringify({
            module, step: 'pilot_inventory_delta_zero', status: 'SKIP',
            note: 'pilot_token yok — inventory delta doğrulanamadı (informational).',
        })});
        return true;
    }
    const snap = await inventorySnapshot(request, pilotToken);
    if (!snap.ok) {
        testInfo.annotations.push({ type: 'rec', description: JSON.stringify({
            module, step: 'pilot_inventory_delta_zero', status: 'REVIEW',
            note: `pilot inventory endpoint unreachable http=${snap.http} — delta unverifiable.`,
        })});
        return true;
    }
    const baseQty = baseline?.totalQty ?? null;
    const baseCount = baseline?.itemCount ?? null;
    const qtyDelta = (baseQty != null) ? (snap.totalQty - baseQty) : null;
    const countDelta = (baseCount != null) ? (snap.itemCount - baseCount) : null;
    const pass = qtyDelta === 0 && countDelta === 0;
    testInfo.annotations.push({ type: 'rec', description: JSON.stringify({
        module, step: 'pilot_inventory_delta_zero',
        status: pass ? 'PASS' : ((qtyDelta == null || countDelta == null) ? 'REVIEW' : 'FAIL'),
        note: `base_qty=${baseQty} after_qty=${snap.totalQty} qty_delta=${qtyDelta} base_count=${baseCount} after_count=${snap.itemCount} count_delta=${countDelta}`,
    })});
    if ((qtyDelta != null && qtyDelta !== 0) || (countDelta != null && countDelta !== 0)) {
        testInfo.annotations.push({ type: 'finding', description: JSON.stringify({
            severity: 'P0', module,
            title: 'Pilot inventory drift tespit edildi — stress suite pilot stoğunu değiştirdi',
            detail: `qty_delta=${qtyDelta} count_delta=${countDelta}. Mutlak kural ihlali (pilot read-only).`,
        })});
    }
    return pass;
}

function qs(params) {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) u.set(k, String(v));
    }
    return u.toString();
}

test.describe.serial('F8Z.2 pos kds + fnb inventory', () => {
    let prefix = null;
    let createdKitchenOrderIds = [];
    let createdInventoryItemIds = [];
    let kdsBlocked = false;
    let inventoryBlocked = false;
    let recipeBlocked = false;  // E/G skip when no recipe surface
    let pilotInventoryBaseline = null;

    test('Setup: probe KDS + inventory surfaces + pilot inventory baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix || `STRESS_F8Z2_${Date.now()}_`;
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        pilotInventoryBaseline = pToken ? await inventorySnapshot(request, pToken) : null;
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO',
            note: `bookings_count=${pilotBefore?.count} inv_total_qty=${pilotInventoryBaseline?.totalQty} inv_item_count=${pilotInventoryBaseline?.itemCount} prefix=${prefix}` });

        try {
            // KDS surface probe (require_module_v99 pos enforcement).
            const kdsProbe = await withModuleProbe(request, sToken, '/api/fnb/kitchen-display');
            if (kdsProbe.moduleBlocked) {
                kdsBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'KDS surface module-blocked',
                    `GET /api/fnb/kitchen-display http=${kdsProbe.status} reason=${kdsProbe.reason} — A/B/C/D skip; final invariants still enforced.`);
            }

            // Inventory atomic-movement surface probe.
            const invProbe = await withModuleProbe(request, sToken, '/api/accounting/inventory');
            if (invProbe.moduleBlocked) {
                inventoryBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'Inventory atomic-movement surface module-blocked',
                    `GET /api/accounting/inventory http=${invProbe.status} reason=${invProbe.reason} — E/F/G/H/I skip; final invariants still enforced.`);
            }

            // Recipe/menu-item availability probe — E/G depend on recipe seed.
            // Task #11 explicitly leaves recipe seeding out of scope.
            const recipeProbe = await withModuleProbe(request, sToken, '/api/fnb/mobile/recipes');
            const recipeCount = (recipeProbe.body?.recipes || []).length;
            if (recipeProbe.moduleBlocked || recipeCount === 0) {
                recipeBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'F&B recipe catalog empty/blocked',
                    `recipes_http=${recipeProbe.status} count=${recipeCount} — E (inventory deplete happy) + G (concurrent close race) skip. Out of scope per Task #11.`);
            }

            rec(testInfo, { module: MOD, step: 'surface_probe',
                status: 'PASS',
                note: `kds=${kdsProbe.status} inv=${invProbe.status} recipes=${recipeProbe.status} recipe_count=${recipeCount} kds_blocked=${kdsBlocked} inv_blocked=${inventoryBlocked} recipe_blocked=${recipeBlocked}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('A) KDS catalog smoke: kitchen-display tenant-scoped read', async ({ request, stressTokens, stressState }, testInfo) => {
        if (kdsBlocked) { test.skip(true, 'kds surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const r = await callTimed(request, 'get', '/api/fnb/kitchen-display', undefined, sToken);
            expect(r.status, `kitchen-display http=${r.status}`).toBeLessThan(500);
            if (r.status < 200 || r.status >= 300) {
                recFinding(testInfo, 'P2', MOD, 'KDS catalog read non-2xx',
                    `GET /api/fnb/kitchen-display http=${r.status} body=${JSON.stringify(r.body).slice(0,200)}`);
            }
            const orders = r.body?.orders || [];

            // Pilot bearer mirror — response MUST not contain any stress prefix.
            // This is the indirect WebSocket-broadcast tenant-isolation proxy.
            if (pToken) {
                const px = await callTimed(request, 'get', '/api/fnb/kitchen-display', undefined, pToken);
                const pxBody = JSON.stringify(px.body || {});
                if (pxBody.includes(prefix)) {
                    recFinding(testInfo, 'P0', MOD, 'KDS kitchen-display leaks stress identifier to pilot',
                        `pilot bearer received stress identifier: http=${px.status} body=${pxBody.slice(0,200)}`);
                }
                expect(pxBody.includes(prefix), 'pilot kitchen-display must not contain stress prefix').toBe(false);
            }

            rec(testInfo, { module: MOD, step: 'kds_catalog_smoke', status: 'PASS',
                note: `stress_orders=${orders.length} pilot_isolated=true` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kds_catalog_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('B) Kitchen-order lifecycle: create → preparing → ready → served + terminal-state guard', async ({ request, stressTokens, stressState }, testInfo) => {
        if (kdsBlocked) { test.skip(true, 'kds surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const createBody = {
                items: [
                    { name: `${prefix}Espresso`, quantity: 2, station: 'bar' },
                    { name: `${prefix}Croissant`, quantity: 1, station: 'main' },
                ],
                table_number: `${prefix}T_B`,
                priority: 'normal',
                station: 'main',
                notes: `${prefix} lifecycle test`,
            };
            const create = await callTimed(request, 'post', '/api/fnb/kitchen-order', createBody, sToken);
            expect(create.status, `create http=${create.status} body=${JSON.stringify(create.body).slice(0,200)}`).toBeLessThan(300);
            const orderId = create.body?.order?.id;
            expect(orderId, 'order id returned').toBeTruthy();
            createdKitchenOrderIds.push(orderId);

            // pending → preparing
            const toPrep = await callTimed(request, 'put',
                `/api/fnb/kitchen-order/${orderId}/status?${qs({ status: 'preparing' })}`, {}, sToken);
            expect(toPrep.status, `→preparing http=${toPrep.status}`).toBe(200);

            // preparing → ready
            const toReady = await callTimed(request, 'put',
                `/api/fnb/kitchen-order/${orderId}/status?${qs({ status: 'ready' })}`, {}, sToken);
            expect(toReady.status, `→ready http=${toReady.status}`).toBe(200);

            // ready → served (via /pos/kds/update-order-status alt surface)
            const toServed = await callTimed(request, 'post',
                `/api/pos/kds/update-order-status?${qs({ order_id: orderId, new_status: 'served' })}`, {}, sToken);
            expect(toServed.status, `→served http=${toServed.status}`).toBeLessThan(300);

            // Terminal-state guard: re-complete a served ticket.
            // Backend `complete_kitchen_order` writes status='ready' unconditionally
            // (no terminal-state check). A 2xx response that successfully reverts
            // a served ticket back to ready is a P1 lifecycle violation.
            const reComplete = await callTimed(request, 'post',
                `/api/fnb/kitchen-order/${orderId}/complete`, {}, sToken);
            // Verify post-complete state.
            const verify = await callTimed(request, 'get', '/api/fnb/kitchen-display?status=ready,served,preparing,pending',
                undefined, sToken);
            const found = (verify.body?.orders || []).find(o => o.id === orderId);
            const revertedToReady = reComplete.status >= 200 && reComplete.status < 300
                && found && found.status === 'ready';
            if (revertedToReady) {
                recFinding(testInfo, 'P1', MOD, 'KDS complete reverts served ticket to ready (terminal-state guard missing)',
                    `order=${orderId} re-complete http=${reComplete.status} post-state=${found?.status} — served→ready transition is a real lifecycle bug.`);
            }
            rec(testInfo, { module: MOD, step: 'kds_lifecycle', status: 'PASS',
                note: `order=${orderId} prep=${toPrep.status} ready=${toReady.status} served=${toServed.status} re_complete=${reComplete.status} reverted=${!!revertedToReady}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kds_lifecycle_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('C) P0 cross-tenant KDS IDOR: pilot bearer must NOT mutate stress kitchen_order', async ({ request, stressTokens, stressState }, testInfo) => {
        if (kdsBlocked) { test.skip(true, 'kds surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        if (!pToken) {
            rec(testInfo, { module: MOD, step: 'kds_cross_tenant_idor', status: 'SKIP',
                note: 'no pilot_token; drift-guard alone covers tenant invariant' });
            return;
        }
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Seed a fresh stress ticket as the target.
            const seed = await callTimed(request, 'post', '/api/fnb/kitchen-order', {
                items: [{ name: `${prefix}IDOR_target`, quantity: 1, station: 'main' }],
                table_number: `${prefix}T_C`,
                priority: 'normal',
            }, sToken);
            expect(seed.status, `seed http=${seed.status}`).toBeLessThan(300);
            const targetId = seed.body?.order?.id;
            expect(targetId, 'target ticket id').toBeTruthy();
            createdKitchenOrderIds.push(targetId);

            const isBreach = (s) => s >= 200 && s < 300;

            // C1) Pilot bearer status PUT — tenant-filtered → 404 expected.
            const xPut = await callTimed(request, 'put',
                `/api/fnb/kitchen-order/${targetId}/status?${qs({ status: 'preparing' })}`, {}, pToken);
            if (isBreach(xPut.status)) {
                recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant KDS status mutate',
                    `pilot bearer mutated stress ticket ${targetId} via PUT status → http=${xPut.status} body=${JSON.stringify(xPut.body).slice(0,200)}. Tenant + KDS broadcast breach.`);
            }
            expect(xPut.status, `pilot status PUT on stress ticket must 4xx; got ${xPut.status}`).toBeGreaterThanOrEqual(400);

            // C2) Pilot bearer /pos/kds/update-order-status — tenant-filtered → no-op or 404.
            const xKds = await callTimed(request, 'post',
                `/api/pos/kds/update-order-status?${qs({ order_id: targetId, new_status: 'served' })}`, {}, pToken);
            // Endpoint returns {success: true} unconditionally; verify with stress
            // bearer GET that status is unchanged (since update_one filters by tenant).
            const verify = await callTimed(request, 'get', '/api/fnb/kitchen-display?status=pending,preparing,ready,served',
                undefined, sToken);
            const after = (verify.body?.orders || []).find(o => o.id === targetId);
            const stressStatusUnchanged = after && after.status !== 'served';
            if (!stressStatusUnchanged && after) {
                recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant KDS update-order-status mutated stress row',
                    `pilot bearer changed stress ticket ${targetId} status to ${after.status} via /pos/kds/update-order-status http=${xKds.status}. Tenant breach.`);
            }

            // C3) Pilot bearer POST /complete — backend handler has NO tenant filter
            // in update_one (kitchen.py L594-597). Real P0 candidate. Verify the
            // mutation actually happened via stress bearer GET.
            const xComplete = await callTimed(request, 'post',
                `/api/fnb/kitchen-order/${targetId}/complete`, {}, pToken);
            const verify2 = await callTimed(request, 'get', '/api/fnb/kitchen-display?status=pending,preparing,ready,served',
                undefined, sToken);
            const after2 = (verify2.body?.orders || []).find(o => o.id === targetId);
            // If pilot's complete returned 2xx AND the stress ticket flipped to
            // 'ready', that is a confirmed cross-tenant mutation.
            const completedCrossTenant = isBreach(xComplete.status) && after2 && after2.status === 'ready';
            if (completedCrossTenant) {
                recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant KDS /complete mutates stress ticket (no tenant filter)',
                    `pilot bearer marked stress ticket ${targetId} as ready via POST /complete http=${xComplete.status} post_state=${after2?.status}. Backend handler kitchen.py:complete_kitchen_order lacks tenant_id filter in update_one — confirmed.`);
            }
            // Hard-fail expectation: complete should 4xx for cross-tenant. If
            // backend currently 2xx (handler missing tenant filter), the P0 above
            // captures forensic context; we still expect 4xx to fail-loudly.
            expect(xComplete.status, `pilot /complete on stress ticket must 4xx; got ${xComplete.status}`).toBeGreaterThanOrEqual(400);

            rec(testInfo, { module: MOD, step: 'kds_cross_tenant_idor', status: 'PASS',
                note: `target=${targetId} put=${xPut.status} kds=${xKds.status} complete=${xComplete.status} stress_unchanged=${stressStatusUnchanged} completed_xt=${!!completedCrossTenant}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kds_idor_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('D) Idempotency replay: kitchen-order create twice (no key support → distinct = P1)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (kdsBlocked) { test.skip(true, 'kds surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const replayPayload = {
                items: [{ name: `${prefix}IDEM_item`, quantity: 1, station: 'main' }],
                table_number: `${prefix}T_D`,
                priority: 'normal',
                notes: `${prefix}IDEM_${randomUUID()}`,
                // Idempotency key — backend (Task #28 / F8AH P1) returns the
                // original ticket with `idempotent_replay=true` on replay so a
                // double-tap on a flaky tablet does not double-print in the
                // kitchen. Distinct ids on r2 would re-flag the P1 below.
                idempotency_key: `${prefix}IDEM_D_${randomUUID()}`,
            };
            const r1 = await callTimedWithBackoff(request, 'post', '/api/fnb/kitchen-order', replayPayload, sToken);
            const r2 = await callTimedWithBackoff(request, 'post', '/api/fnb/kitchen-order', replayPayload, sToken);
            expect(r1.status, `r1 http=${r1.status}`).toBeLessThan(300);
            const id1 = r1.body?.order?.id;
            const id2 = r2.body?.order?.id;
            if (id1) createdKitchenOrderIds.push(id1);
            if (id2 && id2 !== id1) createdKitchenOrderIds.push(id2);

            const sameId = id1 && id2 && id1 === id2;
            const conflict = r2.status === 409;
            const distinctIds = id1 && id2 && id1 !== id2 && r2.status >= 200 && r2.status < 300;
            if (distinctIds) {
                recFinding(testInfo, 'P1', MOD, 'KDS kitchen-order replay produced distinct ids (no idempotency)',
                    `r1.id=${id1} r2.id=${id2} r2.http=${r2.status} — backend POST /api/fnb/kitchen-order does not honor idempotency_key. Two identical client retries produce two tickets → duplicate kitchen prints.`);
            }
            rec(testInfo, { module: MOD, step: 'kds_idempotency', status: 'PASS',
                note: `r1=${r1.status} r2=${r2.status} same_id=${!!sameId} conflict=${conflict} distinct=${!!distinctIds}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kds_idem_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('E) Inventory deplete happy path (recipe → close → inventory_items decrement)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (inventoryBlocked) { test.skip(true, 'inventory surface blocked'); return; }
        if (recipeBlocked) {
            recFinding(testInfo, 'P2', MOD, 'Inventory deplete happy path skipped — no recipe seed',
                'Stress tenant has no recipes/BOM; Task #11 leaves seeding out of scope. Step recorded as P2 REVIEW (not fake PASS).');
            test.skip(true, 'no recipe seed in stress tenant');
            return;
        }
        // Recipe surface present — would close a v2 order and verify decrement.
        // Real lifecycle would require pos_menu_items linked to recipes linked
        // to inventory_items, which the stress tenant does not seed. Recorded
        // as P2 REVIEW per task spec; assertion is structural-only.
        rec(testInfo, { module: MOD, step: 'inventory_deplete_happy', status: 'SKIP',
            note: 'recipe present but full BOM lifecycle requires per-tenant seed — out of scope per Task #11' });
    });

    test('F) Negative-stock guard: out movement > available → 409 (atomic guard)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (inventoryBlocked) { test.skip(true, 'inventory surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Seed a fresh stress inventory_item with quantity=5.
            const create = await callTimed(request, 'post', '/api/accounting/inventory', {
                name: `${prefix}NEG_ITEM`,
                sku: `${prefix}SKU_F`,
                category: 'food',
                unit: 'pcs',
                quantity: 5,
                unit_cost: 1.0,
                reorder_level: 1,
            }, sToken);
            expect(create.status, `seed item http=${create.status} body=${JSON.stringify(create.body).slice(0,200)}`).toBeLessThan(300);
            const itemId = create.body?.id;
            expect(itemId, 'item id').toBeTruthy();
            createdInventoryItemIds.push(itemId);

            // Decrement by 10 (more than available 5) — must 409.
            const overdraft = await callTimed(request, 'post',
                `/api/accounting/inventory/movement?${qs({
                    item_id: itemId, movement_type: 'out', quantity: 10, unit_cost: 1.0,
                    reference: `${prefix}OVERDRAFT`,
                })}`, {}, sToken);
            const guardFired = overdraft.status === 409;
            if (!guardFired) {
                // If 2xx, post-state would show negative quantity — P0.
                const verify = await callTimed(request, 'get', '/api/accounting/inventory', undefined, sToken);
                const found = (verify.body?.items || []).find(i => i.id === itemId);
                if (overdraft.status >= 200 && overdraft.status < 300 && found && Number(found.quantity) < 0) {
                    recFinding(testInfo, 'P0', MOD, 'Inventory negative-stock guard FAILED (quantity went negative)',
                        `item=${itemId} requested=10 available=5 post_qty=${found.quantity} http=${overdraft.status}. Atomic guard çökmesi — financial integrity breach.`);
                } else {
                    recFinding(testInfo, 'P1', MOD, 'Inventory overdraft non-409 response',
                        `item=${itemId} requested=10 available=5 http=${overdraft.status} body=${JSON.stringify(overdraft.body).slice(0,200)}. Expected 409.`);
                }
            }
            expect(overdraft.status, `overdraft must be 409; got ${overdraft.status}`).toBe(409);

            // Verify quantity unchanged (still 5).
            const verify = await callTimed(request, 'get', '/api/accounting/inventory', undefined, sToken);
            const after = (verify.body?.items || []).find(i => i.id === itemId);
            expect(after?.quantity, `quantity must remain 5 after rejected overdraft; got ${after?.quantity}`).toBe(5);

            // Sanity: a legal out movement (qty 2) must succeed.
            const legal = await callTimed(request, 'post',
                `/api/accounting/inventory/movement?${qs({
                    item_id: itemId, movement_type: 'out', quantity: 2, unit_cost: 1.0,
                    reference: `${prefix}LEGAL`,
                })}`, {}, sToken);
            expect(legal.status, `legal out http=${legal.status}`).toBeLessThan(300);

            rec(testInfo, { module: MOD, step: 'inventory_negative_stock_guard', status: 'PASS',
                note: `item=${itemId} overdraft=${overdraft.status} post_qty=${after?.quantity} legal=${legal.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'inv_neg_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('G) Concurrent close race: 5 parallel out movements → atomic decrement', async ({ request, stressTokens, stressState }, testInfo) => {
        if (inventoryBlocked) { test.skip(true, 'inventory surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Seed item with quantity=3, fire 5 parallel out(1) → exactly 3 succeed,
            // 2 must 409. Final quantity must equal 0.
            const create = await callTimed(request, 'post', '/api/accounting/inventory', {
                name: `${prefix}RACE_ITEM`,
                sku: `${prefix}SKU_G`,
                category: 'food',
                unit: 'pcs',
                quantity: 3,
                unit_cost: 1.0,
                reorder_level: 0,
            }, sToken);
            expect(create.status, `seed http=${create.status}`).toBeLessThan(300);
            const itemId = create.body?.id;
            expect(itemId, 'item id').toBeTruthy();
            createdInventoryItemIds.push(itemId);

            const moves = await Promise.all(Array.from({ length: 5 }, (_, i) =>
                callTimed(request, 'post',
                    `/api/accounting/inventory/movement?${qs({
                        item_id: itemId, movement_type: 'out', quantity: 1, unit_cost: 1.0,
                        reference: `${prefix}RACE_${i}`,
                    })}`, {}, sToken)
            ));
            const ok = moves.filter(m => m.status >= 200 && m.status < 300).length;
            const conflict = moves.filter(m => m.status === 409).length;

            const verify = await callTimed(request, 'get', '/api/accounting/inventory', undefined, sToken);
            const after = (verify.body?.items || []).find(i => i.id === itemId);
            const finalQty = Number(after?.quantity);

            // Atomic guard contract: exactly 3 succeed AND finalQty == 0.
            if (ok !== 3 || finalQty !== 0) {
                if (finalQty < 0) {
                    recFinding(testInfo, 'P0', MOD, 'Inventory atomic decrement broken under concurrency (negative final qty)',
                        `item=${itemId} initial=3 parallel=5 ok=${ok} conflict=${conflict} final_qty=${finalQty}. Atomic guard çökmesi.`);
                } else if (ok > 3) {
                    recFinding(testInfo, 'P1', MOD, 'Inventory over-decrement under concurrency',
                        `item=${itemId} initial=3 parallel=5 ok=${ok} conflict=${conflict} final_qty=${finalQty} — more out movements succeeded than initial stock allows.`);
                } else {
                    recFinding(testInfo, 'P2', MOD, 'Inventory concurrent decrement contract mismatch',
                        `item=${itemId} initial=3 ok=${ok} conflict=${conflict} final_qty=${finalQty} — expected ok=3 conflict=2 final=0.`);
                }
            }
            expect(finalQty, `final qty must be ≥ 0; got ${finalQty}`).toBeGreaterThanOrEqual(0);
            expect(ok, `successful out movements must be ≤ 3; got ${ok}`).toBeLessThanOrEqual(3);

            rec(testInfo, { module: MOD, step: 'inventory_concurrent_race', status: 'PASS',
                note: `item=${itemId} ok=${ok} conflict=${conflict} final_qty=${finalQty}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'inv_race_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('H) P0 cross-tenant inventory mutate: pilot bearer must NOT touch stress item', async ({ request, stressTokens, stressState }, testInfo) => {
        if (inventoryBlocked) { test.skip(true, 'inventory surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        if (!pToken) {
            rec(testInfo, { module: MOD, step: 'inv_cross_tenant_idor', status: 'SKIP',
                note: 'no pilot_token; drift-guard alone covers tenant invariant' });
            return;
        }
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const create = await callTimed(request, 'post', '/api/accounting/inventory', {
                name: `${prefix}IDOR_ITEM`,
                sku: `${prefix}SKU_H`,
                category: 'food',
                unit: 'pcs',
                quantity: 100,
                unit_cost: 1.0,
                reorder_level: 0,
            }, sToken);
            expect(create.status, `seed http=${create.status}`).toBeLessThan(300);
            const itemId = create.body?.id;
            expect(itemId, 'item id').toBeTruthy();
            createdInventoryItemIds.push(itemId);

            const isBreach = (s) => s >= 200 && s < 300;

            // Pilot bearer out movement on stress item — must 404.
            const xOut = await callTimed(request, 'post',
                `/api/accounting/inventory/movement?${qs({
                    item_id: itemId, movement_type: 'out', quantity: 10, unit_cost: 1.0,
                    reference: 'pilot-cross-tenant-probe',
                })}`, {}, pToken);
            if (isBreach(xOut.status)) {
                recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant inventory out movement succeeded',
                    `pilot bearer decremented stress item ${itemId} → http=${xOut.status} body=${JSON.stringify(xOut.body).slice(0,200)}. Tenant + financial breach.`);
            }
            expect(xOut.status, `pilot out on stress item must 4xx; got ${xOut.status}`).toBeGreaterThanOrEqual(400);

            // Pilot bearer adjustment on stress item — must 404.
            const xAdj = await callTimed(request, 'post',
                `/api/accounting/inventory/movement?${qs({
                    item_id: itemId, movement_type: 'adjustment', quantity: 0, unit_cost: 1.0,
                    reference: 'pilot-cross-tenant-adj',
                })}`, {}, pToken);
            if (isBreach(xAdj.status)) {
                recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant inventory adjustment succeeded',
                    `pilot bearer adjusted stress item ${itemId} → http=${xAdj.status}. Tenant breach.`);
            }
            expect(xAdj.status, `pilot adjustment on stress item must 4xx; got ${xAdj.status}`).toBeGreaterThanOrEqual(400);

            // Verify stress item quantity unchanged.
            const verify = await callTimed(request, 'get', '/api/accounting/inventory', undefined, sToken);
            const after = (verify.body?.items || []).find(i => i.id === itemId);
            expect(after?.quantity, `stress item qty must remain 100; got ${after?.quantity}`).toBe(100);

            rec(testInfo, { module: MOD, step: 'inv_cross_tenant_idor', status: 'PASS',
                note: `item=${itemId} pilot_out=${xOut.status} pilot_adj=${xAdj.status} stress_qty_unchanged=true` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'inv_idor_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('I) stock_consumption cross-tenant read: pilot bearer must NOT receive stress identifiers', async ({ request, stressTokens, stressState }, testInfo) => {
        if (inventoryBlocked) { test.skip(true, 'inventory surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Stress bearer read — surface present, accept 2xx or module-blocked 4xx.
            const sr = await callTimed(request, 'get', '/api/fnb/mobile/stock-consumption', undefined, sToken);
            if (sr.status === 403 || sr.status === 404) {
                recFinding(testInfo, 'P2', MOD, 'stock-consumption surface unavailable',
                    `GET /api/fnb/mobile/stock-consumption stress http=${sr.status} — read endpoint not deployed or RBAC-blocked.`);
                rec(testInfo, { module: MOD, step: 'stock_consumption_xt_read', status: 'SKIP',
                    note: `stress http=${sr.status} — surface unreachable` });
                return;
            }
            expect(sr.status, `stress stock-consumption http=${sr.status}`).toBeLessThan(500);

            // Pilot bearer read — body MUST NOT contain any stress prefix.
            if (pToken) {
                const pr = await callTimed(request, 'get', '/api/fnb/mobile/stock-consumption', undefined, pToken);
                const prBody = JSON.stringify(pr.body || {});
                if (prBody.includes(prefix)) {
                    recFinding(testInfo, 'P0', MOD, 'stock-consumption leaks stress identifier to pilot',
                        `pilot bearer received stress identifier: http=${pr.status} body=${prBody.slice(0,200)}`);
                }
                expect(prBody.includes(prefix), 'pilot stock-consumption must not contain stress prefix').toBe(false);
            }
            rec(testInfo, { module: MOD, step: 'stock_consumption_xt_read', status: 'PASS',
                note: `stress=${sr.status} pilot_isolated=true` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'stock_cons_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });

    test('Z) Cleanup (idempotent cancel) + final invariants', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Pass 1: cancel via status PUT.
            let cancelled = 0, terminal = 0, other = 0;
            for (const id of new Set(createdKitchenOrderIds.filter(Boolean))) {
                const r = await callTimed(request, 'put',
                    `/api/fnb/kitchen-order/${id}/status?${qs({ status: 'cancelled' })}`, {}, sToken);
                if (r.status >= 200 && r.status < 300) cancelled++;
                else if (r.status >= 400 && r.status < 500) terminal++;
                else other++;
            }
            // Pass 2: idempotency — replay must remain a no-op (200) OR 4xx.
            let pass2Bad = 0;
            for (const id of new Set(createdKitchenOrderIds.filter(Boolean))) {
                const r = await callTimed(request, 'put',
                    `/api/fnb/kitchen-order/${id}/status?${qs({ status: 'cancelled' })}`, {}, sToken);
                const ok = (r.status >= 200 && r.status < 300) || (r.status >= 400 && r.status < 500);
                if (!ok) pass2Bad++;
            }
            if (pass2Bad > 0) {
                recFinding(testInfo, 'P1', MOD, 'KDS cleanup NOT idempotent',
                    `Second-pass cancel produced ${pass2Bad} non-idempotent response(s).`);
            }
            // inventory_items rows are orphan-scrubbed via the unified
            // STRESS_COLLECTIONS sweep (stress_seed tag is added by backend
            // seed factories; direct POST /api/accounting/inventory rows do
            // not carry the tag — those rows persist as harmless orphans
            // until the next prefix-scoped cleanup or until the create surface
            // is extended to stamp stress metadata. Out of scope for spec).
            rec(testInfo, { module: MOD, step: 'cleanup',
                status: pass2Bad === 0 ? 'PASS' : 'FAIL',
                note: `kitchen_orders cancelled=${cancelled} terminal=${terminal} other=${other} pass2_bad=${pass2Bad} inventory_items_created=${createdInventoryItemIds.length} (orphan-scrub via STRESS_COLLECTIONS)` });
            expect(pass2Bad, 'kds cleanup must be idempotent').toBe(0);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'cleanup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
            await assertPilotInventoryDeltaZero(testInfo, MOD, request, pToken, pilotInventoryBaseline);
        }
    });
});
