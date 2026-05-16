import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi } from './fixtures/api.js';
import { factory, trackEntity } from './fixtures/data-factory.js';
import {
    pickNAvailableRooms, createTestBooking, checkInBooking, checkoutBooking,
    roomMove, todayDates,
} from './fixtures/pms-flow.js';

const M = 'checkin-checkout';

test.describe('Scope 4 — Check-in / Check-out', () => {
    test('Front Desk / PMS sayfası check-in akışı keşfi', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/pms', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 4, step: 'PMS navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/pms', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 4, step: 'PMS içerik', status: insp.empty ? REVIEW : PASS, note: `len=${insp.lengthChars}` });

        const ciBtn = await page.locator('button:has-text("Check-in"), button:has-text("Giriş Yap")').count();
        const coBtn = await page.locator('button:has-text("Check-out"), button:has-text("Çıkış Yap")').count();
        rec(testInfo, { module: M, scope: 4, step: 'Check-in butonları görünür', status: ciBtn > 0 ? PASS : REVIEW, note: `count=${ciBtn}` });
        rec(testInfo, { module: M, scope: 4, step: 'Check-out butonları görünür', status: coBtn > 0 ? PASS : REVIEW, note: `count=${coBtn}` });
        rec(testInfo, { module: M, scope: 4, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });

    // ── E2E (regression-catching): Create → check-in → assign-room (room-move) → check-out ──
    // Hard-fails:
    //   1. Booking create 2xx + id
    //   2. Check-in POST success
    //   3. Room-move (assign-room transition) POST success — room A → room B
    //   4. Check-out POST success
    // Pilot pre-condition (2 müsait oda) yoksa SKIP. trackEntity ile recap'e
    // güvenlik ağı bırakılır; check-out tamamlanırsa terminal-state → cleanup gerekmez.
    test('E2E: Create → check-in → assign room → check-out', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        const dates = todayDates(1);
        rec(testInfo, { module: M, scope: 4, step: 'Hedef tarih (today)', status: PASS, note: `${dates.check_in}→${dates.check_out}` });

        const pick = await pickNAvailableRooms(api, dates, 2);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 4, step: 'İki müsait oda (kaynak+hedef)', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        const [roomA, roomB] = pick.rooms;
        rec(testInfo, { module: M, scope: 4, step: 'Oda çifti', status: PASS, note: `A=${roomA.room_number || roomA.id} B=${roomB.room_number || roomB.id}` });

        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: roomA.id, guestName,
            check_in: dates.check_in, check_out: dates.check_out,
            totalAmount: 1,
        });
        rec(testInfo, { module: M, scope: 4, step: 'POST /api/pms/quick-booking', status: created.ok ? PASS : FAIL, endpoint: '/api/pms/quick-booking', http: created.status, note: created.ok ? `id=${created.bookingId} room=${roomA.id}` : (created.reason || '') });
        expect(created.ok, `Booking create FAILED: ${created.reason || created.status}`).toBe(true);
        expect(created.bookingId, 'No booking id returned').toBeTruthy();
        trackEntity({
            kind: 'booking', id: created.bookingId, label: guestName,
            cleanup: 'pending', endpoint: '/api/pms-core/cancel',
        });

        // Hard-assert: check-in
        const ci = await checkInBooking(api, created.bookingId, 'E2E pilot check-in');
        const ciOk = ci.ok && ci.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 4, step: 'POST /api/pms-core/check-in',
            status: ciOk ? PASS : FAIL,
            endpoint: '/api/pms-core/check-in', http: ci.status,
            note: ciOk ? 'checked_in' : (ci.body?.slice(0, 200) || ''),
        });
        expect(ciOk, `Check-in FAILED: HTTP ${ci.status} ${ci.body?.slice(0, 200) || ''}`).toBe(true);

        // Hard-assert: assign-room (room-move) — checked_in misafiri room A → room B'ye taşı.
        // Bu front_desk.room_move endpoint'i assign-room transition'ını exercise eder
        // (lock release, availability güncelleme, status reconcile dahil).
        const mv = await roomMove(api, created.bookingId, roomB.id, 'E2E assign-room');
        const mvOk = mv.ok && mv.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 4, step: 'POST /api/pms-core/room-move (assign room)',
            status: mvOk ? PASS : FAIL,
            endpoint: '/api/pms-core/room-move', http: mv.status,
            note: mvOk ? `assigned→${roomB.id}` : (mv.body?.slice(0, 200) || ''),
        });
        expect(mvOk, `Room-move (assign) FAILED: HTTP ${mv.status} ${mv.body?.slice(0, 200) || ''}`).toBe(true);

        // Hard-assert: checkout
        const co = await checkoutBooking(api, created.bookingId, true);
        const coOk = co.ok && co.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 4, step: 'POST /api/pms-core/checkout (force)',
            status: coOk ? PASS : FAIL,
            endpoint: '/api/pms-core/checkout', http: co.status,
            note: coOk ? 'checked_out' : (co.body?.slice(0, 200) || ''),
        });
        expect(coOk, `Checkout FAILED: HTTP ${co.status} ${co.body?.slice(0, 200) || ''}`).toBe(true);
        trackEntity({
            kind: 'booking', id: created.bookingId, label: `${guestName} (checked_out)`,
            cleanup: 'completed', endpoint: '/api/pms-core/checkout',
        });
        await api.dispose();
    });
});
