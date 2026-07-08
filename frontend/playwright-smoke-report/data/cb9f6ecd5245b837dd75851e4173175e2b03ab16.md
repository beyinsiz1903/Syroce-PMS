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
      - generic [ref=e53]:
        - generic [ref=e54]:
          - generic [ref=e55]:
            - heading "PMS Operasyonlar" [level=1] [ref=e56]
            - paragraph [ref=e57]: 2026-07-08 - Syroce Demo Hotel
          - button "Yenile" [active] [ref=e58] [cursor=pointer]:
            - img
            - text: Yenile
        - generic [ref=e59]:
          - generic [ref=e62]:
            - generic [ref=e63]:
              - paragraph [ref=e64]: Gelenler
              - paragraph [ref=e65]: "0"
            - img [ref=e66]
          - generic [ref=e71]:
            - generic [ref=e72]:
              - paragraph [ref=e73]: Gidenler
              - paragraph [ref=e74]: "0"
            - img [ref=e75]
          - generic [ref=e79]:
            - generic [ref=e80]:
              - paragraph [ref=e81]: Konaklayan
              - paragraph [ref=e82]: "19"
            - img [ref=e83]
          - generic [ref=e90]:
            - generic [ref=e91]:
              - paragraph [ref=e92]: Hazır Oda
              - paragraph [ref=e93]: "7"
              - paragraph [ref=e94]: / 30
            - img [ref=e95]
          - generic [ref=e100]:
            - generic [ref=e101]:
              - paragraph [ref=e102]: Kirli Oda
              - paragraph [ref=e103]: "22"
            - img [ref=e104]
          - generic [ref=e108]:
            - generic [ref=e109]:
              - paragraph [ref=e110]: Folio Sorunları
              - paragraph [ref=e111]: "14"
            - img [ref=e112]
          - generic [ref=e116]:
            - generic [ref=e117]:
              - paragraph [ref=e118]: İstisnalar
              - paragraph [ref=e119]: "0"
            - img [ref=e120]
        - generic [ref=e124]:
          - generic [ref=e126]:
            - img [ref=e127]
            - text: Oda Durumu Genel Bakış
          - generic [ref=e131]:
            - generic [ref=e132]:
              - 'generic "Müsait: 7" [ref=e133]'
              - 'generic "Dolu: 1" [ref=e134]'
              - 'generic "Kirli: 21" [ref=e135]'
              - 'generic "Temizleniyor: 1" [ref=e136]'
            - generic [ref=e137]:
              - generic [ref=e138]:
                - generic [ref=e140]: Müsait
                - generic [ref=e141]: "7"
              - generic [ref=e142]:
                - generic [ref=e144]: Dolu
                - generic [ref=e145]: "1"
              - generic [ref=e146]:
                - generic [ref=e148]: Kirli
                - generic [ref=e149]: "21"
              - generic [ref=e150]:
                - generic [ref=e152]: Temizleniyor
                - generic [ref=e153]: "1"
              - generic [ref=e154]:
                - generic [ref=e156]: Kontrol Edildi
                - generic [ref=e157]: "0"
              - generic [ref=e158]:
                - generic [ref=e160]: Arızalı
                - generic [ref=e161]: "0"
              - generic [ref=e162]:
                - generic [ref=e164]: Bakımda
                - generic [ref=e165]: "0"
        - generic [ref=e166]:
          - tablist [ref=e167]:
            - tab "Genel Bakış" [selected] [ref=e168] [cursor=pointer]:
              - img [ref=e169]
              - text: Genel Bakış
            - tab "Trendler" [ref=e172] [cursor=pointer]:
              - img [ref=e173]
              - text: Trendler
            - tab "Gece Denetimi" [ref=e176] [cursor=pointer]:
              - img [ref=e177]
              - text: Gece Denetimi
            - tab "Çoklu Tesis" [ref=e179] [cursor=pointer]:
              - img [ref=e180]
              - text: Çoklu Tesis
            - tab "Otomat. Temizlik" [ref=e184] [cursor=pointer]:
              - img [ref=e185]
              - text: Otomat. Temizlik
            - tab "Denetim İzi" [ref=e187] [cursor=pointer]:
              - img [ref=e188]
              - text: Denetim İzi
          - tabpanel "Genel Bakış" [ref=e191]:
            - generic [ref=e192]:
              - generic [ref=e193]:
                - generic [ref=e195]: Bugünkü Gelenler (0)
                - paragraph [ref=e197]: Bugün gelen misafir yok
              - generic [ref=e198]:
                - generic [ref=e200]: Bugünkü Gidenler (0)
                - paragraph [ref=e202]: Bugün ayrılan misafir yok
              - generic [ref=e203]:
                - generic [ref=e205]: Denetim İstisnaları (0)
                - paragraph [ref=e207]: Açık istisna yok
              - generic [ref=e208]:
                - generic [ref=e210]: Engellenen Girişler (0)
                - paragraph [ref=e212]: Engellenen giriş yok
    - generic [ref=e214]:
      - img [ref=e215]
      - generic [ref=e217]: "PMS:"
      - generic [ref=e218]: 08 Tem 2026
  - button "Personel mesajlaşmasını aç" [ref=e219] [cursor=pointer]:
    - img
  - button "Softphone" [ref=e221] [cursor=pointer]:
    - img [ref=e222]
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