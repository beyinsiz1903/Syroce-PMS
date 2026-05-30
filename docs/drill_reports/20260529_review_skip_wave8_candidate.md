# REVIEW/SKIP Zeroing — Wave 8 Candidate (Endpoint / Mount / Surface Contract)

> **Tarih:** 2026-05-30 · **Faz:** Wave 8 (kategori 3 ENDPOINT_NOT_DEPLOYED,
> 4 FEATURE_FLAG_OFF / TEST_DRIFT) · **Baseline:** Run #162 SABİT
> (`bde7662744c9b94a5c9294fa778202d813319dfc`) — pointer TAŞINMAZ.
> Full stress suite bu turda **koşulmadı**; targeted read-only probe + tek
> test-drift düzeltmesi. "GO" / "/100" iddiası YOK.

---

## 0) Yöntem — canlı read-only probe (ground truth)

Wave 8'in kritik farkı: endpoint'lerin **gerçekten** stres ortamında ne
döndürdüğünü tahmin etmek yerine **ölçtük**. Lokal backend Atlas (shared)
DB'ye bağlı; `E2E_STRESS_ADMIN_*` ile login olup **yalnız GET** (mutasyon
yok) probe yaptık. Stres admin = tenant-scoped ADMIN (platform super_admin
DEĞİL — bilinçli; aşağıya bak).

| Probe (GET) | HTTP | Yorum |
|---|:--:|---|
| `/api/admin/tenants` | **404** | super_admin guard `not_found=True` → 404 (varlığı gizler). Stres admin platform-super-admin değil. |
| `/api/admin/feature-flags` | **404** | Aynı (entitlement_admin_router, super_admin global). |
| `/api/webhooks/status` | **404** | Aynı (webhook_admin, super_admin global). |
| `/api/webhooks/dlq` | **404** | Aynı. |
| `/api/outbox/status` | **404** | Aynı (outbox_admin, super_admin global). |
| `/api/security/audit-logs` | 200 | ADMIN/SUPER_ADMIN kabul → stres admin geçer. |
| `/api/audit/timeline` | 200 | Tenant-scoped. |
| `/api/messaging-center/settings` | 200 | **Gerçek path** (spec `/api/messaging/settings` 404). |
| `/api/messaging/settings` | **404** | Spec path-drift (legacy prefix). |
| `/api/messaging-center/delivery-logs` | 200 | Gerçek path. |
| `/api/messaging-center/activity` | 200 | Gerçek path (`activity-feed` değil). |
| `/api/channel-manager/conflict-queue/count` | 200 | Tenant-scoped, `edit_booking`. |
| `/api/infra/backup/status` | 200 | Mounted (`/api/infra`); spec L97 ile uyumlu. |
| `/api/infra-hardening/backup/status` | **404** | Yanlış prefix (gerçek `/api/infra`). |
| `/api/enterprise/ws/stats` | 200 | WS observability mounted. |
| `/api/admin/cm/outbox/stats` | **404** | Hiç yok; gerçek outbox `/api/outbox/status` (super_admin → out-of-scope). |

---

## 1) Headline bulgu

**ENDPOINT_NOT_DEPLOYED kategorisi büyük ölçüde MİSCLASSIFICATION'dır.**
Hedeflenen "404" yüzeylerinin çoğu **deploy edilmiş ve mount'lu**; 404'ün kök
sebebi:

1. **Platform-super-admin guard fail-closed 404** (kategori 8 — güvenlik
   by-design): `require_super_admin_guard(not_found=True)` super_admin
   olmayan çağırana **403 değil 404** döner (varlığı gizleme). Stres admin
   bilinçli olarak **tenant-scoped** ADMIN; platform-super-admin DEĞİL.
   Bunu 2xx yapmak = stres tenant'a platform-super-admin yetkisi vermek =
   **AUTH WEAKENING → YASAK.** Doğru cevap **404'tür**.
2. **Spec path-drift** (kategori 4): gerçek endpoint farklı path'te yaşıyor
   (`/api/messaging-center/*`, `/api/finance/folio/list`, `/api/infra/...`).
3. **Gerçek absent** (kategori 3 roadmap / deploy-only): `pos_tables` list,
   waitlist `/promote`, mice F&B order-send, QR rotation HTTP endpoint.

> **Sonuç:** Wave 8'de mount edilecek "eksik ürün yüzeyi" **yok**; var olanlar
> ya doğru-guard'lı (by-design) ya path-drift ya roadmap. **Kör stub / boş
> endpoint EKLENMEDİ.** Tek kod değişikliği: 1 test-drift düzeltmesi.

---

## 2) Uygulanan düzeltme (kategori 4 — DONE)

### `45-notification-batch-dryrun` — messaging path + field drift
- **Sorun:** spec `/api/messaging/settings|send|delivery-logs|activity-feed`
  probe ediyordu → hepsi 404 → `moduleBlocked=true` → A/B/C **SKIP** + P2×3.
  Spec body `{channel, to, ...}` kullanıyordu; gerçek model `SendReq` alanı
  **`recipient`**.
