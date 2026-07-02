import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers } from './fixtures/observers.js';
import { makeApi, safePost } from './fixtures/api.js';
import { factory, trackEntity } from './fixtures/data-factory.js';
import {
    pickAvailableRoom, createTestBooking,
    cancelBooking, todayDates,
} from './fixtures/pms-flow.js';

const M = 'reservation';

// ── E2E (regression-catching): booking-conflict-dialog wiring ──
// Task #232 — Task #227 added unit + component coverage for parseBookingConflict
// ve <BookingConflictDialog/>; bu spec üç gerçek call-site'tan en az birinin
// (RoomsTab quick-booking) gerçek 409 cevabını dialog olarak yüzeylediğini
// doğrular. Parent yanlışlıkla parseBookingConflict çağrısını düşürürse
// (regression), toast fallback'ine düşer ve dialog görünmez → spec FAIL.
//
// Akış:
//   1. Pilot'ta uzak tarihli boş oda seç, baseline booking oluştur (track).
//   2. API ile 2. POST /api/pms/quick-booking → aynı oda+aynı pencere
//      → 409 + structured detail invariant (parser ön koşulu).
//   3. UI: /app/pms#rooms → quick-res-btn-<room> → form aynı pencereyi
//      doldurur → submit → [data-testid="booking-conflict-dialog"] görünür.
//   4. Baseline booking 20-recap dışında bu spec'te de cancel edilir
//      (defense-in-depth; registry'e completed işaretlenir).
test.describe('Scope 3 — Booking conflict dialog (end-to-end wiring)', () => {
    test('E2E: Quick-booking 409 surfaces BookingConflictDialog (RoomsTab)', async ({ baseURL, page }, testInfo) => {
        const api = await makeApi(baseURL);
        const obs = attachObservers(page);
        const dates = todayDates();
        rec(testInfo, { module: M, scope: 3, step: 'Hedef tarih aralığı', status: PASS, note: `${dates.check_in}→${dates.check_out}` });

        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi (conflict)', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        const roomNumber = pick.room.room_number;
        rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi (conflict)', status: PASS, note: `room=${roomNumber || pick.room.id}` });

        // 1) Baseline booking — bu, ikinci girişimi 409'a zorlayacak.
        const baselineGuest = factory.guestName();
        const baseline = await createTestBooking(api, {
            roomId: pick.room.id, guestName: baselineGuest,
            check_in: dates.check_in, check_out: dates.check_out,
            totalAmount: 100,
        });
        rec(testInfo, {
            module: M, scope: 3, step: 'POST /api/pms/quick-booking (baseline)',
            status: baseline.ok ? PASS : FAIL,
            endpoint: '/api/pms/quick-booking', http: baseline.status,
            note: baseline.ok ? `id=${baseline.bookingId}` : (baseline.reason || ''),
        });
        expect(baseline.ok, `Baseline booking create FAILED: ${baseline.reason || baseline.status}`).toBe(true);
        trackEntity({
            kind: 'booking', id: baseline.bookingId, label: baselineGuest,
            cleanup: 'pending', endpoint: '/api/pms-core/cancel',
        });

        // 2) API-level invariant: 2. POST aynı oda+pencere → 409 + structured
        // detail. Bu, parseBookingConflict'in ön koşuludur; backend sözleşmesi
        // bozulursa dialog hiç tetiklenemez.
        const collide = await safePost(api, '/api/pms/quick-booking', {
            guest_name: factory.guestName(),
            room_id: pick.room.id,
            check_in: `${dates.check_in}T14:00:00+00:00`,
            check_out: `${dates.check_out}T11:00:00+00:00`,
            total_amount: 100,
        }, { headers: { 'Idempotency-Key': `collide-${Date.now()}` } });
        const detail = collide.json?.detail;
        const detailIsObj = detail && typeof detail === 'object';
        const hasStructured = detailIsObj && (
            detail.conflict_type || detail.conflicting_booking_id || detail.conflict_window
        );
        const is409 = collide.status === 409;
        rec(testInfo, {
            module: M, scope: 3, step: 'POST /api/pms/quick-booking (collision) → 409 structured',
            status: is409 && hasStructured ? PASS : FAIL,
            endpoint: '/api/pms/quick-booking', http: collide.status,
            note: is409 ? `detail_keys=${detailIsObj ? Object.keys(detail).join(',') : typeof detail}` : (collide.body?.slice(0, 200) || ''),
        });
        expect(collide.status, `Expected 409 on overlapping booking, got ${collide.status}: ${collide.body?.slice(0, 200) || ''}`).toBe(409);
        expect(hasStructured, `Conflict response missing structured detail (parseBookingConflict pre-condition broken): ${JSON.stringify(detail).slice(0, 200)}`).toBeTruthy();

        // Baseline'i iptal et ki oda tekrar "available" görünsün ve quick-res butonu çıksın.
        await cancelBooking(api, baseline.bookingId, 'E2E conflict test (reset for UI step)');

        // 3) UI: gerçek RoomsTab quick-booking yolunu sür.
        let dialogVisible = false;
        let baseline2Id = null;
        try {
            const nav = await page.goto('/app/pms#rooms', { waitUntil: 'networkidle', timeout: 30_000 });
            rec(testInfo, { module: M, scope: 3, step: 'Navigate /app/pms#rooms', status: nav?.ok() ? PASS : REVIEW, endpoint: '/app/pms', http: nav?.status() });

            // Rooms tab tenant config'inde kapatılmış olabilir (pms.rooms=false).
            const roomsTab = page.locator('[data-testid="tab-rooms"]').first();
            if ((await roomsTab.count()) === 0) {
                rec(testInfo, { module: M, scope: 3, step: 'tab-rooms görünür', status: SKIP, note: 'rooms_tab_disabled' });
                // Cleanup baseline before skip — 21-* spec 20-recap'ten sonra
                // koştuğu için recap fallback'i bu run'da etmez; pilot
                // veri sızıntısı bırakmamak için burada cancel et.
                const c = await cancelBooking(api, baseline.bookingId, 'E2E conflict-dialog spec cleanup (skip path)').catch(() => ({ ok: false }));
                trackEntity({
                    kind: 'booking', id: baseline.bookingId, label: `${baselineGuest} (cancelled)`,
                    cleanup: c?.ok ? 'completed' : 'pending', endpoint: '/api/pms-core/cancel',
                });
                await api.dispose();
                test.skip(true, 'Pilot tenant rooms tab\'ı görünür değil');
                return;
            }
            await roomsTab.click({ timeout: 5_000 }).catch(() => {});
            await page.waitForTimeout(500);

            // Quick-res tetikleyici: kart bazında oda numarasına göre testid.
            const quickBtn = page.locator(`[data-testid="quick-res-btn-${roomNumber}"]`).first();
            if ((await quickBtn.count()) === 0) {
                // Sanal liste / paginate ihtimaline karşı scroll dene.
                await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)).catch(() => {});
                await page.waitForTimeout(400);
            }
            await quickBtn.waitFor({ state: 'visible', timeout: 8_000 });
            await quickBtn.click();

            // Form alanlarını doldur (guest_name search input quickResForm.guest_name'i de set eder).
            const guestInput = page.locator('[data-testid="quick-res-guest-search"]').first();
            await guestInput.waitFor({ state: 'visible', timeout: 5_000 });
            await guestInput.fill(factory.guestName());
            // Açılır listeyi kapat (dropdown submit'i engelleyebilir).
            await page.keyboard.press('Escape').catch(() => {});

            await page.locator('[data-testid="quick-res-check-in"]').first().fill(dates.check_in);
            await page.locator('[data-testid="quick-res-check-out"]').first().fill(dates.check_out);
            await page.locator('[data-testid="quick-res-total-amount"]').first().fill('100');

            // Form dolduruldu, submit etmeden ÖNCE aynı odaya arkadan rezervasyon çak
            // (Concurrent booking simülasyonu)
            const baseline2 = await createTestBooking(api, {
                roomId: pick.room.id, guestName: baselineGuest + ' 2',
                check_in: dates.check_in, check_out: dates.check_out,
                totalAmount: 100,
            });
            baseline2Id = baseline2.bookingId;
            trackEntity({
                kind: 'booking', id: baseline2Id, label: baselineGuest + ' 2',
                cleanup: 'pending', endpoint: '/api/pms-core/cancel',
            });

            await page.locator('[data-testid="quick-res-submit"]').first().click();

            // ASIL ASSERTION: dialog görünmeli. Regression: parent
            // parseBookingConflict çağrısını düşürürse burası FAIL.
            const dialog = page.locator('[data-testid="booking-conflict-dialog"]').first();
            await dialog.waitFor({ state: 'visible', timeout: 10_000 });
            dialogVisible = await dialog.isVisible();
        } catch (e) {
            rec(testInfo, { module: M, scope: 3, step: 'UI conflict dialog flow', status: FAIL, note: `error=${e.message?.slice(0, 200)}` });
            // Cleanup baseline before failing.
            await cancelBooking(api, baseline.bookingId, 'E2E conflict-dialog spec cleanup (on error)').catch(() => {});
            trackEntity({
                kind: 'booking', id: baseline.bookingId, label: `${baselineGuest} (cancelled)`,
                cleanup: 'completed', endpoint: '/api/pms-core/cancel',
            });
            await api.dispose();
            throw e;
        }

        rec(testInfo, {
            module: M, scope: 3, step: '[data-testid="booking-conflict-dialog"] görünür',
            status: dialogVisible ? PASS : FAIL,
            note: dialogVisible ? 'visible' : 'not_visible',
        });
        expect(dialogVisible, 'BookingConflictDialog quick-booking 409\'unda yüzeylenmedi — parent parseBookingConflict bağlantısı bozuk olabilir').toBe(true);

        // Console errors (yumuşak sinyal).
        rec(testInfo, { module: M, scope: 3, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });

        // 4) Defense-in-depth cleanup — 20-recap yine kontrol eder.
        const cancelled = await cancelBooking(api, baseline.bookingId, 'E2E conflict-dialog spec cleanup');
        const cancelOk = cancelled.ok && cancelled.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 3, step: 'POST /api/pms-core/cancel (baseline cleanup)',
            status: cancelOk ? PASS : REVIEW,
            endpoint: '/api/pms-core/cancel', http: cancelled.status,
            note: cancelOk ? 'cancelled' : (cancelled.body?.slice(0, 160) || ''),
        });
        trackEntity({
            kind: 'booking', id: baseline.bookingId, label: `${baselineGuest} (cancelled)`,
            cleanup: cancelOk ? 'completed' : 'pending', endpoint: '/api/pms-core/cancel',
        });

        await api.dispose();
    });
});
