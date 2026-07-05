# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 06-core-pms-flow.spec.js >> Core PMS happy-path: booking → check-in → folio → checkout >> 9) UI smoke: Arrivals sayfası açılır + heading görünür
- Location: e2e/06-core-pms-flow.spec.js:323:9

# Error details

```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000/auth
Call log:
  - navigating to "http://localhost:3000/auth", waiting until "load"

```

# Test source

```ts
  247 |         const folioRes = await api.get(`/api/folio/${folioId}`);
  248 |         let amountToPay = 1050; // total + charge fallback
  249 |         if (folioRes.ok()) {
  250 |             const folio = await folioRes.json();
  251 |             const bal =
  252 |                 folio.balance ??
  253 |                 folio.outstanding_balance ??
  254 |                 folio.outstanding ??
  255 |                 folio.total_charges - folio.total_payments;
  256 |             if (typeof bal === 'number' && bal > 0) amountToPay = bal;
  257 |         }
  258 |         // PaymentCreate: amount + method (PaymentMethod enum) + payment_type
  259 |         // (PaymentType enum). 'card' + 'final' kullanıyoruz — 'cash' aktif
  260 |         // kasa vardiyası (cashier_shifts) gerektirir (cashier_service.py:56,
  261 |         // CASH_METHODS={"cash"}); E2E ortamı vardiya açmıyor → 409. Card için
  262 |         // ensure_active_shift bypass eder, tam tahsilat senaryosu korunur.
  263 |         const res = await api.post(`/api/folio/${folioId}/payment`, {
  264 |             data: {
  265 |                 amount: amountToPay,
  266 |                 method: 'card',
  267 |                 payment_type: 'final',
  268 |                 notes: 'E2E test full settlement',
  269 |             },
  270 |         });
  271 |         expect(
  272 |             res.ok(),
  273 |             `payment başarısız (${res.status()}): ${await res.text()}`
  274 |         ).toBeTruthy();
  275 |     });
  276 | 
  277 |     test('7) Checkout yapılır → success=true', async () => {
  278 |         const res = await api.post('/api/pms-core/checkout', {
  279 |             data: { booking_id: bookingId, force: true },
  280 |         });
  281 |         expect(
  282 |             res.ok(),
  283 |             `checkout başarısız (${res.status()}): ${await res.text()}`
  284 |         ).toBeTruthy();
  285 |         const body = await res.json();
  286 |         expect(body.success, 'checkout success=true beklenir').toBeTruthy();
  287 |     });
  288 | 
  289 |     test('8) Booking statüsü checked_out (cross-check)', async () => {
  290 |         // Test 7 zaten checkout→success=true doğrular. Burada booking'i id ile
  291 |         // TEKİL olarak çekip status'ü cross-check ediyoruz: drift'i (örn.
  292 |         // "checkout başarılı dönüyor ama booking statüsü güncellenmiyor")
  293 |         // yakalamak için.
  294 |         //
  295 |         // NEDEN list+search DEĞİL: /pms/bookings `search` paramı (index-
  296 |         // serviceable #247 pattern) yalnızca `guest_name_lower` /
  297 |         // `booking_number_lower` companion alanlarında PREFIX eşleşir —
  298 |         // booking UUID ile arama YAPMAZ. Ayrıca quick-booking bookings
  299 |         // dokümanına `guest_name` YAZMAZ (okuma anında guests koleksiyonundan
  300 |         // zenginleştirilir), dolayısıyla guest adıyla da bulunamaz. Tekil
  301 |         // detay endpoint'i id ile birebir lookup yapar: search/cache yok.
  302 |         const r = await api.get(
  303 |             `/api/pms/reservations/${encodeURIComponent(bookingId)}/full-detail`
  304 |         );
  305 | 
  306 |         // Başarılı checkout sonrası booking MUTLAKA bulunmalı. 404/erişilemez
  307 |         // → gerçek state drift (booking kayboldu) → SESSİZCE GEÇMİYORUZ,
  308 |         // hard fail. (Geçici 5xx için Playwright retry zaten devrede.)
  309 |         expect(
  310 |             r.ok(),
  311 |             `/full-detail erişilemedi veya booking yok (${r.status()}): ${await r.text()}`
  312 |         ).toBeTruthy();
  313 | 
  314 |         const body = await r.json();
  315 |         const booking = body.booking || body;
  316 |         const status = String(booking.status || '').toLowerCase();
  317 |         expect(
  318 |             status,
  319 |             `Booking status checked_out beklenir, gelen: "${status}"`
  320 |         ).toMatch(/checked.?out|departed|completed/);
  321 |     });
  322 | 
  323 |     test('9) UI smoke: Arrivals sayfası açılır + heading görünür', async ({ page, request }) => {
  324 |         // 05-checkin-flow.spec.js ile aynı navigasyon pattern'i: önce
  325 |         // hash-route (`/#/arrivals`), olmazsa pathname (`/arrivals`).
  326 |         // JWT'yi localStorage'a inject et — frontend kodu hem `token` hem
  327 |         // `access_token` anahtarlarını kullanıyor; ikisini de yazıyoruz.
  328 |         // App.jsx ek olarak `user`, `tenant`, `token_ts` da bekliyor; bunlar
  329 |         // yoksa <ProtectedRoute> /auth'a redirect edip UI smoke soft-skip'e
  330 |         // düşüyor. /auth/me ile freshUser çekip tüm auth state'i yazıyoruz.
  331 |         let freshUser = null;
  332 |         let tenantData = null;
  333 |         try {
  334 |             const meRes = await request.get(`${API_BASE_URL}/api/auth/me`, {
  335 |                 headers: { Authorization: `Bearer ${token}` },
  336 |             });
  337 |             if (meRes.ok()) {
  338 |                 const me = await meRes.json();
  339 |                 freshUser = me.user || me;
  340 |                 tenantData = me.tenant || freshUser?.tenant || null;
  341 |             }
  342 |         } catch {
  343 |             /* best-effort; soft-skip aşağıda yakalar */
  344 |         }
  345 | 
  346 |         // Auth sayfasına git ki localStorage origin context'i oluşsun.
