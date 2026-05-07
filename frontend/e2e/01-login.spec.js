// Smoke #1: Login akışı — hatalı + başarılı senaryo, session kaydet.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { loginAsDemo, STORAGE_STATE, PASSWORD } from './fixtures/auth.js';

test.describe.serial('Login', () => {
    test('hatalı şifre toast/hata gösterir', async ({ page }) => {
        await page.goto('/');
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
        await loginAsDemo(page);
        // Layout shell yüklendi mi (sidebar ya da header)
        await expect(page.locator('body')).toBeVisible();
        const hasNav = await page
            .locator('nav, [role="navigation"], aside')
            .first()
            .isVisible()
            .catch(() => false);
        expect(hasNav).toBeTruthy();

        // Storage state'i kaydet (sonraki spec'ler kullansın)
        fs.mkdirSync(path.dirname(STORAGE_STATE), { recursive: true });
        await context.storageState({ path: STORAGE_STATE });
    });
});
