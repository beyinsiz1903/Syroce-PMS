// ─────────────────────────────────────────────────────────────────────────
// F10A — Mobile smoke fixtures (Playwright on Expo Web).
// ─────────────────────────────────────────────────────────────────────────
// Credentials EXCLUSIVELY from env (no hardcoded fallbacks — env-hijack
// protection mirrors frontend/e2e-smoke/fixtures.js):
//   MOBILE_E2E_BASE_URL           Expo Web bundle URL (e.g. http://localhost:8081)
//   MOBILE_E2E_FRONTDESK_EMAIL    + MOBILE_E2E_FRONTDESK_PASSWORD
//   MOBILE_E2E_GM_EMAIL           + MOBILE_E2E_GM_PASSWORD
//   MOBILE_E2E_HK_EMAIL           + MOBILE_E2E_HK_PASSWORD
//   MOBILE_E2E_GUEST_EMAIL        + MOBILE_E2E_GUEST_PASSWORD
// ─────────────────────────────────────────────────────────────────────────

import { expect, type Page } from '@playwright/test';
import { CONSOLE_ERROR_ALLOWLIST, type Role } from './routes';

export function requireEnv(name: string): string {
    const v = process.env[name];
    if (!v) {
        throw new Error(
            `[mobile-smoke] ${name} env-var zorunlu. ` +
            `Tüm değişkenler için bkz. mobile/e2e/README.md.`,
        );
    }
    return v;
}

const ROLE_CREDS: Record<Role, { emailEnv: string; passwordEnv: string }> = {
    frontdesk:    { emailEnv: 'MOBILE_E2E_FRONTDESK_EMAIL', passwordEnv: 'MOBILE_E2E_FRONTDESK_PASSWORD' },
    gm:           { emailEnv: 'MOBILE_E2E_GM_EMAIL',        passwordEnv: 'MOBILE_E2E_GM_PASSWORD' },
    housekeeping: { emailEnv: 'MOBILE_E2E_HK_EMAIL',        passwordEnv: 'MOBILE_E2E_HK_PASSWORD' },
    guest:        { emailEnv: 'MOBILE_E2E_GUEST_EMAIL',     passwordEnv: 'MOBILE_E2E_GUEST_PASSWORD' },
};

/**
 * UI-driven login through the (auth)/login screen. Uses testID-derived
 * selectors that match `mobile/app/(auth)/login.tsx`. On Expo Web,
 * `testID` becomes `data-testid`.
 */
export async function loginAsRole(page: Page, role: Role): Promise<void> {
    const { emailEnv, passwordEnv } = ROLE_CREDS[role];
    const email = requireEnv(emailEnv);
    const password = requireEnv(passwordEnv);

    await page.goto('/login', { waitUntil: 'domcontentloaded' });

    const emailInput = page.locator('[data-testid="smoke-login-email"]').first();
    const passwordInput = page.locator('[data-testid="smoke-login-password"]').first();
    const submit = page.locator('[data-testid="smoke-login-submit"]').first();

    await expect(emailInput, `Login email input görünmüyor (${role})`).toBeVisible({ timeout: 20_000 });
    await emailInput.fill(email);
    await passwordInput.fill(password);
    await submit.click();

    // AuthGate redirects to the role's root once /api/auth/login resolves.
    // Poll for either the redirect (success) or a rendered auth error, so a
    // bad/inactive MOBILE_E2E_<ROLE>_* secret fails FAST with the real reason
    // (e.g. "E-posta veya şifre hatalı") instead of an opaque 30s navigation
    // timeout. This does NOT mask failures — a genuine 401 still fails; it
    // only surfaces the cause. A true transient (no redirect AND no error)
    // still times out at 30s, but with a distinct, diagnostic message.
    const errorLoc = page.locator('[data-testid="smoke-login-error"]').first();
    const onLogin = (pathname: string) => /\/login(\?|$)/.test(pathname);
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) {
        if (!onLogin(new URL(page.url()).pathname)) return; // redirected → success
        if (await errorLoc.isVisible().catch(() => false)) {
            const msg = ((await errorLoc.innerText().catch(() => '')) || '(boş hata)').trim();
            throw new Error(
                `[mobile-smoke] Login reddedildi (${role}): "${msg}". ` +
                `Secret'ları (${emailEnv} / ${passwordEnv}) ve hesabın deploy ` +
                `backend'de aktif olduğunu doğrula.`,
            );
        }
        await page.waitForTimeout(250);
    }
    throw new Error(
        `[mobile-smoke] Login sonrası 30s içinde yönlendirme yok (${role}) ve ` +
        `auth hatası da görünmedi — olası neden: geçici ağ veya tıklama UI ` +
        `hydration'dan önce kayboldu (deploy backend login'i ~2s'de yanıtlıyor).`,
    );
}

export type ObservedError = { type: string; text: string; location?: string; url?: string };
export type ObservedNetError = { url: string; status: number; statusText: string };

const RESOURCE_STATUS_RE = /the server responded with a status of (\d{3})/i;

