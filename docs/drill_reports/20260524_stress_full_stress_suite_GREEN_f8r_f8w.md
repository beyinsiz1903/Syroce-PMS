# Full Operational Stress Suite — GREEN BASELINE (F8R–F8W dahil) — 2026-05-24

> **Bu rapor yeni resmi baseline'dır.** 2026-05-23 baseline'ına F8R–F8W
> Hardening Pack'i (5 spec) eklendi; backend tarafında F8S'in yakaladığı
> gerçek path-traversal P1 fix'lendi; full-suite tek run GREEN döndü.
> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`).
> Tag: `full_stress_suite`.

## 1) Run künyesi

| Alan | Değer |
|---|---|
| Run tarihi | 2026-05-24 |
| Suite kapsamı | F8A + F8B + F8C + F8D (v2 + v3 HR extension) + F8E + F8F..F8O + **F8R + F8S + F8U + F8V + F8W** |
| Workflow | GitHub Actions — Full Operational Stress Suite (CI one-shot) |
| Commit SHA (HEAD) | `ee7573b3` — Securely handle document uploads by sanitizing filenames |
| Contributing fix (bu run) | `ee7573b3` (`backend/domains/hr/router.py` `_sanitize_doc_filename()` upload + download apply) |
| Önceki baseline | `a035568c` (2026-05-23 GREEN, 413 test) |
| Spec count | **68** (`frontend/e2e-stress/specs/`) — +5 F8R–F8W (09/64/91/98/98B) |
| Başarısız test | **0** |
| FAIL adım | **0** |
| P0 / P1 | **0 / 0** |
| Final verdict | ✅ **GO** — failedTests=0, FAIL adım=0, P0=P1=0 |

## 2) Mutlak invariant gates (hepsi PASS)

| Gate | Status |
|---|---|
| `failedTests == 0` | ✅ |
| `failedSteps (FAIL) == 0` | ✅ |
| `P0 == 0` | ✅ |
| `P1 == 0` | ✅ |
| `external_calls == []` | ✅ (her modülde re-assert) |
| `pilot_drift == 0` | ✅ |
| Cleanup idempotent | ✅ (cleanup#1 deleted>0, cleanup#2 deleted=0) |

## 3) F8R–F8W Hardening Pack — PASS

5 yeni spec full-suite içinde geçti:

| Spec | Modül | Sonuç |
|---|---|---|
| `09-ops-readiness-smoke.spec.js` | `ops_readiness` | ✅ PASS |
| `64-file-upload-security.spec.js` | `file_upload_security` | ✅ PASS (HR docs path-traversal sanitized) |
| `91-export-artifact-idor.spec.js` | `export_artifact_idor` | ✅ PASS |
| `98-auth-token-lifecycle.spec.js` | `auth_token_lifecycle` | ✅ PASS |
| `98B-websocket-tenant-isolation.spec.js` | `ws_tenant_isolation` | ✅ PASS |

## 4) İterasyon: F8S P1 → fix → GREEN

**İlk CI run'ında bulgu:** `64-file-upload-security.spec.js` test A —
`hr_docs_traversal_sanitize` adımı **FAIL**, P1 finding:
```
HR docs path-traversal filename DB'ye literal yazıldı
stored=../../../../etc/passwd
```

**Root cause (gerçek backend bug):** `backend/domains/hr/router.py:5217`
`upload_from_stream(file.filename or 'document', ...)` ve `item['filename']`,
`item['label']` raw `file.filename` kullanıyordu. Sanitization yoktu.
Saldırı yüzeyi: DB literal `../` + download response Content-Disposition
header'da yansıma (client-side path traversal + header injection).

**Fix (doctrine: assertion gevşetme yok, backend sanitize):**
`_sanitize_doc_filename()` helper eklendi (`backend/domains/hr/router.py:5208-5214`):
1. Basename (`rsplit('/', 1)[-1]` + `\` → `/` normalize)
2. Leading dot strip (`lstrip('.')`)
3. ASCII allowlist `[A-Za-z0-9._\- ]` dışı → `_`
4. 200-char cap, boşsa `'document'` fallback

Uygulama noktaları:
- Upload: `safe_filename` → GridFS filename + `item['filename']` + `item['label']`
- Download: defense-in-depth — legacy raw kayıtlar için Content-Disposition'da
  da `_sanitize_doc_filename(doc.get('filename'))`

**Architect review:** PASS — URL-encoded / Unicode / nullbyte / CRLF /
quote-escape / header-injection vektörlerinin tümü neutralize, legacy kayıt
geriye uyumluluğu korunmuş, başka raw `file.filename` call-site yok.

**Republish → CI re-run → GREEN.**

## 5) Doctrine pekiştirme

- Spec assertion gevşetme: **YOK**. P1 bulgusu gerçek bug olarak fix'lendi.
- Skip-as-pass: **YOK**. F8S `hr_docs_traversal_sanitize` step gerçekten PASS dönüyor.
- Pilot tenant mutation: **0**.
- External (SMS / e-posta / OTA / payment) çağrı: **0**.
- Cleanup idempotent: ✅.

## 6) Çıktı cümlesi (pilot/yatırımcı için)

> Syroce PMS; PMS çekirdek, finans, İK, channel manager, guest/public,
> GraphQL/B2B, AI dry-run, cross-tenant güvenlik, **auth token lifecycle,
> WebSocket tenant izolasyonu, file upload security, export artifact IDOR
> ve ops readiness** dahil geniş üretim yüzeylerinde Full Operational
> Stress Suite'i yeşil geçmiştir (2026-05-24, commit `ee7573b3`, 68 spec,
> failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0, cleanup idempotent).

## 7) Referanslar

- ADR: `docs/adr/2026-05-f8r-f8w-hardening.md`
- Roadmap baseline tablosu: `docs/STRESS_TEST_ROADMAP.md` § Latest verified baseline (2026-05-24)
- Önceki baseline (referans): `docs/drill_reports/20260523_stress_full_stress_suite_GREEN.md`
- Fix commit: `ee7573b3` — `backend/domains/hr/router.py:5195-5214`, `5240-5242`, `5339-5341`
