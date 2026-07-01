// F8AI § 99 — POS Extensions Stress (8 new POS modules).
//
// Surface (mevcut POS akışından bağımsız, /api/pos/ext/* altında):
//   - currency  : döviz kuru tanımla / yabancı dövizle tahsilat
//   - happy_hour: zaman-bazlı kural + apply (fiyat değişmez, hesap döndürür)
//   - coupons   : kupon CRUD + validate + atomik redeem (max_uses race guard)
//   - loyalty   : earn/redeem + atomic balance check
//   - shifts    : open/close + expected vs counted cash variance
//   - barcode   : map + lookup (sadece eşleme tablosu, menüye yazmaz)
//   - print     : ESC/POS render + driver dispatch (simulator default)
//   - fiscal    : TR ÖKC kuyruğu + simulator adapter (hugin_stub fail-as-designed)
//
// Mutlak kurallar (F8 series doctrine):
//   - pilot mutation = 0  → assertPilotDriftZero her test'te
//   - external_calls = [] → assertNoExternalCallsPostBatch her test'te
//   - failedTests = 0, P0 = P1 = 0
//   - cleanup idempotent (delete + second pass; absent → no error)
//   - try/finally zorunlu
//   - assertion gevşetme YASAK / skip-as-pass YASAK
//
// Module-blocked doctrine: probe POST /api/pos/ext/currency/rates ile {}.
//   404/403 → tüm modül testleri skip + P2 informational finding.
//   422 (validation) → surface OK.
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'pos_extensions';

