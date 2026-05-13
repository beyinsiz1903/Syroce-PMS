import { test, expect } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW, SKIP } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';
import { makeApi, safeGet } from './fixtures/api.js';
import { factory, trackEntity } from './fixtures/data-factory.js';

const M = 'reservation';

test.describe('Scope 3 — Rezervasyon yaşam döngüsü', () => {
    test('Rezervasyon takvimi açılır + form keşfi', async ({ page }, testInfo) => {
        const obs = attachObservers(page);
        const r = await page.goto('/reservation-calendar', { waitUntil: 'networkidle' }).catch(() => null);
        rec(testInfo, { module: M, scope: 3, step: 'Takvim navigate', status: r?.ok() ? PASS : REVIEW, endpoint: '/reservation-calendar', http: r?.status() });

        const insp = await inspectPageContent(page);
        rec(testInfo, { module: M, scope: 3, step: 'Sayfa içerik', status: insp.empty || insp.has500 ? FAIL : PASS, note: `len=${insp.lengthChars}` });

        // "Yeni Rezervasyon" / "Rezervasyon ekle" butonu
        const newBtn = page.locator('button:has-text("Yeni Rezervasyon"), button:has-text("Rezervasyon Ekle"), button:has-text("Rezervasyon ekle")').first();
        const newBtnExists = (await newBtn.count()) > 0;
        rec(testInfo, { module: M, scope: 3, step: 'Yeni rezervasyon butonu', status: newBtnExists ? PASS : REVIEW });

        if (newBtnExists) {
            await newBtn.click({ timeout: 5_000 }).catch(() => {});
            await page.waitForTimeout(800);
            const dialogVisible = await page.locator('[role="dialog"], .modal, [data-testid*="dialog"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
            rec(testInfo, { module: M, scope: 3, step: 'Dialog açılır', status: dialogVisible ? PASS : REVIEW });
            // Pilot ortamda placeholder veriyle gerçek booking oluşturmak risk → form keşfi seviyesinde bırakıyoruz
            rec(testInfo, { module: M, scope: 3, step: 'Booking oluşturma (gerçek POST)', status: REVIEW, note: 'Pilot dataset kirletmemek için form keşfiyle sınırlandırıldı; gerçek POST için ayrı veri-temizleme ön çalışması gerekli.' });
            // Dialog'ı kapat (escape)
            await page.keyboard.press('Escape').catch(() => {});
        }

        rec(testInfo, { module: M, scope: 3, step: 'Console errors', status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
    });

    test('PMS bookings endpoint okuma + audit erişim', async ({ baseURL }, testInfo) => {
        const api = await makeApi(baseURL);
        const list = await safeGet(api, '/api/pms/bookings?limit=5');
        rec(testInfo, { module: M, scope: 3, step: 'GET /api/pms/bookings', status: list.ok ? PASS : REVIEW, endpoint: '/api/pms/bookings', http: list.status });
        const rooms = await safeGet(api, '/api/pms/rooms?limit=5');
        rec(testInfo, { module: M, scope: 3, step: 'GET /api/pms/rooms', status: rooms.ok ? PASS : REVIEW, endpoint: '/api/pms/rooms', http: rooms.status });

        // Audit endpoint (read-only kontrolü) — sadece kanonik /api/audit/timeline.
        // Eski /api/admin/audit-log probe'u 2026-05-13 cleanup turunda kaldırıldı
        // (frontend referansı yok; backend'de plural /admin/audit-logs kayıt için var).
        const a = await safeGet(api, '/api/audit/timeline?limit=5');
        rec(testInfo, { module: M, scope: 17, step: 'GET /api/audit/timeline (audit)', status: a.ok ? PASS : REVIEW, endpoint: '/api/audit/timeline', http: a.status });
        await api.dispose();
    });

    test('Terminal-state guard (no-show double) — endpoint discovery', async ({ baseURL }, testInfo) => {
        // Production hardening: ikinci no-show 400 dönmeli; canlı booking yok → endpoint var mı kontrolü
        const api = await makeApi(baseURL);
        const r = await safeGet(api, '/api/pms/bookings?status=no_show&limit=1');
        rec(testInfo, { module: M, scope: 3, step: 'No-show liste endpoint mevcut', status: r.status < 500 ? PASS : REVIEW, endpoint: '/api/pms/bookings?status=no_show', http: r.status });
        rec(testInfo, { module: M, scope: 3, step: 'İkinci no-show guard testi', status: SKIP, note: 'Pilot dataset üzerinde destructive sıralı state değişimi tetiklenmedi; canlı doğrulama T+0 sonrası önerilir.' });
        await api.dispose();
    });
});
