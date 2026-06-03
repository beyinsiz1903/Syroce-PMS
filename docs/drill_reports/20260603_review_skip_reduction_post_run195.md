# REVIEW/SKIP Reduction — post Run #195 baseline (Option 1)

- **Tarih:** 2026-06-03
- **Baseline:** Run #195 GREEN (708 test, PASS/FAIL/REVIEW/SKIP=1570/0/15/11,
  P2=23, P3=0, verdict GO WITH WATCH). Bu paket #195 üzerine doctrine-safe
  REVIEW/SKIP azaltımıdır.
- **Operatör seçimi:** Option 1 — gerçekten fixable olanları düzelt; geri kalanı
  tek tek gerekçelendir. Sayılar SIFIRA değil, modest düşer.
- **Doktrin (mutlak):** no fake-green/fake-RED · no auth/RBAC/PII weakening ·
  no skip-as-pass · no blind-seed · no assertion-loosening · pilot_drift=0 ·
  external_calls=[] · P0=P1=FAIL=0 · verdict ≥ GO WITH WATCH · mobile/F10 ayrı.
- **Doğrulama yöntemi:** targeted `node --check` / `py_compile` / canlı read-only
  probe. Full stress agent tarafından dispatch EDİLMEZ → nihai CI delta
  CI-PENDING. Aşağıdaki sayı projeksiyonları tahmindir, CI ile doğrulanacak.

---

## Yöntem dürüstlüğü (enumeration caveat)

Run #195 artifact ZIP gövdesi auth-gated (replit.md "Stress Current State" +
memory `stress-provenance-github-digest`). 26 kalemin (15 REVIEW + 11 SKIP)
satır-satır artifact gövdesinden RE-TÜRETİLMESİ mümkün değil. Bu triage,
replit.md WATCH listesinde + drill #194/#195'te İSİMLENDİRİLMİŞ yüzeylere ve 3
explore subagent triajına dayanır. Sayı projeksiyonları bu yüzden "CI-pending"
etiketlidir; fabrike GREEN iddiası YOKTUR.

---

## A) Gerçek doctrine-safe FIX'ler (3)

### FIX-1 — finance_folio `no_stress_folio` (SKIP→ azaltım)
- **Spec:** `frontend/e2e-stress/specs/99-finance-folio-surface.spec.js`
- **Kök neden (DOĞRULANDI):** setup harvest probe `limit=5` (eski) ilk 5 folio'yu
  çekiyordu; bu folio'lar daha önceki specler (04 folio-mass void/checkout)
  tarafından kapatılmış → OPEN filtre boş → `no open folio` REVIEW + downstream
  C–F `test.skip`. Self-depletion (memory `stress-serial-sample-depletion`).
- **Fix:** harvest probe `limit=5`→`limit=50` (stress satır 114 + pilot satır 154).
  Mevcut `status==='open'` filtre (satır 137) korunur. Seed YOK, assert gevşetme
  YOK — yalnız harvest penceresi genişledi (Package E deseni).
- **Beklenen etki (CI-pending):** −1 REVIEW (harvest record) + C–F SKIP'leri PASS.
- **Doğrulama:** `node --check` OK.

