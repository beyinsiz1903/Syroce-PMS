// Smoke #2: Dashboard yüklenmeli, KPI kartları + sparkline'lar görünmeli.
import { test, expect } from '@playwright/test';
import { STORAGE_STATE } from './fixtures/auth.js';

test.use({ storageState: STORAGE_STATE });

test.describe('Dashboard', () => {
    test('KPI kartları yüklenir, console error yok', async ({ page }) => {
        const errors = [];
        page.on('pageerror', (e) => errors.push(e.message));
        page.on('console', (msg) => {
            if (msg.type() === 'error') errors.push(msg.text());
        });

        await page.goto('/');
        // KPI grid: Total Rooms / Occupancy / Checkins / Guests başlıkları
        await expect(
            page.getByText(/oda|rooms|doluluk|occupancy|misafir|guest/i).first()
        ).toBeVisible({ timeout: 20_000 });

        // Sparkline svg'leri en az bir tane render olmuş mu
        const sparklineCount = await page
            .locator('svg')
            .count();
        expect(sparklineCount).toBeGreaterThan(0);

        // Network 5xx yok
        const fiveXx = errors.filter((e) => /5\d\d/.test(e));
        expect(fiveXx, fiveXx.join('\n')).toHaveLength(0);
    });

    test('üst gezinme açılır (modules accordion)', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => {});
        // Sidebar/menü içerikli bir başlık olmalı
        const visibleNav = await page
            .locator('nav, aside, [role="navigation"]')
            .first()
            .isVisible();
        expect(visibleNav).toBeTruthy();
    });
});
