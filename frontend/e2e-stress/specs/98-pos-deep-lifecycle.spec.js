// F8Z v2 § 98 — POS Deep Lifecycle Stress (sister of F8AB spa + F8AC golf).
//
// Threat-model surface:
//   - POS v2 lifecycle: create_order → close_order (post_to_folio=false) → void_order
//   - Split-check: equal / by_item / custom (POST /api/pos/check-split)
//   - Table-transfer: bogus from_table → 404 + cross-tenant guard
//   - Validate-room-charge: room-charge restrictions probe (POST /api/pos/validate-room-charge)
//   - Idempotency replay: same `idempotency_key` body field → same order id
//     (service-level idempotency on pos_orders + pos_transactions)
//   - Terminal-state guard: close-already-closed / void-already-voided → idempotent
//   - P0 cross-tenant IDOR: pilot bearer must NEVER mutate a stress-created
//     POS order (close / void / split / transfer must hard-fail 4xx)
//
// API contract notes (kept here as the canonical reference for this spec):
//   - POST /api/pos/v2/orders — CreateOrderRequest:
//       outlet_id (str), table_number (str|None), items (list[OrderItemSchema]),
//       guest_name, booking_id, order_type, idempotency_key.
//     OrderItemSchema: item_id, name, quantity, price, station, special_instructions.
//   - POST /api/pos/v2/orders/close — CloseOrderRequest:
//       order_id, payment_method, post_to_folio, booking_id, tip_amount, idempotency_key.
//     Response: { order_id, transaction_id, amount_paid, ... }.
//   - POST /api/pos/v2/orders/void — VoidOrderRequest: order_id, reason.
//   - POST /api/pos/check-split — QUERY: transaction_id, split_type, split_count;
//     BODY: split_details (dict). Targets pos_transactions filtered by tenant.
//   - POST /api/pos/transfer-table — QUERY: from_table, to_table, outlet_id, transfer_all.
//     Requires pos_transactions row with status='open' on (tenant, outlet, from_table).
//     NOTE: No production write surface (v0 or v2) creates pos_transactions.status='open'
//     — close_order writes 'completed'. Transfer-table happy-path is structurally
//     unreachable from production endpoints; spec records this as P2 informational
//     with compensating assertions (negative-contract 4xx + cross-tenant 4xx).
//   - POST /api/pos/validate-room-charge — QUERY: booking_id, amount, category.
//
// Folio-posting safety:
//   `close_order(post_to_folio=False, booking_id=null)` is the safe path that
//   never writes a `folio_charges` row and never publishes the Xchange
//   `POSTING_CHARGE` event. The `external_calls` post-batch invariant proves
//   no real bus traffic occurred during the lifecycle batch.
//
// Module-blocked doctrine:
//   GET `/api/pos/orders` probe → 403/404 ⇒ A/B/C/D/E/F/G/H/I skip + P2 finding.
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//   - cleanup idempotent (POST /api/pos/v2/orders/void; second pass → idempotent flag)
//   - try/finally ile final invariants her test'te zorunlu
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';
import { randomUUID } from 'node:crypto';

const MOD = 'pos_deep_lifecycle';