- **Gerçek kontrat** (canlı probe + kod ile doğrulandı):
  `/api/messaging-center/settings|send|delivery-logs|activity` (router prefix
  `/api/messaging-center`, `backend/routers/messaging.py:19`); `SendReq`
  `{channel, recipient, subject?, body}` (`:395`).
- **Düzeltme:** spec'teki 6 path prefix `/api/messaging` → `/api/messaging-center`,
  `activity-feed` → `activity`, ve 3 POST body `to:` → `recipient:`.
- **Neden fake-green DEĞİL:** Bu spec'in amacı = **no 5xx**, **delivery-logs
  cross-tenant leak yok**, **PII mask**, **external_calls=[]**, **pilot_drift=0**.
  Düzeltme bu güvenlik assertion'larını SKIP'ten **gerçekten koşar** hale
  getiriyor (zayıflatma DEĞİL, güçlendirme). Send `recipient`+`manage_sales`
  ile çalışmazsa bile 4xx (422/403) döner → `serverErr=0` hard-assert tutar;
  hiçbir assertion gevşetilmedi. Yazımlar stres-tenant'a (in_app), pilot'a
  DEĞİL; DISABLE_EXPO_PUSH ile external HTTP fail-closed.
- **Step C (activity feed) ek güçlendirme (architect round-1 + round-2 bulguları):**
  ilk düzeltme yalnız path/field idi; Step C hâlâ `feed.body.notifications|items`
  parse ediyordu, ama gerçek kontrat `{ activities: [...] }`. Bu, PII/leak
  assertion'ını **boş kümede vacuous-PASS** yapardı (fake-green riski). Düzeltmeler:
  - **(1) Parse anahtarı** `activities` (legacy `notifications`/`items` fallback
    geri-uyum için korundu).
  - **(2) Cross-tenant leak** taraması (delivery-logs ile aynı `"PILOT_`/`"PROD_"`
    kontratı) + hard `expect(feedLeaks).toBe(0)` — kesin tenant ihlali → hard gate.
  - **(3) Structural PII** `assertPiiMasked(items, ['phone','email'])` — helper
    yalnız bilinen field-key+pattern tarar (phone/email/identity_number/passport/
    iban). Round-2 bulgusu: `recipient`/`message` alan adlarını helper'a vermek
    **no-op** (sahte kapsam iddiası) → bilinçle EKLENMEDİ.
  - **(4) Serbest-metin PII** (round-2 gerçek kapatma): activity `message`/`title`
    içinde gerçek-domain email regex taraması. Demo seed (`_get_demo_delivery_logs`)
    gerçek-domain (`@gmail.com`) recipient kullandığından gerçek-domain email
    **BEKLENEN** olabilir → **SOFT REVIEW** (P2), hard-fail DEĞİL (false-P0 riski).
    Sentetik test domain'leri (`.invalid`/`.test`/`.example`) muaf.
  - **(5) Boş feed** → 2xx+0-item **REVIEW** (P2) → boş feed artık PASS sayılmaz.
  - **Genuine Wave 9 pointer:** `/api/messaging-center/activity` yalnız
    `get_current_user` ile korunur, `require_op("view_guest_list")` YOK; oysa
    `/delivery-logs` bu op'u ister. Activity feed recipient'i `message`'da ifşa
    eder → recipient PII gate+mask **Wave 9 RBAC/ürün-kontrat kararı** (test-drift
    DEĞİL; bilinçli kategori-3 dokümantasyon).
  - Step B (delivery-logs) zaten doğru `logs` anahtarını parse ediyor (değişmedi).
- **Beklenen etki:** notification_batch P2×3 + 3 SKIP → gerçek PASS/REVIEW
  (boş feed REVIEW, dolu feed PASS; CI-deferred doğrulama). `node --check` PASS,
  gerçek legacy `/api/messaging/*` path yok (yalnız bilinçli geri-uyum fallback).

---

## 3) Per-surface karar tablosu

