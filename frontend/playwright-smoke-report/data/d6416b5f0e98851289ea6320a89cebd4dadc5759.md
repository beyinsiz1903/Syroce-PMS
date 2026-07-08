# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.js >> [CRITICAL] PMS Operasyonlar (/pms-operations)
- Location: e2e-smoke/smoke.spec.js:46:9

# Error details

```
Error: PMS Operasyonlar: 2 console error (allowlist sonrası)

expect(received).toBe(expected) // Object.is equality

Expected: 0
Received: 2
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
      - generic [ref=e18]:
        - generic [ref=e19]:
          - generic [ref=e20]:
            - heading "PMS Operasyonlar" [level=1] [ref=e21]
            - paragraph [ref=e22]: 2026-07-08 - Syroce Demo Hotel
          - button "Yenile" [active] [ref=e23] [cursor=pointer]:
            - img
            - text: Yenile
        - generic [ref=e24]:
          - generic [ref=e27]:
            - generic [ref=e28]:
              - paragraph [ref=e29]: Gelenler
              - paragraph [ref=e30]: "0"
            - img [ref=e31]
          - generic [ref=e36]:
            - generic [ref=e37]:
              - paragraph [ref=e38]: Gidenler
              - paragraph [ref=e39]: "0"
            - img [ref=e40]
          - generic [ref=e44]:
            - generic [ref=e45]:
              - paragraph [ref=e46]: Konaklayan
              - paragraph [ref=e47]: "19"
            - img [ref=e48]
          - generic [ref=e55]:
            - generic [ref=e56]:
              - paragraph [ref=e57]: Hazır Oda
              - paragraph [ref=e58]: "7"
              - paragraph [ref=e59]: / 30
            - img [ref=e60]
          - generic [ref=e65]:
            - generic [ref=e66]:
              - paragraph [ref=e67]: Kirli Oda
              - paragraph [ref=e68]: "22"
            - img [ref=e69]
          - generic [ref=e73]:
            - generic [ref=e74]:
              - paragraph [ref=e75]: Folio Sorunları
              - paragraph [ref=e76]: "14"
            - img [ref=e77]
          - generic [ref=e81]:
            - generic [ref=e82]:
              - paragraph [ref=e83]: İstisnalar
              - paragraph [ref=e84]: "0"
            - img [ref=e85]
        - generic [ref=e89]:
          - generic [ref=e91]:
            - img [ref=e92]
            - text: Oda Durumu Genel Bakış
          - generic [ref=e96]:
            - generic [ref=e97]:
              - 'generic "Müsait: 7" [ref=e98]'
              - 'generic "Dolu: 1" [ref=e99]'
              - 'generic "Kirli: 21" [ref=e100]'
              - 'generic "Temizleniyor: 1" [ref=e101]'
            - generic [ref=e102]:
              - generic [ref=e103]:
                - generic [ref=e105]: Müsait
                - generic [ref=e106]: "7"
              - generic [ref=e107]:
                - generic [ref=e109]: Dolu
                - generic [ref=e110]: "1"
              - generic [ref=e111]:
                - generic [ref=e113]: Kirli
                - generic [ref=e114]: "21"
              - generic [ref=e115]:
                - generic [ref=e117]: Temizleniyor
                - generic [ref=e118]: "1"
              - generic [ref=e119]:
                - generic [ref=e121]: Kontrol Edildi
                - generic [ref=e122]: "0"
              - generic [ref=e123]:
                - generic [ref=e125]: Arızalı
                - generic [ref=e126]: "0"
              - generic [ref=e127]:
                - generic [ref=e129]: Bakımda
                - generic [ref=e130]: "0"
        - generic [ref=e131]:
          - tablist [ref=e132]:
            - tab "Genel Bakış" [selected] [ref=e133] [cursor=pointer]:
              - img [ref=e134]
              - text: Genel Bakış
            - tab "Trendler" [ref=e137] [cursor=pointer]:
              - img [ref=e138]
              - text: Trendler
            - tab "Gece Denetimi" [ref=e141] [cursor=pointer]:
              - img [ref=e142]
              - text: Gece Denetimi
            - tab "Çoklu Tesis" [ref=e144] [cursor=pointer]:
              - img [ref=e145]
              - text: Çoklu Tesis
            - tab "Otomat. Temizlik" [ref=e149] [cursor=pointer]:
              - img [ref=e150]
              - text: Otomat. Temizlik
            - tab "Denetim İzi" [ref=e152] [cursor=pointer]:
              - img [ref=e153]
              - text: Denetim İzi
          - tabpanel "Genel Bakış" [ref=e156]:
            - generic [ref=e157]:
              - generic [ref=e158]:
                - generic [ref=e160]: Bugünkü Gelenler (0)
                - paragraph [ref=e162]: Bugün gelen misafir yok
              - generic [ref=e163]:
                - generic [ref=e165]: Bugünkü Gidenler (0)
                - paragraph [ref=e167]: Bugün ayrılan misafir yok
              - generic [ref=e168]:
                - generic [ref=e170]: Denetim İstisnaları (0)
                - paragraph [ref=e172]: Açık istisna yok
              - generic [ref=e173]:
                - generic [ref=e175]: Engellenen Girişler (0)
                - paragraph [ref=e177]: Engellenen giriş yok
    - generic [ref=e179]:
      - img [ref=e180]
      - generic [ref=e182]: "PMS:"
      - generic [ref=e183]: 08 Tem 2026
  - button "Personel mesajlaşmasını aç" [ref=e184] [cursor=pointer]:
    - img
  - button "Softphone" [ref=e186] [cursor=pointer]:
    - img [ref=e187]
```

# Test source

```ts
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
  125 |             expect(inspect.ok, `${route.label}: boş/hata ekranı (${inspect.reason}). Snippet: ${inspect.snippet || '-'}`).toBeTruthy();
> 126 |             expect(consoleErrors.length, `${route.label}: ${consoleErrors.length} console error (allowlist sonrası)`).toBe(0);
      |                                                                                                                       ^ Error: PMS Operasyonlar: 2 console error (allowlist sonrası)
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