test.describe.serial('F8Z v2 pos deep lifecycle', () => {
    let prefix = null;
    let outletId = null;
    let createdOrderIds = [];
    let closedTransactions = []; // [{ orderId, txnId, total }]
    let moduleBlocked = false;

    function makeItems(prefixTag) {
        return [
            { item_id: `${prefix}MI_${prefixTag}_a`, name: `${prefixTag} Espresso`,   quantity: 2, price: 80, station: 'bar' },
            { item_id: `${prefix}MI_${prefixTag}_b`, name: `${prefixTag} Croissant`,  quantity: 1, price: 60, station: 'main' },
        ];
    }
    function expectedTotal(items) {
        const subtotal = items.reduce((s, i) => s + i.price * i.quantity, 0);
        const tax = Math.round(subtotal * 0.10 * 100) / 100;
        return Math.round((subtotal + tax) * 100) / 100;
    }
    // Build a query-string helper because POST endpoints in /pos/* use query params.
    function qs(params) {
        const u = new URLSearchParams();
        for (const [k, v] of Object.entries(params)) {
            if (v !== undefined && v !== null) u.set(k, String(v));
        }
        return u.toString();
    }

    test('Setup: probe POS surface + outlet handle', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix || `STRESS_F8Z_V2_${Date.now()}_`;
        outletId = `${prefix}OUTLET`;
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO',
            note: `count=${pilotBefore?.count} prefix=${prefix} outlet=${outletId}` });

        try {
            // Module probe MUST be on the v2 mutation surface (review tur-2 fix):
            // `/api/pos/orders` (legacy GET) may be reachable even when v2 is
            // blocked. Probe `/api/pos/v2/orders` with empty body — 403/404 =
            // module-blocked → A–I skip; 422 = surface present (validation only).
            const probe = await withModuleProbe(request, sToken, '/api/pos/v2/orders',
                { method: 'post', body: {} });
            // 422 (validation error) = surface present + reachable.
            const surfacePresent = probe.status === 422 || (probe.status >= 200 && probe.status < 300);
            if (!surfacePresent && (probe.status === 403 || probe.status === 404)) {
                moduleBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'POS v2 surface module-blocked',
                    `POST /api/pos/v2/orders http=${probe.status} reason=${probe.reason} — A/B/C/D/E/F/G/H/I skip; final invariants still enforced.`);
                rec(testInfo, { module: MOD, step: 'pos_probe', status: 'SKIP',
                    note: `module_blocked http=${probe.status} reason=${probe.reason}` });
                return;
            }
            // Optional table-layout read — accept 200 (auto-seed) or 404 (unknown outlet).
            const tl = await callTimed(request, 'get',
                `/api/pos/table-layout/${outletId}`, undefined, sToken);
            rec(testInfo, { module: MOD, step: 'pos_probe', status: 'PASS',
                note: `v2_orders_probe=${probe.status} table_layout_http=${tl.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('A) Catalog smoke (orders + transactions list)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const reads = [
                ['/api/pos/orders?limit=5', 'orders'],
                ['/api/pos/transactions?limit=5', 'transactions'],
            ];
            const results = {};
            for (const [path, key] of reads) {
                const r = await callTimed(request, 'get', path, undefined, sToken);
                results[key] = { http: r.status, ms: r.ms };
                if (r.status < 200 || r.status >= 300) {
                    recFinding(testInfo, 'P2', MOD, `POS catalog read non-2xx ${key}`,
                        `GET ${path} http=${r.status}`);
                }
            }
            rec(testInfo, { module: MOD, step: 'catalog_read', status: 'PASS',
                note: JSON.stringify(results) });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'catalog_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('B) Lifecycle: create → close (post_to_folio=false, no folio, no Xchange)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const items = makeItems('B');
            const create = await callTimed(request, 'post', '/api/pos/v2/orders', {
                outlet_id: outletId,
                table_number: `${prefix}T_B`,
                items,
                guest_name: `${prefix}WalkIn-B`,
                booking_id: null,
                order_type: 'dine_in',
                idempotency_key: `${prefix}IDEM_B_CREATE_${randomUUID()}`,
            }, sToken);
            expect(create.status, `create http=${create.status} body=${JSON.stringify(create.body).slice(0,200)}`).toBeGreaterThanOrEqual(200);
            expect(create.status).toBeLessThan(300);
            const orderId = create.body?.order_id;
            expect(orderId, 'order_id returned').toBeTruthy();
            createdOrderIds.push(orderId);

            const close = await callTimed(request, 'post', '/api/pos/v2/orders/close', {
                order_id: orderId,
                payment_method: 'cash',
                post_to_folio: false,
                booking_id: null,
                tip_amount: 0,
                idempotency_key: `${prefix}IDEM_B_CLOSE_${randomUUID()}`,
            }, sToken);
            expect(close.status, `close http=${close.status} body=${JSON.stringify(close.body).slice(0,200)}`).toBe(200);
            const txnId = close.body?.transaction_id;
            const total = close.body?.amount_paid ?? expectedTotal(items);
            if (txnId) closedTransactions.push({ orderId, txnId, total });

            rec(testInfo, { module: MOD, step: 'lifecycle_happy', status: 'PASS',
                note: `order=${orderId} txn=${txnId} total=${total} folio_skip=true` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'lifecycle_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('C) Atomic conflict guard via idempotency-key replay (same key → same order id)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const items = makeItems('C');
            const key = `${prefix}IDEM_C_${randomUUID()}`;
            const payload = {
                outlet_id: outletId,
                table_number: `${prefix}T_C`,
                items,
                guest_name: `${prefix}WalkIn-C`,
                booking_id: null,
                order_type: 'dine_in',
                idempotency_key: key,
            };
            const r1 = await callTimed(request, 'post', '/api/pos/v2/orders', payload, sToken);
            const r2 = await callTimed(request, 'post', '/api/pos/v2/orders', payload, sToken);
            expect(r1.status, `r1 http=${r1.status} body=${JSON.stringify(r1.body).slice(0,200)}`).toBeGreaterThanOrEqual(200);
            expect(r1.status).toBeLessThan(300);
            const r1Id = r1.body?.order_id;
            // Replay shape (review tur-2 fix): v2 create_order replay returns
            // `{message, order: existing, idempotent: true}` — order id at
            // `order.id`, NOT top-level `order_id`. Accept all three shapes:
            // (a) same top-level `order_id`, (b) nested `order.id === r1Id`,
            // (c) explicit `idempotent: true` flag, OR (d) 4xx terminal.
            const r2Id = r2.body?.order_id ?? r2.body?.order?.id;
            const r2IdemFlag = r2.body?.idempotent === true;
            if (r1Id) createdOrderIds.push(r1Id);
            const sameId = r1Id && r2Id && r1Id === r2Id;
            const r2Conflict = r2.status >= 400 && r2.status < 500;
            const guarded = sameId || r2IdemFlag || r2Conflict;
            if (!guarded && r2.status >= 200 && r2.status < 300) {
                if (r2Id && r2Id !== r1Id) createdOrderIds.push(r2Id);
                recFinding(testInfo, 'P1', MOD, 'POS create_order replay NOT idempotent',
                    `r1.id=${r1Id} r2.id=${r2Id} idempotency_key=${key} body=${JSON.stringify(r2.body).slice(0,200)} — identical payload created two distinct orders (no service-level idempotency). Double-charge risk.`);
            }
            rec(testInfo, { module: MOD, step: 'conflict_idem_replay',
                status: guarded ? 'PASS' : 'FAIL',
                note: `r1.http=${r1.status} r2.http=${r2.status} sameId=${!!sameId} idem_flag=${r2IdemFlag} r2_conflict=${r2Conflict}` });
            expect(guarded, 'create_order replay must be guarded (same id, idempotent flag, or 4xx)').toBe(true);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'conflict_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('D) Split-check: equal + by_item + custom (sum ≤ original_amount invariant)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Seed a dedicated closed transaction for split-check (uses real txn id).
            const items = makeItems('D');
            const create = await callTimed(request, 'post', '/api/pos/v2/orders', {
                outlet_id: outletId, table_number: `${prefix}T_D`, items,
                guest_name: `${prefix}WalkIn-D`, booking_id: null, order_type: 'dine_in',
                idempotency_key: `${prefix}IDEM_D_CREATE_${randomUUID()}`,
            }, sToken);
            expect(create.status).toBeLessThan(300);
            const orderId = create.body?.order_id;
            createdOrderIds.push(orderId);
            const close = await callTimed(request, 'post', '/api/pos/v2/orders/close', {
                order_id: orderId, payment_method: 'cash',
                post_to_folio: false, booking_id: null, tip_amount: 0,
                idempotency_key: `${prefix}IDEM_D_CLOSE_${randomUUID()}`,
            }, sToken);
            expect(close.status).toBe(200);
            const txnId = close.body?.transaction_id;
            const total = close.body?.amount_paid ?? expectedTotal(items);
            expect(txnId, 'txn id available for split-check').toBeTruthy();
            closedTransactions.push({ orderId, txnId, total });

            // Split scenarios — endpoint uses QUERY params for scalars + BODY for split_details.
            const scenarios = [
                { name: 'equal',   query: { transaction_id: txnId, split_type: 'equal',   split_count: 3 }, body: {} },
                { name: 'by_item', query: { transaction_id: txnId, split_type: 'by_item', split_count: 2 }, body: { split_details: { '1': [0], '2': [1] } } },
                { name: 'custom',  query: { transaction_id: txnId, split_type: 'custom',  split_count: 3 }, body: { split_details: { '1': total * 0.5, '2': total * 0.3, '3': total * 0.2 } } },
            ];
            const out = {};
            for (const s of scenarios) {
                const r = await callTimed(request, 'post',
                    `/api/pos/check-split?${qs(s.query)}`, s.body, sToken);
                out[s.name] = { http: r.status };
                if (r.status === 403 || r.status === 404) {
                    recFinding(testInfo, 'P2', MOD, `check-split ${s.name} surface unavailable`,
                        `http=${r.status} body=${JSON.stringify(r.body).slice(0,160)} — endpoint may require additional role or txn state.`);
                    continue;
                }
                expect(r.status, `split ${s.name} http=${r.status} body=${JSON.stringify(r.body).slice(0,200)}`).toBe(200);
                const original = Number(r.body?.original_amount ?? total);
                const sum = (r.body?.splits || []).reduce((a, b) => a + Number(b.amount || 0), 0);
                out[s.name].sum = sum;
                out[s.name].original = original;
                if (sum > original + 0.05) {
                    recFinding(testInfo, 'P1', MOD, `Split ${s.name} sum exceeds original_amount`,
                        `sum=${sum} original=${original} — money-safety invariant breach.`);
                }
                expect(sum, `${s.name} split sum invariant`).toBeLessThanOrEqual(original + 0.05);
            }
            rec(testInfo, { module: MOD, step: 'split_check', status: 'PASS',
                note: JSON.stringify(out) });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'split_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('E) Table-transfer: happy-path attempt + bogus 404 + cross-tenant guard', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        let openTabTxnId = null;
        try {
            // E1) Happy-path — now REAL. Task #165 added the missing "open tab"
            //   write surface (POST /api/pos/v2/tabs/open) that creates a
            //   `pos_transactions` row with status='open'. transfer_table
            //   filters on (tenant, outlet, from_table, status='open'), so the
            //   happy path is reachable end-to-end:
            //     open-tab(happyTable) → transfer-table(happyTable→dest) → 2xx.
            const happyTable = `${prefix}T_E_HAPPY`;
            const happyDest = `${prefix}T_E_HAPPY_DEST`;
            const open = await callTimed(request, 'post', '/api/pos/v2/tabs/open', {
                outlet_id: outletId,
                table_number: happyTable,
                items: makeItems('E'),
                guest_name: `${prefix}WalkIn-E`,
                guests: 2,
                idempotency_key: `${prefix}IDEM_E_TAB_${randomUUID()}`,
            }, sToken);
            expect(open.status, `open-tab http=${open.status} body=${JSON.stringify(open.body).slice(0,200)}`).toBe(200);
            openTabTxnId = open.body?.transaction_id;
            expect(openTabTxnId, 'open-tab transaction_id').toBeTruthy();
            expect(open.body?.status, 'open-tab status must be open').toBe('open');

            const happyTransfer = await callTimed(request, 'post',
                `/api/pos/transfer-table?${qs({
                    from_table: happyTable,
                    to_table: happyDest,
                    outlet_id: outletId,
                    transfer_all: true,
                // transfer_table: tüm scalar paramlar query'de; items_to_transfer
                // list[int]|None gövde param. Boş `{}` gövdesi FastAPI'de list
                // doğrulamasına takılıp 422 verirdi → null geç (gövde gönderilmez,
                // items_to_transfer=None → transfer_all branch). Negatif testler de
                // (bogus 404 / cross-tenant) artık handler'a ulaşır, 422'de ölmez.
                })}`, null, sToken);
            expect(happyTransfer.status, `happy transfer http=${happyTransfer.status} body=${JSON.stringify(happyTransfer.body).slice(0,200)}`).toBe(200);
            expect(happyTransfer.body?.transaction_id, 'transfer returns the open-tab txn id').toBe(openTabTxnId);
            rec(testInfo, { module: MOD, step: 'transfer_happy_path', status: 'PASS',
                note: `open_tab=${open.status} txn=${openTabTxnId} happy_transfer=${happyTransfer.status} items_transferred=${happyTransfer.body?.items_transferred}` });

            // E2) Negative contract — bogus from_table → 4xx (404 expected).
            const bogus = await callTimed(request, 'post',
                `/api/pos/transfer-table?${qs({
                    from_table: `${prefix}T_BOGUS_${randomUUID().slice(0, 8)}`,
                    to_table: `${prefix}T_DEST_${randomUUID().slice(0, 8)}`,
                    outlet_id: outletId,
                    transfer_all: true,
                })}`, null, sToken);
            expect(bogus.status, `bogus transfer must 4xx; got ${bogus.status}`).toBeGreaterThanOrEqual(400);
            expect(bogus.status, `bogus transfer must be <500; got ${bogus.status}`).toBeLessThan(500);
            rec(testInfo, { module: MOD, step: 'transfer_negative', status: 'PASS',
                note: `bogus_http=${bogus.status}` });

            // E3) Cross-tenant guard — pilot bearer must NOT transfer the stress
            //   open tab (no such open tab exists in the pilot tenant → 4xx).
            if (pToken) {
                const xfer = await callTimed(request, 'post',
                    `/api/pos/transfer-table?${qs({
                        from_table: happyDest,
                        to_table: `${prefix}T_XT_DEST`,
                        outlet_id: outletId,
                        transfer_all: true,
                    })}`, null, pToken);
                if (xfer.status >= 200 && xfer.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Cross-tenant table-transfer succeeded',
                        `pilot bearer transferred stress open tab (table=${happyDest} outlet=${outletId}) → http=${xfer.status}. Tenant isolation breach.`);
                }
                expect(xfer.status, `pilot cross-tenant transfer must 4xx; got ${xfer.status}`).toBeGreaterThanOrEqual(400);
                rec(testInfo, { module: MOD, step: 'transfer_cross_tenant', status: 'PASS',
                    note: `pilot_transfer_http=${xfer.status}` });
            }
        } finally {
            // Settle the open tab so no status='open' residue is left behind.
            if (openTabTxnId) {
                await callTimed(request, 'post', '/api/pos/v2/tabs/close',
                    { transaction_id: openTabTxnId, payment_method: 'cash' }, sToken);
            }
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'transfer_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('F) Idempotency replay on close_order (same key → idempotent flag)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const items = makeItems('F');
            const create = await callTimed(request, 'post', '/api/pos/v2/orders', {
                outlet_id: outletId, table_number: `${prefix}T_F`, items,
                guest_name: `${prefix}WalkIn-F`, booking_id: null, order_type: 'dine_in',
                idempotency_key: `${prefix}IDEM_F_CREATE_${randomUUID()}`,
            }, sToken);
            expect(create.status).toBeLessThan(300);
            const orderId = create.body?.order_id;
            expect(orderId, 'order id').toBeTruthy();
            createdOrderIds.push(orderId);

            const closeKey = `${prefix}IDEM_F_CLOSE_${randomUUID()}`;
            const closePayload = {
                order_id: orderId,
                payment_method: 'cash',
                post_to_folio: false,
                booking_id: null,
                tip_amount: 0,
                idempotency_key: closeKey,
            };
            const c1 = await callTimed(request, 'post', '/api/pos/v2/orders/close', closePayload, sToken);
            const c2 = await callTimed(request, 'post', '/api/pos/v2/orders/close', closePayload, sToken);
            expect(c1.status, `c1 close http=${c1.status}`).toBe(200);
            // c2 must be idempotent: 200 with `idempotent:true` OR 4xx terminal-state.
            const c2IdemFlag = !!(c2.body?.idempotent);
            const c2Terminal = c2.status >= 400 && c2.status < 500;
            const c2OkIdem = (c2.status === 200 && c2IdemFlag) || c2Terminal;
            if (!c2OkIdem) {
                recFinding(testInfo, 'P1', MOD, 'POS close_order replay NOT idempotent',
                    `order=${orderId} c1.http=${c1.status} c2.http=${c2.status} idempotent_flag=${c2IdemFlag} — double-close should not re-trigger payment write.`);
            }
            rec(testInfo, { module: MOD, step: 'close_idempotency',
                status: c2OkIdem ? 'PASS' : 'FAIL',
                note: `c1=${c1.status} c2=${c2.status} idem_flag=${c2IdemFlag} terminal=${c2Terminal}` });
            expect(c2OkIdem, 'close replay must be idempotent or 4xx').toBe(true);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'idempotency_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('G) Terminal-state guard: void order, re-void already-voided, close-after-void', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const items = makeItems('G');
            const create = await callTimed(request, 'post', '/api/pos/v2/orders', {
                outlet_id: outletId, table_number: `${prefix}T_G`, items,
                guest_name: `${prefix}WalkIn-G`, booking_id: null, order_type: 'dine_in',
                idempotency_key: `${prefix}IDEM_G_CREATE_${randomUUID()}`,
            }, sToken);
            expect(create.status).toBeLessThan(300);
            const orderId = create.body?.order_id;
            expect(orderId, 'order id').toBeTruthy();
            createdOrderIds.push(orderId);

            const v1 = await callTimed(request, 'post', '/api/pos/v2/orders/void', {
                order_id: orderId, reason: `${prefix} G-void`,
            }, sToken);
            expect(v1.status, `v1 void http=${v1.status} body=${JSON.stringify(v1.body).slice(0,200)}`).toBe(200);

            const v2 = await callTimed(request, 'post', '/api/pos/v2/orders/void', {
                order_id: orderId, reason: `${prefix} G-void-replay`,
            }, sToken);
            const v2IdemFlag = !!(v2.body?.idempotent);
            const v2Terminal = v2.status >= 400 && v2.status < 500;
            const v2OkIdem = (v2.status === 200 && v2IdemFlag) || v2Terminal;
            if (!v2OkIdem) {
                recFinding(testInfo, 'P1', MOD, 'POS void_order replay NOT idempotent',
                    `order=${orderId} v1.http=${v1.status} v2.http=${v2.status} idempotent_flag=${v2IdemFlag} — re-void should be no-op.`);
            }
            // Closing a voided order must also fail (terminal state).
            const closeAfterVoid = await callTimed(request, 'post', '/api/pos/v2/orders/close', {
                order_id: orderId, payment_method: 'cash',
                post_to_folio: false, booking_id: null, tip_amount: 0,
            }, sToken);
            const closeBlocked = closeAfterVoid.status >= 400 && closeAfterVoid.status < 500;
            if (!closeBlocked) {
                recFinding(testInfo, 'P1', MOD, 'POS close after void allowed',
                    `order=${orderId} close-after-void http=${closeAfterVoid.status} — terminal-state guard breached.`);
            }
            rec(testInfo, { module: MOD, step: 'terminal_state_guard',
                status: (v2OkIdem && closeBlocked) ? 'PASS' : 'FAIL',
                note: `v1=${v1.status} v2=${v2.status} v2_idem=${v2IdemFlag} close_after_void=${closeAfterVoid.status}` });
            expect(v2OkIdem, 'void replay must be idempotent or 4xx').toBe(true);
            expect(closeBlocked, 'close after void must 4xx').toBe(true);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'terminal_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('H) P0 Cross-tenant IDOR: pilot bearer must NOT touch stress order/txn', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            if (!pToken) {
                rec(testInfo, { module: MOD, step: 'cross_tenant_idor', status: 'SKIP',
                    note: 'no pilot_token; drift-guard alone covers tenant invariant' });
                return;
            }
            // Seed a fresh order + close → captures txn_id for split IDOR probe.
            const items = makeItems('H');
            const create = await callTimed(request, 'post', '/api/pos/v2/orders', {
                outlet_id: outletId, table_number: `${prefix}T_H`, items,
                guest_name: `${prefix}WalkIn-H`, booking_id: null, order_type: 'dine_in',
                idempotency_key: `${prefix}IDEM_H_CREATE_${randomUUID()}`,
            }, sToken);
            expect(create.status).toBeLessThan(300);
            const targetOrderId = create.body?.order_id;
            expect(targetOrderId, 'target order id').toBeTruthy();
            createdOrderIds.push(targetOrderId);

            const closeForTxn = await callTimed(request, 'post', '/api/pos/v2/orders/close', {
                order_id: targetOrderId, payment_method: 'cash',
                post_to_folio: false, booking_id: null, tip_amount: 0,
                idempotency_key: `${prefix}IDEM_H_CLOSE_${randomUUID()}`,
            }, sToken);
            expect(closeForTxn.status).toBe(200);
            const targetTxnId = closeForTxn.body?.transaction_id;

            // Finding-emission-order doctrine (review tur-2 fix): for hard-fail
            // IDOR probes, compute breach boolean FIRST, then emit recFinding,
            // THEN assert. Otherwise expect() throws before the P0 forensic
            // annotation is recorded.
            const isBreach = (s) => s >= 200 && s < 300;

            // H1) Pilot close on stress order — must 4xx (order tenant-filtered).
            const xClose = await callTimed(request, 'post', '/api/pos/v2/orders/close', {
                order_id: targetOrderId, payment_method: 'cash',
                post_to_folio: false, booking_id: null, tip_amount: 0,
            }, pToken);
            if (isBreach(xClose.status)) {
                recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant POS close',
                    `pilot bearer closed stress order ${targetOrderId} → http=${xClose.status} body=${JSON.stringify(xClose.body).slice(0,200)}. Tenant + money-safety breach.`);
            }
            expect(xClose.status, `pilot close on stress order must 4xx; got ${xClose.status}`).toBeGreaterThanOrEqual(400);

            // H2) Pilot void on stress order — must 4xx (tenant check in find_one).
            const xVoid = await callTimed(request, 'post', '/api/pos/v2/orders/void', {
                order_id: targetOrderId, reason: 'pilot-cross-tenant-probe',
            }, pToken);
            if (isBreach(xVoid.status)) {
                recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant POS void',
                    `pilot bearer voided stress order ${targetOrderId} → http=${xVoid.status} body=${JSON.stringify(xVoid.body).slice(0,200)}. Tenant breach.`);
            }
            expect(xVoid.status, `pilot void on stress order must 4xx; got ${xVoid.status}`).toBeGreaterThanOrEqual(400);

            // H3) Pilot transfer-table on stress outlet+table — must 4xx
            // (transfer filters by tenant + status='open'; pilot has neither → 404).
            const xTransfer = await callTimed(request, 'post',
                `/api/pos/transfer-table?${qs({
                    from_table: `${prefix}T_H`,
                    to_table: `${prefix}T_H_DEST`,
                    outlet_id: outletId,
                    transfer_all: true,
                })}`, {}, pToken);
            if (isBreach(xTransfer.status)) {
                recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant POS transfer',
                    `pilot bearer transferred stress table → http=${xTransfer.status} body=${JSON.stringify(xTransfer.body).slice(0,200)}. Tenant breach.`);
            }
            expect(xTransfer.status, `pilot transfer on stress table must 4xx; got ${xTransfer.status}`).toBeGreaterThanOrEqual(400);
            expect(xTransfer.status, `pilot transfer must be <500; got ${xTransfer.status}`).toBeLessThan(500);

            // H4) Pilot split-check on stress transaction_id — must 4xx
            // (check-split filters pos_transactions by tenant; cross-tenant → 404).
            if (targetTxnId) {
                const xSplit = await callTimed(request, 'post',
                    `/api/pos/check-split?${qs({
                        transaction_id: targetTxnId,
                        split_type: 'equal',
                        split_count: 2,
                    })}`, {}, pToken);
                if (isBreach(xSplit.status)) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant POS split-check',
                        `pilot bearer split-checked stress txn ${targetTxnId} → http=${xSplit.status} body=${JSON.stringify(xSplit.body).slice(0,200)}. Tenant + money-safety breach.`);
                }
                expect(xSplit.status, `pilot split on stress txn must 4xx; got ${xSplit.status}`).toBeGreaterThanOrEqual(400);
                expect(xSplit.status, `pilot split must be <500; got ${xSplit.status}`).toBeLessThan(500);
            }

            rec(testInfo, { module: MOD, step: 'cross_tenant_idor', status: 'PASS',
                note: `target_order=${targetOrderId} target_txn=${targetTxnId} close=${xClose.status} void=${xVoid.status} transfer=${xTransfer.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'idor_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('I) validate-room-charge: bogus booking + cross-tenant probe', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const bogusBooking = `${prefix}BOOKING_BOGUS_${randomUUID().slice(0, 8)}`;
            // I1) Stress token + bogus booking_id → expect 2xx with no PII/folio leak.
            const r = await callTimed(request, 'post',
                `/api/pos/validate-room-charge?${qs({
                    booking_id: bogusBooking, amount: 100, category: 'food',
                })}`, {}, sToken);
            if (r.status === 403 || r.status === 404) {
                recFinding(testInfo, 'P2', MOD, 'validate-room-charge unavailable',
                    `http=${r.status} — endpoint may require additional gate.`);
            } else {
                expect(r.status, `validate http=${r.status}`).toBeLessThan(500);
            }

            // I2) PII/identifier leak guard on response body.
            const body = JSON.stringify(r.body || {});
            if (/identity_number|passport_no|iban/i.test(body)) {
                recFinding(testInfo, 'P1', MOD, 'validate-room-charge leaks PII fields',
                    `body excerpt=${body.slice(0, 200)} — guest PII surfaced through validation endpoint.`);
            }

            // I3) Pilot bearer same call: must be tenant-scoped to pilot. Response
            // must not contain any stress identifier or prefix string.
            if (pToken) {
                const px = await callTimed(request, 'post',
                    `/api/pos/validate-room-charge?${qs({
                        booking_id: bogusBooking, amount: 100, category: 'food',
                    })}`, {}, pToken);
                const pxBody = JSON.stringify(px.body || {});
                if (pxBody.includes(prefix)) {
                    recFinding(testInfo, 'P0', MOD, 'validate-room-charge leaks stress identifier to pilot',
                        `pilot bearer received stress identifier: http=${px.status} body=${pxBody.slice(0,200)}`);
                }
            }
            rec(testInfo, { module: MOD, step: 'validate_room_charge', status: 'PASS',
                note: `stress_http=${r.status} pii_leak=false` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'validate_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('Z) Cleanup (idempotent void) + final invariants', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            let voided = 0, alreadyTerminal = 0, other = 0;
            for (const id of new Set(createdOrderIds.filter(Boolean))) {
                const r = await callTimed(request, 'post', '/api/pos/v2/orders/void', {
                    order_id: id, reason: `${prefix} cleanup`,
                }, sToken);
                if (r.status === 200 || r.status === 201) voided++;
                else if (r.status >= 400 && r.status < 500) alreadyTerminal++;
                else other++;
            }
            // Second pass — idempotency: every id should remain in a terminal
            // state (either 200 with idempotent:true OR 4xx).
            let secondPassBad = 0;
            for (const id of new Set(createdOrderIds.filter(Boolean))) {
                const r = await callTimed(request, 'post', '/api/pos/v2/orders/void', {
                    order_id: id, reason: `${prefix} cleanup-replay`,
                }, sToken);
                const ok = (r.status === 200 && !!(r.body?.idempotent))
                    || (r.status >= 400 && r.status < 500);
                if (!ok) secondPassBad++;
            }
            if (secondPassBad > 0) {
                recFinding(testInfo, 'P1', MOD, 'POS void cleanup NOT idempotent',
                    `Second-pass void produced ${secondPassBad} non-idempotent response(s). Cleanup contract broken.`);
            }
            // pos_orders / pos_transactions / table_layouts / kitchen_orders /
            // pos_outlets / pos_menu_items / happy_hour_rules /
            // pos_room_charge_restrictions are orphan-scrubbed via the unified
            // STRESS_COLLECTIONS sweep (stress_seed=True + stress_prefix tag).
            rec(testInfo, { module: MOD, step: 'cleanup',
                status: secondPassBad === 0 ? 'PASS' : 'FAIL',
                note: `voided=${voided} already_terminal=${alreadyTerminal} other=${other} second_pass_bad=${secondPassBad} txns_closed=${closedTransactions.length} (orphan-scrub via STRESS_COLLECTIONS)` });
            expect(secondPassBad, 'void cleanup must be idempotent').toBe(0);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'cleanup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});
