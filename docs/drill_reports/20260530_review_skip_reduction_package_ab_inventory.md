# REVIEW/SKIP Reduction — Package A+B Inventory (Post-Run #167)

**Baseline:** Run #167 (official), commit `0b99607fe3a64a7ada660d1f1bcb8607bd47f5dd`,
702 test, PASS/FAIL/REVIEW/SKIP=1379/0/48/44, P0/P1/P2/P3=0/0/58/1,
external_calls=[], pilot_drift=0, GO WITH WATCH.

**Amaç:** REVIEW(48)/SKIP(44)/P2(58)'i düşür; FAIL/P0/P1=0 koru. Yalnız düşük
riskli **ENV/posture (Paket A)** + gerçek güvenli **seed/data-state (Paket B)**.
Baseline pointer TAŞINMAZ. Full suite KOŞTURULMAZ (operatör dispatch).

**Doktrin:** fake-green YOK · RBAC/auth zayıflatma YOK · gerçek prod secret YOK ·
pilot mutation YOK (read-only anchor hariç, açıkça belgeli) · external_calls=[].

---

## Kategori sözlüğü

1. ENV_SECRET_POSTURE — eksik env/secret; backend kodu zaten doğru.
2. SEED_DATA_STATE — stress tenant'a güvenli seed/fixture eksiği.
3. PRODUCT_CONTRACT_DECISION — ürün/iş-kuralı kararı (ayrı paket C).
4. ROADMAP_BACKLOG — ürün henüz yok; deploy/roadmap.
5. RBAC_POLICY — by-design rol/erişim kararı.
6. ENDPOINT_SURFACE — path-drift veya mount/deploy.
7. TEST_EXPECTATION_DRIFT — spec beklentisi gerçek davranışla uyuşmuyor.
8. PERFORMANCE_WATCH — informational P2/P3 izleme.
9. INTENTIONAL_FAIL_CLOSED — bilinçli fail-closed; 2xx yapmak YASAK.
10. DO_NOT_TOUCH — değiştirilemez/riskli; honest REVIEW kalır.

---

## Önemli mimari ayrım — CI runner env vs backend deployment env