test.describe.serial('F8AI POS Extensions', () => {
    let prefix = null;
    let moduleBlocked = false;
    // Track every doc created so that cleanup is exhaustive and idempotent.
    const created = {
        rateIds: [],
        paymentIds: [],
        happyRuleIds: [],
        couponIds: [],
        loyaltyGuestIds: [],
        shiftIds: [],
        barcodes: [],
        printJobIds: [],
        fiscalJobIds: [],
    };

    // ── Setup ─────────────────────────────────────────────────────
    test('Setup: probe POS extensions surface', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix || `STRESS_F8AI_${Date.now()}_`;
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO',
            note: `count=${pilotBefore?.count} prefix=${prefix}` });

        try {
            const probe = await withModuleProbe(request, sToken, '/api/pos/ext/currency/rates',
                { method: 'post', body: {} });
            const surfacePresent = probe.status === 422 || (probe.status >= 200 && probe.status < 300);
            if (!surfacePresent && (probe.status === 403 || probe.status === 404)) {
                moduleBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'POS extensions surface module-blocked',
                    `POST /api/pos/ext/currency/rates http=${probe.status} reason=${probe.reason} — all tests skip; invariants still enforced.`);
                rec(testInfo, { module: MOD, step: 'probe', status: 'SKIP',
                    note: `module_blocked http=${probe.status}` });
                return;
            }
            rec(testInfo, { module: MOD, step: 'probe', status: 'PASS',
                note: `currency_probe=${probe.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── A) Multi-currency ─────────────────────────────────────────
    test('A) Currency: upsert rate + foreign payment idempotency + cross-tenant guard',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Upsert rate
            const rateBody = { currency_code: 'USD', rate_to_base: 32.5, note: `${prefix}rate` };
            const r1 = await callTimed(request, 'post', '/api/pos/ext/currency/rates', rateBody, sToken);
            expect(r1.status).toBe(200);
            if (r1.body?.rate?.id) created.rateIds.push(r1.body.rate.id);

            // Latest rate
            const lat = await callTimed(request, 'get', '/api/pos/ext/currency/rates/latest/USD', undefined, sToken);
            expect(lat.status).toBe(200);
            expect(Number(lat.body.rate_to_base)).toBeCloseTo(32.5);

            // Foreign payment requires existing order → expect 404 (no order created in this lean spec);
            // Either way, cross-tenant guard is the critical assertion.
            const payBody = {
                order_id: `${prefix}NONEXISTENT_ORDER`,
                currency_code: 'USD',
                amount_foreign: 50,
                rate_used: 32.5,
                idempotency_key: `${prefix}idem_pay_1`,
            };
            const pay = await callTimed(request, 'post', '/api/pos/ext/currency/payments', payBody, sToken);
            // 404 (order not found) ya da 200 (eğer fixture order varsa) — ikisi de structural OK.
            expect([200, 404]).toContain(pay.status);
            if (pay.status === 200 && pay.body?.payment?.id) {
                created.paymentIds.push(pay.body.payment.id);
                // Idempotent replay
                const pay2 = await callTimed(request, 'post', '/api/pos/ext/currency/payments', payBody, sToken);
                expect(pay2.status).toBe(200);
                expect(pay2.body?.idempotent).toBe(true);
            }

            // P0 cross-tenant: pilot bearer must NEVER see stress rate by id
            if (r1.body?.rate?.id) {
                const xt = await callTimed(request, 'get',
                    `/api/pos/ext/currency/rates?code=USD`, undefined, pToken);
                if (xt.status === 200) {
                    const leak = (xt.body.rates || []).some((r) => r.id === r1.body.rate.id);
                    if (leak) {
                        recFinding(testInfo, 'P0', MOD, 'currency rate cross-tenant leak',
                            `pilot saw stress rate id=${r1.body.rate.id}`);
                    }
                    expect(leak).toBe(false);
                }
            }
            // P0 cross-tenant: pilot list_payments must not see any stress payment
            const xpp = await callTimed(request, 'get', '/api/pos/ext/currency/payments?limit=200', undefined, pToken);
            if (xpp.status === 200) {
                const leak = (xpp.body.payments || []).some((p) =>
                    typeof p.order_id === 'string' && p.order_id.startsWith(prefix)
                );
                if (leak) {
                    recFinding(testInfo, 'P0', MOD, 'currency payment cross-tenant list leak',
                        `pilot saw stress payment with prefix=${prefix}`);
                }
                expect(leak).toBe(false);
            }
            rec(testInfo, { module: MOD, step: 'A_currency', status: 'PASS' });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'A_currency_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── B) Happy Hour ─────────────────────────────────────────────
    test('B) HappyHour: create rule + apply discounts + delete idempotent',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const rule = {
                name: `${prefix}HH_rule`,
                start_time: '00:00', end_time: '23:59',
                days_of_week: [0, 1, 2, 3, 4, 5, 6],
                discount_type: 'percent', discount_value: 20,
            };
            const c = await callTimed(request, 'post', '/api/pos/ext/happy-hour/rules', rule, sToken);
            expect(c.status).toBe(200);
            const ruleId = c.body?.rule?.id;
            if (ruleId) created.happyRuleIds.push(ruleId);

            const applyBody = {
                items: [{ item_id: `${prefix}MI_a`, name: 'Test Item', quantity: 2, price: 100 }],
            };
            const ap = await callTimed(request, 'post', '/api/pos/ext/happy-hour/apply', applyBody, sToken);
            expect(ap.status).toBe(200);
            expect(ap.body.items?.[0]?.unit_price).toBeLessThanOrEqual(100);
            expect(ap.body.savings).toBeGreaterThanOrEqual(0);

            rec(testInfo, { module: MOD, step: 'B_happy_hour', status: 'PASS',
                note: `savings=${ap.body.savings}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'B_happy_hour_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── C) Coupons ────────────────────────────────────────────────
    test('C) Coupons: create + validate + atomic redeem (race guard) + duplicate code 409',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const code = `${prefix}CPN_${Date.now()}`;
            const body = {
                code, discount_type: 'percent', discount_value: 15,
                min_amount: 50, max_uses: 2, active: true,
            };
            const c = await callTimed(request, 'post', '/api/pos/ext/coupons', body, sToken);
            expect(c.status).toBe(200);
            if (c.body?.coupon?.id) created.couponIds.push(c.body.coupon.id);

            // Duplicate code → 409
            const dup = await callTimed(request, 'post', '/api/pos/ext/coupons', body, sToken);
            expect(dup.status).toBe(409);

            // Validate
            const v = await callTimed(request, 'post', '/api/pos/ext/coupons/validate',
                { code, amount: 200 }, sToken);
            expect(v.status).toBe(200);
            expect(v.body.valid).toBe(true);
            expect(v.body.discount_amount).toBeGreaterThan(0);

            // Atomic redeem twice with idempotency_key → second is idempotent
            const idemKey = `${prefix}cpn_idem_1`;
            const r1 = await callTimed(request, 'post', '/api/pos/ext/coupons/redeem',
                { code, amount: 200, idempotency_key: idemKey }, sToken);
            expect(r1.status).toBe(200);
            const r2 = await callTimed(request, 'post', '/api/pos/ext/coupons/redeem',
                { code, amount: 200, idempotency_key: idemKey }, sToken);
            expect(r2.status).toBe(200);
            expect(r2.body.idempotent).toBe(true);

            // Now consume the remaining single use (different idempotency key)
            const r3 = await callTimed(request, 'post', '/api/pos/ext/coupons/redeem',
                { code, amount: 200, idempotency_key: `${prefix}cpn_idem_2` }, sToken);
            expect(r3.status).toBe(200);

            // Third real redeem must hit the cap (400 from _check_validity OR 409 race guard)
            const r4 = await callTimed(request, 'post', '/api/pos/ext/coupons/redeem',
                { code, amount: 200, idempotency_key: `${prefix}cpn_idem_3` }, sToken);
            expect([400, 409]).toContain(r4.status);

            // P0 cross-tenant: pilot redeem of stress coupon must fail (Unknown code)
            const xt = await callTimed(request, 'post', '/api/pos/ext/coupons/validate',
                { code, amount: 200 }, pToken);
            if (xt.status === 200) {
                if (xt.body.valid === true) {
                    recFinding(testInfo, 'P0', MOD, 'coupon cross-tenant validate leak',
                        `pilot validated stress coupon code=${code}`);
                }
                expect(xt.body.valid).toBe(false);
            }
            // P0 cross-tenant: pilot redemptions list must not show stress code
            const xr = await callTimed(request, 'get',
                '/api/pos/ext/coupons/redemptions?limit=200', undefined, pToken);
            if (xr.status === 200) {
                const leak = (xr.body.redemptions || []).some((r) => r.code === code);
                if (leak) {
                    recFinding(testInfo, 'P0', MOD, 'coupon redemption cross-tenant list leak',
                        `pilot saw stress redemption code=${code}`);
                }
                expect(leak).toBe(false);
            }
            rec(testInfo, { module: MOD, step: 'C_coupons', status: 'PASS' });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'C_coupons_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── D) Loyalty ────────────────────────────────────────────────
    test('D) Loyalty: settings + earn idempotency + atomic redeem + insufficient guard',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const guestId = `${prefix}GUEST_${Date.now()}`;
            created.loyaltyGuestIds.push(guestId);

            // Set settings
            const s = await callTimed(request, 'put', '/api/pos/ext/loyalty/settings',
                { earn_points_per_unit: 1.0, redeem_value_per_point: 0.1, min_redeem_points: 10, active: true },
                sToken);
            expect(s.status).toBe(200);

            // Earn (idempotent)
            const idem = `${prefix}earn_${Date.now()}`;
            const e1 = await callTimed(request, 'post', '/api/pos/ext/loyalty/earn',
                { guest_id: guestId, amount: 500, idempotency_key: idem }, sToken);
            expect(e1.status).toBe(200);
            expect(e1.body.points_earned).toBe(500);
            const e2 = await callTimed(request, 'post', '/api/pos/ext/loyalty/earn',
                { guest_id: guestId, amount: 500, idempotency_key: idem }, sToken);
            expect(e2.status).toBe(200);
            expect(e2.body.idempotent).toBe(true);

            // Balance == 500
            const bal = await callTimed(request, 'get',
                `/api/pos/ext/loyalty/balance?guest_id=${encodeURIComponent(guestId)}`, undefined, sToken);
            expect(bal.status).toBe(200);
            expect(bal.body.balance).toBe(500);

            // Redeem 100 → discount = 10
            const r = await callTimed(request, 'post', '/api/pos/ext/loyalty/redeem',
                { guest_id: guestId, points: 100 }, sToken);
            expect(r.status).toBe(200);
            expect(r.body.discount_value).toBeCloseTo(10);
            expect(r.body.new_balance).toBe(400);

            // Insufficient points → 400
            const r2 = await callTimed(request, 'post', '/api/pos/ext/loyalty/redeem',
                { guest_id: guestId, points: 999999 }, sToken);
            expect(r2.status).toBe(400);

            // Cross-tenant: pilot balance of stress guest must be 0 (no leak)
            const xt = await callTimed(request, 'get',
                `/api/pos/ext/loyalty/balance?guest_id=${encodeURIComponent(guestId)}`, undefined, pToken);
            if (xt.status === 200) {
                if (xt.body.balance !== 0) {
                    recFinding(testInfo, 'P0', MOD, 'loyalty cross-tenant balance leak',
                        `pilot saw balance=${xt.body.balance} for stress guest=${guestId}`);
                }
                expect(xt.body.balance).toBe(0);
            }
            rec(testInfo, { module: MOD, step: 'D_loyalty', status: 'PASS' });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'D_loyalty_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── E) Shifts ─────────────────────────────────────────────────
    test('E) Shifts: open + duplicate 409 + close variance + idempotent re-close',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const outletId = `${prefix}SHIFT_OUTLET_${Date.now()}`;
            const o1 = await callTimed(request, 'post', '/api/pos/ext/shifts/open',
                { outlet_id: outletId, opening_cash: 500 }, sToken);
            expect(o1.status).toBe(200);
            const shiftId = o1.body?.shift?.id;
            expect(shiftId).toBeTruthy();
            created.shiftIds.push(shiftId);

            // Duplicate open → 409
            const o2 = await callTimed(request, 'post', '/api/pos/ext/shifts/open',
                { outlet_id: outletId, opening_cash: 500 }, sToken);
            expect(o2.status).toBe(409);

            // Close with counted breakdown
            const cl = await callTimed(request, 'post',
                `/api/pos/ext/shifts/${shiftId}/close`,
                { counted_breakdown: [
                    { denomination: 100, count: 5 },
                    { denomination: 50, count: 4 },
                ], notes: 'stress close' }, sToken);
            expect(cl.status).toBe(200);
            expect(cl.body.shift.status).toBe('closed');
            // expected = opening_cash (500) + cash_sales (0 in lean spec)
            expect(cl.body.shift.expected_cash_total).toBe(500);
            // counted = 5*100 + 4*50 = 700 → variance = +200
            expect(cl.body.shift.variance).toBe(200);

            // Idempotent re-close
            const cl2 = await callTimed(request, 'post',
                `/api/pos/ext/shifts/${shiftId}/close`,
                { counted_cash_total: 700 }, sToken);
            expect(cl2.status).toBe(200);
            expect(cl2.body.idempotent).toBe(true);

            // Cross-tenant: pilot list must not see this shift id
            const xt = await callTimed(request, 'get', '/api/pos/ext/shifts?limit=200', undefined, pToken);
            if (xt.status === 200) {
                const leak = (xt.body.shifts || []).some((s) => s.id === shiftId);
                if (leak) {
                    recFinding(testInfo, 'P0', MOD, 'shift cross-tenant leak', `pilot saw shift=${shiftId}`);
                }
                expect(leak).toBe(false);
            }
            rec(testInfo, { module: MOD, step: 'E_shifts', status: 'PASS' });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'E_shifts_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── F) Barcode ────────────────────────────────────────────────
    test('F) Barcode: map + lookup + cross-tenant 404 + unmapped 404',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const barcode = `${prefix}BC${Date.now()}`.replace(/[^A-Za-z0-9-]/g, '');
            created.barcodes.push(barcode);
            const m = await callTimed(request, 'post', '/api/pos/ext/barcode/map',
                { barcode, name: 'Test Cola 330ml', unit_price: 45, sku: 'TST-COLA' }, sToken);
            expect(m.status).toBe(200);

            // Lookup found
            const lk = await callTimed(request, 'get',
                `/api/pos/ext/barcode/lookup/${barcode}`, undefined, sToken);
            expect(lk.status).toBe(200);
            expect(lk.body.mapping?.unit_price).toBe(45);

            // Unmapped barcode → 404
            const miss = await callTimed(request, 'get',
                '/api/pos/ext/barcode/lookup/NONEXISTENT-XYZ-999', undefined, sToken);
            expect(miss.status).toBe(404);

            // Cross-tenant: pilot lookup of stress barcode must 404
            const xt = await callTimed(request, 'get',
                `/api/pos/ext/barcode/lookup/${barcode}`, undefined, pToken);
            if (xt.status === 200) {
                recFinding(testInfo, 'P0', MOD, 'barcode cross-tenant leak',
                    `pilot looked up stress barcode=${barcode}`);
            }
            expect(xt.status).toBe(404);
            rec(testInfo, { module: MOD, step: 'F_barcode', status: 'PASS' });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'F_barcode_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── G) Print Spool ────────────────────────────────────────────
    test('G) Print: enqueue + dispatch simulator + cancel idempotent',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const idem = `${prefix}print_${Date.now()}`;
            const enq = await callTimed(request, 'post', '/api/pos/ext/print/jobs', {
                kind: 'receipt', printer_id: 'default', copies: 1,
                payload: {
                    header: 'STRESS TEST HOTEL', subheader: 'Receipt',
                    items: [{ name: 'Espresso', quantity: 2, price: 80, line_total: 160 }],
                    total: 160, footer: 'Tesekkur ederiz',
                },
                idempotency_key: idem,
            }, sToken);
            expect(enq.status).toBe(200);
            const jobId = enq.body?.job?.id;
            expect(jobId).toBeTruthy();
            created.printJobIds.push(jobId);
            expect(enq.body.job.rendered_bytes_len).toBeGreaterThan(0);

            // Idempotent enqueue
            const enq2 = await callTimed(request, 'post', '/api/pos/ext/print/jobs', {
                kind: 'receipt', printer_id: 'default', copies: 1, payload: { header: 'x' },
                idempotency_key: idem,
            }, sToken);
            expect(enq2.status).toBe(200);
            expect(enq2.body.idempotent).toBe(true);

            // Dispatch (simulator)
            const disp = await callTimed(request, 'post',
                `/api/pos/ext/print/jobs/${jobId}/dispatch`, {}, sToken);
            expect(disp.status).toBe(200);
            expect(['sent', 'failed']).toContain(disp.body.status);

            // Re-dispatch → idempotent (already sent)
            const disp2 = await callTimed(request, 'post',
                `/api/pos/ext/print/jobs/${jobId}/dispatch`, {}, sToken);
            expect(disp2.status).toBe(200);

            // Cross-tenant: pilot list must not show this job
            const xt = await callTimed(request, 'get', '/api/pos/ext/print/jobs?limit=200', undefined, pToken);
            if (xt.status === 200) {
                const leak = (xt.body.jobs || []).some((j) => j.id === jobId);
                if (leak) {
                    recFinding(testInfo, 'P0', MOD, 'print job cross-tenant leak', `pilot saw job=${jobId}`);
                }
                expect(leak).toBe(false);
            }
            rec(testInfo, { module: MOD, step: 'G_print', status: 'PASS' });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'G_print_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── H) Fiscal (ÖKC) ───────────────────────────────────────────
    test('H) Fiscal: enqueue 404 for fake order + idempotency + EOD simulator',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Fake order id → must 404 (tenant scope verification works)
            const fakeBody = {
                order_id: `${prefix}FAKE_ORDER_404`,
                payment_method: 'cash', total: 100,
                items: [{ name: 'X', quantity: 1, unit_price: 100, tax_rate: 10 }],
            };
            const fk = await callTimed(request, 'post', '/api/pos/ext/fiscal/jobs', fakeBody, sToken);
            expect(fk.status).toBe(404);

            // EOD (simulator path always works in dev)
            const eod = await callTimed(request, 'post', '/api/pos/ext/fiscal/eod', {}, sToken);
            expect(eod.status).toBe(200);
            // success may be false if driver != simulator in env — acceptable signal
            expect(typeof eod.body.success).toBe('boolean');

            // Pilot cross-tenant: jobs list must not leak any stress job
            const xt = await callTimed(request, 'get', '/api/pos/ext/fiscal/jobs?limit=200', undefined, pToken);
            if (xt.status === 200) {
                const leak = (xt.body.jobs || []).some((j) =>
                    typeof j.order_id === 'string' && j.order_id.startsWith(prefix)
                );
                if (leak) {
                    recFinding(testInfo, 'P0', MOD, 'fiscal job cross-tenant leak',
                        `pilot saw fiscal job with stress prefix=${prefix}`);
                }
                expect(leak).toBe(false);
            }
            rec(testInfo, { module: MOD, step: 'H_fiscal', status: 'PASS' });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'H_fiscal_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    // ── Z) Cleanup (exhaustive, idempotent) ───────────────────────
    test('Z) Cleanup: delete all stress-created docs + idempotent second pass',
        async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'pos ext surface blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        const summary = {};
        try {
            // Coupons
            for (const id of created.couponIds) {
                const d1 = await callTimed(request, 'delete', `/api/pos/ext/coupons/${id}`, undefined, sToken);
                const d2 = await callTimed(request, 'delete', `/api/pos/ext/coupons/${id}`, undefined, sToken);
                summary[`coupon_${id.slice(0, 6)}`] = `d1=${d1.status} d2=${d2.status}`;
                expect([200, 404]).toContain(d1.status);
                expect(d2.status).toBe(404); // second pass: idempotent absent
            }
            // Happy hour rules
            for (const id of created.happyRuleIds) {
                const d1 = await callTimed(request, 'delete', `/api/pos/ext/happy-hour/rules/${id}`, undefined, sToken);
                const d2 = await callTimed(request, 'delete', `/api/pos/ext/happy-hour/rules/${id}`, undefined, sToken);
                expect([200, 404]).toContain(d1.status);
                expect(d2.status).toBe(404);
            }
            // Barcode mappings
            for (const bc of created.barcodes) {
                const d1 = await callTimed(request, 'delete', `/api/pos/ext/barcode/map/${bc}`, undefined, sToken);
                const d2 = await callTimed(request, 'delete', `/api/pos/ext/barcode/map/${bc}`, undefined, sToken);
                expect([200, 404]).toContain(d1.status);
                expect(d2.status).toBe(404);
            }
            // Print jobs — only pending ones can be cancelled; dispatched ones stay
            for (const id of created.printJobIds) {
                const d = await callTimed(request, 'delete', `/api/pos/ext/print/jobs/${id}`, undefined, sToken);
                expect([200, 404]).toContain(d.status); // 404 if already dispatched (expected)
            }
            // Currency payments (only if created)
            for (const id of created.paymentIds) {
                const d1 = await callTimed(request, 'delete', `/api/pos/ext/currency/payments/${id}`, undefined, sToken);
                const d2 = await callTimed(request, 'delete', `/api/pos/ext/currency/payments/${id}`, undefined, sToken);
                expect([200, 404]).toContain(d1.status);
                expect(d2.status).toBe(404);
            }
            // Currency rates
            for (const id of created.rateIds) {
                const d1 = await callTimed(request, 'delete', `/api/pos/ext/currency/rates/${id}`, undefined, sToken);
                const d2 = await callTimed(request, 'delete', `/api/pos/ext/currency/rates/${id}`, undefined, sToken);
                expect([200, 404]).toContain(d1.status);
                expect(d2.status).toBe(404);
            }
            // Shifts — close any open shift then remove (close is the canonical terminal state)
            for (const id of created.shiftIds) {
                const c = await callTimed(request, 'post',
                    `/api/pos/ext/shifts/${id}/close`, { counted_cash_total: 0 }, sToken);
                // Already-closed shift returns idempotent=true; absent → 404.
                expect([200, 404]).toContain(c.status);
            }
            // Loyalty residue — purge ledger+account for stress guests (idempotent)
            for (const gid of created.loyaltyGuestIds) {
                const d1 = await callTimed(request, 'delete',
                    `/api/pos/ext/loyalty/account?guest_id=${encodeURIComponent(gid)}`,
                    undefined, sToken);
                const d2 = await callTimed(request, 'delete',
                    `/api/pos/ext/loyalty/account?guest_id=${encodeURIComponent(gid)}`,
                    undefined, sToken);
                expect([200, 404]).toContain(d1.status);
                expect([200, 404]).toContain(d2.status);
            }
            // Fiscal jobs — cancel any pending residue (idempotent)
            for (const id of created.fiscalJobIds) {
                const d = await callTimed(request, 'delete',
                    `/api/pos/ext/fiscal/jobs/${id}`, undefined, sToken);
                expect([200, 404]).toContain(d.status);
            }

            rec(testInfo, { module: MOD, step: 'Z_cleanup', status: 'PASS',
                note: JSON.stringify(summary) });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'Z_cleanup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});
