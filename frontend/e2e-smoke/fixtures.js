// ─────────────────────────────────────────────────────────────────────────
// Smoke suite — login fixture + page observers.
// ─────────────────────────────────────────────────────────────────────────
// Credentials EXCLUSIVELY from env:
//   E2E_BASE_URL          (taşıma katmanı — playwright.smoke.config.js'de)
//   E2E_ADMIN_EMAIL       (login)
//   E2E_ADMIN_PASSWORD    (login)
// Hardcoded fallback YOK — eksikse setup() FAIL (env hijack riskini önler).
// ─────────────────────────────────────────────────────────────────────────

import { expect } from '@playwright/test';
import { CONSOLE_ERROR_ALLOWLIST, NETWORK_ERROR_ALLOWLIST } from './routes.js';

export function requireEnv(name) {
    const v = process.env[name];
    if (!v) {
        throw new Error(
            `[smoke] ${name} env-var zorunlu. Komut: ` +
            `E2E_BASE_URL=... E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... yarn test:e2e:smoke`
        );
    }
    return v;
}

export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL || '';
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || '';

/**
 * UI üzerinden login. AuthPage email/password form'una doldurur, dashboard'a
 * yönlendirme bekler. Başarısızlık halinde test FAIL (suite önkoşulu).
 */
export async function loginUI(page) {
    requireEnv('E2E_ADMIN_EMAIL');
    requireEnv('E2E_ADMIN_PASSWORD');

    await page.goto('/auth', { waitUntil: 'domcontentloaded' });

    const emailInput = page
        .locator('[data-testid="hotel-login-email"], input[type="email"], input[name="email"]')
        .first();
    const passwordInput = page
        .locator('[data-testid="hotel-login-password"], input[type="password"], input[name="password"]')
        .first();

    await expect(emailInput, 'Login email input görünmüyor').toBeVisible({ timeout: 20_000 });
    await emailInput.fill(ADMIN_EMAIL);
    await passwordInput.fill(ADMIN_PASSWORD);

    const submit = page
        .getByRole('button', { name: /giriş yap|sign in|log in/i })
        .first();
    await submit.click();

    await page.waitForURL((u) => !/\/(auth|login)/i.test(u.pathname), { timeout: 30_000 });
}

/**
 * Sayfa observer — console error + network error topla. Test bitince
 * `flush()` çağrılınca allowlist'e göre filtrelenmiş listeyi döner.
 */
export function attachObservers(page) {
    /** @type {{type:string,text:string,location?:string}[]} */
    const consoleErrors = [];
    /** @type {{url:string,status:number,statusText:string}[]} */
    const networkErrors = [];

    page.on('console', (msg) => {
        if (msg.type() !== 'error') return;
        const text = msg.text();
        if (CONSOLE_ERROR_ALLOWLIST.some((p) => text.toLowerCase().includes(p.toLowerCase()))) return;
        consoleErrors.push({
            type: msg.type(),
            text,
            location: `${msg.location()?.url || ''}:${msg.location()?.lineNumber || ''}`,
        });
    });

    page.on('pageerror', (err) => {
        consoleErrors.push({ type: 'pageerror', text: String(err && err.message || err) });
    });

    page.on('response', (res) => {
        const url = res.url();
        const status = res.status();
        if (status < 400) return;
        if (NETWORK_ERROR_ALLOWLIST.some((re) => re.test(url))) return;
        // 401/403 normal kabul: bazı endpoint'ler tenant/role'e bağlı.
        if (status === 401 || status === 403) return;
        networkErrors.push({ url, status, statusText: res.statusText() });
    });

    return {
        flush() {
            return { consoleErrors, networkErrors };
        },
    };
}

/**
 * Sayfanın "boş ekran" / "hata sayfası" olup olmadığını kontrol et.
 *   - body innerText < 50 char → boş
 *   - "404", "500", "Error", "Hata", "Bir şeyler ters" → error UI
 *   - F9A: PII / token leak sanity scan (DOM içinde JWT, kart no, çoklu e-posta)
 * Döner: { ok:boolean, reason?:string, snippet?:string, pii_findings?:string[] }
 */
