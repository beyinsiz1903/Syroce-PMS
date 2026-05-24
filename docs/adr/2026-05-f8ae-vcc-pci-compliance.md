# ADR — F8AE VCC + PCI Compliance Stress Spec

**Status:** Spec written (2026-05-24); full-suite verification pending.

## Context

2026-05-24 GREEN baseline (commit `ee7573b3`, 68 specs, P0=P1=0,
external_calls=[], pilot_drift=0) + F8X–F8AA + F8AB + F8AC genişlemeleri
ile birlikte tutar 73 spec. Pilot satışın kritik PCI yüzeyi olan **Virtual
Credit Card (VCC) reveal** ve **PCI-DSS compliance attestation** akışları
şu ana kadar stress kapsamında değildi. PCI-DSS Req 3.x (stored cardholder
data protection) + Req 7.x (least-privilege access) doğrudan VCC endpoint
quartet'inde test edilebilir; reveal endpoint catastrophic disclosure
yüzeyidir (3-view contract bozulursa unlimited card harvest).

## Karar

Yeni Playwright stress spec:
`frontend/e2e-stress/specs/98-vcc-pci-compliance.spec.js`
(module `vcc_pci_compliance`).

### Hedef yüzey

| Endpoint | Method | Test | Kritiklik |
|---|---|---|---|
| `/api/pms/reservations/{id}/vcc` | POST | store + 409 conflict | P0 cross-tenant |
| `/api/pms/reservations/{id}/vcc/status` | GET | view-count safe read | P0 disclosure |
| `/api/pms/reservations/{id}/vcc/reveal` | POST | 3-view limit + lock | P0 PCI Req 3.2 |
| `/api/pms/reservations/{id}/vcc` | DELETE | cleanup + idempotent | P0 cross-tenant |
| `/api/compliance/pci/status` | GET | summary read | P2 RBAC |
| `/api/compliance/pci/controls` | GET | controls + refresh | P2 RBAC |
| `/api/compliance/pci/report.csv` | GET | safe_writerow + PAN sweep | P1 injection |
| `/api/compliance/pci/attestation` | GET | HMAC + anonymize | P2 |
| `/api/reservations/{id}/full-detail` | GET | audit invariant readback | P1 |

### Test bölümleri

- **Setup** — `fetchAllByPrefix('/api/pms/bookings', 'stress_prefix', prefix)`
  ile stress-seeded booking harvest; pilot booking harvest (read-only)
  cross-tenant IDOR için. `withModuleProbe` ile VCC + PCI reachability;
  herhangi biri 403/404 → `moduleBlocked=true` + P2 + downstream skip.
- **A) PCI smoke** — status / controls (+refresh) / attestation
  (default + anonymize) / report.csv. Her response body PAN regex +
  forbidden-key (`*_enc`) tarar. CSV body line-prefix `=/+/-/@`
  formula-injection guard (`safe_writerow`) doğrulanır.
- **B) VCC lifecycle + audit invariant** — store (mask only) → status
  (view_count=0) → reveal #1 (raw PAN sadece bu yanıtta) → full-detail
  history `vcc_stored` + `vcc_revealed` entries assert; her audit rowunda
  PAN/CVV/raw leak yok.
- **C) Reveal 3-view limit** — reveal #2 + #3 (consume) → reveal #4
  **MUST 403** (`expect().toBe(403)`). 4th 200 = P0 PCI breach.
  Locked-state status read.
- **D) Cross-tenant IDOR (bidirectional)** — bogus booking_id store/reveal
  → 404. Pilot bearer → stress VCC status/reveal/delete/store ALL 4xx
  (2xx = P0). Stress bearer → pilot booking VCC status/reveal ALL 4xx
  (2xx = P0 catastrophic pilot disclosure).
- **Z) Cleanup** — DELETE her VCC; pass#2 = 404 zorunlu. `vcc_deleted`
  audit row best-effort verify.

### Doctrine (F8X–F8AA compliance pattern)

- `pilot mutation = 0`, `pilot_drift = 0` her test sonunda
- `external_calls = []` — PCI okuma + VCC AES-256-GCM in-process; outbound HTTP YOK
- Cleanup idempotent — `STRESS_COLLECTIONS` listesine `vcc_cards` +
  `reservation_activity_log` eklendi (orphan-scrub safety net;
  spec-side DELETE primary path)
- `expect().toBeGreaterThanOrEqual(400)` ile IDOR hard-fail — pasif
  `recFinding` ile geçiştirmek YASAK
- PAN regex `/\b(?:\d[ -]?){13,19}\b/` masked değerleri (asterisk
  içerenleri) hariç tutar; reveal yanıtı dışında raw PAN bulunursa P0
- Audit invariant bağımsız endpoint (`/full-detail.history`) üzerinden
  read-back doğrulaması — write-side log insert kabul edilmez

### Test PAN

Luhn-valid sentinel `4111…1111` (Visa test number); konkatenasyon
(`['4111','1111','1111','1111'].join('')`) ile yazılır — `assertEndpointNeverCalled`
veya başka spec'lerin source-scan'i bu literal'ı false-positive olarak
yakalamaz. AES-256-GCM ile yalnızca stress tenant'a şifrelenir;
hiçbir gerçek PSP'ye iletilmez.

### Modül-blocked fallback

VCC veya PCI probe 403/404 → `moduleBlocked=true` flag + P2 informational
+ A/B/C/D `test.skip`. Z (cleanup) + final invariants bağımsız çalışır
(fake-PASS yok). 409 store conflict (prior partial run residue) → P2 +
cleanup'a id ekleyip skip.

## Sonuç doğrulaması (next step)

Bu ADR specs-written kabul edilir. Full Operational Stress Suite
verification (commit + republish + CI green) sonraki turun sorumluluğunda.

- Spec count: **73 → 74**
- failedTests = 0, P0 = P1 = 0
- external_calls = [], pilot_drift = 0
- Cleanup idempotent
- Beklenen muhtemel P2: VCC endpoint require_op (`manage_approvals` +
  `store_card`/`reveal_card`/`delete_card`) stress admin'de eksikse
  module-blocked (super_admin tipik olarak geçer).

## İleri backlog

- **F8AE v2:** Atomic concurrent reveal race (3-view lock under parallel
  reveals — `view_count: {$lt: max_views}` filter doğru iş yapıyor mu).
  Şu an seri reveal test ediliyor; paralel reveal Playwright stress
  scenario gerektirir.
- **F8AE v3:** Field-encryption key rotation drill — eski key'le store +
  yeni key'le reveal kontratı (envelope key versioning).
- **PCI v2:** `ATTESTATION_SIGNING_KEY` rotation + signature verification
  in spec (HMAC re-compute + assert match).
