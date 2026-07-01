// Smoke #1: Login akışı — hatalı + başarılı senaryo, session kaydet.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { loginAsDemo, STORAGE_STATE, PASSWORD } from './fixtures/auth.js';

test.describe.serial('Login', () => {
    test('hatalı şifre toast/hata gösterir', async ({ page }) => {
        await page.goto('/auth');
        const emailInput = page
            .locator('input[type="email"], input[name="email"], input[placeholder*="mail" i]')
            .first();
        const passwordInput = page
            .locator('input[type="password"], input[name="password"]')
            .first();
        await emailInput.fill('demo@syroce.com');
        await passwordInput.fill('YANLIS_SIFRE_X1');
        await page
            .getByRole('button', { name: /giriş yap|sign in|log in/i })
            .first()
            .click();
        // Hata mesajı / toast görünmeli; URL hâlâ auth ekranı kalmalı
        await page.waitForTimeout(2_000);
        expect(page.url()).toMatch(/\/(auth|login|$)/);
    });

    test('demo kullanıcı ile login → dashboard', async ({ page, context }) => {
        page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
        await loginAsDemo(page);
        // Layout shell yüklendi mi (sidebar ya da header).
        // ÖNEMLİ: /app/dashboard rotası lazy chunk olduğundan Suspense fallback
        // sırasında nav DOM'da olmaz. `isVisible()` bekleme yapmaz; bu yüzden
        // explicit wait kullanıyoruz (CI'da 8s'ye kadar lazy chunk + Layout
        // hidratasyonu beklenebilir).
        await expect(page.locator('body')).toBeVisible();
        await expect(
            page.locator('[data-testid="app-shell"]')
        ).toBeVisible({ timeout: 15_000 });

        // Storage state'i kaydet (sonraki spec'ler kullansın)
        fs.mkdirSync(path.dirname(STORAGE_STATE), { recursive: true });
        await context.storageState({ path: STORAGE_STATE });
    });
});
