# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.js >> [CRITICAL] Folio (/folio-detail)
- Location: e2e-smoke/smoke.spec.js:46:9

# Error details

```
TimeoutError: page.waitForURL: Timeout 30000ms exceeded.
=========================== logs ===========================
waiting for navigation until "load"
============================================================
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - region "Notifications alt+T"
  - main "Syroce PMS — Giriş ve Kayıt Sayfası" [ref=e4]:
    - generic [ref=e5]:
      - generic [ref=e6]:
        - link "Syroce Logo" [ref=e7] [cursor=pointer]:
          - /url: /
          - img "Syroce Logo" [ref=e9]
        - paragraph [ref=e10]: Kapsamlı Otel Yönetim Platformu
        - generic [ref=e12]:
          - img [ref=e13]
          - combobox [ref=e17] [cursor=pointer]:
            - generic: 🇹🇷 Türkçe
            - img [ref=e18]
      - generic [ref=e20]:
        - generic [ref=e21]:
          - heading "Hoş Geldiniz" [level=2] [ref=e22]
          - paragraph [ref=e23]: Hesabınıza giriş yapın veya yeni bir hesap oluşturun
        - generic "Giriş veya kayıt sekmesi" [ref=e24]:
          - tablist "Hesap erişimi sekmeleri" [ref=e25]:
            - tab "Giriş sekmesi" [selected] [ref=e26] [cursor=pointer]: Giriş Yap
            - tab "Kayıt olma sekmesi" [ref=e27] [cursor=pointer]: Kayıt Ol
          - tabpanel "Giriş sekmesi" [ref=e28]:
            - form "Otel yönetici giriş formu" [ref=e29]:
              - generic [ref=e30]:
                - text: E-posta
                - textbox "E-posta adresi" [ref=e31]:
                  - /placeholder: ornek@hotel.com
                  - text: demo@syroce.com
              - generic [ref=e32]:
                - text: Şifre
                - textbox "Şifre" [ref=e33]:
                  - /placeholder: ••••••••
                  - text: demo123
              - button "Şifremi unuttum — şifre sıfırlama formunu aç" [ref=e35] [cursor=pointer]: Şifremi Unuttum
              - button "Giriş yap" [ref=e36] [cursor=pointer]: Giriş Yap
```

# Test source