/**
 * Attach console + network observers. Returns a `flush()` that yields
 * filtered errors using CONSOLE_ERROR_ALLOWLIST. Network 4xx/5xx is
 * collected for diagnostic annotations; 401/403 ignored (role gating).
 *
 * Two browser-logged "Failed to load resource" console errors are
 * structurally expected on this deployment and are dropped at flush()
 * (NOT via the substring allowlist, which would also hide real broken
 * chunks/assets):
 *   - 401/403 — role gating. Mirrors the network-observer policy below;
 *     the same auth-gated fetch must not hard-fail render-only smoke when
 *     it merely surfaces as a console twin of an already-ignored 401/403.
 *   - the SPA-shell document 404 — Replit static deployments serve the
 *     SPA shell (index.html copied to 404.html, see mobile/build-web.sh)
 *     for any client route that isn't a real file, with a 404 *status*.
 *     The app boots and renders fine; the 404 is on the main-document
 *     navigation only. We record those document URLs from the response
 *     stream and drop ONLY their console twin — every sub-resource /
 *     chunk / asset 404 still fails, and inspect.ok independently proves
 *     the shell actually rendered.
 */
export function attachObservers(page: Page) {
    const consoleErrors: ObservedError[] = [];
    const networkErrors: ObservedNetError[] = [];
    const spaShellDoc404 = new Set<string>();

    page.on('console', (msg) => {
        if (msg.type() !== 'error') return;
        const text = msg.text();
        if (CONSOLE_ERROR_ALLOWLIST.some((p) => text.toLowerCase().includes(p.toLowerCase()))) return;
        consoleErrors.push({
            type: msg.type(),
            text,
            location: `${msg.location()?.url || ''}:${msg.location()?.lineNumber || ''}`,
            url: msg.location()?.url || '',
        });
    });

    page.on('pageerror', (err) => {
        consoleErrors.push({ type: 'pageerror', text: String((err && err.message) || err) });
    });

    page.on('response', (res) => {
        const status = res.status();
        const req = res.request();
        // Static-host SPA fallback: a 404 on the main-document navigation
        // is the index.html→404.html shell, not a broken resource.
        if (status === 404 && req.resourceType() === 'document' && req.isNavigationRequest()) {
            spaShellDoc404.add(res.url());
        }
        if (status < 400) return;
        if (status === 401 || status === 403) return;
        networkErrors.push({ url: res.url(), status, statusText: res.statusText() });
    });

    return {
        flush() {
            const filtered = consoleErrors.filter((e) => {
                const m = e.text.match(RESOURCE_STATUS_RE);
                if (!m) return true; // not a resource-load error → keep
                const httpStatus = Number(m[1]);
                // Role gating — twin of the network-observer 401/403 skip.
                if (httpStatus === 401 || httpStatus === 403) return false;
                // SPA-shell document 404 (and only that) — keep every other 404.
                if (httpStatus === 404 && e.url && spaShellDoc404.has(e.url)) return false;
                return true;
            });
            return { consoleErrors: filtered, networkErrors };
        },
    };
}

/**
 * F10A PII / secret leak scan — same patterns as
 * frontend/e2e-smoke/fixtures.js inspectPageContent(). Also runs on
 * the **document HTML source** so leaks living in attributes (e.g.
 * inline JSON dumps) are caught alongside visible text.
 *
 * Returns `{ ok, reason?, snippet?, pii_findings? }`. PII findings are
 * informational at the call site — the spec emits them as `finding`
 * annotations rather than hard-failing render-only smoke.
 */
export async function inspectPageContent(
    page: Page,
): Promise<{ ok: boolean; reason?: string; snippet?: string; pii_findings?: string[] }> {
    const visible = ((await page.locator('body').innerText().catch(() => '')) || '').trim();
    const html = (await page.content().catch(() => '')) || '';

    if (visible.length < 20) {
        return { ok: false, reason: 'empty_screen', snippet: visible };
    }

    const errorPatterns: RegExp[] = [
        /\b404\b.*\b(not found|bulunam)/i,
        /\b500\b.*\b(error|hata|internal)/i,
        /something went wrong/i,
        /bir şeyler (ters|yanlış)/i,
        /unhandled (error|exception)/i,
        /uygulama (çöktü|hata)/i,
    ];
    for (const re of errorPatterns) {
        if (re.test(visible)) {
            return { ok: false, reason: 'error_ui', snippet: visible.slice(0, 200) };
        }
    }

    // Scan both visible text and full HTML — `bearer …` headers logged
    // into the DOM by a misconfigured logger would otherwise hide in
    // <script> tags. Patterns are identical to the web smoke fixture.
    const haystack = `${visible}\n${html}`;
    const piiFindings: string[] = [];

    if (/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/.test(haystack)) {
        piiFindings.push('jwt_in_dom');
    }
    if (
        /\b(?:\d[ -]?){13,19}\b/.test(haystack) &&
        /\b4\d{3}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b/.test(haystack)
    ) {
        piiFindings.push('card_pan_like');
    }
    if (/\b(cvv|cvc)[\s:]+\d{3,4}\b/i.test(haystack)) {
        piiFindings.push('cvv_inline');
    }
    if (/\b(bearer\s+[A-Za-z0-9_\-.]{20,}|api[_-]?key["':\s]+[A-Za-z0-9_\-]{20,})\b/i.test(haystack)) {
        piiFindings.push('bearer_or_apikey_in_dom');
    }

    return { ok: true, ...(piiFindings.length ? { pii_findings: piiFindings } : {}) };
}
