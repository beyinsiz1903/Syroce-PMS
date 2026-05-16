import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';
import { factory, trackEntity } from './fixtures/data-factory.js';
import {
    pickAvailableRoom, createTestBooking, cancelBooking,
    fetchCalendarBookings, farFutureDates, noShowBooking,
} from './fixtures/pms-flow.js';

const M = 'reservation';

test.describe('Scope 3 — Rezervasyon yaşam döngüsü', () => {
    test('Rezervasyon takvimi açılır + form keşfi', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/reservation-calendar', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 3, step: 'Takvim navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/reservation-calendar', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 3, step: 'Sayfa içerik', status: insp.empty || insp.has500 ? FAIL : PASS, note: `len=${insp.lengthChars}` });

        const newBtn = page.locator('button:has-text("Yeni Rezervasyon"), button:has-text("Rezervasyon Ekle"), button:has-text("Rezervasyon ekle")').first();
        const newBtnExists = (await newBtn.count()) > 0;
        rec(testInfo, { module: M, scope: 3, step: 'Yeni rezervasyon butonu', status: newBtnExists ? PASS : REVIEW });

        if (newBtnExists) {
            await newBtn.click({ timeout: 5_000 }).catch(() => {});
            await page.waitForTimeout(800);
            const dialogVisible = await page.locator('[role="dialog"], .modal, [data-testid*="dialog"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
            rec(testInfo, { module: M, scope: 3, step: 'Dialog açılır', status: dialogVisible ? PASS : REVIEW });
            await page.keyboard.press('Escape').catch(() => {});
        }

        rec(testInfo, { module: M, scope: 3, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });

    test('PMS bookings + audit endpoint okuma', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        const list = await safeGet(api, '/api/pms/bookings?limit=5');
        rec(testInfo, { module: M, scope: 3, step: 'GET /api/pms/bookings', status: list.ok ? PASS : REVIEW, endpoint: '/api/pms/bookings', http: list.status });
        const rooms = await safeGet(api, '/api/pms/rooms?limit=5');
        rec(testInfo, { module: M, scope: 3, step: 'GET /api/pms/rooms', status: rooms.ok ? PASS : REVIEW, endpoint: '/api/pms/rooms', http: rooms.status });
        const a = await safeGet(api, '/api/audit/timeline?limit=5');
        rec(testInfo, { module: M, scope: 17, step: 'GET /api/audit/timeline (audit)', status: a.ok ? PASS : REVIEW, endpoint: '/api/audit/timeline', http: a.status });
        await api.dispose();
    });

    // ── E2E (regression-catching): Create → verify in calendar → cancel ──
    // Hard-fails (expect) tüm zorunlu adımlarda:
    //   1. Booking POST 2xx + id
    //   2. ReservationCalendar.jsx'in tükettiği endpoint
    //      (/api/pms/bookings?start_date&end_date) o aralıkta booking_id'yi içerir
    //   3. /reservation-calendar UI'da guest name DOM'da görünür
    //   4. Cancel POST 2xx success
    // SKIP yalnızca "pilot pre-condition" eksikse (örn. müsait oda yok); kırık API
    // path'leri PASS göstermez. trackEntity registry'e yazılır → 20-recap güvenlik
    // ağı olarak ikinci defa cancel'i dener.
    test('E2E: Create → verify in calendar → cancel reservation', async ({ baseURL, page }, testInfo) => {
        const api = await makeApi(baseURL);
        const dates = farFutureDates();
        rec(testInfo, { module: M, scope: 3, step: 'Hedef tarih aralığı', status: PASS, note: `${dates.check_in}→${dates.check_out}` });

        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi', status: PASS, note: `room=${pick.room.room_number || pick.room.id}` });

        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: pick.room.id, guestName,
            check_in: dates.check_in, check_out: dates.check_out,
            totalAmount: 100,
        });
        // Hard-assert: regression-catching anchor #1 — create POST mutlaka başarılı olmalı.
        rec(testInfo, { module: M, scope: 3, step: 'POST /api/pms/quick-booking', status: created.ok ? PASS : FAIL, endpoint: '/api/pms/quick-booking', http: created.status, note: created.ok ? `id=${created.bookingId}` : (created.reason || '') });
        expect(created.ok, `Booking create FAILED: ${created.reason || created.status}`).toBe(true);
        expect(created.bookingId, 'Booking create returned no id').toBeTruthy();
        trackEntity({
            kind: 'booking', id: created.bookingId, label: guestName,
            cleanup: 'pending', endpoint: '/api/pms-core/cancel',
        });

        // Hard-assert: regression-catching anchor #2 — calendar API o aralıktaki bookingleri
        // dönerken yeni id'yi içermeli (calendar UI bu endpoint'i çiziyor).
        const cal = await fetchCalendarBookings(api, { start_date: dates.check_in, end_date: dates.check_out });
        const inCal = cal.ok && cal.bookings.some((b) => (b.id || b.booking_id) === created.bookingId);
        rec(testInfo, {
            module: M, scope: 3, step: 'Calendar API booking içerir',
            status: inCal ? PASS : FAIL,
            endpoint: `/api/pms/bookings?start_date=${dates.check_in}&end_date=${dates.check_out}`,
            http: cal.status, note: `total_in_range=${cal.bookings?.length || 0}`,
        });
        expect(inCal, 'Yeni booking calendar veri kaynağında görünmüyor — calendar render bozuk olabilir').toBe(true);

        // UI-level calendar verification: /reservation-calendar sayfası guest adını render etmeli.
        // Best-effort (DOM gecikmesi/virtualization ihtimaline karşı REVIEW; API kontrolü zaten hard-fail).
        try {
            await page.goto('/reservation-calendar', { waitUntil: 'networkidle', timeout: 30_000 });
            await page.waitForTimeout(1500);
            const domHit = await page.locator(`text=${guestName.slice(0, 24)}`).first().isVisible({ timeout: 3_000 }).catch(() => false);
            rec(testInfo, { module: M, scope: 3, step: 'Calendar UI guest name render', status: domHit ? PASS : REVIEW, note: domHit ? 'visible' : 'not_visible_in_first_viewport' });
        } catch (e) {
            rec(testInfo, { module: M, scope: 3, step: 'Calendar UI guest name render', status: REVIEW, note: `nav_error=${e.message}` });
        }

        // Hard-assert: regression-catching anchor #3 — cancel başarılı dönmeli.
        const cancelled = await cancelBooking(api, created.bookingId, 'E2E lifecycle cleanup');
        const cancelOk = cancelled.ok && cancelled.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 3, step: 'POST /api/pms-core/cancel',
            status: cancelOk ? PASS : FAIL,
            endpoint: '/api/pms-core/cancel', http: cancelled.status,
            note: cancelOk ? 'cancelled' : (cancelled.body?.slice(0, 160) || ''),
        });
        expect(cancelOk, `Cancel FAILED: HTTP ${cancelled.status} ${cancelled.body?.slice(0, 160) || ''}`).toBe(true);
        trackEntity({
            kind: 'booking', id: created.bookingId, label: `${guestName} (cancelled)`,
            cleanup: 'completed', endpoint: '/api/pms-core/cancel',
        });
        await api.dispose();
    });

    // ── E2E (regression-catching): Terminal-state guard for no-show double-mark ──
    // Hard-fails:
    //   1. Booking create 2xx + id (confirmed)
    //   2. İlk no-show POST 2xx + success
    //   3. İkinci no-show POST 400 + "Cannot mark ... in 'no_show' state"
    // No_show booking terminal'dir, recap cancel deneyemez → trackEntity completed.
    // Bu test üretim-hardening fix'ini (NON_NOSHOWABLE_STATES guard,
    // reservation_state_machine.py:31) regresyondan korur.
    test('E2E: No-show terminal-state guard (double-mark 400)', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        const dates = farFutureDates();
        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi (no-show)', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        rec(testInfo, { module: M, scope: 3, step: 'Müsait oda seçimi (no-show)', status: PASS, note: `room=${pick.room.room_number || pick.room.id}` });

        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: pick.room.id, guestName,
            check_in: dates.check_in, check_out: dates.check_out,
            totalAmount: 1,
        });
        rec(testInfo, { module: M, scope: 3, step: 'POST /api/pms/quick-booking (no-show src)', status: created.ok ? PASS : FAIL, endpoint: '/api/pms/quick-booking', http: created.status, note: created.ok ? `id=${created.bookingId}` : (created.reason || '') });
        expect(created.ok, `Booking create FAILED: ${created.reason || created.status}`).toBe(true);
        expect(created.bookingId, 'Booking create returned no id').toBeTruthy();
        trackEntity({
            kind: 'booking', id: created.bookingId, label: guestName,
            cleanup: 'pending', endpoint: '/api/pms-core/cancel',
        });

        // Hard-assert #1: İlk no-show 2xx + success.
        const ns1 = await noShowBooking(api, created.bookingId);
        const ns1Ok = ns1.ok && ns1.json?.success !== false;
        rec(testInfo, {
            module: M, scope: 3, step: 'POST /api/pms-core/no-show (1st)',
            status: ns1Ok ? PASS : FAIL,
            endpoint: '/api/pms-core/no-show', http: ns1.status,
            note: ns1Ok ? 'no_show_marked' : (ns1.body?.slice(0, 200) || ''),
        });
        expect(ns1Ok, `First no-show FAILED: HTTP ${ns1.status} ${ns1.body?.slice(0, 200) || ''}`).toBe(true);
        // Terminal → cancel mümkün değil; recap'i bilgilendir.
        trackEntity({
            kind: 'booking', id: created.bookingId, label: `${guestName} (no_show)`,
            cleanup: 'completed', endpoint: '/api/pms-core/no-show',
        });

        // Hard-assert #2: İkinci no-show 400 (terminal-state guard).
        // Recorder PASS/FAIL ile expect kontratı senkron: ikisi de yalnız status 400'e bakar
        // (mesaj formatı ileride değişebilir; status guard'ın kararlı sinyalidir).
        const ns2 = await noShowBooking(api, created.bookingId);
        const blocked = ns2.status === 400;
        rec(testInfo, {
            module: M, scope: 3, step: 'POST /api/pms-core/no-show (2nd, beklenen 400)',
            status: blocked ? PASS : FAIL,
            endpoint: '/api/pms-core/no-show', http: ns2.status,
            note: blocked ? `guard_enforced body="${(ns2.body || '').slice(0, 120)}"` : (ns2.body?.slice(0, 200) || `unexpected_status=${ns2.status}`),
        });
        expect(ns2.status, `Second no-show should return 400, got ${ns2.status}: ${ns2.body?.slice(0, 200) || ''}`).toBe(400);
        await api.dispose();
    });
});