```ts
  1   | // ─────────────────────────────────────────────────────────────────────────
  2   | // Smoke suite — login fixture + page observers.
  3   | // ─────────────────────────────────────────────────────────────────────────
  4   | // Credentials EXCLUSIVELY from env:
  5   | //   E2E_BASE_URL          (taşıma katmanı — playwright.smoke.config.js'de)
  6   | //   E2E_ADMIN_EMAIL       (login)
  7   | //   E2E_ADMIN_PASSWORD    (login)
  8   | // Hardcoded fallback YOK — eksikse setup() FAIL (env hijack riskini önler).
  9   | // ─────────────────────────────────────────────────────────────────────────
  10  | 
  11  | import { expect } from '@playwright/test';
  12  | import { CONSOLE_ERROR_ALLOWLIST, NETWORK_ERROR_ALLOWLIST } from './routes.js';
  13  | 
  14  | export function requireEnv(name) {
  15  |     const v = process.env[name];
  16  |     if (!v) {
  17  |         throw new Error(
  18  |             `[smoke] ${name} env-var zorunlu. Komut: ` +
  19  |             `E2E_BASE_URL=... E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... yarn test:e2e:smoke`
  20  |         );
  21  |     }
  22  |     return v;
  23  | }
  24  | 
  25  | export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL || '';
  26  | export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || '';
  27  | 
  28  | /**
  29  |  * UI üzerinden login. AuthPage email/password form'una doldurur, dashboard'a
  30  |  * yönlendirme bekler. Başarısızlık halinde test FAIL (suite önkoşulu).
  31  |  */
  32  | export async function loginUI(page) {
  33  |     requireEnv('E2E_ADMIN_EMAIL');
  34  |     requireEnv('E2E_ADMIN_PASSWORD');
  35  | 
  36  |     await page.goto('/auth', { waitUntil: 'domcontentloaded' });
  37  | 
  38  |     const emailInput = page
  39  |         .locator('[data-testid="hotel-login-email"], input[type="email"], input[name="email"]')
  40  |         .first();
  41  |     const passwordInput = page
  42  |         .locator('[data-testid="hotel-login-password"], input[type="password"], input[name="password"]')
  43  |         .first();
  44  | 
  45  |     await expect(emailInput, 'Login email input görünmüyor').toBeVisible({ timeout: 20_000 });
  46  |     await emailInput.fill(ADMIN_EMAIL);
  47  |     await passwordInput.fill(ADMIN_PASSWORD);
  48  | 
  49  |     const submit = page
  50  |         .getByRole('button', { name: /giriş yap|sign in|log in/i })
  51  |         .first();
  52  |     await submit.click();
  53  | 
> 54  |     await page.waitForURL((u) => !/\/(auth|login)/i.test(u.pathname), { timeout: 30_000 });
      |                ^ TimeoutError: page.waitForURL: Timeout 30000ms exceeded.
  55  | }
  56  | 
  57  | /**
  58  |  * Sayfa observer — console error + network error topla. Test bitince
  59  |  * `flush()` çağrılınca allowlist'e göre filtrelenmiş listeyi döner.
  60  |  */
  61  | export function attachObservers(page) {
  62  |     /** @type {{type:string,text:string,location?:string}[]} */
  63  |     const consoleErrors = [];
  64  |     /** @type {{url:string,status:number,statusText:string}[]} */
  65  |     const networkErrors = [];
  66  | 
  67  |     page.on('console', (msg) => {
  68  |         if (msg.type() !== 'error') return;
  69  |         const text = msg.text();
  70  |         if (CONSOLE_ERROR_ALLOWLIST.some((p) => text.toLowerCase().includes(p.toLowerCase()))) return;
  71  |         consoleErrors.push({
  72  |             type: msg.type(),
  73  |             text,
  74  |             location: `${msg.location()?.url || ''}:${msg.location()?.lineNumber || ''}`,
  75  |         });
  76  |     });
  77  | 
  78  |     page.on('pageerror', (err) => {
  79  |         consoleErrors.push({ type: 'pageerror', text: String(err && err.message || err) });
  80  |     });
  81  | 
  82  |     page.on('response', (res) => {
  83  |         const url = res.url();
  84  |         const status = res.status();
  85  |         if (status < 400) return;
  86  |         if (NETWORK_ERROR_ALLOWLIST.some((re) => re.test(url))) return;
  87  |         // 401/403 normal kabul: bazı endpoint'ler tenant/role'e bağlı.
  88  |         if (status === 401 || status === 403) return;
  89  |         networkErrors.push({ url, status, statusText: res.statusText() });
  90  |     });
  91  | 
  92  |     return {
  93  |         flush() {
  94  |             return { consoleErrors, networkErrors };
  95  |         },
  96  |     };
  97  | }
  98  | 
  99  | /**
  100 |  * Sayfanın "boş ekran" / "hata sayfası" olup olmadığını kontrol et.
  101 |  *   - body innerText < 50 char → boş
  102 |  *   - "404", "500", "Error", "Hata", "Bir şeyler ters" → error UI
  103 |  *   - F9A: PII / token leak sanity scan (DOM içinde JWT, kart no, çoklu e-posta)
  104 |  * Döner: { ok:boolean, reason?:string, snippet?:string, pii_findings?:string[] }
  105 |  */
  106 | export async function inspectPageContent(page) {
  107 |     const text = (await page.locator('body').innerText().catch(() => '')) || '';
  108 |     const trimmed = text.trim();
  109 | 
  110 |     if (trimmed.length < 50) {
  111 |         return { ok: false, reason: 'empty_screen', snippet: trimmed };
  112 |     }
  113 | 
  114 |     // Yaygın hata UI sinyalleri (hem TR hem EN)
  115 |     const errorPatterns = [
  116 |         /\b404\b.*\b(not found|bulunam)/i,
  117 |         /\b500\b.*\b(error|hata|internal)/i,
  118 |         /something went wrong/i,
  119 |         /bir şeyler (ters|yanlış)/i,
  120 |         /unhandled (error|exception)/i,
  121 |         /uygulama (çöktü|hata)/i,
  122 |     ];
  123 |     for (const re of errorPatterns) {
  124 |         if (re.test(trimmed)) {
  125 |             return { ok: false, reason: 'error_ui', snippet: trimmed.slice(0, 200) };
  126 |         }
  127 |     }
  128 | 
  129 |     // F9A: PII / token leak scan — DOM içinde **görünür metin** olarak
  130 |     // hassas pattern var mı? Strict değil (false-positive olabilir), ama
  131 |     // smoke seviyesinde sanity: gerçek leak'i fark etmemize yetecek kadar.
  132 |     // Bulgular informational; suite'i bloke etmez (annotate edilir).
  133 |     const piiFindings = [];
  134 | 
  135 |     // JWT (header.payload.signature — base64url segmentleri)
  136 |     if (/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/.test(trimmed)) {
  137 |         piiFindings.push('jwt_in_dom');
  138 |     }
  139 |     // Kart no (13–19 hane, Luhn check değil ama spaced veya unspaced)
  140 |     if (/\b(?:\d[ -]?){13,19}\b/.test(trimmed) && /\b4\d{3}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b/.test(trimmed)) {
  141 |         piiFindings.push('card_pan_like');
  142 |     }
  143 |     // CVV/CVC inline (label + 3-4 hane)
  144 |     if (/\b(cvv|cvc)[\s:]+\d{3,4}\b/i.test(trimmed)) {
  145 |         piiFindings.push('cvv_inline');
  146 |     }
  147 |     // Bearer / api-key string'i (DOM'a stringify edilmiş response leak)
  148 |     if (/\b(bearer\s+[A-Za-z0-9_\-.]{20,}|api[_-]?key["':\s]+[A-Za-z0-9_\-]{20,})\b/i.test(trimmed)) {
  149 |         piiFindings.push('bearer_or_apikey_in_dom');
  150 |     }
  151 | 
  152 |     return { ok: true, ...(piiFindings.length ? { pii_findings: piiFindings } : {}) };
  153 | }
  154 | 
```