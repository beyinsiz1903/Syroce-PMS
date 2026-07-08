# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.js >> [CRITICAL] Folio (/folio-detail)
- Location: e2e-smoke/smoke.spec.js:46:9

# Error details

```
Error: Folio: boş/hata ekranı (empty_screen). Snippet: 9+
Folio Yükle
PMS:
08 Tem 2026

expect(received).toBeTruthy()

Received: false
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - region "Notifications alt+T"
  - generic [ref=e4]:
    - banner [ref=e5]:
      - generic [ref=e7]:
        - img "Syroce" [ref=e9] [cursor=pointer]
        - generic [ref=e10]:
          - button "9+" [ref=e12] [cursor=pointer]:
            - img
            - generic [ref=e13]: 9+
          - button "Tema" [ref=e14] [cursor=pointer]:
            - img
          - button [ref=e15] [cursor=pointer]:
            - img
          - button [ref=e16] [cursor=pointer]:
            - img
    - main [ref=e17]:
      - generic [ref=e19]:
        - textbox "Folio ID girin..." [ref=e20]
        - button "Folio Yükle" [disabled]
    - generic [ref=e22]:
      - img [ref=e23]
      - generic [ref=e25]: "PMS:"
      - generic [ref=e26]: 08 Tem 2026
  - button "Personel mesajlaşmasını aç" [ref=e27] [cursor=pointer]:
    - img
  - button "Softphone" [ref=e29] [cursor=pointer]:
    - img [ref=e30]
```

# Test source

