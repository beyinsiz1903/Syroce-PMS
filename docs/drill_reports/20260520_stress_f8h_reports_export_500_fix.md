# Drill Report — F8H §90 reports_export 500 fix (Task #246)

**Tarih:** 2026-05-20
**Bağlı task:** #246 — F8H §90 reports export 500 fix
**Önceki spec authoring task:** #199 (F8H reports/analytics/export stress, MERGED)
**Spec:** `frontend/e2e-stress/specs/90-reports-analytics-export.spec.js` — § C

## Özet

Full stress suite CI'ında F8H §90 § C iki endpoint'te 500 raporluyordu:

- `POST /api/reports/builder/export/excel`
- `GET /api/reports/company-aging/excel`

Spec hatası: `5xx must be 0; got 2 statuses=[200,200,200,200,200,500,500]`. Dev backend'de demo super_admin ile aynı payload 200 dönüyordu; fark stress tenant data shape'inden + cache state'inden geliyordu.

## Root cause analizi (statik + lokal repro)

### Bug 1 — `company-aging/excel` @cached + StreamingResponse

`export_company_aging_excel` `@cached(ttl=900)` decorated idi. `@cached` wrapper StreamingResponse'u serialize edemiyor; Python objesinin `repr()`'sini saklıyor:

```
b'"<starlette.responses.StreamingResponse object at 0x7f...>"'
```

İlk çağrı XLSX dönüyor (cache miss, fonksiyon çalışıyor), ikinci çağrı 200 ile JSON-string repr dönüyor (XLSX magic bytes değil). Stress spec her çalıştırmada cache state'i farklı yakaladığında — özellikle warm cache + concurrent çağrılarla — istemci tarafı 500'e (parse fail / downstream consume hatası) düşebilir. Yerel pytest case (e) ile bu davranış bire-bir reprodüks edildi.

### Bug 2 — `company-aging` datetime parse (TypeError → 500)

`get_company_aging_report`:
```python
folio_created = datetime.fromisoformat(folio['created_at']).date()
```

Stress tenant'ta `created_at` BSON Date olarak saklanmış olabiliyor; motor native `datetime` objesi döndürünce `datetime.fromisoformat()` `TypeError: fromisoformat: argument must be str` raise ediyor → 500 (handler içinde guard yok).

### Bug 3 — `builder/export/excel` route handler doğrudan başka cached route handler'ı çağırma

`export_company_aging_excel` doğrudan `await get_company_aging_report(current_user)` çağırıyordu. Mevcut `@cached` versiyonu User objesini cache key'den dışlasa da, decorator semantiği gelecekte değişirse (örn. positional binding mantığı) bu kalıp sessizce yanlış sonuç dönebilir.

### Bug 4 — `builder/export/excel` heterojen BSON tipler

`fetch_report_data` Decimal, native datetime, ObjectId, NaN/Inf, bytes dönebiliyor. Mevcut `xlsx_safe(str(val))` ve `isinstance(val, (int, float))` kontrolleri:
- Decimal değerleri silent string'e düşürüp summary'den dışlıyordu.
- NaN/Inf float'lar openpyxl tarafından kabul ediliyor ama Excel'de geçersiz hücre üretiyor.
- Bytes ve nadir custom tipler `str()` çağrısında raise edebilir.

## Yapılan değişiklikler

| Dosya | Değişiklik |
|---|---|
| `backend/routers/departments/reports.py` | (a) `_coerce_to_date(v)` helper — str/datetime/date/None tolerant. (b) `_compute_company_aging(tenant_id)` pure helper — route'tan çıkarıldı, hem JSON hem Excel route aynı helper'ı çağırıyor. (c) `export_company_aging_excel`'den `@cached` REMOVED — StreamingResponse cache edilemez. (d) Her iki endpoint'te `try/except + logger.exception + HTTPException(500, "report_failed"/"report_export_failed")`. |
| `backend/routers/report_builder.py` | (a) `_coerce_excel_value(val) -> (typed_value, is_numeric)` helper — None/bool/int/float/Decimal/datetime/date/bytes/list/dict/arbitrary obj coercion; NaN/Inf güvenli. (b) Data row writer + summary row writer yeni helper'ı kullanıyor. (c) `export_report_excel` body'si `_build_excel_response()` private helper'ına ayrıldı; outer route handler `try/except + logger.exception + HTTPException(500, "report_export_failed")` ile sarılı. |
| `backend/tests/test_reports_export_excel_500_regression.py` | YENİ. 23 case: 11 unit (`_coerce_excel_value`) + 7 unit (`_coerce_to_date`) + 3 HTTP (builder/export/excel) + 2 HTTP (company-aging/excel cache hit + zero-row). Tümü PASS. |

## Mutlak kural uyumu

