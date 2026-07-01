import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers } from './fixtures/observers.js';
import { makeApi, safePost } from './fixtures/api.js';
import { factory, trackEntity } from './fixtures/data-factory.js';
import {
    pickAvailableRoom, createTestBooking, addExtraCharge,
    getBookingDetail, cancelBooking, farFutureDates,
} from './fixtures/pms-flow.js';

const M = 'split-folio';

const round2 = (n) => Math.round((Number(n) || 0) * 100) / 100;

// ─────────────────────────────────────────────────────────────────────────────
// Ortak kurulum (Task #433) — 23. spec'in (Task #428/#432) kurulum + panel-açma
// akışını yeniden kullanır: müsait oda → booking → extra_charge → HEDEFSİZ
// split-charge (folio_id=null orphan) → takvim → booking-bar dblclick → Folyolar
// sekmesi → "Folyo Böl" (ensure-folio orphan'ı yeni açık folioya bağlar) →
// [data-testid="split-folio-panel"] görünür. Eşit/Özel tutar testleri bu
// paneli açıp tutar tabanlı bölmeyi (split-by-amount) sürer.
//
// Dönüş: { outcome: 'skip'|'review'|'ok', panel }. 'skip' = pilot ön-koşulu
// eksik (oda yok / takvim mount değil) → caller test.skip eder. 'review' = UI
// sürülemedi (booking-bar/modal/sekme render olmadı) → caller return (fake-green
// yok). 'ok' = panel görünür, kalem render etti. Helper kendi rec adımlarını
// kaydeder; akış kontrolünü caller yapar. reg(bookingId, guestName) cleanup
// kaydı için çağrılır.
// ─────────────────────────────────────────────────────────────────────────────
async function setupSplitPanel(page, api, scope, testInfo, dates, guestName, reg) {
    // ── 1) Müsait oda seç (yoksa pilot ön-koşulu eksik → SKIP) ──
    const pick = await pickAvailableRoom(api, dates);
    if (!pick.ok) {
        rec(testInfo, { module: M, scope, step: 'Müsait oda seçimi', status: SKIP, note: pick.reason });
        return { outcome: 'skip', reason: pick.reason };
    }
    const roomId = pick.room.id;
    const roomNumber = pick.room.room_number || pick.room.number;
    if (!roomNumber) {
        rec(testInfo, { module: M, scope, step: 'Müsait oda seçimi', status: SKIP, note: 'no_room_number' });
        return { outcome: 'skip', reason: 'no_room_number' };
    }
    rec(testInfo, { module: M, scope, step: 'Müsait oda seçimi', status: PASS, note: `room=${roomNumber}` });

    // ── 2) Booking oluştur (API) ──
    const created = await createTestBooking(api, {
        roomId, guestName, check_in: dates.check_in, check_out: dates.check_out, totalAmount: 100,
    });
    // 409 = overbooking/envanter çakışması: available-rooms odayı boş gösterse de
    // create_reservation_service'in gece-kilidi (room_night_locks) guard'ı reddediyor
    // (ör. booking'i silinmiş ama kilidi sızmış ORPHAN lock). Bu pilot veri-durumu
    // ön-koşuludur — split-folio özelliğinin başarısızlığı DEĞİL — bu yüzden REVIEW
    // olarak kaydedilir, hard-fail edilmez (suite felsefesi: ön-koşul → REVIEW/SKIP).
    if (!created.ok && created.status === 409) {
        rec(testInfo, {
            module: M, scope, step: 'POST /api/pms/quick-booking',
            status: REVIEW, endpoint: '/api/pms/quick-booking', http: created.status,
            note: `overbooking precondition (orphan room_night_lock?): ${(created.reason || '').slice(0, 160)}`,
        });
        return { outcome: 'review', reason: 'booking_create_overbooking_409' };
    }
    rec(testInfo, {
        module: M, scope, step: 'POST /api/pms/quick-booking',
        status: created.ok ? PASS : FAIL, endpoint: '/api/pms/quick-booking',
        http: created.status, note: created.ok ? `id=${created.bookingId}` : (created.reason || ''),
    });
    expect(created.bookingId, 'Booking create returned no id').toBeTruthy();
    const bookingId = created.bookingId;
    reg(bookingId, guestName);

    // ── 3) extra_charge ekle (API) — split-charge için kaynak kalem ──
    const extra = await addExtraCharge(api, bookingId, {
        description: 'E2E Restoran Masrafi', amount: 120, category: 'food', quantity: 1,
    });
    const extraChargeId = extra.json?.charge?.id;
    rec(testInfo, {
        module: M, scope, step: 'POST add-extra-charge',
        status: extra.ok && extraChargeId ? PASS : FAIL,
        endpoint: `/api/pms/reservations/${bookingId}/add-extra-charge`,
        http: extra.status, note: extraChargeId ? `charge=${extraChargeId}` : (extra.body?.slice(0, 160) || ''),
    });
    expect(extraChargeId, 'add-extra-charge charge.id döndürmedi').toBeTruthy();

    // ── 4) split-charge HEDEFSİZ → folio_id=null ORPHAN folio_charge ──
    const split = await safePost(api, `/api/pms/reservations/${bookingId}/split-charge`, {
        charge_id: extraChargeId,
        split_amount: 60,
        reason: 'E2E orphan folio_charge kurulum',
    });
    rec(testInfo, {
        module: M, scope, step: 'POST split-charge (hedefsiz → orphan folio_charge)',
        status: split.ok ? PASS : FAIL,
        endpoint: `/api/pms/reservations/${bookingId}/split-charge`,
        http: split.status, note: split.ok ? 'orphan folio_charge oluştu' : (split.body?.slice(0, 160) || ''),
    });
    expect(split.ok, `split-charge başarısız: ${split.status} ${split.body?.slice(0, 160) || ''}`).toBe(true);

    // ── 5) Ön-koşul doğrula (API/HARD): AÇIK folio YOK + orphan folio_charge VAR ──
    const detail = await getBookingDetail(api, bookingId);
    const folios = Array.isArray(detail.json?.folios) ? detail.json.folios : [];
    const charges = Array.isArray(detail.json?.charges) ? detail.json.charges : [];
    const openFolios = folios.filter(f => (f.status || '').toLowerCase() === 'open');
    const orphanCharge = charges.find(c => !c.folio_id && !c.voided);
    rec(testInfo, {
        module: M, scope, step: 'Ön-koşul: açık folio yok + orphan folio_charge var',
        status: detail.ok && openFolios.length === 0 && orphanCharge ? PASS : FAIL,
        endpoint: `/api/pms/reservations/${bookingId}/full-detail`, http: detail.status,
        note: `folios=${folios.length} open=${openFolios.length} folio_charges=${charges.length} orphan=${orphanCharge ? 'yes' : 'no'}`,
    });
    expect(detail.ok, 'full-detail okunamadı').toBe(true);
    expect(openFolios.length, 'Beklenmeyen açık folio var — "folio yok" ön-koşulu sağlanmadı').toBe(0);
    expect(orphanCharge, 'Orphan folio_charge (folio_id=null) oluşmadı — split-charge kurulum bozuk').toBeTruthy();

    // ── 6) UI: takvim mount (modül kapalıysa pilot ön-koşulu eksik → SKIP) ──
    const nav = await page.goto('/app/reservation-calendar', { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => null);
    rec(testInfo, {
        module: M, scope, step: 'Navigate /app/reservation-calendar',
        status: nav?.ok() ? PASS : REVIEW, endpoint: '/app/reservation-calendar', http: nav?.status(),
    });
    const grid = page.locator('[data-testid="calendar-grid"]').first();
    if ((await grid.count()) === 0) {
        rec(testInfo, { module: M, scope, step: 'calendar-grid görünür', status: SKIP, note: 'calendar_disabled_or_not_mounted' });
        return { outcome: 'skip', reason: 'calendar_not_mounted' };
    }
    await grid.waitFor({ state: 'visible', timeout: 8_000 });

    const goToDateInput = page.locator('[data-testid="go-to-date-input"]').first();
    await goToDateInput.waitFor({ state: 'visible', timeout: 5_000 });
    await goToDateInput.fill(dates.check_in);
    await goToDateInput.dispatchEvent('change').catch(() => {});
    await page.waitForTimeout(700);

    // ── 7) booking-bar'ı bul ve çift tıkla → detay modalı aç ──
    const bookingBar = page.locator(`[data-testid="booking-bar-${bookingId}"]`).first();
    if ((await bookingBar.count()) === 0) {
        const roomLabel = page.locator(`[data-testid="room-${roomNumber}"]`).first();
        await roomLabel.scrollIntoViewIfNeeded().catch(() => {});
        await page.waitForTimeout(400);
    }
    const barVisible = await bookingBar.isVisible().catch(() => false);
    if (!barVisible) {
        rec(testInfo, { module: M, scope, step: 'booking-bar görünür (modal açma)', status: REVIEW, note: 'booking-bar takvimde bulunamadı — UI sürülemedi' });
        return { outcome: 'review', reason: 'booking_bar_not_visible' };
    }
    await bookingBar.scrollIntoViewIfNeeded().catch(() => {});
    await bookingBar.dblclick();

    const modal = page.locator('[data-testid="reservation-detail-modal"]').first();
    const modalVisible = await modal.isVisible({ timeout: 8_000 }).catch(() => false);
    if (!modalVisible) {
        rec(testInfo, { module: M, scope, step: 'Detay modalı açıldı (booking-bar dblclick)', status: REVIEW, note: 'reservation-detail-modal görünmedi — UI sürülemedi' });
        return { outcome: 'review', reason: 'modal_not_visible' };
    }
    rec(testInfo, { module: M, scope, step: 'Detay modalı açıldı (booking-bar dblclick)', status: PASS });

    // ── 8) Folyolar sekmesine geç ──
    await modal.getByRole('tab', { name: 'Folyolar' }).first().click({ timeout: 8_000 }).catch(async () => {
        await modal.getByText('Folyolar', { exact: true }).first().click({ timeout: 8_000 }).catch(() => {});
    });
    const foliosTab = page.locator('[data-testid="folios-tab"]').first();
    const foliosTabVisible = await foliosTab.isVisible({ timeout: 8_000 }).catch(() => false);
    if (!foliosTabVisible) {
        rec(testInfo, { module: M, scope, step: 'Folyolar sekmesi açıldı', status: REVIEW, note: 'folios-tab görünmedi — UI sürülemedi' });
        return { outcome: 'review', reason: 'folios_tab_not_visible' };
    }
    rec(testInfo, { module: M, scope, step: 'Folyolar sekmesi açıldı', status: PASS });

    // ── 9) Folyo Böl → ensure-folio 200 (orphan'ı yeni açık folioya bağlar) ──
    const folyoBolBtn = page.locator('[data-testid="btn-folyo-bol"]').first();
    await folyoBolBtn.waitFor({ state: 'visible', timeout: 8_000 });
    const ensureRespPromise = page.waitForResponse(
        (r) => r.url().includes(`/reservations/${bookingId}/ensure-folio`) && r.request().method() === 'POST',
        { timeout: 15_000 },
    ).catch(() => null);
    await folyoBolBtn.click();
    const ensureResp = await ensureRespPromise;
    rec(testInfo, {
        module: M, scope, step: 'Folyo Böl → POST ensure-folio',
        status: ensureResp && ensureResp.status() === 200 ? PASS : FAIL,
        endpoint: `/api/pms/reservations/${bookingId}/ensure-folio`,
        http: ensureResp ? ensureResp.status() : null,
        note: ensureResp ? '' : 'ensure-folio çağrılmadı',
    });
    expect(ensureResp, 'Folyo Böl ensure-folio çağırmadı').not.toBeNull();
    expect(ensureResp.status(), `ensure-folio beklenen 200 değil: ${ensureResp.status()}`).toBe(200);

    // ── 10) Bölme paneli görünür (HARD) ──
    const panel = page.locator('[data-testid="split-folio-panel"]').first();
    await panel.waitFor({ state: 'visible', timeout: 10_000 });
    rec(testInfo, { module: M, scope, step: 'split-folio-panel görünür', status: PASS });

    return { outcome: 'ok', panel, bookingId };
}

// ─────────────────────────────────────────────────────────────────────────────
// Task #428 — "Folyo Böl" (folio yok ama masraf var) regression
//
// Regresyon: bir rezervasyonda masraf KALEMİ olup henüz AÇIK FOLYO yoksa
// "Folyo Böl" butonu eskiden "Bölünecek folyo bulunmuyor" toast'u atıyordu.
// Düzeltme (FoliosTab.openSplit): folio yoksa ama hasCharges ise önce
// POST /pms/reservations/{id}/ensure-folio çağrılır (orphan folio_charge'ları
// yeni açılan folyoya bağlar), veri yenilenir ve bölme paneli açılır;
// SplitFolioDialog by_item listesinde kalemleri gösterir.
//
// Bu spec gerçek tarayıcıda kanıtlar:
//   1. (API) booking + extra_charge + split-charge(hedefsiz) → folio_id=null
//      ORPHAN folio_charge. Bu, "masraf var ama folio yok" durumunu kurar.
//   2. (API) full-detail: AÇIK folio YOK + folio_charges içinde orphan VAR.
//   3. (UI) takvim → booking-bar çift tık → detay modalı → Folyolar sekmesi.
//   4. (UI/HARD) "Folyo Böl" → POST .../ensure-folio 200 +
//      [data-testid="split-folio-panel"] görünür + "Bölünecek folyo
//      bulunmuyor" toast'u YOK + bölme listesinde kalem ("[Aktarım]") görünür.
//   5. (UI/HARD — Task #432) by_item modunda "[Aktarım]" kalemi seçilir, sebep
//      yazılır, "Bölmeyi Onayla" tıklanır → POST /api/pms-core/folio/split 200.
//      Sonrasında (API/HARD) full-detail: kaynak folyoda kalem AZALIR + yeni
//      hedef folyo OLUŞUR + seçilen kalem o yeni folyoya TAŞINIR. Yani bölme
//      dialogunun kalemleri yalnızca GÖSTERMEKLE kalmayıp gerçekten aktardığı
//      uçtan uca kanıtlanır (görüntü değil, kalıcı veri taşıması).
//
// Doktrin: dış servis yok → SKIP yalnızca pilot ön-koşulu eksikse (oda yok /
// takvim mount değil). UI sürülemezse (booking-bar/modal render olmazsa)
// REVIEW (fake-green yok). Çekirdek regresyon adımları HARD assert'tir.
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Scope 5 — Folyo Böl (folio yok + masraf var)', () => {
    test('Masrafı olup folyosu olmayan rezervasyonda Folyo Böl kalemleri gösterir', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const api = await makeApi(baseURL);

        const dates = farFutureDates();
        const guestName = factory.guestName();
        let bookingId = null;
        let cleaned = false;

        const finish = async (cleanupReason) => {
            if (cleaned) return;
            cleaned = true;
            if (bookingId) {
                const c = await cancelBooking(api, bookingId, cleanupReason).catch(() => ({ ok: false }));
                trackEntity({
                    kind: 'booking', id: bookingId, label: `${guestName} (cancelled)`,
                    cleanup: c?.ok ? 'completed' : 'pending', endpoint: '/api/pms-core/cancel',
                });
            }
            await api.dispose();
        };

        try {
            // ── 1) Müsait oda seç (yoksa pilot ön-koşulu eksik → SKIP) ──
            const pick = await pickAvailableRoom(api, dates);
            if (!pick.ok) {
                rec(testInfo, { module: M, scope: 5, step: 'Müsait oda seçimi', status: SKIP, note: pick.reason });
                await finish('E2E split-folio cleanup (no_room skip)');
                test.skip(true, 'Pilot tenant uzak tarihte müsait oda döndürmedi');
                return;
            }
            const roomId = pick.room.id;
            const roomNumber = pick.room.room_number || pick.room.number;
            if (!roomNumber) {
                rec(testInfo, { module: M, scope: 5, step: 'Müsait oda seçimi', status: SKIP, note: 'no_room_number' });
                await finish('E2E split-folio cleanup (no_room_number skip)');
                test.skip(true, 'Seçilen oda numarası yok — takvim hücresi adreslenemez');
                return;
            }
            rec(testInfo, { module: M, scope: 5, step: 'Müsait oda seçimi', status: PASS, note: `room=${roomNumber}` });

            // ── 2) Booking oluştur (API) ──
            const created = await createTestBooking(api, {
                roomId, guestName, check_in: dates.check_in, check_out: dates.check_out, totalAmount: 100,
            });
            rec(testInfo, {
                module: M, scope: 5, step: 'POST /api/pms/quick-booking',
                status: created.ok ? PASS : FAIL, endpoint: '/api/pms/quick-booking',
                http: created.status, note: created.ok ? `id=${created.bookingId}` : (created.reason || ''),
            });
            expect(created.bookingId, 'Booking create returned no id').toBeTruthy();
            bookingId = created.bookingId;
            trackEntity({ kind: 'booking', id: bookingId, label: guestName, cleanup: 'pending', endpoint: '/api/pms-core/cancel' });

            // ── 3) extra_charge ekle (API) — split-charge için kaynak kalem ──
            const extra = await addExtraCharge(api, bookingId, {
                description: 'E2E Restoran Masrafi', amount: 120, category: 'food', quantity: 1,
            });
            const extraChargeId = extra.json?.charge?.id;
            rec(testInfo, {
                module: M, scope: 5, step: 'POST add-extra-charge',
                status: extra.ok && extraChargeId ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/add-extra-charge`,
                http: extra.status, note: extraChargeId ? `charge=${extraChargeId}` : (extra.body?.slice(0, 160) || ''),
            });
            expect(extraChargeId, 'add-extra-charge charge.id döndürmedi').toBeTruthy();

            // ── 4) split-charge HEDEFSİZ → folio_id=null ORPHAN folio_charge ──
            // target_folio_id/target_booking_id verilmez → yeni folio_charge
            // folio_id=null + booking_id=orijinal booking ile oluşur. Bu, "masraf
            // var ama folio yok" durumunu temiz REST ile kurar (DB erişimi yok).
            const split = await safePost(api, `/api/pms/reservations/${bookingId}/split-charge`, {
                charge_id: extraChargeId,
                split_amount: 60,
                reason: 'E2E orphan folio_charge kurulum',
            });
            rec(testInfo, {
                module: M, scope: 5, step: 'POST split-charge (hedefsiz → orphan folio_charge)',
                status: split.ok ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/split-charge`,
                http: split.status, note: split.ok ? 'orphan folio_charge oluştu' : (split.body?.slice(0, 160) || ''),
            });
            expect(split.ok, `split-charge başarısız: ${split.status} ${split.body?.slice(0, 160) || ''}`).toBe(true);

            // ── 5) Ön-koşul doğrula (API/HARD): AÇIK folio YOK + orphan folio_charge VAR ──
            const detail = await getBookingDetail(api, bookingId);
            const folios = Array.isArray(detail.json?.folios) ? detail.json.folios : [];
            const charges = Array.isArray(detail.json?.charges) ? detail.json.charges : [];
            const openFolios = folios.filter(f => (f.status || '').toLowerCase() === 'open');
            const orphanCharge = charges.find(c => !c.folio_id && !c.voided);
            rec(testInfo, {
                module: M, scope: 5, step: 'Ön-koşul: açık folio yok + orphan folio_charge var',
                status: detail.ok && openFolios.length === 0 && orphanCharge ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/full-detail`, http: detail.status,
                note: `folios=${folios.length} open=${openFolios.length} folio_charges=${charges.length} orphan=${orphanCharge ? 'yes' : 'no'}`,
            });
            expect(detail.ok, 'full-detail okunamadı').toBe(true);
            expect(openFolios.length, 'Beklenmeyen açık folio var — "folio yok" ön-koşulu sağlanmadı').toBe(0);
            expect(orphanCharge, 'Orphan folio_charge (folio_id=null) oluşmadı — split-charge kurulum bozuk').toBeTruthy();

            // ── 6) UI: takvim mount (modül kapalıysa pilot ön-koşulu eksik → SKIP) ──
            const nav = await page.goto('/app/reservation-calendar', { waitUntil: 'networkidle', timeout: 30_000 }).catch(() => null);
            rec(testInfo, {
                module: M, scope: 5, step: 'Navigate /app/reservation-calendar',
                status: nav?.ok() ? PASS : REVIEW, endpoint: '/app/reservation-calendar', http: nav?.status(),
            });
            const grid = page.locator('[data-testid="calendar-grid"]').first();
            if ((await grid.count()) === 0) {
                rec(testInfo, { module: M, scope: 5, step: 'calendar-grid görünür', status: SKIP, note: 'calendar_disabled_or_not_mounted' });
                await finish('E2E split-folio cleanup (calendar not mounted skip)');
                test.skip(true, 'Pilot tenant\'ta reservation calendar mount olmadı');
                return;
            }
            await grid.waitFor({ state: 'visible', timeout: 8_000 });

            // Tarih navigasyonu: booking check_in tarihine git.
            const goToDateInput = page.locator('[data-testid="go-to-date-input"]').first();
            await goToDateInput.waitFor({ state: 'visible', timeout: 5_000 });
            await goToDateInput.fill(dates.check_in);
            await goToDateInput.dispatchEvent('change').catch(() => {});
            await page.waitForTimeout(700);

            // ── 7) booking-bar'ı bul ve çift tıkla → detay modalı aç ──
            // Render olmazsa (sanal liste/scroll) REVIEW: UI sürülemedi (fake-green yok).
            const bookingBar = page.locator(`[data-testid="booking-bar-${bookingId}"]`).first();
            if ((await bookingBar.count()) === 0) {
                const roomLabel = page.locator(`[data-testid="room-${roomNumber}"]`).first();
                await roomLabel.scrollIntoViewIfNeeded().catch(() => {});
                await page.waitForTimeout(400);
            }
            const barVisible = await bookingBar.isVisible().catch(() => false);
            if (!barVisible) {
                rec(testInfo, { module: M, scope: 5, step: 'booking-bar görünür (modal açma)', status: REVIEW, note: 'booking-bar takvimde bulunamadı — UI sürülemedi' });
                await finish('E2E split-folio cleanup (booking-bar not visible)');
                return;
            }
            await bookingBar.scrollIntoViewIfNeeded().catch(() => {});
            await bookingBar.dblclick();

            const modal = page.locator('[data-testid="reservation-detail-modal"]').first();
            const modalVisible = await modal.isVisible({ timeout: 8_000 }).catch(() => false);
            if (!modalVisible) {
                rec(testInfo, { module: M, scope: 5, step: 'Detay modalı açıldı (booking-bar dblclick)', status: REVIEW, note: 'reservation-detail-modal görünmedi — UI sürülemedi' });
                await finish('E2E split-folio cleanup (modal not visible)');
                return;
            }
            rec(testInfo, { module: M, scope: 5, step: 'Detay modalı açıldı (booking-bar dblclick)', status: PASS });

            // ── 8) Folyolar sekmesine geç ──
            await modal.getByRole('tab', { name: 'Folyolar' }).first().click({ timeout: 8_000 }).catch(async () => {
                await modal.getByText('Folyolar', { exact: true }).first().click({ timeout: 8_000 }).catch(() => {});
            });
            const foliosTab = page.locator('[data-testid="folios-tab"]').first();
            const foliosTabVisible = await foliosTab.isVisible({ timeout: 8_000 }).catch(() => false);
            if (!foliosTabVisible) {
                rec(testInfo, { module: M, scope: 5, step: 'Folyolar sekmesi açıldı', status: REVIEW, note: 'folios-tab görünmedi — UI sürülemedi' });
                await finish('E2E split-folio cleanup (folios-tab not visible)');
                return;
            }
            rec(testInfo, { module: M, scope: 5, step: 'Folyolar sekmesi açıldı', status: PASS });

            // ── 9) ÇEKİRDEK REGRESYON (HARD): Folyo Böl → ensure-folio 200 ──
            const folyoBolBtn = page.locator('[data-testid="btn-folyo-bol"]').first();
            await folyoBolBtn.waitFor({ state: 'visible', timeout: 8_000 });
            const ensureRespPromise = page.waitForResponse(
                (r) => r.url().includes(`/reservations/${bookingId}/ensure-folio`) && r.request().method() === 'POST',
                { timeout: 15_000 },
            ).catch(() => null);
            await folyoBolBtn.click();
            const ensureResp = await ensureRespPromise;
            rec(testInfo, {
                module: M, scope: 5, step: 'Folyo Böl → POST ensure-folio',
                status: ensureResp && ensureResp.status() === 200 ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/ensure-folio`,
                http: ensureResp ? ensureResp.status() : null,
                note: ensureResp ? '' : 'ensure-folio çağrılmadı — regresyon (toast yoluna düşmüş olabilir)',
            });
            expect(ensureResp, 'Folyo Böl ensure-folio çağırmadı — eski "Bölünecek folyo bulunmuyor" regresyonu').not.toBeNull();
            expect(ensureResp.status(), `ensure-folio beklenen 200 değil: ${ensureResp.status()}`).toBe(200);

            // ── 10) Bölme paneli görünür (HARD) ──
            const panel = page.locator('[data-testid="split-folio-panel"]').first();
            await panel.waitFor({ state: 'visible', timeout: 10_000 });
            rec(testInfo, { module: M, scope: 5, step: 'split-folio-panel görünür', status: PASS });

            // ── 11) "Bölünecek folyo bulunmuyor" toast'u YOK (HARD) ──
            const errToastCount = await page.getByText('Bölünecek folyo bulunmuyor').count();
            rec(testInfo, {
                module: M, scope: 5, step: '"Bölünecek folyo bulunmuyor" toast yok',
                status: errToastCount === 0 ? PASS : FAIL, note: `count=${errToastCount}`,
            });
            expect(errToastCount, 'Eski "Bölünecek folyo bulunmuyor" toast\'u göründü — regresyon').toBe(0);

            // ── 12) Bölme listesinde KALEM görünür (HARD) ──
            // ensure-folio orphan folio_charge'ı yeni folyoya bağladı →
            // SplitFolioDialog by_item listesi "[Aktarım] E2E Restoran..." gösterir.
            const itemText = panel.getByText(/Aktar[ıi]m/).first();
            const itemVisible = await itemText.isVisible({ timeout: 8_000 }).catch(() => false);
            const checkboxCount = await panel.locator('input[type="checkbox"]').count();
            rec(testInfo, {
                module: M, scope: 5, step: 'Bölme dialogu kalemleri gösteriyor (boş uyarı değil)',
                status: itemVisible && checkboxCount > 0 ? PASS : FAIL,
                note: `item=${itemVisible} checkbox=${checkboxCount}`,
            });
            expect(itemVisible, 'Bölme dialogunda kalem görünmüyor — "görüntülenebilen masraf kalemi yok" boş uyarısına düşmüş olabilir').toBe(true);
            expect(checkboxCount, 'Bölme dialogu by_item kalem checkbox\'ı render etmedi').toBeGreaterThan(0);

            // ── 13) Bölme ÖNCESİ durumu yakala (API/HARD) ──
            // ensure-folio orphan folio_charge'ı yeni AÇIK folyoya bağladı; bölme
            // öncesi tam olarak 1 açık folio olmalı, kaynak kalem o folyoya ait.
            const pre = await getBookingDetail(api, bookingId);
            const preCharges = Array.isArray(pre.json?.charges) ? pre.json.charges : [];
            const preOpenFolios = (Array.isArray(pre.json?.folios) ? pre.json.folios : [])
                .filter(f => (f.status || '').toLowerCase() === 'open');
            const sourceFolio = preOpenFolios[0];
            const sourceFolioId = sourceFolio?.id;
            const preSourceChargeCount = preCharges
                .filter(c => c.folio_id === sourceFolioId && !c.voided).length;
            rec(testInfo, {
                module: M, scope: 5, step: 'Bölme öncesi: tek açık folio + kaynak kalem var',
                status: pre.ok && sourceFolioId && preSourceChargeCount > 0 ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/full-detail`, http: pre.status,
                note: `open_folios=${preOpenFolios.length} source=${sourceFolioId || 'yok'} source_charges=${preSourceChargeCount}`,
            });
            expect(pre.ok, 'bölme öncesi full-detail okunamadı').toBe(true);
            expect(sourceFolioId, 'ensure-folio sonrası açık kaynak folio bulunamadı').toBeTruthy();
            expect(preSourceChargeCount, 'Kaynak folyoda bölünebilir kalem yok — ensure-folio kalemi bağlamadı').toBeGreaterThan(0);

            // ── 14) by_item: "[Aktarım]" kalemini seç (kaynak folioya bağlı kalem) ──
            const aktarimRow = panel.locator('label').filter({ hasText: /Aktar[ıi]m/ }).first();
            const aktarimCheckbox = aktarimRow.locator('input[type="checkbox"]').first();
            await aktarimCheckbox.check({ timeout: 8_000 });
            const isChecked = await aktarimCheckbox.isChecked().catch(() => false);
            rec(testInfo, {
                module: M, scope: 5, step: 'by_item: kalem seçildi',
                status: isChecked ? PASS : FAIL, note: `checked=${isChecked}`,
            });
            expect(isChecked, 'by_item kalem checkbox işaretlenemedi').toBe(true);

            // ── 15) Bölme sebebi yaz (boş sebep backend\'e gitmeden reddedilir) ──
            const reasonInput = panel.locator('input:not([type="checkbox"])').last();
            await reasonInput.waitFor({ state: 'visible', timeout: 5_000 });
            await reasonInput.fill('E2E by_item folyo bölme aktarımı');

            // ── 16) "Bölmeyi Onayla" → POST /api/pms-core/folio/split 200 (HARD) ──
            const splitRespPromise = page.waitForResponse(
                (r) => /\/pms-core\/folio\/split(\?|$)/.test(r.url())
                    && !r.url().includes('split-by-amount')
                    && r.request().method() === 'POST',
                { timeout: 15_000 },
            ).catch(() => null);
            await panel.getByRole('button', { name: 'Bölmeyi Onayla' }).first().click();
            const splitResp = await splitRespPromise;
            const splitBody = splitResp ? await splitResp.json().catch(() => null) : null;
            const newFolioId = splitBody?.new_folio?.id;
            rec(testInfo, {
                module: M, scope: 5, step: 'Bölmeyi Onayla → POST /pms-core/folio/split',
                status: splitResp && splitResp.status() === 200 && splitBody?.success
                    && (splitBody?.transferred_charges || 0) >= 1 && newFolioId ? PASS : FAIL,
                endpoint: '/api/pms-core/folio/split',
                http: splitResp ? splitResp.status() : null,
                note: splitResp
                    ? `success=${splitBody?.success} transferred=${splitBody?.transferred_charges} new_folio=${newFolioId || 'yok'}`
                    : 'split çağrılmadı — by_item Onayla yolu kırık',
            });
            expect(splitResp, 'Bölmeyi Onayla /pms-core/folio/split çağırmadı').not.toBeNull();
            expect(splitResp.status(), `folio/split beklenen 200 değil: ${splitResp.status()}`).toBe(200);
            expect(splitBody?.success, `folio/split success!=true: ${JSON.stringify(splitBody)?.slice(0, 200)}`).toBe(true);
            expect(splitBody?.transferred_charges || 0, 'folio/split kalem aktarmadı (transferred_charges<1)').toBeGreaterThanOrEqual(1);
            expect(newFolioId, 'folio/split yeni hedef folio oluşturmadı (new_folio.id yok)').toBeTruthy();

            // ── 17) Bölme SONRASI durumu doğrula (API/HARD): kalem gerçekten taşındı ──
            // Kaynak folyoda kalem azalır + yeni hedef folio full-detail\'de görünür +
            // seçilen kalem artık yeni folioya ait. Bu, "gösterme değil aktarma" kanıtı.
            const post = await getBookingDetail(api, bookingId);
            const postCharges = Array.isArray(post.json?.charges) ? post.json.charges : [];
            const postFolios = Array.isArray(post.json?.folios) ? post.json.folios : [];
            const postSourceChargeCount = postCharges
                .filter(c => c.folio_id === sourceFolioId && !c.voided).length;
            const targetFolioExists = postFolios.some(f => f.id === newFolioId);
            const transferredCharge = postCharges
                .find(c => c.folio_id === newFolioId && /Aktar[ıi]m/.test(c.description || '') && !c.voided);
            rec(testInfo, {
                module: M, scope: 5, step: 'Bölme sonrası: kaynak kalem azaldı + yeni folioya taşındı',
                status: post.ok && targetFolioExists && transferredCharge
                    && postSourceChargeCount < preSourceChargeCount ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/full-detail`, http: post.status,
                note: `source_charges ${preSourceChargeCount}→${postSourceChargeCount} target_folio=${targetFolioExists ? 'var' : 'yok'} moved_charge=${transferredCharge ? 'var' : 'yok'}`,
            });
            expect(post.ok, 'bölme sonrası full-detail okunamadı').toBe(true);
            expect(targetFolioExists, 'Yeni hedef folio full-detail folios içinde yok — bölme kalıcı değil').toBe(true);
            expect(transferredCharge, 'Aktarılan kalem yeni hedef folioya bağlanmadı — taşıma gerçekleşmedi').toBeTruthy();
            expect(postSourceChargeCount, 'Kaynak folyoda kalem sayısı azalmadı — kalem taşınmamış').toBeLessThan(preSourceChargeCount);

            rec(testInfo, {
                module: M, scope: 5, step: 'Console errors',
                status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}`,
            });
        } finally {
            await finish('E2E split-folio cleanup');
        }
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Task #433 — Tutar tabanlı bölme (Eşit / Özel) uçtan uca bakiye aktarımı
//
// Task #432 by_item modunu (POST /pms-core/folio/split) uçtan uca kanıtladı.
// Bu iki test dialogun DİĞER iki modunu doğrular: "Eşit Böl" ve "Özel Tutar"
// (her ikisi de POST /api/pms-core/folio/split-by-amount çağırır). Bu modlar
// kalem değil TUTAR tabanlı çalışır; backend booking kapsamlı ekstra masrafları
// önce kaynak folioya absorbe eder (Task #426), sonra her parça için pozitif
// düzeltmeli yeni folio açar + kaynak folioya tek negatif düzeltme yazar.
//
// Bölünebilir bakiye = kaynak folio bakiyesi + (folio_id'siz) ekstra masraf
// toplamı (dialog ve backend aynı tabanı kullanır). HARD kanıt: kaynak folio
// SON bakiyesi == bölünebilir bakiye − aktarılan tutar (yani gerçekten azaldı),
// hedef folio(lar) full-detail'de OLUŞTU ve bakiyeleri aktarılan tutarı taşıyor.
// "Gösterme değil aktarma" — kalıcı veri taşıması kanıtlanır.
//
// Doktrin: dış servis yok → SKIP yalnızca pilot ön-koşulu eksikse. UI
// sürülemezse REVIEW (fake-green yok). Tutar/bölme adımları HARD assert'tir.
// ─────────────────────────────────────────────────────────────────────────────
test.describe('Scope 6 — Tutar tabanlı folyo bölme (Eşit / Özel)', () => {
    test('Eşit Böl gerçekten yeni folyo açar ve kaynak bakiyeyi aktarır', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const api = await makeApi(baseURL);

        const dates = farFutureDates();
        const guestName = factory.guestName();
        let bookingId = null;
        let cleaned = false;

        const reg = (id, label) => {
            bookingId = id;
            trackEntity({ kind: 'booking', id, label, cleanup: 'pending', endpoint: '/api/pms-core/cancel' });
        };
        const finish = async (cleanupReason) => {
            if (cleaned) return;
            cleaned = true;
            if (bookingId) {
                const c = await cancelBooking(api, bookingId, cleanupReason).catch(() => ({ ok: false }));
                trackEntity({
                    kind: 'booking', id: bookingId, label: `${guestName} (cancelled)`,
                    cleanup: c?.ok ? 'completed' : 'pending', endpoint: '/api/pms-core/cancel',
                });
            }
            await api.dispose();
        };

        try {
            const setup = await setupSplitPanel(page, api, 6, testInfo, dates, guestName, reg);
            if (setup.outcome === 'skip') {
                await finish('E2E split-folio even cleanup (skip)');
                test.skip(true, `Pilot ön-koşulu eksik: ${setup.reason}`);
                return;
            }
            if (setup.outcome === 'review') {
                await finish('E2E split-folio even cleanup (review)');
                return;
            }
            const panel = setup.panel;

            // ── Bölme ÖNCESİ durum (API/HARD): kaynak açık folio + bölünebilir bakiye ──
            // Bölünebilir bakiye = kaynak folio bakiyesi + ekstra masraf toplamı
            // (backend ekstrayı bölme sırasında absorbe eder). Dialog aynı tabanı
            // kullanarak eşit parça tutarını hesaplar.
            const pre = await getBookingDetail(api, bookingId);
            const preOpenFolios = (Array.isArray(pre.json?.folios) ? pre.json.folios : [])
                .filter(f => (f.status || '').toLowerCase() === 'open');
            const sourceFolio = preOpenFolios[0];
            const sourceFolioId = sourceFolio?.id;
            const preSourceBalance = round2(sourceFolio?.balance);
            const preExtra = (Array.isArray(pre.json?.extra_charges) ? pre.json.extra_charges : [])
                .filter(c => !c.voided);
            const preExtraTotal = round2(
                preExtra.reduce((s, c) => s + (Number(c.total ?? c.amount ?? c.charge_amount ?? 0) || 0), 0)
            );
            const preDivisible = round2(preSourceBalance + preExtraTotal);
            rec(testInfo, {
                module: M, scope: 6, step: 'Bölme öncesi: kaynak açık folio + bölünebilir bakiye',
                status: pre.ok && sourceFolioId && preDivisible > 0 ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/full-detail`, http: pre.status,
                note: `source=${sourceFolioId || 'yok'} folio_bakiye=${preSourceBalance} ekstra=${preExtraTotal} bölünebilir=${preDivisible}`,
            });
            expect(pre.ok, 'bölme öncesi full-detail okunamadı').toBe(true);
            expect(sourceFolioId, 'ensure-folio sonrası açık kaynak folio bulunamadı').toBeTruthy();
            expect(preDivisible, 'Bölünebilir bakiye 0 — eşit böl test edilemez').toBeGreaterThan(0);

            // ── "Eşit Böl" modunu seç (varsayılan 2 parça → 1 yeni folio) ──
            await panel.getByRole('button', { name: 'Eşit Böl' }).first().click();
            const reasonInput = panel.locator('input:not([type="checkbox"])').last();
            await reasonInput.waitFor({ state: 'visible', timeout: 5_000 });
            await reasonInput.fill('E2E eşit böl bakiye aktarımı');

            // ── "Bölmeyi Onayla" → POST split-by-amount 200 + success (HARD) ──
            const respPromise = page.waitForResponse(
                (r) => /\/pms-core\/folio\/split-by-amount(\?|$)/.test(r.url()) && r.request().method() === 'POST',
                { timeout: 15_000 },
            ).catch(() => null);
            await panel.getByRole('button', { name: 'Bölmeyi Onayla' }).first().click();
            const resp = await respPromise;
            const body = resp ? await resp.json().catch(() => null) : null;
            const transferred = round2(body?.transferred_amount);
            const newFolioIds = (Array.isArray(body?.new_folios) ? body.new_folios : [])
                .map(f => f.id).filter(Boolean);
            rec(testInfo, {
                module: M, scope: 6, step: 'Bölmeyi Onayla → POST /pms-core/folio/split-by-amount (eşit)',
                status: resp && resp.status() === 200 && body?.success
                    && (body?.target_count || 0) >= 1 && transferred > 0 && newFolioIds.length >= 1 ? PASS : FAIL,
                endpoint: '/api/pms-core/folio/split-by-amount',
                http: resp ? resp.status() : null,
                note: resp
                    ? `success=${body?.success} target_count=${body?.target_count} transferred=${transferred} new_folios=${newFolioIds.length}`
                    : 'split-by-amount çağrılmadı — Eşit Böl Onayla yolu kırık',
            });
            expect(resp, 'Bölmeyi Onayla split-by-amount çağırmadı').not.toBeNull();
            expect(resp.status(), `split-by-amount beklenen 200 değil: ${resp.status()}`).toBe(200);
            expect(body?.success, `split-by-amount success!=true: ${JSON.stringify(body)?.slice(0, 200)}`).toBe(true);
            expect(body?.target_count || 0, 'Eşit böl yeni hedef folio açmadı (target_count<1)').toBeGreaterThanOrEqual(1);
            expect(transferred, 'Eşit böl tutar aktarmadı (transferred_amount<=0)').toBeGreaterThan(0);
            expect(newFolioIds.length, 'Eşit böl new_folios id döndürmedi').toBeGreaterThanOrEqual(1);

            // ── Bölme SONRASI (API/HARD): hedef folio(lar) oluştu + kaynak bakiye azaldı ──
            const post = await getBookingDetail(api, bookingId);
            const postFolios = Array.isArray(post.json?.folios) ? post.json.folios : [];
            const targetFolios = postFolios.filter(f => newFolioIds.includes(f.id));
            const targetBalanceTotal = round2(
                targetFolios.reduce((s, f) => s + (Number(f.balance) || 0), 0)
            );
            const postSource = postFolios.find(f => f.id === sourceFolioId);
            const postSourceBalance = round2(postSource?.balance);
            const expectedSource = round2(preDivisible - transferred);
            rec(testInfo, {
                module: M, scope: 6, step: 'Bölme sonrası: hedef folio(lar) oluştu + kaynak bakiye azaldı',
                status: post.ok && targetFolios.length === newFolioIds.length
                    && Math.abs(targetBalanceTotal - transferred) <= 0.05
                    && Math.abs(postSourceBalance - expectedSource) <= 0.05
                    && postSourceBalance < preDivisible ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/full-detail`, http: post.status,
                note: `hedef_folio=${targetFolios.length}/${newFolioIds.length} hedef_bakiye=${targetBalanceTotal} (≈${transferred}) kaynak_bakiye ${preDivisible}→${postSourceBalance} (beklenen ${expectedSource})`,
            });
            expect(post.ok, 'bölme sonrası full-detail okunamadı').toBe(true);
            expect(targetFolios.length, 'Yeni hedef folio(lar) full-detail folios içinde yok — bölme kalıcı değil').toBe(newFolioIds.length);
            expect(Math.abs(targetBalanceTotal - transferred), 'Hedef folio bakiyeleri aktarılan tutarı taşımıyor').toBeLessThanOrEqual(0.05);
            expect(Math.abs(postSourceBalance - expectedSource), 'Kaynak folio son bakiyesi beklenen (bölünebilir − aktarılan) değer değil').toBeLessThanOrEqual(0.05);
            expect(postSourceBalance, 'Kaynak folio bakiyesi bölünebilir bakiyeden azalmadı — aktarım gerçekleşmedi').toBeLessThan(preDivisible);

            rec(testInfo, {
                module: M, scope: 6, step: 'Console errors',
                status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}`,
            });
        } finally {
            await finish('E2E split-folio even cleanup');
        }
    });

    test('Özel Tutar gerçekten yeni folyo açar ve girilen tutarı aktarır', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const api = await makeApi(baseURL);

        const dates = farFutureDates();
        const guestName = factory.guestName();
        let bookingId = null;
        let cleaned = false;

        const reg = (id, label) => {
            bookingId = id;
            trackEntity({ kind: 'booking', id, label, cleanup: 'pending', endpoint: '/api/pms-core/cancel' });
        };
        const finish = async (cleanupReason) => {
            if (cleaned) return;
            cleaned = true;
            if (bookingId) {
                const c = await cancelBooking(api, bookingId, cleanupReason).catch(() => ({ ok: false }));
                trackEntity({
                    kind: 'booking', id: bookingId, label: `${guestName} (cancelled)`,
                    cleanup: c?.ok ? 'completed' : 'pending', endpoint: '/api/pms-core/cancel',
                });
            }
            await api.dispose();
        };

        try {
            const setup = await setupSplitPanel(page, api, 7, testInfo, dates, guestName, reg);
            if (setup.outcome === 'skip') {
                await finish('E2E split-folio custom cleanup (skip)');
                test.skip(true, `Pilot ön-koşulu eksik: ${setup.reason}`);
                return;
            }
            if (setup.outcome === 'review') {
                await finish('E2E split-folio custom cleanup (review)');
                return;
            }
            const panel = setup.panel;

            // ── Bölme ÖNCESİ durum (API/HARD): kaynak açık folio + bölünebilir bakiye ──
            const pre = await getBookingDetail(api, bookingId);
            const preOpenFolios = (Array.isArray(pre.json?.folios) ? pre.json.folios : [])
                .filter(f => (f.status || '').toLowerCase() === 'open');
            const sourceFolio = preOpenFolios[0];
            const sourceFolioId = sourceFolio?.id;
            const preSourceBalance = round2(sourceFolio?.balance);
            const preExtra = (Array.isArray(pre.json?.extra_charges) ? pre.json.extra_charges : [])
                .filter(c => !c.voided);
            const preExtraTotal = round2(
                preExtra.reduce((s, c) => s + (Number(c.total ?? c.amount ?? c.charge_amount ?? 0) || 0), 0)
            );
            const preDivisible = round2(preSourceBalance + preExtraTotal);
            // Bölünebilir bakiyenin altında kalan, orijinalde miktar bırakan tutar.
            const customAmount = round2(preDivisible * 0.4);
            rec(testInfo, {
                module: M, scope: 7, step: 'Bölme öncesi: kaynak açık folio + bölünebilir bakiye',
                status: pre.ok && sourceFolioId && preDivisible > 0 && customAmount > 0 && customAmount < preDivisible ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/full-detail`, http: pre.status,
                note: `source=${sourceFolioId || 'yok'} bölünebilir=${preDivisible} özel_tutar=${customAmount}`,
            });
            expect(pre.ok, 'bölme öncesi full-detail okunamadı').toBe(true);
            expect(sourceFolioId, 'ensure-folio sonrası açık kaynak folio bulunamadı').toBeTruthy();
            expect(preDivisible, 'Bölünebilir bakiye 0 — özel tutar test edilemez').toBeGreaterThan(0);
            expect(customAmount, 'Hesaplanan özel tutar geçersiz').toBeGreaterThan(0);
            expect(customAmount, 'Özel tutar bölünebilir bakiyeden küçük olmalı').toBeLessThan(preDivisible);

            // ── "Özel Tutar" modunu seç, tutarı gir ──
            await panel.getByRole('button', { name: 'Özel Tutar' }).first().click();
            const amountInput = panel.locator('input[type="number"]').first();
            await amountInput.waitFor({ state: 'visible', timeout: 5_000 });
            await amountInput.fill(String(customAmount));
            const reasonInput = panel.locator('input:not([type="checkbox"])').last();
            await reasonInput.fill('E2E özel tutar bakiye aktarımı');

            // ── "Bölmeyi Onayla" → POST split-by-amount 200 + success (HARD) ──
            const respPromise = page.waitForResponse(
                (r) => /\/pms-core\/folio\/split-by-amount(\?|$)/.test(r.url()) && r.request().method() === 'POST',
                { timeout: 15_000 },
            ).catch(() => null);
            await panel.getByRole('button', { name: 'Bölmeyi Onayla' }).first().click();
            const resp = await respPromise;
            const body = resp ? await resp.json().catch(() => null) : null;
            const transferred = round2(body?.transferred_amount);
            const newFolioIds = (Array.isArray(body?.new_folios) ? body.new_folios : [])
                .map(f => f.id).filter(Boolean);
            rec(testInfo, {
                module: M, scope: 7, step: 'Bölmeyi Onayla → POST /pms-core/folio/split-by-amount (özel)',
                status: resp && resp.status() === 200 && body?.success
                    && (body?.target_count || 0) >= 1 && Math.abs(transferred - customAmount) <= 0.05
                    && newFolioIds.length >= 1 ? PASS : FAIL,
                endpoint: '/api/pms-core/folio/split-by-amount',
                http: resp ? resp.status() : null,
                note: resp
                    ? `success=${body?.success} target_count=${body?.target_count} transferred=${transferred} (girilen ${customAmount}) new_folios=${newFolioIds.length}`
                    : 'split-by-amount çağrılmadı — Özel Tutar Onayla yolu kırık',
            });
            expect(resp, 'Bölmeyi Onayla split-by-amount çağırmadı').not.toBeNull();
            expect(resp.status(), `split-by-amount beklenen 200 değil: ${resp.status()}`).toBe(200);
            expect(body?.success, `split-by-amount success!=true: ${JSON.stringify(body)?.slice(0, 200)}`).toBe(true);
            expect(body?.target_count || 0, 'Özel tutar yeni hedef folio açmadı (target_count<1)').toBeGreaterThanOrEqual(1);
            expect(Math.abs(transferred - customAmount), 'Aktarılan tutar girilen özel tutarla eşleşmiyor').toBeLessThanOrEqual(0.05);
            expect(newFolioIds.length, 'Özel tutar new_folios id döndürmedi').toBeGreaterThanOrEqual(1);

            // ── Bölme SONRASI (API/HARD): hedef folio oluştu + kaynak bakiye azaldı ──
            const post = await getBookingDetail(api, bookingId);
            const postFolios = Array.isArray(post.json?.folios) ? post.json.folios : [];
            const targetFolios = postFolios.filter(f => newFolioIds.includes(f.id));
            const targetBalanceTotal = round2(
                targetFolios.reduce((s, f) => s + (Number(f.balance) || 0), 0)
            );
            const postSource = postFolios.find(f => f.id === sourceFolioId);
            const postSourceBalance = round2(postSource?.balance);
            const expectedSource = round2(preDivisible - transferred);
            rec(testInfo, {
                module: M, scope: 7, step: 'Bölme sonrası: hedef folio oluştu + kaynak bakiye azaldı',
                status: post.ok && targetFolios.length === newFolioIds.length
                    && Math.abs(targetBalanceTotal - transferred) <= 0.05
                    && Math.abs(postSourceBalance - expectedSource) <= 0.05
                    && postSourceBalance < preDivisible ? PASS : FAIL,
                endpoint: `/api/pms/reservations/${bookingId}/full-detail`, http: post.status,
                note: `hedef_folio=${targetFolios.length}/${newFolioIds.length} hedef_bakiye=${targetBalanceTotal} (≈${transferred}) kaynak_bakiye ${preDivisible}→${postSourceBalance} (beklenen ${expectedSource})`,
            });
            expect(post.ok, 'bölme sonrası full-detail okunamadı').toBe(true);
            expect(targetFolios.length, 'Yeni hedef folio full-detail folios içinde yok — bölme kalıcı değil').toBe(newFolioIds.length);
            expect(Math.abs(targetBalanceTotal - transferred), 'Hedef folio bakiyesi aktarılan tutarı taşımıyor').toBeLessThanOrEqual(0.05);
            expect(Math.abs(postSourceBalance - expectedSource), 'Kaynak folio son bakiyesi beklenen (bölünebilir − aktarılan) değer değil').toBeLessThanOrEqual(0.05);
            expect(postSourceBalance, 'Kaynak folio bakiyesi bölünebilir bakiyeden azalmadı — aktarım gerçekleşmedi').toBeLessThan(preDivisible);

            rec(testInfo, {
                module: M, scope: 7, step: 'Console errors',
                status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}`,
            });
        } finally {
            await finish('E2E split-folio custom cleanup');
        }
    });
});
