# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.js >> [secondary] Control Plane (/control-plane)
- Location: e2e-smoke/smoke.spec.js:46:9

# Error details

```
Error: Control Plane: boş/hata ekranı (secondary)

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
        - generic [ref=e8] [cursor=pointer]:
          - img "Syroce" [ref=e9]
          - generic [ref=e10]:
            - generic [ref=e11]: Syroce PMS
            - generic "Syroce Demo Hotel" [ref=e12]
        - navigation [ref=e13]:
          - button "Kontrol Paneli" [ref=e14] [cursor=pointer]:
            - img
            - generic [ref=e15]: Kontrol Paneli
          - button "Ön Büro & Rez." [ref=e17] [cursor=pointer]:
            - img
            - generic [ref=e18]: Ön Büro & Rez.
            - img
          - button "Satış & Gelir" [ref=e19] [cursor=pointer]:
            - img
            - generic [ref=e20]: Satış & Gelir
            - img
          - button "Misafir & CRM" [ref=e21] [cursor=pointer]:
            - img
            - generic [ref=e22]: Misafir & CRM
            - img
          - button "Operasyon" [ref=e23] [cursor=pointer]:
            - img
            - generic [ref=e24]: Operasyon
            - img
          - button "Restoran & F&B" [ref=e25] [cursor=pointer]:
            - img
            - generic [ref=e26]: Restoran & F&B
            - img
          - button "Arka Ofis" [ref=e27] [cursor=pointer]:
            - img
            - generic [ref=e28]: Arka Ofis
            - img
          - button "Raporlar" [ref=e29] [cursor=pointer]:
            - img
            - generic [ref=e30]: Raporlar
            - img
          - button "Kanallar & Sistem" [ref=e31] [cursor=pointer]:
            - img
            - generic [ref=e32]: Kanallar & Sistem
            - img
        - generic [ref=e33]:
          - button [ref=e34] [cursor=pointer]:
            - img
          - generic [ref=e36]:
            - img [ref=e37]
            - combobox [ref=e41] [cursor=pointer]:
              - generic: 🇹🇷 Türkçe
              - img [ref=e42]
          - button "Push kapalı" [ref=e44] [cursor=pointer]:
            - img
            - generic [ref=e45]: Push kapalı
          - button "9+" [ref=e47] [cursor=pointer]:
            - img
            - generic [ref=e48]: 9+
          - button "Tema" [ref=e49] [cursor=pointer]:
            - img
          - button "Demo Kullanıcı" [ref=e50] [cursor=pointer]:
            - img
            - generic [ref=e51]: Demo Kullanıcı
    - main [ref=e52]:
      - generic [ref=e54]:
        - paragraph [ref=e55]: Something went wrong
        - paragraph [ref=e56]: Cannot read properties of undefined (reading 'id')
        - button "Retry" [ref=e57] [cursor=pointer]
    - generic [ref=e59]:
      - img [ref=e60]
      - generic [ref=e62]: "PMS:"
      - generic [ref=e63]: 08 Tem 2026
  - button "Personel mesajlaşmasını aç" [ref=e64] [cursor=pointer]:
    - img
  - button "Softphone" [ref=e66] [cursor=pointer]:
    - img [ref=e67]
```

# Test source

```ts
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
  125 |             expect(inspect.ok, `${route.label}: boş/hata ekranı (${inspect.reason}). Snippet: ${inspect.snippet || '-'}`).toBeTruthy();
  126 |             expect(consoleErrors.length, `${route.label}: ${consoleErrors.length} console error (allowlist sonrası)`).toBe(0);
  127 |             expect(networkErrors.length, `${route.label}: ${networkErrors.length} network error (allowlist sonrası)`).toBe(0);
  128 |             // F9A: CRITICAL sayfada PII/token leak = hard fail (security gate)
  129 |             expect(
  130 |                 (inspect.pii_findings || []).length,
  131 |                 `${route.label}: DOM içinde PII/token leak pattern: ${(inspect.pii_findings || []).join(',')}`,
  132 |             ).toBe(0);
  133 |         } else {
> 134 |             expect.soft(inspect.ok, `${route.label}: boş/hata ekranı (secondary)`).toBeTruthy();
      |                                                                                    ^ Error: Control Plane: boş/hata ekranı (secondary)
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