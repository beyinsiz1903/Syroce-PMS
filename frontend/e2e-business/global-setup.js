import { chromium, request } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const AUTH_DIR = path.join(process.cwd(), 'e2e-business', '.auth');
const AUTH_FILE = path.join(AUTH_DIR, 'admin.json');

export default async function globalSetup() {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    // Data-registry reset: her run'da temiz başlasın; cleanup ledger'ı geçmiş
    // run'lardan kirlenmesin (önceki turda 20-recap çalışsa bile).
    try { fs.writeFileSync(path.join(AUTH_DIR, 'data-registry.json'), JSON.stringify({ entities: [] }, null, 2)); }
    catch (e) { console.warn('[global-setup] data-registry reset başarısız:', e.message); }
    const baseURL = process.env.E2E_BASE_URL;
    const email = process.env.E2E_ADMIN_EMAIL;
    const password = process.env.E2E_ADMIN_PASSWORD;

    const browser = await chromium.launch();
    const ctx = await browser.newContext({ baseURL, ignoreHTTPSErrors: true });
    const page = await ctx.newPage();
    try {
        await page.goto('/login', { waitUntil: 'domcontentloaded', timeout: 30_000 });

        const emailInput = page.locator('[data-testid="hotel-login-email"]').first();
        const passInput = page.locator('[data-testid="hotel-login-password"]').first();
        const submitBtn = page.locator('[data-testid="hotel-login-btn"]').first();

        await emailInput.waitFor({ state: 'visible', timeout: 15_000 });
        await emailInput.fill(email);
        await passInput.fill(password);
        await Promise.all([
            page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => {}),
            submitBtn.click(),
        ]);

        await page.waitForURL((url) => !/\/login\b/.test(url.pathname), { timeout: 25_000 }).catch(() => {});
        const stillOnLogin = /\/login\b/.test(new URL(page.url()).pathname);
        if (stillOnLogin) {
            const html = await page.content().catch(() => '');
            const snippet = html.slice(0, 400);
            throw new Error(`[global-setup] Login başarısız. URL: ${page.url()}\nİlk 400 char: ${snippet}`);
        }

        await ctx.storageState({ path: AUTH_FILE });
        console.log(`[global-setup] Login OK; storageState yazıldı: ${AUTH_FILE}`);
    } finally {
        await ctx.close();
        await browser.close();
    }

    // Bearer token'ı diğer testlerin API çağrıları için ayrıca yakala
    try {
        const apiCtx = await request.newContext({ baseURL, ignoreHTTPSErrors: true });
        const resp = await apiCtx.post('/api/auth/login', { data: { email, password }, failOnStatusCode: false });
        if (resp.ok()) {
            const body = await resp.json().catch(() => ({}));
            const token = body?.access_token || body?.token;
            if (token) {
                fs.writeFileSync(path.join(AUTH_DIR, 'token.json'), JSON.stringify({ token, capturedAt: Date.now() }, null, 2));
                console.log('[global-setup] Bearer token cache yazıldı.');
            }
        } else {
            console.warn(`[global-setup] /api/auth/login non-OK: ${resp.status()} (token cache atlandı)`);
        }
        await apiCtx.dispose();
    } catch (err) {
        console.warn('[global-setup] Token cache başarısız:', err.message);
    }
}
