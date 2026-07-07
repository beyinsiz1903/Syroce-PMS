# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 01-login.spec.js >> Login >> hatalı şifre toast/hata gösterir
- Location: e2e/01-login.spec.js:8:9

# Error details

```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000/auth
Call log:
  - navigating to "http://localhost:3000/auth", waiting until "load"

```

# Test source

```ts
  1  | // Smoke #1: Login akışı — hatalı + başarılı senaryo, session kaydet.
  2  | import { test, expect } from '@playwright/test';
  3  | import fs from 'node:fs';
  4  | import path from 'node:path';
  5  | import { loginAsDemo, STORAGE_STATE, PASSWORD } from './fixtures/auth.js';
  6  | 
  7  | test.describe.serial('Login', () => {
  8  |     test('hatalı şifre toast/hata gösterir', async ({ page }) => {
> 9  |         await page.goto('/auth');
     |                    ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000/auth
  10 |         const emailInput = page
  11 |             .locator('input[type="email"], input[name="email"], input[placeholder*="mail" i]')
  12 |             .first();
  13 |         const passwordInput = page
  14 |             .locator('input[type="password"], input[name="password"]')
  15 |             .first();
  16 |         await emailInput.fill('demo@syroce.com');
  17 |         await passwordInput.fill('YANLIS_SIFRE_X1');
  18 |         await page
  19 |             .getByRole('button', { name: /giriş yap|sign in|log in/i })
  20 |             .first()
  21 |             .click();
  22 |         // Hata mesajı / toast görünmeli; URL hâlâ auth ekranı kalmalı
  23 |         await page.waitForTimeout(2_000);
  24 |         expect(page.url()).toMatch(/\/(auth|login|$)/);
  25 |     });
  26 | 
  27 |     test('demo kullanıcı ile login → dashboard', async ({ page, context }) => {
  28 |         page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
  29 |         await loginAsDemo(page);
  30 |         // Layout shell yüklendi mi (sidebar ya da header).
  31 |         // ÖNEMLİ: /app/dashboard rotası lazy chunk olduğundan Suspense fallback
  32 |         // sırasında nav DOM'da olmaz. `isVisible()` bekleme yapmaz; bu yüzden
  33 |         // explicit wait kullanıyoruz (CI'da 8s'ye kadar lazy chunk + Layout
  34 |         // hidratasyonu beklenebilir).
  35 |         await expect(page.locator('body')).toBeVisible();
  36 |         await expect(
  37 |             page.locator('[data-testid="app-shell"]')
  38 |         ).toBeVisible({ timeout: 15_000 });
  39 | 
  40 |         // Storage state'i kaydet (sonraki spec'ler kullansın)
  41 |         fs.mkdirSync(path.dirname(STORAGE_STATE), { recursive: true });
  42 |         await context.storageState({ path: STORAGE_STATE });
  43 |     });
  44 | });
  45 | 
```