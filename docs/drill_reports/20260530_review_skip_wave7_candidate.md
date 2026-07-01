# REVIEW/SKIP Zeroing — Wave 7 (SEED / DATA-STATE) candidate

> **Tarih:** 2026-05-30 · **Faz:** Wave 7 (seed/data-state, kategori 2)
> **Baseline:** Run #162 (REVIEW 46 / SKIP 61 / P2 60) — **pointer TAŞINMAZ**.
> **Doctrine:** blind PASS downgrade YOK · fake-green YOK · güvenlik zayıflatma YOK ·
> gerçek prod secret YOK (test-only) · full stress bu turda KOŞULMAZ.
> **Validation:** Wave 6 gibi lokal doğrulanamaz (stres tenant yok, gate'ler
> fail-closed) → **CI-DEFERRED**, skip-as-pass YOK.

---

## 0) Özet

Wave 7 envanteri 14 item-grup içeriyordu (hepsi kategori 2 "seed gerekli" diye
işaretlenmişti). Seed kodu (`backend/domains/admin/router/stress.py`
`_build_*_docs` + `STRESS_COLLECTIONS`) ve pilot fixtures
(`pilot_fixtures.py`) **birebir** okunduğunda ortaya çıkan gerçek:

- **6 item ZATEN SEEDLİ** (factory üretiyor) → gerçek blocker seed DEĞİL:
  endpoint mount (Wave 8), env-gate, veya RBAC (Wave 9). Bunlara seed eklemek
  **duplicate/false-green** olurdu — eklenmedi, yeniden sınıflandırıldı.
- **4 item MODULE-BLOCKED / endpoint-absent** (POS/SPA entitlement, generic
  `waitlist` ve `pos_tables` endpoint'i yok) → seed tek başına çözmez; Wave 8.
- **2 item GERÇEK SEED GAP, güvenli & endpoint-bağımsız** → bu turda implemente:
  1. **B2B `agencies`** stres seed (41B matrix `agencies_list_len=0`, P2×10).
  2. **Pilot `payroll_runs`** read-only IDOR fixture (91 export-artifact, SKIP×1).

Bu, Wave 7'nin dürüst sonucudur: 2 gerçek seed düzeltmesi + envanteri düzelten
büyük bir yeniden-sınıflandırma (gereksiz duplicate-seed işini ve false-green'i
önler).

---

## 1) Per-item gap analizi (14/14)

| # | Item | Sınıf | Gerçek kök sebep | Aksiyon |
|---|---|:--:|---|---|
| 1 | `b2b_api` agencies_list_len=0 | **B SEED-GAP** | `agencies` koleksiyonu stres tenant'ında seedli değildi (STRESS_COLLECTIONS'ta da yoktu) | **DONE** `_build_agency_docs` (5 doc) |
| 2 | `folio-mass` charges[] boş | **A ZATEN-SEEDLİ** | `_build_factory_docs` folio+≥2 charge+tax üretiyor; spec okuma endpoint'i (`/api/folios`,`/api/folio-charges`) eksik | → **Wave 8** (endpoint/alias) |
| 3 | `pos_kds_inventory` recipe/BOM | **C MODULE-BLOCKED** | `pos` modül entitlement yok; seed dataset modül probe SKIP'ine takılır | → **Wave 8** (POS mount/entitlement) |
| 4 | `vcc_pci_compliance` VCC attach | **A ZATEN-SEEDLİ** | 500 booking seedli; spec kendi vcc_card'ını yaratıyor; reveal `cashier_supervisor` rolü ister | → **Wave 9** (RBAC alt-rol) |
| 5 | `full_24h` simülasyon | **A ZATEN-SEEDLİ** | 500 booking/560 oda/500 guest mevcut; review env-gate (`STRESS_FULL_SUITE`) ile ilgili | → env-gate (operatör/devops) |
| 6 | `finance_reports_currency` convert 0/2 | **A ZATEN-SEEDLİ** | `currency_rates` orphan-scrub'lı; spec kendi rate'ini POST ile yaratıyor; convert okuma endpoint'i | → **Wave 8** (endpoint) |
| 7 | `reservation_deep` waitlist promote | **C ENDPOINT-ABSENT** | generic `/api/waitlist` yok (`spa_waitlist` var); boş koleksiyon seed'i 404'ü çözmez | → **Wave 8** (waitlist endpoint) |
| 8 | `spa_operations` katalog | **C MODULE-BLOCKED** | `spa` modül entitlement yok; katalog seed'i modül probe SKIP'ine takılır | → **Wave 8** (SPA mount/entitlement) |
| 9 | `hr_rbac_pii` team_create per-role 404 | **A/Wave 8** | 404 = endpoint cevabı (rol değil veri değil). `users` koleksiyonuna auth-hassas seed lokal doğrulanamaz → bu turda YAPILMADI | → **Wave 8** (endpoint teyidi); seed gerekirse W7-takip |
| 10 | `export_artifact_idor` hr_payroll_run pilot boş | **B SEED-GAP** | pilot tenant'ta `payroll_runs` IDOR anchor yoktu → bogus-UUID fallback | **DONE** `_ensure_payroll_run` (1 read-only fixture) |
| 11 | `ai_noshow_risk` no bookings | **A ZATEN-SEEDLİ** | 500 booking seedli (gelecek check_in); review env-gate (`E2E_AI_DRY_RUN`) | → env-gate (operatör/devops) |
| 12 | `housekeeping` OOO/BLOCKED transition | **A ZATEN-SEEDLİ** | rooms seedli; spec OOO'yu POST ile kuruyor; inconclusive = state-machine/endpoint | → **Wave 8** (HK transition endpoint) |
| 13 | `cross_tenant_pentest` IDOR sample | **A ZATEN-SEEDLİ** | `pilot_fixtures.py` room_blocks/kbs_reports/sales-lead anchor üretiyor | aksiyon yok |
| 14 | `payment_pos_reconciliation` aktif shift | **C UNSAFE-SEED** | seed shift'ler **bilinçli** `status=closed` (`uniq_tenant_open_shift` partial unique; spec 24 kendi açık shift'ini açar). OPEN shift seed'i spec 24'ü 400 ile kırar → eklenmedi. Gerçek blocker `pos_tables` endpoint | → **Wave 8** (pos_tables); spec self-open shift |

