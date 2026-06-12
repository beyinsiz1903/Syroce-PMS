import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers } from './fixtures/observers.js';
import { makeApi } from './fixtures/api.js';
import { factory, trackEntity } from './fixtures/data-factory.js';
import {
    pickAvailableRoom, createTestBooking, checkoutBooking, cancelBooking,
    getBookingDetail, todayDates,
} from './fixtures/pms-flow.js';

// Scope 24 — Cevrimdisi check-in (offline -> kuyruk -> online -> otomatik eslesme)
// Gercek tarayicida tam zinciri dogrular:
//   1. Pilot'ta bugun-girisli onayli rezervasyon olustur (API).
//   2. /ai-pms -> On Buro sekmesine git, varis satirini bekle.
//   3. setOffline(true) -> amber cevrimdisi gostergesi (offline-indicator).
//   4. Hizli check-in tikla -> performCheckin navigator.onLine===false ile
//      IndexedDB kuyruguna yazar -> offline-pending-count gorunur.
//   5. setOffline(false) -> 'online' olayi -> hook sync() -> processQueuedCheckins
//      idempotent /frontdesk/v2/checkin'e replay -> kuyruk bosalir -> serit kaybolur.
//   6. API ile booking.status === 'checked_in' dogrula.
// Cakisma yolu (room occupied/invalid): kuyruga aldiktan SONRA, sayfa cevrimdisiyken
// ayri API context'i ile booking iptal et -> online'a don -> replay 400 INVALID_STATUS
// -> kirmizi serit (offline-conflict-bar + item) -> "Anladim" (offline-conflict-dismiss)
// tiklanir -> serit temizlenir.
//
// Servis worker yalniz production build'de kayitli oldugundan e2e deployed/prod-build
// base_url'e kosturulur; SW yoksa sayfa-baglami yedek ('online' olayi) yine de
// eslestirir, bu yuzden SW eksikligi REVIEW olarak not edilir, hard-fail DEGIL.
// Pilot pre-condition (musait oda / varis render / onayli durum) yoksa SKIP.

const M = 'offline-checkin';
const FD_URL = '/ai-pms';

// /ai-pms -> On Buro sekmesini ac, hedef rezervasyonun varis satirini dondur.
async function openFrontDeskArrival(page, bookingId) {
    await page.goto(FD_URL, { waitUntil: 'domcontentloaded' });
    const tab = page.getByTestId('ai-pms-tab-frontdesk');
    try {
        await tab.waitFor({ state: 'visible', timeout: 20000 });
    } catch {
        return { ok: false, reason: 'front_desk_tab_not_rendered' };
    }
    await tab.click();
    const row = page.getByTestId(`fd-arrival-${bookingId}`);
    try {
        await row.waitFor({ state: 'visible', timeout: 15000 });
    } catch {
        return { ok: false, reason: 'arrival_row_not_rendered' };
    }
    const checkinBtn = page.getByTestId(`fd-checkin-${bookingId}`);
    try {
        await checkinBtn.waitFor({ state: 'visible', timeout: 5000 });
    } catch {
        return { ok: false, reason: 'checkin_button_not_visible_status_not_confirmed' };
    }
    return { ok: true, row, checkinBtn };
}

// Servis worker kayitli mi? (prod build göstergesi — bilgi amacli, gate degil.)
async function swRegistered(page) {
    try {
        return await page.evaluate(async () => {
            if (!('serviceWorker' in navigator)) return false;
            const reg = await navigator.serviceWorker.getRegistration();
            return !!reg;
        });
    } catch {
        return false;
    }
}

