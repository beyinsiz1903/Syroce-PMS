// Login helper + storage state generator.
// İlk spec çalıştığında auth.json dosyası oluşur ve sonraki spec'ler
// `test.use({ storageState: ... })` ile session'ı yeniden kullanır.

import { expect } from '@playwright/test';
import path from 'node:path';

export const HOTEL_ID = process.env.E2E_HOTEL_ID || '100001';
export const USERNAME = process.env.E2E_USERNAME || 'demo';
export const PASSWORD = process.env.E2E_PASSWORD || 'demo123';
export const STORAGE_STATE = path.resolve('./e2e/.auth/state.json');

/**
 * AuthPage'de "Otel Girişi" sekmesinden login olur.
 * AuthPage email/password alanları bekliyor (demo seed: demo@syroce.com).
 */
export async function loginAsDemo(page) {
    const email = process.env.E2E_EMAIL || 'demo@syroce.com';
    await page.goto('/');
    // AuthPage yüklendi mi?
    await expect(
        page.getByRole('heading', { name: /syroce|otel|hotel|giriş/i }).first()
    ).toBeVisible({ timeout: 15_000 });

    // Email + password input'larını generic seç (placeholder/label varyasyonları)
    const emailInput = page
        .locator('input[type="email"], input[name="email"], input[placeholder*="mail" i]')
        .first();
    const passwordInput = page
        .locator('input[type="password"], input[name="password"]')
        .first();

    await emailInput.fill(email);
    await passwordInput.fill(PASSWORD);

    const submitButton = page
        .getByRole('button', { name: /giriş yap|sign in|log in/i })
        .first();
    await submitButton.click();

    // Başarılı login: dashboard/ana ekrana yönlenir
    await page.waitForURL((url) => !/\/(auth|login)/i.test(url.pathname), {
        timeout: 20_000,
    });
}