Stress suite iki ayrı ortam kullanır:
- **CI runner** (`.github/workflows/stress.yml`): Playwright koşar, `E2E_BASE_URL`'e
  HTTP atar. Runner env'i YALNIZ test'in kendisinin kullandığı değerler için
  anlamlıdır (ör. imzalama HMAC secret'ı). `HOTELRUNNER_WEBHOOK_SECRET` runner'da
  zaten set (line 105) — çünkü test payload'ı runner'da imzalanır.
- **Stress BACKEND deployment** (operatör-kontrollü, repl dışı devops): KBS_TEST_MODE,
  GRAPHQL_INTROSPECTION, EXELY_*, HOTELRUNNER_WEBHOOK_SECRET **mirror** burada okunur.
  Agent bu deployment env'ini SET EDEMEZ → operatör devops runbook'u.

Sonuç: Paket A'da agent'ın **kod** görevi yalnız Exely test-auth-mode gate'idir
(W6 deferred). KBS/GraphQL/HotelRunner backend zaten fail-closed/doğru; eksik olan
stress backend deployment env'i (operatör devops, aşağıda tablo).

---

## Paket A — ENV_SECRET_POSTURE

| # | Item | Spec | Backend durumu | Agent aksiyonu | Operatör devops |
|---|---|---|---|---|---|
| A1 | Exely valid-path (G testi) | `50-cm-webhooks-exely.spec.js` | `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK` var (operatör KULLANMA dedi); `EXELY_TEST_WEBHOOK_AUTH_MODE` YOK | **KOD: çok-koşullu fail-closed test-auth gate ekle** + pytest | stress backend'e `EXELY_TEST_WEBHOOK_AUTH_MODE=open_for_testing` + E2E_* flags |
| A2 | KBS TEST- prefix kontratı | `65-identity-reporting-*` | `_kbs_test_mode()` zaten `KBS_TEST_MODE=1` okur, TEST- prefix zorlar | KOD YOK (zaten doğru) | stress backend'e `KBS_TEST_MODE=1` |
| A3 | GraphQL introspection kapalı | `40-graphql-tenant-isolation.spec.js` | `_introspection_enabled()` default fail-closed OFF; yalnız explicit `true/1` açar | KOD YOK (zaten doğru) | stress backend'de `GRAPHQL_INTROSPECTION` unset veya `false` (drift varsa düzelt) |
| A4 | HotelRunner imzalı valid-path | `51-cm-hotelrunner-outbox.spec.js` | HMAC doğrulama backend'de mevcut | KOD YOK (runner secret zaten wired) | stress backend `HOTELRUNNER_WEBHOOK_SECRET` = runner ile AYNI değer |

**A kararı:** Yalnız **A1 kod gerektirir**. A2/A3/A4 operatör backend-deployment env;
agent kör env-wiring eklemez (runner env'i backend'i etkilemez → fake-green olurdu).

---

## Paket B — SEED_DATA_STATE (Wave 7 kör-seed yasağı altında)

| # | Item | Spec | Sınıf | Güvenli seed mümkün mü | Aksiyon |
|---|---|---|---|---|---|
| B1 | payment manual idempotency — active shift yok | `98-payment-pos-reconciliation*` | SEED_DATA_STATE | Spec kendi izole shift'ini açıp kapatabilir (uniq_tenant_open_shift'e saygı) | **İncele; spec self-open güvenliyse uygula** |
| B2 | 24h simulation scarcity (bookings=2 vs seed=500) | `99-full-24h-hotel-simulation.spec.js` | TEST_EXPECTATION_DRIFT (muhtemel) | Harvest/query prefix drift olabilir → kör seed DEĞİL | **İncele; sadece drift ise düzelt** |
| B3 | folio-mass void charge/payment örneği | `04-folio-mass.spec.js` | ENDPOINT_SURFACE / TEST_DRIFT | Okuma endpoint/alias eksikliği; seed değil | İncele; path-drift ise düzelt, değilse REVIEW |
| B4 | notification activity feed empty | `45-notification-batch-dryrun.spec.js` | RESOLVED (W8/9) | — | Kapalı; tekrar açma |
| B5 | city ledger transfer pre-req | `25-finance-cityledger.spec.js` | ROADMAP_BACKLOG | Transfer endpoint yoksa seed anlamsız | REVIEW kalır, belgele |
| B6 | POS recipe/BOM | `98-pos-kds-inventory.spec.js` | DO_NOT_TOUCH (entitlement module-blocked) | Hayır (entitlement yok) | REVIEW kalır |
| B7 | VCC stress booking | `98-vcc-pci-compliance.spec.js` | RBAC_POLICY | cashier_supervisor rol gerekir; PCI mask korunmalı | Paket C/RBAC turu |
| B8 | accommodation tax pilot declaration | `98-konaklama-vergisi-dryrun.spec.js` | DO_NOT_TOUCH (pilot mutation riski) | Yalnız read-only anchor, onaylı | REVIEW kalır; pilot mutation YASAK |

**B kararı:** Yalnız **B1/B2/B3 incelenir**; sadece gerçekten güvenli + endpoint-bağımsız
+ yeşil-kırmayan olanlar uygulanır. Gerisi doğru sınıfa reclassify, honest REVIEW.

---

## PRODUCT_CONTRACT / RBAC / ROADMAP (Paket C — bu turda DEĞİL)

- e-Fatura VKN/TCKN `customer_type`-zorunlu (geriye-uyum+migration) — C.
- revenue `dry_run` server-side kill-switch (çok-endpoint) — C.
- B2B per-subrouter scope — C.
- CRM contract approval lifecycle — C.
- KVKK anonymize-only policy netleştirme — C (CONFIRM by-design).
- admin/settings surface, digital key / QR rotation, websocket enterprise_live — C/roadmap.

---

## Gerçekçi hedef (operatör)

REVIEW 48 → 38-42 · SKIP 44 → 32-36 · P2 58 → 45-50. Tek turda sıfırlama YOK.

## Bu turun somut teslimi

1. A1 — Exely test-auth gate (backend kod + pytest).
2. A2/A3/A4 — operatör devops env runbook (kod yok).
3. B1/B2/B3 — incele; yalnız güvenli olanı uygula.
4. candidate doc + GOTCHAS + replit.md (env notu değiştiyse).
5. architect review PASS.
