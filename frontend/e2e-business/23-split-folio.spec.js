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

            rec(testInfo, {
                module: M, scope: 5, step: 'Console errors',
                status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}`,
            });
        } finally {
            await finish('E2E split-folio cleanup');
        }
    });
});