export async function inspectPageContent(page) {
    const text = (await page.locator('body').innerText().catch(() => '')) || '';
    const trimmed = text.trim();

    if (trimmed.length < 50) {
        return { ok: false, reason: 'empty_screen', snippet: trimmed };
    }

    // Yaygın hata UI sinyalleri (hem TR hem EN)
    const errorPatterns = [
        /\b404\b.*\b(not found|bulunam)/i,
        /\b500\b.*\b(error|hata|internal)/i,
        /something went wrong/i,
        /bir şeyler (ters|yanlış)/i,
        /unhandled (error|exception)/i,
        /uygulama (çöktü|hata)/i,
    ];
    for (const re of errorPatterns) {
        if (re.test(trimmed)) {
            return { ok: false, reason: 'error_ui', snippet: trimmed.slice(0, 200) };
        }
    }

    // F9A: PII / token leak scan — DOM içinde **görünür metin** olarak
    // hassas pattern var mı? Strict değil (false-positive olabilir), ama
    // smoke seviyesinde sanity: gerçek leak'i fark etmemize yetecek kadar.
    // Bulgular informational; suite'i bloke etmez (annotate edilir).
    const piiFindings = [];

    // JWT (header.payload.signature — base64url segmentleri)
    if (/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/.test(trimmed)) {
        piiFindings.push('jwt_in_dom');
    }
    // Kart no (13–19 hane, Luhn check değil ama spaced veya unspaced)
    if (/\b(?:\d[ -]?){13,19}\b/.test(trimmed) && /\b4\d{3}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b/.test(trimmed)) {
        piiFindings.push('card_pan_like');
    }
    // CVV/CVC inline (label + 3-4 hane)
    if (/\b(cvv|cvc)[\s:]+\d{3,4}\b/i.test(trimmed)) {
        piiFindings.push('cvv_inline');
    }
    // Bearer / api-key string'i (DOM'a stringify edilmiş response leak)
    if (/\b(bearer\s+[A-Za-z0-9_\-.]{20,}|api[_-]?key["':\s]+[A-Za-z0-9_\-]{20,})\b/i.test(trimmed)) {
        piiFindings.push('bearer_or_apikey_in_dom');
    }

    return { ok: true, ...(piiFindings.length ? { pii_findings: piiFindings } : {}) };
}

/**
 * Güvenli buton tıklama — sadece NON-DESTRUCTIVE eylemler.
 * Destructive black-list (case-insensitive substring on button text):
 *   sil, delete, remove, iptal, cancel, kapat shift, geri al, refund,
 *   void, ödeme al, çıkış (=logout when at top level)
 *
 * Beyaz liste (denenecek): yenile, refresh, ara, search, filtrele, filter
 */
export async function clickSafeButtons(page, maxClicks = 3) {
    const SAFE_PATTERNS = [/^yenile$/i, /^refresh$/i, /^ara$/i, /^search$/i];
    const DESTRUCTIVE = [
        /sil/i, /delete/i, /remove/i, /iptal/i, /cancel/i, /vardiya kapat/i,
        /geri al/i, /refund/i, /void/i, /ödeme al/i, /tahsil/i, /onayla/i,
        /confirm.*delete/i, /logout/i, /çıkış yap/i,
    ];

    const buttons = await page.locator('button:visible, [role="button"]:visible').all();
    let clicks = 0;
    const clicked = [];

    for (const btn of buttons) {
        if (clicks >= maxClicks) break;
        const label = ((await btn.textContent().catch(() => '')) || '').trim();
        if (!label) continue;
        if (DESTRUCTIVE.some((re) => re.test(label))) continue;
        if (!SAFE_PATTERNS.some((re) => re.test(label))) continue;

        try {
            await btn.click({ timeout: 3_000, trial: false });
            clicked.push(label);
            clicks += 1;
            // Tıklama sonrası kısa render bekle, ama navigasyon yaptırma
            await page.waitForTimeout(500);
        } catch {
            /* skip — element detached vs.; smoke kapsamı dışı */
        }
    }
    return clicked;
}
