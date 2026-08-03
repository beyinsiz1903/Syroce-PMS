import { test, request } from '@playwright/test';
import { rec, PASS, FAIL, REVIEW } from './fixtures/recorder.js';

const M = 'security-rbac';

test.describe('Scope 18 — Güvenlik / izolasyon', () => {
    test('Bearer YOK ile kritik endpointlere erişim 401/403 dönmeli', async ({ baseURL }, testInfo) => {
        const ctx = await request.newContext({ baseURL, ignoreHTTPSErrors: true });
        const targets = ['/api/admin/users', '/api/pms/bookings', '/api/audit/timeline', '/api/channel-manager/conflict-queue'];
        for (const ep of targets) {
            const r = await ctx.get(ep, { failOnStatusCode: false });
            const status = r.status();
            // Architect bulgu #2: önceki kod "herhangi 4xx" → PASS yapıyordu;
            // 404 (eksik endpoint) auth bypass'ı maskeleyebilirdi. Şimdi katı:
            // sadece 401/403 → PASS, geri kalan her şey FAIL.
            const ok = status === 401 || status === 403;
            rec(testInfo, { module: M, scope: 18, step: `Token-less ${ep}`, status: ok ? PASS : FAIL, endpoint: ep, http: status, note: ok ? '' : `Beklenen 401/403, alınan ${status}` });
        }
        await ctx.dispose();
    });

    test('URL üzerinden başka tenant verisine erişim — sahte ID ile', async ({ page }, testInfo) => {
        // 2026-05-13 cleanup: doğru route /folio-detail/:folioId (eski test /folio/:id
        // bilinmeyen path → SPA shell yüklüyordu, REVIEW'a düşüyordu).
        // FolioDetailView artık geçersiz ObjectId formatı veya backend 404'te
        // "Folio bulunamadı" NotFound ekranı gösterir (aynı turda eklendi).
        const fakeIds = [
            '000000000000000000000000', // valid hex but unknown → backend 404
            'aaaaaaaaaaaaaaaaaaaaaaaa', // valid hex but unknown → backend 404
            'invalid-id-format-xyz',    // invalid format → frontend guard 404
        ];
        for (const id of fakeIds) {
            const url = `/folio-detail/${id}`;
            const r = await page.goto(url, { waitUntil: 'networkidle' }).catch(() => null);
            const status = r?.status() ?? 0;
            // Wait for either NotFound state or fetch settle (toast errors render quickly)
            await page.waitForTimeout(800);
            const bodyTxt = (await page.locator('body').innerText().catch(() => '')).slice(0, 500);
            const safeBlock =
                /(folio bulunamad|folio not found|geçersiz folio id|invalid folio id|404|forbidden|yetki yok)/i.test(bodyTxt)
                || status === 404
                || status === 403;
            rec(testInfo, {
                module: M, scope: 18, step: `Sahte folio id ${id}`,
                status: safeBlock ? PASS : REVIEW,
                endpoint: url, http: status,
                note: safeBlock ? 'NotFound guard tetiklendi' : bodyTxt.slice(0, 80),
            });
        }
    });

    test('Console secret leak heuristik — token/password görünmez', async ({ page }, testInfo) => {
        const leaks = [];
        page.on('console', (msg) => {
            const t = msg.text();
            if (/(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)|password\s*[:=]/i.test(t)) leaks.push(t.slice(0, 100));
        });
        await page.goto('/');
        await page.waitForTimeout(2_000);
        rec(testInfo, { module: M, scope: 18, step: 'Console JWT/password leak', status: leaks.length === 0 ? PASS : FAIL, note: leaks.length ? `samples=${leaks.slice(0, 2).join(' | ')}` : '' });
    });
});
