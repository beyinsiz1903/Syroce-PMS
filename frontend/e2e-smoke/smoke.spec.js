// ─────────────────────────────────────────────────────────────────────────
// UI E2E SMOKE — pilot/canlı uygulama nezaket testi.
// ─────────────────────────────────────────────────────────────────────────
// Her ROUTE için:
//   1) Navigasyon (waitUntil=networkidle, soft-fallback)
//   2) Boş ekran / 404 / 500 / Error UI tespit
//   3) Console error + network 4xx/5xx (allowlist'li)
//   4) Güvenli buton tıklamaları (sadece "Yenile" / "Ara" benzeri)
//
// Destructive eylem YOK: silme, ödeme, iptal, vardiya kapama, force-checkout.
// ─────────────────────────────────────────────────────────────────────────

import { test, expect } from '@playwright/test';
import { ROUTES } from './routes.js';
import { loginUI, attachObservers, inspectPageContent, clickSafeButtons } from './fixtures.js';

test.describe.serial('UI smoke — login + dashboard', () => {
    test('Login → dashboard yönlenir', async ({ page }) => {
        const obs = attachObservers(page);
        await loginUI(page);
        // Dashboard ya da herhangi bir /app/* sayfasına düşmeli
        await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
        const inspect = await inspectPageContent(page);
        const { consoleErrors, networkErrors } = obs.flush();

        // Login sonrası "boş ekran" varsa kritik failure
        expect.soft(inspect.ok, `Post-login boş/hata ekranı: ${inspect.reason}`).toBeTruthy();
        // Console errors raporlanır ama login adımı için bloke etmez
        if (consoleErrors.length) {
            test.info().annotations.push({
                type: 'console-errors',
                description: JSON.stringify(consoleErrors.slice(0, 5)),
            });
        }
        if (networkErrors.length) {
            test.info().annotations.push({
                type: 'network-errors',
                description: JSON.stringify(networkErrors.slice(0, 5)),
            });
        }
    });
});

for (const route of ROUTES) {
    const tag = route.critical ? '[CRITICAL]' : '[secondary]';
    test(`${tag} ${route.label} (${route.path})`, async ({ page }) => {
        const obs = attachObservers(page);

        // Her test bağımsız login (storageState paylaşmıyoruz — env'den
        // gelen admin'in tüm sayfalara erişmesi bekleniyor)
        await loginUI(page);

        const navStart = Date.now();
        const navResp = await page.goto(route.path, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => null);
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
        const navDurationMs = Date.now() - navStart;

        // Document HTTP status (frontend SPA — genelde 200 ya da 304)
        const httpStatus = navResp?.status() ?? 0;

        // Sayfa içeriği inspect
        const inspect = await inspectPageContent(page);

        // Güvenli buton tıklamaları (sadece critical sayfalarda)
        let clickedButtons = [];
        if (route.critical && inspect.ok) {
            clickedButtons = await clickSafeButtons(page, 2);
        }

        const { consoleErrors, networkErrors } = obs.flush();

        // Annotations — markdown reporter bunları yakalayıp özetler
        test.info().annotations.push({ type: 'route-key', description: route.key });
        test.info().annotations.push({ type: 'route-path', description: route.path });
        test.info().annotations.push({ type: 'route-critical', description: String(route.critical) });
        test.info().annotations.push({ type: 'http-status', description: String(httpStatus) });
        test.info().annotations.push({ type: 'nav-ms', description: String(navDurationMs) });
        test.info().annotations.push({ type: 'inspect', description: JSON.stringify(inspect) });

        // F9A Round-2 (architect feedback): PII/token leak findings görünür olmalı.
        // inspectPageContent dönüşünde pii_findings varsa md-reporter
        // finding kanalına emit et — sessizce annotation içinde kaybolmasın.
        if (inspect.pii_findings && inspect.pii_findings.length > 0) {
            test.info().annotations.push({
                type: 'finding',
                description: JSON.stringify({
                    severity: route.critical ? 'P1' : 'P2',
                    module: 'smoke_pii_scan',
                    title: `PII/token leak pattern detected in DOM: ${route.label}`,
                    detail: `path=${route.path} findings=${inspect.pii_findings.join(',')}`,
                }),
            });
        }
        test.info().annotations.push({
            type: 'console-errors-count',
            description: String(consoleErrors.length),
        });
        test.info().annotations.push({
            type: 'network-errors-count',
            description: String(networkErrors.length),
        });
        if (consoleErrors.length) {
            test.info().annotations.push({
                type: 'console-errors',
                description: JSON.stringify(consoleErrors.slice(0, 5)),
            });
        }
        if (networkErrors.length) {
            test.info().annotations.push({
                type: 'network-errors',
                description: JSON.stringify(networkErrors.slice(0, 5)),
            });
        }
        if (clickedButtons.length) {
            test.info().annotations.push({
                type: 'safe-clicks',
                description: clickedButtons.join(' | '),
            });
        }

        // Assertions:
        //   CRITICAL sayfa: boş/hata ekranı → FAIL; console/network 0 olmalı
        //   SECONDARY sayfa: sadece soft uyarı
        if (route.critical) {
            expect(inspect.ok, `${route.label}: boş/hata ekranı (${inspect.reason}). Snippet: ${inspect.snippet || '-'}`).toBeTruthy();
            expect(consoleErrors.length, `${route.label}: ${consoleErrors.length} console error (allowlist sonrası)`).toBe(0);
            expect(networkErrors.length, `${route.label}: ${networkErrors.length} network error (allowlist sonrası)`).toBe(0);
            // F9A: CRITICAL sayfada PII/token leak = hard fail (security gate)
            expect(
                (inspect.pii_findings || []).length,
                `${route.label}: DOM içinde PII/token leak pattern: ${(inspect.pii_findings || []).join(',')}`,
            ).toBe(0);
        } else {
            expect.soft(inspect.ok, `${route.label}: boş/hata ekranı (secondary)`).toBeTruthy();
            // F9A: SECONDARY sayfada PII leak → soft fail (görünür, suite bloke etmez)
            expect.soft(
                (inspect.pii_findings || []).length,
                `${route.label}: DOM içinde PII/token leak pattern (secondary): ${(inspect.pii_findings || []).join(',')}`,
            ).toBe(0);
        }
    });
}