**Doctrine kanıtı (#14):** "kör seed ekleme" yasağı burada somut karşılığını
buldu — explore'un önerdiği OPEN-shift seed'i partial-unique index'e çarpıp
mevcut yeşil bir spec'i kıracaktı. Reddedildi.

---

## 2) Bu turda yapılan kod değişiklikleri (2 adet)

### 2a) B2B `agencies` stres seed — `stress.py`
- `_build_agency_docs(stress_tid, prefix, now)`: 5 doc, şekil
  `agency_portal.py:create_agency` ile birebir (`status="active"`,
  `name` ≥2 karakter → `list_agencies` placeholder-gizleme regex `^.{2,}$`
  ile uyumlu, gizlenmez).
- `STRESS_COLLECTIONS += "agencies"` + orphan-scrub mirror'a eklendi.
- Seed handler'a factory call + `_chunked_insert(db.agencies, ...)` wire edildi.
- Her doc `stress_seed=True` + `stress_prefix` → unified cleanup loop
  prefix-scoped toplar (ekstra cleanup kodu YOK). Dış servis YOK.
- **Beklenen etki (CI-deferred):** 41B `no_stress_agency_in_list` P2×10 düşer.

### 2b) Pilot `payroll_runs` IDOR fixture — `pilot_fixtures.py`
- `_ensure_payroll_run(pilot_tid)`: idempotent (önce `pilot_fixture=True`
  arar), 1 doc, `status="fixture"` (draft/locked DEĞİL → `(tenant,
  period_month, status=draft)` partial-unique index'e çarpmaz, finalized run
  gibi görünmez), `period_month="2099-01"` (gerçek bordro ile çakışmaz).
- Endpoint return + log payload'ına `payroll_run_id`/`payroll_run` eklendi.
- Residue cleanup script (`cleanup_e2e_pilot_residue.py`) yalnız
  bookings/guests/folio_charges tarar → bu fixture'a dokunmaz.
- **Beklenen etki (CI-deferred):** 91 `hr_payroll_run` harvest gerçek pilot id
  alır (bogus-UUID fallback yerine) → SKIP×1 → gerçek cross-tenant deny assertion.

**Güvenlik invariant'ları korundu:** stres seed tenant_context(stress_tid)
içinde; pilot fixture yalnız `PILOT_TENANT_ID` eşleşince (mismatch=403);
external_calls=[]; pilot mutation yok (read-only anchor); seed gate'leri
(super_admin + ENABLE_SETUP_ENDPOINTS + destructive flag) değişmedi.

---

## 3) Validation matrix (CI-DEFERRED)

| Kontrol | Lokal | Kanıt |
|---|:--:|---|
| `py_compile` stress.py + pilot_fixtures.py | ✅ | COMPILE_OK |
| `ruff check` (2 dosya) | ✅ | All checks passed |
| Backend import/startup | ✅ | "Application startup complete" (Traceback yok) |
| Seed doc şekli endpoint kontratı ile uyumlu | ✅ (kod okuma) | agency=create_agency; payroll=list_payroll_runs |
| 41B agencies_list_len>0 (stres tenant) | ⏳ CI | targeted `41B-b2b-subrouter-matrix` |
| 91 hr_payroll_run gerçek pilot id harvest | ⏳ CI | targeted `91-export-artifact-idor` |
| Cleanup idempotent (agencies prefix-scoped) | ⏳ CI | stress_cleanup STRESS_COLLECTIONS sweep |

Lokal koşulamaz: stres/pilot tenant CI dışında seedli değil; gate'ler
fail-closed. Targeted spec'ler CI'da koşacak; full stress bu turda KOŞULMADI.

---

## 4) Wave 7 sonrası beklenen sayım (tahmin, CI doğrulayacak)

- **Seed gerçek düzeltme:** P2×10 (agencies) + SKIP×1 (payroll IDOR).
- **Yeniden sınıflandırma:** 6 item → Wave 8 (endpoint), 2 item → env-gate,
  1 item → Wave 9 (RBAC). Bunlar Wave 7 seed işi DEĞİLDİ; envanter düzeltildi.
- Tahmini: REVIEW 46→~45, SKIP 61→~60, P2 60→~50. Kalan REVIEW/SKIP'in büyük
  bölümü artık Wave 8 endpoint/mount kapsamında (interim hedef yolunda).

Baseline #162 pointer TAŞINMAZ. Sayımlar yalnız bir sonraki full-stress
CI run'ı resmî olarak günceller.