```ts
  25  | 
  26  |         // Login sonrası "boş ekran" varsa kritik failure
  27  |         expect.soft(inspect.ok, `Post-login boş/hata ekranı: ${inspect.reason}`).toBeTruthy();
  28  |         // Console errors raporlanır ama login adımı için bloke etmez
  29  |         if (consoleErrors.length) {
  30  |             test.info().annotations.push({
  31  |                 type: 'console-errors',
  32  |                 description: JSON.stringify(consoleErrors.slice(0, 5)),
  33  |             });
  34  |         }
  35  |         if (networkErrors.length) {
  36  |             test.info().annotations.push({
  37  |                 type: 'network-errors',
  38  |                 description: JSON.stringify(networkErrors.slice(0, 5)),
  39  |             });
  40  |         }
  41  |     });
  42  | });
  43  | 
  44  | for (const route of ROUTES) {
  45  |     const tag = route.critical ? '[CRITICAL]' : '[secondary]';
  46  |     test(`${tag} ${route.label} (${route.path})`, async ({ page }) => {
  47  |         const obs = attachObservers(page);
  48  | 
  49  |         // Her test bağımsız login (storageState paylaşmıyoruz — env'den
  50  |         // gelen admin'in tüm sayfalara erişmesi bekleniyor)
  51  |         await loginUI(page);
  52  | 
  53  |         const navStart = Date.now();
  54  |         const navResp = await page.goto(route.path, { waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => null);
  55  |         await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
  56  |         const navDurationMs = Date.now() - navStart;
  57  | 
  58  |         // Document HTTP status (frontend SPA — genelde 200 ya da 304)
  59  |         const httpStatus = navResp?.status() ?? 0;
  60  | 
  61  |         // Sayfa içeriği inspect
  62  |         const inspect = await inspectPageContent(page);
  63  | 
  64  |         // Güvenli buton tıklamaları (sadece critical sayfalarda)
  65  |         let clickedButtons = [];
  66  |         if (route.critical && inspect.ok) {
  67  |             clickedButtons = await clickSafeButtons(page, 2);
  68  |         }
  69  | 
  70  |         const { consoleErrors, networkErrors } = obs.flush();
  71  | 
  72  |         // Annotations — markdown reporter bunları yakalayıp özetler
  73  |         test.info().annotations.push({ type: 'route-key', description: route.key });
  74  |         test.info().annotations.push({ type: 'route-path', description: route.path });
  75  |         test.info().annotations.push({ type: 'route-critical', description: String(route.critical) });
  76  |         test.info().annotations.push({ type: 'http-status', description: String(httpStatus) });
  77  |         test.info().annotations.push({ type: 'nav-ms', description: String(navDurationMs) });
  78  |         test.info().annotations.push({ type: 'inspect', description: JSON.stringify(inspect) });
  79  | 
  80  |         // F9A Round-2 (architect feedback): PII/token leak findings görünür olmalı.
  81  |         // inspectPageContent dönüşünde pii_findings varsa md-reporter
  82  |         // finding kanalına emit et — sessizce annotation içinde kaybolmasın.
  83  |         if (inspect.pii_findings && inspect.pii_findings.length > 0) {
  84  |             test.info().annotations.push({
  85  |                 type: 'finding',
  86  |                 description: JSON.stringify({
  87  |                     severity: route.critical ? 'P1' : 'P2',
  88  |                     module: 'smoke_pii_scan',
  89  |                     title: `PII/token leak pattern detected in DOM: ${route.label}`,
  90  |                     detail: `path=${route.path} findings=${inspect.pii_findings.join(',')}`,
  91  |                 }),
  92  |             });
  93  |         }
  94  |         test.info().annotations.push({
  95  |             type: 'console-errors-count',
  96  |             description: String(consoleErrors.length),
  97  |         });
  98  |         test.info().annotations.push({
  99  |             type: 'network-errors-count',
  100 |             description: String(networkErrors.length),
  101 |         });
  102 |         if (consoleErrors.length) {
  103 |             test.info().annotations.push({
  104 |                 type: 'console-errors',
  105 |                 description: JSON.stringify(consoleErrors.slice(0, 5)),
  106 |             });
  107 |         }
  108 |         if (networkErrors.length) {
  109 |             test.info().annotations.push({
  110 |                 type: 'network-errors',
  111 |                 description: JSON.stringify(networkErrors.slice(0, 5)),
  112 |             });
  113 |         }
  114 |         if (clickedButtons.length) {
  115 |             test.info().annotations.push({
  116 |                 type: 'safe-clicks',
  117 |                 description: clickedButtons.join(' | '),
  118 |             });
  119 |         }
  120 | 
  121 |         // Assertions:
  122 |         //   CRITICAL sayfa: boş/hata ekranı → FAIL; console/network 0 olmalı
  123 |         //   SECONDARY sayfa: sadece soft uyarı
  124 |         if (route.critical) {
> 125 |             expect(inspect.ok, `${route.label}: boş/hata ekranı (${inspect.reason}). Snippet: ${inspect.snippet || '-'}`).toBeTruthy();
      |                                                                                                                           ^ Error: Folio: boş/hata ekranı (empty_screen). Snippet: 9+
  126 |             expect(consoleErrors.length, `${route.label}: ${consoleErrors.length} console error (allowlist sonrası)`).toBe(0);
  127 |             expect(networkErrors.length, `${route.label}: ${networkErrors.length} network error (allowlist sonrası)`).toBe(0);
  128 |             // F9A: CRITICAL sayfada PII/token leak = hard fail (security gate)
  129 |             expect(
  130 |                 (inspect.pii_findings || []).length,
  131 |                 `${route.label}: DOM içinde PII/token leak pattern: ${(inspect.pii_findings || []).join(',')}`,
  132 |             ).toBe(0);
  133 |         } else {
  134 |             expect.soft(inspect.ok, `${route.label}: boş/hata ekranı (secondary)`).toBeTruthy();
  135 |             // F9A: SECONDARY sayfada PII leak → soft fail (görünür, suite bloke etmez)
  136 |             expect.soft(
  137 |                 (inspect.pii_findings || []).length,
  138 |                 `${route.label}: DOM içinde PII/token leak pattern (secondary): ${(inspect.pii_findings || []).join(',')}`,
  139 |             ).toBe(0);
  140 |         }
  141 |     });
  142 | }
  143 | 
```