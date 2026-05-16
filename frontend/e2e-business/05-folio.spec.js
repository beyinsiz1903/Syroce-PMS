import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';
import { factory, trackEntity } from './fixtures/data-factory.js';
import {
    pickAvailableRoom, createTestBooking, addExtraCharge, voidCharge,
    recordPayment, voidPayment, postRefund,
    getBookingDetail, cancelBooking, farFutureDates,
} from './fixtures/pms-flow.js';

const M = 'folio';

function readBalance(detail) {
    const summary = detail?.summary || detail?.totals || detail || {};
    const cand = [summary.balance, summary.total_balance, summary.balance_total, summary.total_charges, summary.total];
    for (const v of cand) {
        const n = typeof v === 'number' ? v : parseFloat(v);
        if (!Number.isNaN(n)) return n;
    }
    return null;
}

test.describe('Scope 5 — Folio', () => {
    test('Folio ana sayfa + masraf/ödeme/refund/void buton keşfi', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/folio', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 5, step: 'Folio navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/folio', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 5, step: 'Folio içerik', status: insp.empty || insp.has500 ? REVIEW : PASS });

        const probes = [
            ['Masraf Ekle', 'Masraf ekle butonu'],
            ['Ödeme', 'Ödeme alanı/butonu'],
            ['Refund', 'Refund butonu'],
            ['Void', 'Void butonu'],
            ['Split', 'Split (folio bölme)'],
            ['Merge', 'Merge (folio birleştirme)'],
        ];
        for (const [text, label] of probes) {
            const c = await page.locator(`text=/${text}/i`).count();
            rec(testInfo, { module: M, scope: 5, step: `${label} mevcut`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }
        for (const tab of ['folio-tab-timeline', 'folio-tab-tax', 'folio-tab-splits', 'folio-tab-voids']) {
            const c = await page.locator(`[data-testid="${tab}"]`).count();
            rec(testInfo, { module: M, scope: 5, step: `Tab ${tab}`, status: c > 0 ? PASS : REVIEW, note: `count=${c}` });
        }
        rec(testInfo, { module: M, scope: 5, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });

    test('Folio API discovery (read-only)', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        for (const ep of ['/api/pms-core/folio/list?limit=5', '/api/frontdesk/folio/summary']) {
            const r = await safeGet(api, ep);
            rec(testInfo, { module: M, scope: 5, step: `GET ${ep}`, status: r.status < 500 ? PASS : REVIEW, endpoint: ep, http: r.status });
        }
        await api.dispose();
    });

    // ── E2E (regression-catching): Booking → add charge → verify total ↑ → void → total ↓ ──
    // Hard-fails:
    //   1. Booking create 2xx
    //   2. add-extra-charge 2xx + charge.id döner
    //   3. full-detail balance, eklenen tutardan en az charge kadar büyür (delta)
    //   4. void-charge 2xx success
    //   5. void sonrası balance düşer (delta geri çıkar)
    //   6. Booking cancel cleanup 2xx
    // baseline balance okunamazsa delta-check SKIP olur; ana akış hard-fail kalır.
    test('E2E: Folio charge add → verify total → reverse (void)', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        const dates = farFutureDates();
        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 5, step: 'Müsait oda', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }

        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: pick.room.id, guestName,
            check_in: dates.check_in, check_out: dates.check_out,
            totalAmount: 100,
        });
        rec(testInfo, { module: M, scope: 5, step: 'Setup: booking yarat', status: created.ok ? PASS : FAIL, http: created.status, note: created.ok ? `id=${created.bookingId}` : created.reason });
        expect(created.ok, `Booking create FAILED: ${created.reason}`).toBe(true);
        trackEntity({ kind: 'booking', id: created.bookingId, label: guestName, cleanup: 'pending', endpoint: '/api/pms-core/cancel' });

        // Baseline balance (best-effort; bazı pilot tenant'larda summary shape farklı → null tolere)
        const before = await getBookingDetail(api, created.bookingId);
        const balBefore = before.ok ? readBalance(before.json) : null;
        rec(testInfo, { module: M, scope: 5, step: 'Baseline full-detail', status: before.ok ? PASS : REVIEW, http: before.status, note: `balance=${balBefore}` });

        // Hard-assert: add-extra-charge
        const chargeAmount = 42.5;
        const chargeLabel = factory.folioLabel();
        const add = await addExtraCharge(api, created.bookingId, {
            description: chargeLabel, amount: chargeAmount, category: 'other', quantity: 1,
        });
        const chargeId = add.json?.charge?.id;
        const addOk = add.ok && add.json?.success !== false && !!chargeId;
        rec(testInfo, {
            module: M, scope: 5, step: 'POST add-extra-charge',
            status: addOk ? PASS : FAIL,
            endpoint: `/api/pms/reservations/${created.bookingId}/add-extra-charge`, http: add.status,
            note: addOk ? `charge_id=${chargeId}` : (add.body?.slice(0, 200) || ''),
        });
        expect(addOk, `add-extra-charge FAILED: HTTP ${add.status} ${add.body?.slice(0, 200) || ''}`).toBe(true);
        expect(chargeId, 'add-extra-charge response missing charge.id').toBeTruthy();
        trackEntity({ kind: 'extra_charge', id: chargeId, label: chargeLabel, cleanup: 'pending', endpoint: '/api/pms-core/folio/void-charge' });

        // Hard-assert: total arttı (balance shape okunabildiyse delta + ≥ chargeAmount)
        const after = await getBookingDetail(api, created.bookingId);
        const balAfter = after.ok ? readBalance(after.json) : null;
        if (balBefore != null && balAfter != null) {
            rec(testInfo, {
                module: M, scope: 5, step: 'Total arttı doğrulaması',
                status: balAfter >= balBefore + chargeAmount - 0.01 ? PASS : FAIL,
                http: after.status, note: `before=${balBefore} after=${balAfter} expected_delta=${chargeAmount}`,
            });
            expect(balAfter).toBeGreaterThanOrEqual(balBefore + chargeAmount - 0.01);
        } else {
            rec(testInfo, { module: M, scope: 5, step: 'Total arttı doğrulaması', status: SKIP, note: `balance shape okunamadı before=${balBefore} after=${balAfter}` });
        }

        // Hard-assert: void
        const voided = await voidCharge(api, chargeId, 'E2E reverse');
        const vOk = voided.ok && voided.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 5, step: 'POST folio/void-charge',
            status: vOk ? PASS : FAIL,
            endpoint: '/api/pms-core/folio/void-charge', http: voided.status,
            note: vOk ? 'voided' : (voided.body?.slice(0, 200) || ''),
        });
        expect(vOk, `void-charge FAILED: HTTP ${voided.status} ${voided.body?.slice(0, 200) || ''}`).toBe(true);
        trackEntity({ kind: 'extra_charge', id: chargeId, label: `${chargeLabel} (voided)`, cleanup: 'completed', endpoint: '/api/pms-core/folio/void-charge' });

        // Hard-assert: void sonrası total düştü (yine balance shape varsa)
        const post = await getBookingDetail(api, created.bookingId);
        const balPost = post.ok ? readBalance(post.json) : null;
        if (balPost != null && balAfter != null) {
            rec(testInfo, {
                module: M, scope: 5, step: 'Void sonrası total düştü',
                status: balPost <= balAfter - chargeAmount + 0.01 ? PASS : FAIL,
                http: post.status, note: `after=${balAfter} post_void=${balPost}`,
            });
            expect(balPost).toBeLessThanOrEqual(balAfter - chargeAmount + 0.01);
        } else {
            rec(testInfo, { module: M, scope: 5, step: 'Void sonrası total düştü', status: SKIP, note: `balance shape okunamadı after=${balAfter} post=${balPost}` });
        }

        // Cleanup — cancel booking (hard-assert)
        const cleanup = await cancelBooking(api, created.bookingId, 'E2E folio cleanup');
        const cleanOk = cleanup.ok && cleanup.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 5, step: 'Cleanup cancel booking',
            status: cleanOk ? PASS : FAIL,
            endpoint: '/api/pms-core/cancel', http: cleanup.status,
            note: cleanOk ? 'cancelled' : (cleanup.body?.slice(0, 160) || ''),
        });
        expect(cleanOk, `Cleanup cancel FAILED: HTTP ${cleanup.status}`).toBe(true);
        trackEntity({ kind: 'booking', id: created.bookingId, label: `${guestName} (cancelled)`, cleanup: 'completed', endpoint: '/api/pms-core/cancel' });

        await api.dispose();
    });

    // ── E2E (regression-catching): Booking → record-payment (cash) → balance ↓ → void-payment → balance ↑ ──
    // Hard-fails:
    //   1. Booking create 2xx
    //   2. record-payment 2xx + payment.id döner
    //   3. full-detail balance, ödeme miktarı kadar düşer (delta)
    //   4. void-payment 2xx success
    //   5. void sonrası balance geri yükselir (delta geri biner)
    //   6. Booking cancel cleanup 2xx
    // Real gateway tetiklenmez — method='cash' (PCI sınırı dışı, internal ledger only).
    // baseline balance okunamazsa delta-check'ler SKIP olur; ana akış hard-fail kalır.
    test('E2E: Folio record-payment (cash) → verify balance → reverse (void-payment)', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        const dates = farFutureDates();
        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 5, step: 'Müsait oda (payment)', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }

        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: pick.room.id, guestName,
            check_in: dates.check_in, check_out: dates.check_out,
            totalAmount: 200,
        });
        rec(testInfo, { module: M, scope: 5, step: 'Setup: booking yarat (payment)', status: created.ok ? PASS : FAIL, http: created.status, note: created.ok ? `id=${created.bookingId}` : created.reason });
        expect(created.ok, `Booking create FAILED: ${created.reason}`).toBe(true);
        trackEntity({ kind: 'booking', id: created.bookingId, label: guestName, cleanup: 'pending', endpoint: '/api/pms-core/cancel' });

        // Baseline balance
        const before = await getBookingDetail(api, created.bookingId);
        const balBefore = before.ok ? readBalance(before.json) : null;
        rec(testInfo, { module: M, scope: 5, step: 'Baseline full-detail (payment)', status: before.ok ? PASS : REVIEW, http: before.status, note: `balance=${balBefore}` });

        // Hard-assert: record-payment (cash → no gateway)
        const payAmount = 55.25;
        const payLabel = factory.folioLabel();
        const paid = await recordPayment(api, created.bookingId, {
            amount: payAmount, method: 'cash', payment_type: 'interim', reference: payLabel, notes: 'E2E cash payment',
        });
        const paymentId = paid.json?.payment?.id;
        const payOk = paid.ok && paid.json?.success !== false && !!paymentId;
        rec(testInfo, {
            module: M, scope: 5, step: 'POST record-payment (cash)',
            status: payOk ? PASS : FAIL,
            endpoint: `/api/pms/reservations/${created.bookingId}/record-payment`, http: paid.status,
            note: payOk ? `payment_id=${paymentId} method=cash` : (paid.body?.slice(0, 200) || ''),
        });
        expect(payOk, `record-payment FAILED: HTTP ${paid.status} ${paid.body?.slice(0, 200) || ''}`).toBe(true);
        expect(paymentId, 'record-payment response missing payment.id').toBeTruthy();
        trackEntity({ kind: 'payment', id: paymentId, label: payLabel, cleanup: 'pending', endpoint: '/api/pms-core/folio/void-payment' });

        // Hard-assert: balance düştü (payment shape okunabildiyse delta − ≈ payAmount)
        const after = await getBookingDetail(api, created.bookingId);
        const balAfter = after.ok ? readBalance(after.json) : null;
        if (balBefore != null && balAfter != null) {
            rec(testInfo, {
                module: M, scope: 5, step: 'Balance ödeme sonrası düştü',
                status: balAfter <= balBefore - payAmount + 0.01 ? PASS : FAIL,
                http: after.status, note: `before=${balBefore} after=${balAfter} expected_delta=-${payAmount}`,
            });
            expect(balAfter).toBeLessThanOrEqual(balBefore - payAmount + 0.01);
        } else {
            rec(testInfo, { module: M, scope: 5, step: 'Balance ödeme sonrası düştü', status: SKIP, note: `balance shape okunamadı before=${balBefore} after=${balAfter}` });
        }

        // Hard-assert: void-payment
        const voided = await voidPayment(api, paymentId, 'E2E payment reverse');
        const vOk = voided.ok && voided.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 5, step: 'POST folio/void-payment',
            status: vOk ? PASS : FAIL,
            endpoint: '/api/pms-core/folio/void-payment', http: voided.status,
            note: vOk ? 'payment voided' : (voided.body?.slice(0, 200) || ''),
        });
        expect(vOk, `void-payment FAILED: HTTP ${voided.status} ${voided.body?.slice(0, 200) || ''}`).toBe(true);
        trackEntity({ kind: 'payment', id: paymentId, label: `${payLabel} (voided)`, cleanup: 'completed', endpoint: '/api/pms-core/folio/void-payment' });

        // Hard-assert: void sonrası balance geri yükseldi
        const post = await getBookingDetail(api, created.bookingId);
        const balPost = post.ok ? readBalance(post.json) : null;
        if (balPost != null && balAfter != null) {
            rec(testInfo, {
                module: M, scope: 5, step: 'Void-payment sonrası balance geri yükseldi',
                status: balPost >= balAfter + payAmount - 0.01 ? PASS : FAIL,
                http: post.status, note: `after=${balAfter} post_void=${balPost}`,
            });
            expect(balPost).toBeGreaterThanOrEqual(balAfter + payAmount - 0.01);
        } else {
            rec(testInfo, { module: M, scope: 5, step: 'Void-payment sonrası balance geri yükseldi', status: SKIP, note: `balance shape okunamadı after=${balAfter} post=${balPost}` });
        }

        // Cleanup — cancel booking (hard-assert)
        const cleanup = await cancelBooking(api, created.bookingId, 'E2E folio payment cleanup');
        const cleanOk = cleanup.ok && cleanup.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 5, step: 'Cleanup cancel booking (payment)',
            status: cleanOk ? PASS : FAIL,
            endpoint: '/api/pms-core/cancel', http: cleanup.status,
            note: cleanOk ? 'cancelled' : (cleanup.body?.slice(0, 160) || ''),
        });
        expect(cleanOk, `Cleanup cancel FAILED: HTTP ${cleanup.status}`).toBe(true);
        trackEntity({ kind: 'booking', id: created.bookingId, label: `${guestName} (cancelled)`, cleanup: 'completed', endpoint: '/api/pms-core/cancel' });

        await api.dispose();
    });

    // ── E2E (regression-catching): Booking → record-payment → /folio/refund (partial) → balance ↑ ──
    // Hard-fails:
    //   1. Booking create 2xx
    //   2. record-payment 2xx (cash → no gateway) + payment.id döner
    //   3. full-detail folios[0].id resolve edilebilir (refund hedef folio)
    //   4. /folio/refund 2xx + refund.id döner, response.refund.amount negatif
    //   5. balance refund tutarı kadar geri yükselir (delta ≈ +refundAmount)
    //   6. Booking cancel cleanup 2xx
    // Refund void-payment'tan farklı: ayrı kayıt — closed-folio refund guard'ı
    // tetiklenmemeli (folio status='open' aşamasında, partial amount). baseline
    // balance okunamazsa delta-check'ler SKIP olur; ana akış hard-fail kalır.
    test('E2E: Folio /folio/refund partial (cash) → verify balance restored', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        const dates = farFutureDates();
        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 5, step: 'Müsait oda (refund)', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }

        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: pick.room.id, guestName,
            check_in: dates.check_in, check_out: dates.check_out,
            totalAmount: 300,
        });
        rec(testInfo, { module: M, scope: 5, step: 'Setup: booking yarat (refund)', status: created.ok ? PASS : FAIL, http: created.status, note: created.ok ? `id=${created.bookingId}` : created.reason });
        expect(created.ok, `Booking create FAILED: ${created.reason}`).toBe(true);
        trackEntity({ kind: 'booking', id: created.bookingId, label: guestName, cleanup: 'pending', endpoint: '/api/pms-core/cancel' });

        // Ödeme bas — refund öncesi balance düşmüş olmalı ki refund anlamlı bir delta üretsin.
        const payAmount = 100;
        const payLabel = factory.folioLabel();
        const paid = await recordPayment(api, created.bookingId, {
            amount: payAmount, method: 'cash', payment_type: 'interim', reference: payLabel, notes: 'E2E pre-refund cash payment',
        });
        const paymentId = paid.json?.payment?.id;
        const payOk = paid.ok && paid.json?.success !== false && !!paymentId;
        rec(testInfo, {
            module: M, scope: 5, step: 'POST record-payment (pre-refund)',
            status: payOk ? PASS : FAIL,
            endpoint: `/api/pms/reservations/${created.bookingId}/record-payment`, http: paid.status,
            note: payOk ? `payment_id=${paymentId}` : (paid.body?.slice(0, 200) || ''),
        });
        expect(payOk, `record-payment FAILED: HTTP ${paid.status} ${paid.body?.slice(0, 200) || ''}`).toBe(true);
        trackEntity({ kind: 'payment', id: paymentId, label: payLabel, cleanup: 'pending', endpoint: '/api/pms-core/folio/void-payment' });

        // Refund hedef folio_id full-detail.folios[0].id'dan çözümlenir.
        // reservation_detail.get_reservation_full_detail booking_id + tenant_id filtreli folios listesi döner.
        const beforeRefund = await getBookingDetail(api, created.bookingId);
        const folios = Array.isArray(beforeRefund.json?.folios) ? beforeRefund.json.folios : [];
        const folioId = folios.find((f) => f && (f.status === 'open' || !f.status))?.id || folios[0]?.id;
        const balPreRefund = beforeRefund.ok ? readBalance(beforeRefund.json) : null;
        rec(testInfo, {
            module: M, scope: 5, step: 'Resolve folio_id (full-detail.folios[])',
            status: folioId ? PASS : FAIL, http: beforeRefund.status,
            note: folioId ? `folio_id=${folioId} balance=${balPreRefund}` : `folios.length=${folios.length}`,
        });
        expect(folioId, 'full-detail did not expose folios[].id for refund').toBeTruthy();

        // Hard-assert: /folio/refund (cash, partial)
        const refundAmount = 40;
        const refunded = await postRefund(api, {
            folioId, bookingId: created.bookingId, amount: refundAmount, reason: 'E2E partial cash refund', method: 'cash',
        });
        const refundId = refunded.json?.refund?.id;
        const refundDocAmount = refunded.json?.refund?.amount;
        const refOk = refunded.ok && refunded.json?.success !== false && !!refundId && typeof refundDocAmount === 'number' && refundDocAmount < 0;
        rec(testInfo, {
            module: M, scope: 5, step: 'POST folio/refund (cash, partial)',
            status: refOk ? PASS : FAIL,
            endpoint: '/api/pms-core/folio/refund', http: refunded.status,
            note: refOk ? `refund_id=${refundId} amount=${refundDocAmount}` : (refunded.body?.slice(0, 200) || ''),
        });
        expect(refOk, `/folio/refund FAILED: HTTP ${refunded.status} ${refunded.body?.slice(0, 200) || ''}`).toBe(true);
        // Refund kaydı ayrı bir payments rec'i; void-payment endpoint'i ile geri alınmaz.
        // Booking cancel cleanup yetiyor (folio kapanır), trackEntity sadece audit/recap için.
        trackEntity({ kind: 'refund', id: refundId, label: `refund ${refundAmount} (${created.bookingId})`, cleanup: 'completed', endpoint: '/api/pms-core/folio/refund' });

        // Hard-assert: balance refund kadar yükseldi
        const post = await getBookingDetail(api, created.bookingId);
        const balPost = post.ok ? readBalance(post.json) : null;
        if (balPreRefund != null && balPost != null) {
            rec(testInfo, {
                module: M, scope: 5, step: 'Refund sonrası balance yükseldi',
                status: balPost >= balPreRefund + refundAmount - 0.01 ? PASS : FAIL,
                http: post.status, note: `pre_refund=${balPreRefund} post_refund=${balPost} expected_delta=+${refundAmount}`,
            });
            expect(balPost).toBeGreaterThanOrEqual(balPreRefund + refundAmount - 0.01);
        } else {
            rec(testInfo, { module: M, scope: 5, step: 'Refund sonrası balance yükseldi', status: SKIP, note: `balance shape okunamadı pre=${balPreRefund} post=${balPost}` });
        }

        // Cleanup — cancel booking (hard-assert)
        const cleanup = await cancelBooking(api, created.bookingId, 'E2E folio refund cleanup');
        const cleanOk = cleanup.ok && cleanup.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 5, step: 'Cleanup cancel booking (refund)',
            status: cleanOk ? PASS : FAIL,
            endpoint: '/api/pms-core/cancel', http: cleanup.status,
            note: cleanOk ? 'cancelled' : (cleanup.body?.slice(0, 160) || ''),
        });
        expect(cleanOk, `Cleanup cancel FAILED: HTTP ${cleanup.status}`).toBe(true);
        trackEntity({ kind: 'booking', id: created.bookingId, label: `${guestName} (cancelled)`, cleanup: 'completed', endpoint: '/api/pms-core/cancel' });
        trackEntity({ kind: 'payment', id: paymentId, label: `${payLabel} (folio cancelled)`, cleanup: 'completed', endpoint: '/api/pms-core/cancel' });

        await api.dispose();
    });
});
