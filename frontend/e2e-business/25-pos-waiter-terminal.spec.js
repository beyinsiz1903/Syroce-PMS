import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGetJson } from './fixtures/api.js';
import { trackEntity } from './fixtures/data-factory.js';

const M = 'pos_waiter';
const SCOPE = 25;
const ROUTE = '/pos/terminal';

// Garson terminali (POSWaiterTerminal.jsx) uçtan uca akış kapsaması.
//
// Doktrin notu: bu spec pilotta GERÇEK bir create-order (nakit) yaratır — tıpkı
// 03/04/05 spec'lerinin gerçek booking/folio yaratması gibi. Nakit POS hesabı
// folyo'ya yazılmaz (folio_id yok), misafir/PII içermez; yalnızca terminal
// (pos_orders) kaydı + outlet/iş-günü adisyon sayacını tüketir → düşük etkili,
// temizleme uç noktası olmayan terminal kayıt. Odaya-yazma yolu BİLEREK
// mutasyon yaratmaz: imza zorunluluğu guard'ı tetiklenip akış create-order'a
// ulaşmadan kesilir (folyo kirletmeden imza kontratını kanıtlar).

// Outlet seç → tablo + menü dolu bir outlet bul (UI akışı tamamlanabilsin).
async function pickUsableOutlet(api) {
    const outletsRes = await safeGetJson(api, '/api/pos/outlets');
    if (!outletsRes.ok) return { ok: false, reason: `outlets GET ${outletsRes.status}` };
    const outlets = (Array.isArray(outletsRes.json) ? outletsRes.json : (outletsRes.json?.outlets || []))
        .filter((o) => o && o.status !== 'inactive');
    if (outlets.length === 0) return { ok: false, reason: 'aktif outlet yok' };
    for (const o of outlets) {
        const tablesRes = await safeGetJson(api, `/api/pos/table-layout/${o.id}`);
        const tables = tablesRes.json?.tables || [];
        const menuRes = await safeGetJson(api, `/api/pos/menu-items?outlet_id=${o.id}`);
        const menu = Array.isArray(menuRes.json) ? menuRes.json : (menuRes.json?.menu_items || []);
        if (tables.length > 0 && menu.length > 0) {
            return { ok: true, outlet: o, table: tables[0], menuItem: menu[0], tableCount: tables.length, menuCount: menu.length };
        }
    }
    return { ok: false, reason: 'masa+menü dolu outlet yok' };
}

// outlet → masa → menü → sepet adımlarını UI üzerinden yürür, ürünü sepete ekler.
async function driveToCart(page, pick, testInfo) {
    const r = await page.goto(ROUTE, { waitUntil: 'networkidle' }).catch(() => null);
    rec(testInfo, { module: M, scope: SCOPE, step: 'Terminal navigate', status: r?.ok() ? PASS : REVIEW, endpoint: ROUTE, http: r?.status() });

    const insp = await inspectPageContent(page);
    rec(testInfo, { module: M, scope: SCOPE, step: 'Sayfa içerik', status: insp.empty || insp.has500 || insp.hasErrorBoundary ? FAIL : PASS, note: `len=${insp.lengthChars}` });
    expect(insp.empty || insp.has500 || insp.hasErrorBoundary, 'Garson terminali boş/500/hata-state render etti').toBe(false);

    // Step 1: outlet
    const outletCard = page.locator(`[data-testid="outlet-${pick.outlet.id}"]`);
    await outletCard.first().waitFor({ state: 'visible', timeout: 15_000 });
    rec(testInfo, { module: M, scope: SCOPE, step: 'Outlet kartı render', status: PASS, note: `outlet=${pick.outlet.id}` });
    await outletCard.first().click();

    // Step 2: masa
    const tableBtn = page.locator(`[data-testid="table-${pick.table.table_number}"]`);
    await tableBtn.first().waitFor({ state: 'visible', timeout: 15_000 });
    rec(testInfo, { module: M, scope: SCOPE, step: 'Masa kartı render', status: PASS, note: `masa=${pick.table.table_number}` });
    await tableBtn.first().click();

    // Step 3: menü → sepet
    const menuCard = page.locator(`[data-testid="menu-item-${pick.menuItem.id}"]`);
    await menuCard.first().waitFor({ state: 'visible', timeout: 15_000 });
    rec(testInfo, { module: M, scope: SCOPE, step: 'Menü ürünü render', status: PASS, note: `item=${pick.menuItem.id}` });
    await menuCard.first().click();

    const plus = page.locator(`[data-testid="cart-plus-${pick.menuItem.id}"]`);
    const inCart = await plus.first().isVisible({ timeout: 10_000 }).catch(() => false);
    rec(testInfo, { module: M, scope: SCOPE, step: 'Ürün sepete eklendi', status: inCart ? PASS : FAIL, note: inCart ? 'cart-row visible' : 'cart-row yok' });
    expect(inCart, 'Menü ürünü sepete eklenmedi (adisyon satırı görünmüyor)').toBe(true);
}