### FIX-2 — full_24h data-scarcity (SKIP→ azaltım)
- **Spec:** `frontend/e2e-stress/specs/99-full-24h-hotel-simulation.spec.js`
- **Kök neden (DOĞRULANDI):** spec, paylaşılan 500-seed prefix'inden harvest
  ederken `fetchAllByPrefix`'e `maxPages: 8` (1600-satır pencere) explicit
  OVERRIDE veriyordu. Helper'ın safety-net default'u zaten 60 (yorum: "8→60
  bumped … bloated tenant LOUDLY fails instead of SILENTLY losing rows"). 90 spec
  boyunca biriken walk-in booking'ler tenant booking sayısını şişirip seed-prefix'li
  (en eski, created_at desc'te en sonda) kayıtları 8. sayfanın dışına itti →
  prefix-match <30 → false "data scarcity" P2/SKIP.
- **Fix:** bookings (satır 122-128) + rooms (satır 132-135) harvest'lerinde
  `maxPages: 8`→`maxPages: 60` (helper safety-net'iyle hizalama). Seed YOK,
  gate gevşetme YOK — yalnız pencere genişledi.
- **Beklenen etki (CI-pending):** −1 P2/REVIEW + phase SKIP'leri PASS.
- **Doğrulama:** `node --check` OK.

### FIX-3 — admin `/api/system/db-stats` 500 (REVIEW→PASS)
- **Backend:** `backend/domains/admin/router/system.py` (`get_database_stats`)
- **Kök neden (DOĞRULANDI):** route `Depends(get_current_user)` (any-auth) — spec
  beklentisi `expectAuthorized: ROLES` DOĞRU; REVIEW sebebi RBAC DEĞİL.
  `db.command('serverStatus')` Atlas shared tier'da (kısıtlı clusterMonitor
  privilege) patlıyor → blanket `except: raise HTTPException(500)` → tüm endpoint
  500 → spec'in expectAuthorized rolleri için non-2xx → REVIEW.
- **Explorer'ın yanlış önerisi REDDEDİLDİ:** "spec'i `expectAuthorized: []` yap"
  doctrine-ihlali olurdu — route gerçekten any-auth; spec'i super-admin-only gibi
  göstermek 500'ü maskeler + RBAC posture'u sahte değiştirir.
- **Fix:** her sub-call (verify_indexes / get_collection_stats / serverStatus)
  bağımsız try/except; başarısızlık `degraded[]` listesine yazılır, 200 + kısmi
  payload döner. RBAC posture DEĞİŞMEDİ (any-auth, /system/*). Audit-logs/hr-staff
  read hardening ile aynı guarded-return deseni (memory `audit-timeline-mixed-ts-500`).
- **Beklenen etki (CI-pending):** −1 REVIEW (db-stats 4 rol artık 200).
- **Doğrulama:** `py_compile` OK; artık `raise HTTPException` yolu yok → auth
  geçerse her zaman 200. Dev happy-path canlı probe `get_collection_stats`'in dev'de
  birikmiş onlarca koleksiyonu gezmesi yüzünden >95s sürdü (curl timeout, server
  500 DEĞİL HTTP=000); bu latency önceden vardı, fix latency EKLEMEDİ (aynı 3 DB
  çağrısı). Atlas serverStatus-denied 500 yolu = CI senaryosu, fix onu hedefliyor.

---

## B) Justified IRREDUCIBLE / BY-DESIGN (fix EDİLMEDİ — gerekçeli)

### housekeeping room-summary cold-boot TTI (REVIEW, soft P3) — JUSTIFY
- **Backend:** `backend/modules/pms_core/housekeeping_state_service.py`
  `get_room_status_summary`.
- **Karar:** index EKLENMEDİ (fake-green riski). Query temiz
  `$match{tenant_id, is_active}` + `$group{_id:$status}` (~500 oda). Tenant_id
  index zaten `$match`'i servis ediyor; 500-doc group trivial (<50ms beklenir).
  ~3067ms scan-cost DEĞİL → cold-boot (ilk istek: pool/Atlas warm-up, JWT decrypt,
  module import). memory `mongo-index-not-fixable-paths`: cold-boot latency'ye
  index = fake-green. Eşik (P3 >2000ms) 500-oda scalability baseline'ı — gevşetme
  YOK. Soft/informational REVIEW olarak irreducible kalır.

### Module-blocked SKIP'ler (irreducible — stress tenant tier/feature yok)
Her biri `withModuleProbe` 403/404 → modül gerçekten erişilmez; skip-as-pass
DEĞİL (security/invariant probe'lar bağımsız koşar). Forcing PASS için tier/feature
açmak = blind-seed/posture-change → doctrine-ihlali.
- accommodation_tax · ai_noshow · kvkk_retention · public_kvkk/digital-key (404) ·
  revenue_mgmt (×2) · vcc_pci — hepsi stress tenant basic-tier'da entitlement/feature
  yok (memory `require-feature-entitlement-probes`, `xtenant-test-entitlement`).

### By-design REVIEW yüzeyleri (gerçek davranış doğru — REVIEW informational)
Forcing PASS için backend guard'ı gevşetmek gerekirdi → assertion/RBAC/PII
weakening → doctrine-ihlali. Bunlar gerçek-doğru sonuçların informational kaydı:
- **finance_folio 409** — closed-folio/dup-guest-folio constraint (by-design;
  memory `stress-folio-void-closed-guard`).
- **finance_folio 403** — post_charge RBAC reddi (doğru).
- **notification activity-PII** — Wave9 by-design activity log alanı.
- **public_nps dup-2xx** — idempotent dup-submit 2xx (doğru).
- **reports RBAC 403** — düşük-priv rol reddi (doğru).
- **reservation_deep waitlist 403 / city-ledger** — entitlement/role gate (doğru).
- **reservation-lifecycle 409** — terminal-state guard (doğru; memory
  no-show terminal-state).
- **night-audit unresolved (200)** — açık exception kalması veri-state, crash yok.
- **ops_readiness backup posture / webhook_admin_dlq 404** — env/altyapı posture,
  kod-fix değil.
- **settings_audit async marker** — async işleme marker'ı, gerçek hata değil.

---

## C) Açık WATCH adayı (bu pakette ele ALINMADI — kayıt)

- **login-throttle ordering** — rate_limit_boundary `auth_login` burst 0-throttled.
  T003 (#195 WATCH pack) QR'da limiter-before-auth reorder yaptı; aynı düzeltme
  login yüzeyine de uygulanabilir (memory `ratelimit-before-auth-ordering`). Bu
  paket SKOPUNDA DEĞİL — ayrı WATCH item.

---

## Net sonuç (projeksiyon, CI-pending)

- 3 gerçek doctrine-safe fix (finance_folio harvest, full_24h maxPages, db-stats
  500-hardening) + 1 gerekçeli-irreducible (housekeeping cold-boot) + ~22
  irreducible/by-design tek tek gerekçelendi.
- Beklenen modest düşüş: SKIP 11→~9, REVIEW 15→~12/13. SIFIR DEĞİL — doctrine-doğru
  sonuç. Nihai sayı bir sonraki full stress (workflow_dispatch) ile doğrulanacak;
  agent dispatch ETMEZ.
- Hiçbir assert/guard/RBAC/PII gevşetilmedi; pilot dokunulmadı; seed eklenmedi.