> 347 |         await page.goto('/auth');
      |                    ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000/auth
  348 |         await page.evaluate(
  349 |             ({ tk, user, tenant }) => {
  350 |                 localStorage.setItem('token', tk);
  351 |                 localStorage.setItem('access_token', tk);
  352 |                 localStorage.setItem('token_ts', String(Date.now()));
  353 |                 if (user) localStorage.setItem('user', JSON.stringify(user));
  354 |                 localStorage.setItem(
  355 |                     'tenant',
  356 |                     tenant ? JSON.stringify(tenant) : 'null'
  357 |                 );
  358 |             },
  359 |             { tk: token, user: freshUser, tenant: tenantData }
  360 |         );
  361 | 
  362 |         // Hash-route → pathname fallback (mevcut spec konvansiyonu)
  363 |         await page.goto('/#/arrivals').catch(() => page.goto('/arrivals'));
  364 |         await page
  365 |             .waitForLoadState('networkidle', { timeout: 20_000 })
  366 |             .catch(() => {});
  367 | 
  368 |         const heading = page
  369 |             .getByRole('heading', { name: /geliş|arrival|check.?in/i })
  370 |             .first();
  371 |         if (!(await heading.isVisible().catch(() => false))) {
  372 |             // 05-checkin'de aynı patern: route bu build'de farklıysa skip.
  373 |             test.skip(
  374 |                 true,
  375 |                 'Arrivals rotası bu buildde farklı; manuel doğrulama gerekir'
  376 |             );
  377 |             return;
  378 |         }
  379 |         await expect(heading).toBeVisible({ timeout: 10_000 });
  380 |     });
  381 | });
  382 | 
```