test.describe('Scope 25 — Garson terminali (POS) e2e akış', () => {
    test('E2E: outlet → masa → menü → sepet → nakit create-order başarılı + adisyon/iş-günü ekranda', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const api = await makeApi(baseURL);
        const pick = await pickUsableOutlet(api);
        await api.dispose();
        if (!pick.ok) {
            rec(testInfo, { module: M, scope: SCOPE, step: 'Outlet/masa/menü ön koşulu', status: SKIP, note: pick.reason });
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        rec(testInfo, { module: M, scope: SCOPE, step: 'Outlet/masa/menü ön koşulu', status: PASS, note: `outlet=${pick.outlet.id} masa=${pick.tableCount} menü=${pick.menuCount}` });

        await driveToCart(page, pick, testInfo);

        // Nakit ile create-order — POST yanıtını yakala (regresyon ankoru #1).
        const [resp] = await Promise.all([
            page.waitForResponse(
                (res) => res.url().includes('/api/pos/create-order') && res.request().method() === 'POST',
                { timeout: 25_000 },
            ).catch(() => null),
            page.locator('[data-testid="pay-cash"]').click(),
        ]);

        rec(testInfo, { module: M, scope: SCOPE, step: 'create-order isteği yakalandı', status: resp ? PASS : FAIL, endpoint: '/api/pos/create-order', http: resp?.status() ?? null });
        expect(resp, 'create-order POST isteği yakalanamadı').toBeTruthy();

        const body = await resp.json().catch(() => ({}));
        const order = body?.order || null;
        const createOk = resp.ok() && body?.success === true && order?.adisyon_number != null;
        rec(testInfo, {
            module: M, scope: SCOPE, step: 'POST /api/pos/create-order başarılı',
            status: createOk ? PASS : FAIL, endpoint: '/api/pos/create-order', http: resp.status(),
            note: createOk ? `adisyon=${order.adisyon_number} business_date=${order.business_date}` : JSON.stringify(body).slice(0, 200),
        });
        expect(createOk, `create-order başarısız: HTTP ${resp.status()} ${JSON.stringify(body).slice(0, 200)}`).toBe(true);

        // Terminal kayıt — temizleme uç noktası yok (nakit, folyosuz); recap'in
        // pending cleanup denememesi için cleanup:'manual'.
        trackEntity({
            kind: 'pos_order', id: order.id,
            label: `E2E_pos_cash adisyon#${order.adisyon_number}`,
            cleanup: 'manual', endpoint: null,
        });

        // Başarı dialog'unu kapat (overlay'in altındaki kartı serbest bırak).
        await page.locator('[data-testid="dialog-confirm-btn"]').click({ timeout: 5_000 }).catch(() => {});

        // Regresyon ankoru #2 — adisyon_number + business_date EKRANDA görünür.
        const card = page.locator('[data-testid="last-order"]');
        await card.waitFor({ state: 'visible', timeout: 12_000 });

        const adisyonText = (await page.locator('[data-testid="last-adisyon-number"]').innerText().catch(() => '')).trim();
        const adisyonVisible = adisyonText.includes(String(order.adisyon_number));
        rec(testInfo, { module: M, scope: SCOPE, step: 'Adisyon no ekranda görünür', status: adisyonVisible ? PASS : FAIL, note: `dom="${adisyonText}" api=${order.adisyon_number}` });
        expect(adisyonVisible, `Adisyon no ekranda görünmüyor: dom="${adisyonText}" api=${order.adisyon_number}`).toBe(true);

        const bdText = (await page.locator('[data-testid="last-business-date"]').innerText().catch(() => '')).trim();
        const bdVisible = bdText.length > 0 && (!order.business_date || bdText.includes(String(order.business_date)));
        rec(testInfo, { module: M, scope: SCOPE, step: 'İş günü (business_date) ekranda görünür', status: bdVisible ? PASS : FAIL, note: `dom="${bdText}" api=${order.business_date}` });
        expect(bdVisible, `business_date ekranda görünmüyor: dom="${bdText}" api=${order.business_date}`).toBe(true);

        rec(testInfo, { module: M, scope: SCOPE, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });

    test('E2E: odaya-yazma — in-house misafir seçimi + imza zorunluluğu guard', async ({ page, baseURL }, testInfo) => {
        const obs = attachObservers(page);
        const api = await makeApi(baseURL);
        const pick = await pickUsableOutlet(api);
        const inhouseRes = await safeGetJson(api, '/api/frontdesk/inhouse');
        await api.dispose();

        if (!pick.ok) {
            rec(testInfo, { module: M, scope: SCOPE, step: 'Outlet/masa/menü ön koşulu (odaya-yaz)', status: SKIP, note: pick.reason });
            test.skip(true, `Pilot pre-condition eksik: ${pick.reason}`);
            return;
        }
        const inhouse = Array.isArray(inhouseRes.json) ? inhouseRes.json : [];
        if (inhouse.length === 0) {
            rec(testInfo, { module: M, scope: SCOPE, step: 'In-house misafir ön koşulu', status: SKIP, note: 'konaklayan misafir yok' });
            test.skip(true, 'Pilot pre-condition eksik: in-house misafir yok');
            return;
        }
        const guest = inhouse[0];
        rec(testInfo, { module: M, scope: SCOPE, step: 'In-house misafir ön koşulu', status: PASS, note: `inhouse=${inhouse.length}` });

        await driveToCart(page, pick, testInfo);

        // Odaya-Yaz bölümü: arama kutusuna odak → loadInhouse tetiklenir.
        const search = page.locator('[data-testid="room-guest-search"]');
        await search.first().waitFor({ state: 'visible', timeout: 12_000 });
        await search.first().click();

        // In-house misafir listesi render edilir + seçilir.
        const guestBtn = page.locator(`[data-testid="inhouse-${guest.id}"]`);
        const guestVisible = await guestBtn.first().isVisible({ timeout: 12_000 }).catch(() => false);
        rec(testInfo, { module: M, scope: SCOPE, step: 'In-house misafir listesi render', status: guestVisible ? PASS : FAIL, note: guestVisible ? `guest=${guest.id}` : 'misafir butonu görünmedi' });
        expect(guestVisible, 'In-house misafir seçim listesi render edilmedi').toBe(true);
        await guestBtn.first().click();

        // Misafir seçilince imza pad + "Odaya Yaz ve Onayla" butonu belirir.
        const payRoom = page.locator('[data-testid="pay-room"]');
        await payRoom.first().waitFor({ state: 'visible', timeout: 10_000 });
        const padVisible = await page.locator('[data-testid="signature-pad"]').first().isVisible({ timeout: 5_000 }).catch(() => false);
        rec(testInfo, { module: M, scope: SCOPE, step: 'İmza pad + odaya-yaz butonu görünür', status: padVisible ? PASS : REVIEW, note: `pad=${padVisible}` });

        // İmza ÇİZMEDEN onayla → imza zorunluluğu guard'ı tetiklenmeli, create-order
        // ÇAĞRILMAMALI (mutasyon yok). create-order isteği gelirse guard kırık demektir.
        let createOrderFired = false;
        const onReq = (req) => { if (req.url().includes('/api/pos/create-order')) createOrderFired = true; };
        page.on('request', onReq);
        await payRoom.first().click();

        const dialog = page.locator('[data-testid="app-dialog"]');
        const dialogVisible = await dialog.first().isVisible({ timeout: 8_000 }).catch(() => false);
        const dlgText = dialogVisible ? (await dialog.first().innerText().catch(() => '')) : '';
        const guarded = dialogVisible && /imza/i.test(dlgText);
        rec(testInfo, {
            module: M, scope: SCOPE, step: 'İmza zorunluluğu guard (imzasız → uyarı)',
            status: guarded ? PASS : FAIL, note: guarded ? `uyarı="${dlgText.slice(0, 80)}"` : `dialog=${dialogVisible} text="${dlgText.slice(0, 80)}"`,
        });
        expect(guarded, `İmza zorunluluğu uyarısı çıkmadı: dialog=${dialogVisible} text="${dlgText.slice(0, 120)}"`).toBe(true);

        // Guard create-order'ı kesmiş olmalı (folyo kirletilmedi).
        await page.waitForTimeout(500);
        page.off('request', onReq);
        rec(testInfo, { module: M, scope: SCOPE, step: 'İmzasız create-order ÇAĞRILMADI (mutasyon yok)', status: createOrderFired ? FAIL : PASS, note: `fired=${createOrderFired}` });
        expect(createOrderFired, 'İmzasız odaya-yazmada create-order tetiklendi — guard kırık').toBe(false);

        await page.locator('[data-testid="dialog-confirm-btn"]').click({ timeout: 5_000 }).catch(() => {});
        rec(testInfo, { module: M, scope: SCOPE, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });
});
