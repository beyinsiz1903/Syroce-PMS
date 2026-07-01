# P1 Fix — B2B sub-router missing X-API-Key → 401 (was 422) — 20260530

## Bağlam

Full Operational Stress Suite (commit `a148a455`, tag `full_stress_suite`, 702 test)
**NO-GO** döndü. Tek bloklayan bulgu:

- **P1 [b2b_api]** — `41B-b2b-subrouter-matrix.spec.js › C) Auth matrix — missing/bogus X-API-Key → 401/403 (P0 if 2xx)`
- Belirti: X-API-Key **eksik** iken tüm b2b alt-router'ları **422** (FastAPI required-header validation) döndürüyordu; spec deny path için 401/403/404 bekliyor.
- **Bypass DEĞİL**: 422 erişimi reddediyordu; sorun yalnız status semantiği (çağıran "missing" vs "invalid" key'i status koduyla ayırt edebiliyordu). 2xx olsaydı P0 olurdu — olmadı.

Not: `41B` spec'i Run #162 baseline'ından (29 May, commit `bde7662`) **sonra** eklendi.
Yani bu 422 davranışı **yeni regresyon değil**; yeni eklenen sıkı auth-matrix alt-testi
öteden beri var olan davranışı ilk kez flag'liyor.

## Kök sebep

13 b2b alt-router dosyasında (auto-split, aynı template) `get_b2b_agency` dependency'si:

```python
x_api_key: str = Header(..., alias="X-API-Key")   # (...) = ZORUNLU → eksikse 422
```

`Header(...)` zorunlu olduğu için, key eksik olduğunda istek handler gövdesine
hiç girmeden FastAPI request-validation 422 üretiyordu; mevcut 401/403 auth mantığına
ulaşılamıyordu.

## Düzeltme (minimal, fail-closed)

13 dosyanın hepsinde:

```python
x_api_key: str | None = Header(None, alias="X-API-Key")
...
if not x_api_key:
    raise HTTPException(status_code=401, detail="API key gerekli")
```

- Bogus key → 401 (mevcut `key_doc` miss yolu) — değişmedi.
- Pasif/eksik acente → 403 — değişmedi.
- Valid key yolu (hash lookup, tenant context, last_used) — değişmedi.
- `if not x_api_key` hem eksik header'ı hem boş-string (`X-API-Key: ""`) durumunu 401 yapar (fail-closed).

Değişen dosyalar (13 router):
`api_keys, booking_engine, folio, groups, guest_journey, guests, housekeeping,
identity, kbs, lost_found, services, wake_up, webhooks` (hepsi `backend/routers/b2b_api/`).

## Targeted test güncellemeleri (fake-green değil — yeni sözleşmeye hizalama)

- `backend/tests/test_b2b_api.py`: `test_02_missing_api_key_returns_422` → `_returns_401` (422→401 assert).
- `backend/tests/test_b2b_webhooks.py`: 4 "without key" testi 422→401.

## Doğrulama (canlı, local backend :8000 — restart sonrası)

| Endpoint | Senaryo | Sonuç |
|---|---|---|
| `/api/b2b/content` | eksik key | 401 |
| `/api/b2b/content` | boş-string key | 401 |
| `/api/b2b/content` | bogus key | 401 |
| `/api/b2b/webhooks` | eksik key | 401 |
| `/api/b2b/kbs/guests` | eksik key | 401 |
| `/api/b2b/guests/search` | eksik key | 401 |
| `/api/b2b/lost-found` | eksik key | 401 |

`py_compile` PASS · uygulama restart sonrası temiz boot (curl'ler 401) · architect PASS.

## Kapsam dışı / takip notu

- `backend/routers/marketplace_b2b.py` da aynı `Header(...)` kalıbını kullanır
  (eksik key → 422). Bu P1'i tetikleyen 41B spec'i `/api/b2b/*` kapsamındadır;
  marketplace ayrı yüzey ve bu turda P1 FAIL üretmedi. Genel politika "tüm API-key
  auth 401 olsun" ise ayrı küçük bir takip turunda aynı kalıp uygulanabilir
  (architect notu).

## Gate durumu

Bu düzeltme P1'i kapatmayı hedefler. **Run #162 baseline pointer (`bde7662`) TAŞINMADI.**
Promosyon ancak yeni CI artifact'i (yeniden dispatch edilen Full Stress) tüm gate'leri
geçtikten sonra değerlendirilir: failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0,
cleanup#2 idempotent, verdict ≥ GO WITH WATCH.