| Yüzey / spec | Kalem | Kök sebep | KARAR | Kategori |
|---|---|---|---|:--:|
| `admin_rbac`, `31-settings-audit` | `/api/admin/tenants` 404 | Platform-super-admin guard 404 (stres admin tenant-scoped) | **By-design.** Endpoint mounted+doğru. Spec bu global endpoint'i "module gate" sanıyor; tenant-scoped admin için out-of-stress-scope. **Auth zayıflatma YOK.** | 8 |
| admin feature-flags | `/api/admin/feature-flags` 404 | Aynı (super_admin global) | **By-design.** Mounted; 404 = güvenli cevap. | 8 |
| `webhook_admin_dlq` | `/api/webhooks/status`+`/dlq` 404 | Aynı (super_admin global) | **By-design.** Ops super_admin yüzeyi; stres admin erişemez (doğru). | 8 |
| `ops_readiness` / `bulk-seed-500` | outbox depth/stats | `/api/outbox/status` super_admin (404); `/api/admin/cm/outbox/stats` hiç yok | **By-design + drift.** Outbox observability super_admin global → stres admin out-of-scope; spec "manuel doğrula" REVIEW dürüsttür. | 8/4 |
| `notification_batch` (`45-...`) | `/api/messaging/*` 404 | Path + field drift | **DÜZELTİLDİ** (§2). | 4 |
| `messaging` (`13-...`) | conversations REVIEW (P3 yavaş) | Performans watch | Endpoint var/çalışır; P3 informational (slow). Wave 8 dışı (perf). | 7 |
| `payment_pos_reconciliation` | `/api/pos/tables` 404 | Endpoint absent (yalnız `POST /api/pos/v2/tables/reserve`) | **Roadmap.** POS table-list ürün yüzeyi henüz yok; kör mount YOK. Spec'in `/api/pms/folios` kısmı drift (gerçek `/api/finance/folio/list`). | 3/4 |
| `payment_pos_reconciliation` | SKIP "no open cashier shift" | Shift kapalı seed (Wave 7) | **By-design.** Wave 7 doctrine: OPEN-shift kör seed reddedildi; spec self-open. | 8 |
| `public_token_rotation` | `/api/rooms` 404 | Public room-read main app'te yok (yalnız quick-id microservice); QR rotation env-only | **Deploy-only + drift.** Rooms staff-only (`/api/rooms/...`); QR rotation `ROOM_QR_SECRET` env ile rotate (HTTP endpoint yok → spec "rotation absent" REVIEW dürüsttür). Tampered-token P0 assert'leri zaten public `/api/public/room-qr/...` üzerinde koşuyor. | 3 |
| `reservation_deep` | waitlist `/promote` 404 | `/promote` endpoint yok | **Roadmap.** SPA waitlist (`/api/spa/waitlist`) var; generic promote yüzeyi yok → spec "mount yok" REVIEW dürüsttür. Group rooming-list + city-ledger transfer VAR (P0 assert'leri koşar). | 3 |
| `ws_tenant_isolation` | WS 404 | — | **Mounted.** `/api/enterprise/ws/live` (router_registry.py:65) + `/ws/stats` 200. WS 404 ise stres runner'da `ws` paketi/Upgrade handshake meselesi (env), endpoint-mount değil. Tenant-scope `ws_hub` ile enforce. | 4/env |
| `mice_execution` | F&B order-send absent | Endpoint absent + module gate | **Roadmap + by-design.** mice events/BEO/kitchen-ticket VAR; ayrı "F&B order send" yüzeyi yok → spec REVIEW dürüsttür; mice module entitlement (403 ENTITLEMENT_DENIED) by-design. | 3/8 |
| marketplace (Wave5/7 sonrası) | inventory/PO/cancel | `hidden_marketplace` flag | **Feature-flag.** Read VAR; write surface `require_feature("hidden_marketplace")` → flag-off davranışı by-design; spec flag davranışını yansıtmalı. | 4 |
| spa / vcc / pos catalog | RBAC/module | EntitlementMiddleware 403 | **By-design.** Module yoksa 403 ENTITLEMENT_DENIED (404 değil); RBAC alt-rol Wave 9. | 8 |

---

## 4) Doktrin uyumu (Wave 8)

- ❌ Kör stub / boş endpoint → **EKLENMEDİ** (mount edilecek eksik ürün
  yüzeyi yok; var olanlar by-design/drift/roadmap).
- ❌ Auth zayıflatma → **YOK.** Platform-super-admin 404'leri KORUNDU; stres
  admin'e platform yetkisi verilmedi.
- ❌ Fake-green → **YOK.** Tek değişiklik test-drift düzeltmesi; güvenlik
  assertion'ları SKIP'ten gerçek-koşar oldu (güçlendirme).
- ❌ Pilot mutation → **YOK.** Probe'lar read-only GET; yazımlar (varsa)
  stres-tenant in_app.
- ❌ external_calls → **[]** (DISABLE_EXPO_PUSH fail-closed).
- ❌ Baseline #162 pointer → **TAŞINMADI.**

---

## 5) CI-deferred doğrulama

Targeted stres spec'leri lokalde **koşulmadı** çünkü stres tenant tam
seed/token-matrix gerektiriyor ve fail-closed. `45-notification-batch`
düzeltmesi `node --check` PASS + endpoint'ler canlı GET ile 200 doğrulandı;
gerçek PASS doğrulaması bir sonraki **planlı** full stress / targeted CI
koşusunda görülecek (skip-as-pass YOK). Beklenen REVIEW/SKIP etkisi:
notification_batch P2×3 + 3 SKIP düşer; admin/webhook/outbox by-design
yeniden sınıflandı (sayı düşmez ama kategori 3→8 dürüstleşir).

## 6) Reclassify özeti (envantere işlendi)

- 3→8 (by-design): admin_rbac, settings_audit, webhook_admin_dlq, outbox
  observability, payment SKIP (shift), mice module-gate, spa/vcc/pos catalog.
- 3 (roadmap, dürüst REVIEW kalır): pos_tables list, waitlist promote,
  mice F&B order-send, QR rotation HTTP.
- 4 (drift): notification_batch (DÜZELTİLDİ), folio path, infra prefix,
  messaging prefix, marketplace flag-reflect.