| Kural | Durum |
|---|---|
| Pilot mutation YOK | ✓ — sadece dev tenant ile lokal test |
| Backend response shape DEĞİŞMEDİ | ✓ — sadece 500→200 ve internal error detail |
| Spec gevşetilmedi | ✓ — `5xx==0` assertion aynı |
| PII leak YOK | ✓ — existing PII guard kalıbı korundu; logger.exception body içermiyor |
| External call YOK | ✓ — tamamen in-process XLSX |
| `@cached` route handler doğrudan çağrılmıyor | ✓ — `_compute_company_aging` helper'ı üzerinden |

## Lokal test sonucu

```
$ VITE_BACKEND_URL=http://localhost:8000 \
  python -m pytest backend/tests/test_reports_export_excel_500_regression.py -q
.......................                                                  [100%]
23 passed in 10.01s
```

- 11 unit (`_coerce_excel_value`): None, bool, int, float, NaN/Inf, Decimal, datetime, date, bytes, list, custom obj
- 7 unit (`_coerce_to_date`): ISO string, ISO+Z, native datetime, native date, None, garbage string, int
- 3 HTTP builder excel: empty cols (no-500), zero rows + valid XLSX, default cols + valid XLSX
- 2 HTTP company-aging excel: zero-folio valid XLSX, cache-hit returns valid XLSX (regression for cached repr bug)

## Architect code review (1 tur)

`subagent_evaluate_task` ilk turda 2 valid issue raporladı:

1. **HTTPException import eksik** — `backend/routers/departments/reports.py` `try/except HTTPException + raise HTTPException(500)` ekledim ama `HTTPException` import edilmemişti → exception path'inde `NameError`. FIX: line 21 `from fastapi import APIRouter, Depends, HTTPException, Query`.
2. **`_compute_company_aging` tenant scope eksik** — `db.companies.find_one({'id': company_id}, {'_id': 0})` çağrısı `tenant_id` filtre etmiyordu → company ID çakışması durumunda cross-tenant metadata leak riski. FIX: `{'id': company_id, 'tenant_id': tenant_id}` ile scope edildi.

Her iki fix sonrası 23/23 test yine PASS. Architect performans uyarısı (`@cached` kaldırma sonrası export hot-path latency) bilgi amaçlı; export endpoint'leri düşük frekanslı + correctness-critical olduğu için kabul edildi, ADR followup section'ına data-level cache opsiyonu eklendi.

## Verdict

**GO** — lokal test 23/23 PASS (architect fixes dahil). Stress CI rerun bekleniyor; bu rapor POST-RERUN bölümüyle güncellenecek.

## POST-RERUN tur-1 (CI 22:01 UTC) — NO-GO, gerçek root cause açığa çıktı

CI fix sonrası ilk koşu hala 5xx=2 verdi (`statuses=[200,200,200,200,200,500,500]`). Bizim eklediğimiz `logger.exception` deployment loglarında gerçek traceback'i ortaya çıkardı:

```
2026-05-20T21:53:47 [ERROR] routers.report_builder: report_builder excel export failed
  tenant=23377306-... data_source=folios cols=['folio_number','guest_name','room_number','status']
  File "backend/routers/report_builder.py", line 673, in _build_excel_response
    from openpyxl import Workbook
ModuleNotFoundError: No module named 'openpyxl'

2026-05-20T21:53:49 [ERROR] routers.departments.reports: company_aging excel export failed
  for tenant=23377306-...
  File "backend/core/utils.py", line 53, in create_excel_workbook
    from openpyxl import Workbook
ModuleNotFoundError: No module named 'openpyxl'
```

**Gerçek root cause**: `openpyxl` deployment ortamında kurulu değil. Local dev'de mevcut (yüzeysel test PASS verdi), `backend/requirements/reports.txt` içinde declared ama deploy `pyproject.toml`'dan kurulum yapıyor ve oraya hiç eklenmemiş.

Bizim Task #246 kapsamındaki kod düzeltmeleri (datetime coerce, `@cached` kaldırma, value coerce) doğru ve gerekli savunma katmanları — ancak gerçek 500'lerin nedeni değildi. Tek faydaları: deploy logger.exception sayesinde gerçek traceback'i artık görünür kıldı.

**Fix tur-2**: `openpyxl==3.1.2` `pyproject.toml` `[project].dependencies` listesine eklendi (`installLanguagePackages` üzerinden, uv.lock güncel). Pakage `backend/requirements/reports.txt` (== 3.1.2) ile sürüm uyumlu.

**Gerekli adım**: Deployment redeploy — CI yeniden tetikleneceğinde fix etkili olacak.

## POST-RERUN tur-2 (CI bekleniyor)

Deploy publish + CI rerun sonrası:
- F8H §90 § C `5xx=0` assertion PASS olmalı.
- `builder_excel` ve `dept_aging_xlsx` 2xx + valid XLSX content-type dönmeli.
- Hiçbir P0/P1 finding `reports_export` modülünden çıkmamalı.

(Bu bölüm CI tamamlandıktan sonra doldurulacak.)
