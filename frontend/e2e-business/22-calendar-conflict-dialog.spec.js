import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers } from './fixtures/observers.js';
import { makeApi, safePost } from './fixtures/api.js';
import { factory, trackEntity } from './fixtures/data-factory.js';
import {
    pickAvailableRoom, createTestBooking, cancelBooking, farFutureDates,
} from './fixtures/pms-flow.js';

const M = 'reservation';

// ── E2E (regression-catching): booking-conflict-dialog wiring — 2. call-site ──
// Task #240 — Task #232 (spec 21) RoomsTab quick-booking call-site'ı
// kapsadı. ReservationCalendar'ın create yolu (empty-cell click →
// NewBookingDialog → handleCreateBooking → parseBookingConflict,
// ReservationCalendar.jsx ~line 410) hâlâ end-to-end kapsam dışıydı.
// Parent yanlışlıkla parseBookingConflict çağrısını düşürürse component
// testleri bunu yakalamaz; sadece bu spec regression sinyali verir.
//
// NOT (terminoloji): Task title "dragging on the calendar" diyor; ancak
// ReservationCalendar.jsx kodunda drag-to-create özelliği YOK. Cell'lerde
// sadece `onClick` (empty-cell create) + `onDragOver/onDrop` (mevcut bir
// booking-bar'ı taşımak için) handler'ı var; booking bar olmadan
// `handleDrop` `if (!draggingBooking) return;` ile erken çıkar. Tek
// create call-site task'ın da işaret ettiği `handleCreateBooking`
// (line 410); bu spec o akışı sürer.
//
// Akış:
//   1. Pilot'ta uzak tarihli boş oda seç, API ile baseline booking oluştur (track).
//   2. API ile 2. POST /api/pms/bookings → aynı oda+aynı pencere → 409 +
//      structured detail invariant (parseBookingConflict ön koşulu).
//      NOT: /pms/bookings ve /pms/quick-booking aynı service'e (create_reservation_service)
//      delegate eder; 409 sözleşmesi ortaktır.
//   3. UI: /app/reservation-calendar → go-to-date-input ile ci tarihine git
//      → ilgili oda satırının ilk gün hücresine tıkla → NewBookingDialog
//      açılır (handleCellClick check_in=ci, check_out=ci+1=co prefiller)
//      → guest adı yaz → submit → [data-testid="booking-conflict-dialog"]
//      görünür.
//   4. Baseline booking 20-recap dışında bu spec'te de cancel edilir
//      (defense-in-depth; registry'e completed işaretlenir).
test.describe('Scope 3 — Booking conflict dialog (calendar create wiring)', () => {
    test('E2E: Calendar empty-cell create 409 surfaces BookingConflictDialog', async ({ baseURL, page }, testInfo) => {
        const api = await makeApi(baseURL);
        const obs = attachObservers(page);
        const dates = farFutureDates();
        rec(testInfo, { module: M, scope: 3, step: 'Hedef tarih aralığı', status: PASS, note: `${dates.check_in}→${dates.check_out}` });

        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi (calendar conflict)', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        const roomNumber = pick.room.room_number;
        if (!roomNumber) {
            rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi (calendar conflict)', status: SKIP, note: 'no_room_number' });
            await api.dispose();
            test.skip(true, 'Pilot oda kaydında room_number yok — calendar cell hedeflenemez');
            return;
        }
        rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi (calendar conflict)', status: PASS, note: `room=${roomNumber}` });

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

        // 2) API-level invariant: /pms/bookings 2. POST aynı oda+pencere → 409
        // + structured detail. UI'ın tükettiği endpoint budur (axios.post
        // '/pms/bookings' in ReservationCalendar.handleCreateBooking). 
        const collide = await safePost(api, '/api/pms/bookings', {
            guest_id: baseline.raw?.guest_id || baseline.raw?.guestId,
            room_id: pick.room.id,
            check_in: dates.check_in,
            check_out: dates.check_out,
            adults: 1,
            children: 0,
            guests_count: 1,
            total_amount: 100,
            channel: 'direct',
            origin: 'ui',
        }, { headers: { 'Idempotency-Key': `collide-${Date.now()}` } });
        const detail = collide.json?.detail;
        const detailIsObj = detail && typeof detail === 'object';
        const hasStructured = detailIsObj && (
            detail.conflict_type || detail.conflicting_booking_id || detail.conflict_window
        );
        const is409 = collide.status === 409;
        rec(testInfo, {
            module: M, scope: 3, step: 'POST /api/pms/bookings (collision) → 409 structured',
            status: is409 && hasStructured ? PASS : FAIL,
            endpoint: '/api/pms/bookings', http: collide.status,
            note: is409 ? `detail_keys=${detailIsObj ? Object.keys(detail).join(',') : typeof detail}` : (collide.body?.slice(0, 200) || ''),
        });
        expect(collide.status, `Expected 409 on overlapping calendar booking, got ${collide.status}: ${collide.body?.slice(0, 200) || ''}`).toBe(409);
        expect(hasStructured, `Conflict response missing structured detail (parseBookingConflict pre-condition broken): ${JSON.stringify(detail).slice(0, 200)}`).toBeTruthy();

        // Baseline'i iptal et ki takvim hücresi "boş" görünsün ve tıklanabilsin.
        await cancelBooking(api, baseline.bookingId, 'E2E conflict test (reset for UI step)');

        // 3) UI: gerçek ReservationCalendar create yolunu sür.
        let dialogVisible = false;
        let baseline2Id = null;
        try {
            const nav = await page.goto('/app/reservation-calendar', { waitUntil: 'networkidle', timeout: 30_000 });
            rec(testInfo, {
                module: M, scope: 3, step: 'Navigate /app/reservation-calendar',
                status: nav?.ok() ? PASS : REVIEW, endpoint: '/app/reservation-calendar', http: nav?.status(),
            });

            // Calendar grid'in mount olduğunu doğrula. Modul kapalıysa
            // (pms.reservation_calendar=false) skip et.
            const grid = page.locator('[data-testid="calendar-grid"]').first();
            if ((await grid.count()) === 0) {
                rec(testInfo, { module: M, scope: 3, step: 'calendar-grid görünür', status: SKIP, note: 'calendar_disabled_or_not_mounted' });
                const c = await cancelBooking(api, baseline.bookingId, 'E2E calendar conflict-dialog spec cleanup (skip path)').catch(() => ({ ok: false }));
                trackEntity({
                    kind: 'booking', id: baseline.bookingId, label: `${baselineGuest} (cancelled)`,
                    cleanup: c?.ok ? 'completed' : 'pending', endpoint: '/api/pms-core/cancel',
                });
                await api.dispose();
                test.skip(true, 'Pilot tenant\'ta reservation calendar mount olmadı');
                return;
            }
            await grid.waitFor({ state: 'visible', timeout: 8_000 });

            // Tarih navigasyonu: go-to-date-input check_in tarihine
            // ayarlanır → currentDate = ci → dateRange[0] = ci.
            const goToDateInput = page.locator('[data-testid="go-to-date-input"]').first();
            await goToDateInput.waitFor({ state: 'visible', timeout: 5_000 });
            await goToDateInput.fill(dates.check_in);
            // input type=date fill her tarayıcıda change event'ini
            // garanti etmez — manuel dispatch.
            await goToDateInput.dispatchEvent('change').catch(() => {});
            await page.waitForTimeout(600);

            // Hücreyi stable data-testid ile yakala (CalendarGrid.jsx
            // `calendar-cell-${room_number}-${YYYY-MM-DD}` yayar). Class
            // veya xpath ancestry'sine dayanmıyoruz.
            const cellTid = `calendar-cell-${roomNumber}-${dates.check_in}`;
            const cell = page.locator(`[data-testid="${cellTid}"]`).first();
            if ((await cell.count()) === 0) {
                // Sanal liste / scroll ihtimaline karşı oda satırına scroll.
                const roomLabel = page.locator(`[data-testid="room-${roomNumber}"]`).first();
                await roomLabel.scrollIntoViewIfNeeded().catch(() => {});
                await page.waitForTimeout(300);
            }
            await cell.waitFor({ state: 'visible', timeout: 8_000 });
            await cell.scrollIntoViewIfNeeded().catch(() => {});
            await cell.click();

            // NewBookingDialog açılmalı: guest search input görünmeli.
            const guestInput = page.locator('[data-testid="new-booking-guest-search"]').first();
            await guestInput.waitFor({ state: 'visible', timeout: 8_000 });

            // selected-room-info testid'inin görünmesi handleCellClick'in
            // doğru oda+tarih ile çağrıldığını doğrular (defansif kontrol).
            const selectedRoomInfo = page.locator('[data-testid="selected-room-info"]').first();
            const selectedOk = await selectedRoomInfo.isVisible().catch(() => false);
            rec(testInfo, {
                module: M, scope: 3, step: 'NewBookingDialog açıldı (cell→handleCellClick)',
                status: selectedOk ? PASS : REVIEW,
                note: selectedOk ? `room=${roomNumber}` : 'selected-room-info görünmedi',
            });

            // Guest adını yaz: handleGuestSearch debounce sonrası
            // setNewBooking({guest_name}) tetikler; submit'te
            // handleCreateBooking new-guest yolundan POST /pms/guests +
            // POST /pms/bookings sürer. Escape KULLANMA — Radix Dialog
            // onEscapeKeyDown ile dialog'u kapatır. Bunun yerine dropdown
            // dışındaki sonraki form input'una blur ile geç (dropdown
            // onBlur'da gizlenir, dialog açık kalır).
            await guestInput.fill(factory.guestName());
            await page.waitForTimeout(250); // debounce/dropdown render

            // Check-in/out alanlarına focus ver → guest dropdown blur ile
            // kapanır, dialog kapanmaz. handleCellClick zaten prefilled,
            // değerleri tekrar yazmıyoruz (gereksiz event tetiklemez).
            const checkinInput = page.locator('[data-testid="new-booking-checkin"]').first();
            await checkinInput.focus();
            await page.waitForTimeout(150);

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

            await page.locator('[data-testid="new-booking-submit"]').first().click();

            // ASIL ASSERTION: dialog görünmeli. Regression: ReservationCalendar
            // parseBookingConflict çağrısını düşürürse burası FAIL.
            const dialog = page.locator('[data-testid="booking-conflict-dialog"]').first();
            await dialog.waitFor({ state: 'visible', timeout: 10_000 });
            dialogVisible = await dialog.isVisible();
        } catch (e) {
            rec(testInfo, { module: M, scope: 3, step: 'UI calendar conflict dialog flow', status: FAIL, note: `error=${e.message?.slice(0, 200)}` });
            await cancelBooking(api, baseline.bookingId, 'E2E calendar conflict-dialog spec cleanup (on error)').catch(() => {});
            trackEntity({
                kind: 'booking', id: baseline.bookingId, label: `${baselineGuest} (cancelled)`,
                cleanup: 'completed', endpoint: '/api/pms-core/cancel',
            });
            await api.dispose();
            throw e;
        }

        rec(testInfo, {
            module: M, scope: 3, step: '[data-testid="booking-conflict-dialog"] görünür (calendar create)',
            status: dialogVisible ? PASS : FAIL,
            note: dialogVisible ? 'visible' : 'not_visible',
        });
        expect(dialogVisible, 'BookingConflictDialog calendar empty-cell create 409\'unda yüzeylenmedi — ReservationCalendar.handleCreateBooking → parseBookingConflict bağlantısı bozuk olabilir').toBe(true);

        // Console errors (yumuşak sinyal).
        rec(testInfo, { module: M, scope: 3, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });

        // 4) Defense-in-depth cleanup — 20-recap yine kontrol eder.
        const cancelled = await cancelBooking(api, baseline.bookingId, 'E2E calendar conflict-dialog spec cleanup');
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