test.describe('Scope 24 — Cevrimdisi check-in', () => {
    // ── E2E (regression-catching): offline -> kuyruk -> online -> otomatik eslesme ──
    // Hard-fails:
    //   1. Booking create 2xx + id
    //   2. setOffline -> offline-indicator gorunur
    //   3. Hizli check-in -> offline-pending-count gorunur (kuyruga alindi)
    //   4. online'a don -> offline-status-bar kaybolur (otomatik eslesme)
    //   5. API: booking.status === 'checked_in' (replay gercekten check-in yapti)
    test('E2E: offline check-in -> kuyruk -> online auto-sync -> banner temizlenir', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const api = await makeApi(baseURL);
        const dates = todayDates(1);

        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 24, step: 'Musait oda (bugun)', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        rec(testInfo, { module: M, scope: 24, step: 'Musait oda (bugun)', status: PASS, note: `room=${pick.room.room_number || pick.room.id}` });

        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: pick.room.id, guestName,
            check_in: dates.check_in, check_out: dates.check_out, totalAmount: 1,
        });
        rec(testInfo, {
            module: M, scope: 24, step: 'POST /api/pms/quick-booking',
            status: created.ok ? PASS : FAIL, endpoint: '/api/pms/quick-booking', http: created.status,
            note: created.ok ? `id=${created.bookingId} status=${created.bookingStatus}` : (created.reason || ''),
        });
        expect(created.ok, `Booking create FAILED: ${created.reason || created.status}`).toBe(true);
        expect(created.bookingId, 'No booking id returned').toBeTruthy();
        trackEntity({ kind: 'booking', id: created.bookingId, label: guestName, cleanup: 'pending', endpoint: '/api/pms-core/cancel' });

        const nav = await openFrontDeskArrival(page, created.bookingId);
        if (!nav.ok) {
            rec(testInfo, { module: M, scope: 24, step: 'On Buro varis satiri', status: SKIP, note: nav.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${nav.reason}`);
            return;
        }
        rec(testInfo, { module: M, scope: 24, step: 'On Buro varis satiri + check-in butonu', status: PASS, note: `booking=${created.bookingId}` });

        const sw = await swRegistered(page);
        rec(testInfo, {
            module: M, scope: 24, step: 'Servis worker kayitli (prod build)',
            status: sw ? PASS : REVIEW,
            note: sw ? 'registered' : 'kayit yok — sayfa-baglami yedek ile devam (dev build olabilir)',
        });

        // ── Cevrimdisi ──
        await page.context().setOffline(true);
        const indicator = page.getByTestId('offline-indicator');
        await expect(indicator, 'Cevrimdisi gostergesi (amber serit) gorunmedi').toBeVisible({ timeout: 10000 });
        rec(testInfo, { module: M, scope: 24, step: 'setOffline -> offline-indicator', status: PASS });

        // ── Hizli check-in (kuyruga alinmali) ──
        await nav.checkinBtn.click();
        const pendingCount = page.getByTestId('offline-pending-count');
        await expect(pendingCount, 'Kuyruk gostergesi (offline-pending-count) gorunmedi').toBeVisible({ timeout: 10000 });
        rec(testInfo, { module: M, scope: 24, step: 'Cevrimdisi check-in -> kuyruk gostergesi', status: PASS });

        // ── Online'a don: otomatik eslesme kuyrugu bosaltmali ──
        await page.context().setOffline(false);
        const statusBar = page.getByTestId('offline-status-bar');
        await expect(statusBar, 'Online sonrasi serit kaybolmadi (otomatik eslesme calismadi)').toBeHidden({ timeout: 30000 });
        rec(testInfo, { module: M, scope: 24, step: 'online -> otomatik eslesme -> banner temizlendi', status: PASS });

        // ── API dogrulama: replay gercekten check-in yapti mi ──
        const detail = await getBookingDetail(api, created.bookingId);
        const st = detail.json?.booking?.status;
        const ciOk = detail.ok && st === 'checked_in';
        rec(testInfo, {
            module: M, scope: 24, step: 'GET /api/pms/reservations/:id/full-detail (status=checked_in)',
            status: ciOk ? PASS : FAIL, endpoint: '/api/pms/reservations/:id/full-detail', http: detail.status,
            note: ciOk ? 'checked_in' : `got=${st}`,
        });
        expect(st, `Replay sonrasi booking.status beklenen checked_in degil: got=${st}`).toBe('checked_in');

        rec(testInfo, { module: M, scope: 24, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });

        // ── Cleanup: checked_in -> force checkout (terminal state) ──
        const co = await checkoutBooking(api, created.bookingId, true);
        if (co.ok && co.json?.success !== false) {
            trackEntity({ kind: 'booking', id: created.bookingId, label: `${guestName} (checked_out)`, cleanup: 'completed', endpoint: '/api/pms-core/checkout' });
        }
        await api.dispose();
    });

    // ── E2E (regression-catching): cakisma yolu -> kirmizi serit -> "Anladim" temizler ──
    // Hard-fails:
    //   1. Booking create 2xx + id
    //   2. Cevrimdisi check-in -> kuyruk gostergesi
    //   3. online'a don (booking out-of-band iptal edilmis) -> offline-conflict-bar + item
    //   4. "Anladim" tikla -> offline-conflict-bar kaybolur
    test('E2E: cakisma (iptal edilmis booking) -> kirmizi serit -> Anladim temizler', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const api = await makeApi(baseURL);
        const dates = todayDates(1);

        const pick = await pickAvailableRoom(api, dates);
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: 24, step: 'Musait oda (cakisma)', status: SKIP, note: pick.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        rec(testInfo, { module: M, scope: 24, step: 'Musait oda (cakisma)', status: PASS, note: `room=${pick.room.room_number || pick.room.id}` });

        const guestName = factory.guestName();
        const created = await createTestBooking(api, {
            roomId: pick.room.id, guestName,
            check_in: dates.check_in, check_out: dates.check_out, totalAmount: 1,
        });
        rec(testInfo, {
            module: M, scope: 24, step: 'POST /api/pms/quick-booking (cakisma)',
            status: created.ok ? PASS : FAIL, endpoint: '/api/pms/quick-booking', http: created.status,
            note: created.ok ? `id=${created.bookingId}` : (created.reason || ''),
        });
        expect(created.ok, `Booking create FAILED: ${created.reason || created.status}`).toBe(true);
        expect(created.bookingId, 'No booking id returned').toBeTruthy();
        trackEntity({ kind: 'booking', id: created.bookingId, label: guestName, cleanup: 'pending', endpoint: '/api/pms-core/cancel' });

        const nav = await openFrontDeskArrival(page, created.bookingId);
        if (!nav.ok) {
            rec(testInfo, { module: M, scope: 24, step: 'On Buro varis satiri (cakisma)', status: SKIP, note: nav.reason });
            await api.dispose();
            test.skip(true, `Pilot pre-condition eksik: ${nav.reason}`);
            return;
        }
        rec(testInfo, { module: M, scope: 24, step: 'On Buro varis satiri (cakisma)', status: PASS, note: `booking=${created.bookingId}` });

        // ── Cevrimdisi + check-in kuyruga al ──
        await page.context().setOffline(true);
        await expect(page.getByTestId('offline-indicator')).toBeVisible({ timeout: 10000 });
        await nav.checkinBtn.click();
        await expect(page.getByTestId('offline-pending-count'), 'Kuyruk gostergesi gorunmedi').toBeVisible({ timeout: 10000 });
        rec(testInfo, { module: M, scope: 24, step: 'Cevrimdisi check-in -> kuyruk gostergesi (cakisma)', status: PASS });

        // ── Kuyrukta beklerken booking'i out-of-band iptal et (ayri API context'i,
        //    sayfa offline'dan etkilenmez) -> online replay'de durum cakismasi olusur. ──
        const cancel = await cancelBooking(api, created.bookingId, 'E2E cakisma tetikleme');
        rec(testInfo, {
            module: M, scope: 24, step: 'POST /api/pms-core/cancel (out-of-band)',
            status: cancel.ok ? PASS : FAIL, endpoint: '/api/pms-core/cancel', http: cancel.status,
            note: cancel.ok ? 'cancelled' : (cancel.body?.slice(0, 200) || ''),
        });
        expect(cancel.ok, `Cancel FAILED: HTTP ${cancel.status}`).toBe(true);
        trackEntity({ kind: 'booking', id: created.bookingId, label: `${guestName} (cancelled)`, cleanup: 'completed', endpoint: '/api/pms-core/cancel' });

        // ── Online'a don: replay 400 INVALID_STATUS -> kirmizi cakisma seridi ──
        await page.context().setOffline(false);
        const conflictBar = page.getByTestId('offline-conflict-bar');
        await expect(conflictBar, 'Kirmizi cakisma seridi (offline-conflict-bar) gorunmedi').toBeVisible({ timeout: 30000 });
        const conflictItem = page.getByTestId('offline-conflict-item');
        await expect(conflictItem.first(), 'Cakisma kalemi gorunmedi').toBeVisible({ timeout: 5000 });
        rec(testInfo, { module: M, scope: 24, step: 'online -> kirmizi cakisma seridi', status: PASS });

        // ── "Anladim" -> dismiss -> serit temizlenir ──
        await page.getByTestId('offline-conflict-dismiss').first().click();
        await expect(conflictBar, '"Anladim" sonrasi cakisma seridi temizlenmedi').toBeHidden({ timeout: 10000 });
        rec(testInfo, { module: M, scope: 24, step: '"Anladim" -> cakisma seridi temizlendi', status: PASS });

        rec(testInfo, { module: M, scope: 24, step: 'Console errors (cakisma)', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
        await api.dispose();
    });
});
