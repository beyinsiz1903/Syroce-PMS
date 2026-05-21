# ADR — F8H Reports/Analytics Export Hardening

**Tarih:** 2026-05-20
**Bağlı task:** #246 (root cause fix), #199 (spec authoring)
**Durum:** Accepted

## Bağlam

F8H §90 spec'i `POST /api/reports/builder/export/excel` ve `GET /api/reports/company-aging/excel` yüzeylerinde stress CI'da 500 yakaladı. Root cause iki ayrı sınıfta:

1. `@cached` decorator'ı StreamingResponse cache edemiyor — ikinci çağrı serialize edilmiş `repr()` döndürüyor.
2. `fetch_report_data` / motor dönüşleri Decimal, native datetime/date, ObjectId, NaN/Inf, bytes gibi heterojen tipler içerebiliyor; export pipeline'ı her tip için defansif değil.
3. Bir `@cached` route handler'ı doğrudan başka bir `@cached` route handler'ı çağırıyordu — kırılgan kalıp.

## Karar

### Kural 1 — `@cached` decorator'ı StreamingResponse dönen route'lara UYGULANMAZ

`StreamingResponse`, `FileResponse`, `Response(content=...)` gibi response objesi döndüren handler'lar cache edilemez (`cache_manager.cache.set` value'u JSON serialize ediyor; response objeleri için bu `repr()` string'i üretir). Cache yalnızca dict/list/Pydantic model dönen JSON endpoint'lerinde kullanılır.

İhtiyaç varsa: data builder'ı (`_compute_*` helper'ı) ayrı çağırıp export route'unda her seferinde XLSX render edilir; helper kendi içinde cache'lenebilir.

### Kural 2 — `@cached` route handler'ı doğrudan çağrılmaz

Bir route handler'ı başka bir route handler'ını doğrudan `await func(current_user)` ile çağırmamalı. `@cached` decorator'ı `Depends` sentinel'lerini ve User objelerini cache key'den dışlamaya çalışıyor olsa da decoration semantiği değişirse sessiz bozulma riski yüksek.

**Pattern:** Veri hesaplama logic'i `_compute_X(tenant_id, ...)` saf async helper'ına çıkarılır. Route handler'lar (JSON + Excel + PDF) yalnızca bu helper'ı çağırır.

### Kural 3 — Excel export hücre değer dönüşümleri defansif

`backend/routers/report_builder.py::_coerce_excel_value(val) -> (typed_value, is_numeric)` kontratı:

| Tip | Çıktı | is_numeric |
|---|---|---|
| `None` | `""` | False |
| `bool` | `"Evet"` / `"Hayır"` | False |
| `int` / `float` (finite) | aynı değer | True |
| `float` (NaN/Inf) | `str(val)` | False |
| `Decimal` (finite) | `float(val)` | True |
| `Decimal` (NaN/Inf) | `str(val)` | False |
| `datetime` | ISO string | False |
| `date` | ISO string | False |
| `bytes` | UTF-8 decode (errors=replace) | False |
| `list`/`tuple`/`set` | comma-join (recursive coerce) | False |
| `dict` | `str(val)` | False |
| diğer (ObjectId, UUID, custom) | `str(val)` (fallback `""`) | False |

`xlsx_safe()` yalnızca string yolunda uygulanır (formula injection guard — Bug AN korunur). Numeric tipler `xlsx_safe()`'ten geçmez, böylece `cell.number_format` çalışmaya devam eder.

### Kural 4 — Export route'larında outermost try/except + structured logging

Her export route handler'ı:
```python
try:
    return await _build_export(...)
except HTTPException:
    raise
except Exception:
    logger.exception("...failed tenant=%s ...", tenant_id, ...)
    raise HTTPException(status_code=500, detail="report_export_failed")
```

`logger.exception` PII içermez (sadece tenant_id + data_source + columns metadata). Detail mesajı internal koddur, kullanıcı-yüzü değildir.

## Etkilenen dosyalar

- `backend/routers/departments/reports.py` — `_coerce_to_date`, `_compute_company_aging`, refactored routes (`@cached` excel'den kaldırıldı).
- `backend/routers/report_builder.py` — `_coerce_excel_value`, `_build_excel_response`, try/except wrapping.
- `backend/tests/test_reports_export_excel_500_regression.py` — 23 case regression.

## POST-CI tur-1 (gerçek root cause)

Fix sonrası ilk stress CI koşusunda iki endpoint hala 500 verdi. Eklenen `logger.exception` sayesinde deployment loglarında görünen gerçek hata: `ModuleNotFoundError: No module named 'openpyxl'`. `openpyxl` paketi `pyproject.toml` `[project].dependencies` listesinde tanımlı değildi; deployment kurulumu bu dosyadan yapıldığı için Excel render yapan tüm route'lar (rapor builder + company-aging + diğer `core.utils.create_excel_workbook` çağıranlar) deployment'ta 500 dönüyordu.

**Lokal dev neden PASS verdi**: Dev workspace'inde openpyxl daha önce başka bir bağımlamı tarafından (veya manuel) kurulmuştu; `python -c "import openpyxl"` çalışıyordu. `backend/requirements/reports.txt` doğru sürümü (3.1.2) listeliyor ama deployment bu split-requirements dosyasını okumuyor.

**Fix**: `openpyxl==3.1.2` `pyproject.toml` dependency listesine eklendi. Bu, Task #246 kod düzeltmelerinin **yanı sıra** deploy'a girmesi gereken kritik bir tamamlayıcı düzeltmedir.

### Yeni kural (deployment dep parity)

`backend/requirements/*.txt` ile `pyproject.toml` arasında **dependency parity** garantisi yok. Production'a giden bir route'a yeni runtime bağımlılığı eklendiğinde **her iki dosyaya da** eklenmeli. Aksi halde lokal dev'de çalışan kod deploy'da `ModuleNotFoundError` ile 500 döner.

Önerilen takip: `backend/requirements/api.txt` + `reports.txt` + `worker.txt` zinciri içindeki tüm pin'leri `pyproject.toml` ile karşılaştıran bir CI check (`scripts/verify_pyproject_parity.py` gibi).

## POST-CI tur-2 (Task #253 — stres tenant'ta hâlâ 500)

Tur-1 fix'i sonrası (openpyxl pyproject.toml'a eklendi, defensive coerce + per-folio try/except) F8H §90 drill yeniden stres tenant'a karşı koştu: CSV + JSON path'leri 200, **XLSX'in iki path'i hâlâ 500** (statuses=[200,200,200,200,200,500,500]). Demo tenant'ta lokalde her iki endpoint 200 + geçerli `PK\x03\x04`. Yani bug bu kez **stres-tenant veri şekline** özgü.

**Root cause (defensive prophylaxis):** openpyxl `Cell.value =` ataması sırasında C0 control char (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F) veya >32767 char string ile karşılaşırsa `IllegalCharacterError` fırlatır. Stres tenant 27 spec × N round boyunca birikmiş residue tutuyor (free-text descriptions, decoded byte arrays with errors='replace', kullanıcı-tipi notes) — kanonik factory clean ASCII üretiyor olsa bile prior rounds artığı kalmış olabilir. CSV path bu chars'ı kabul ediyor (csv yazıcı yalnız CSV grammar'ını escape ediyor), XLSX path patlıyor.

**Fix (üç katmanlı defense):**

1. **`_coerce_excel_value` string sanitization** (`backend/routers/report_builder.py`): yeni `_xlsx_sanitize_str(s)` helper — `ILLEGAL_CHARACTERS_RE.sub("", s)` + `[:32767]` cap (ellipsis sentinel ile audit-visible truncation). Her string-üreten branch'ten geçiyor (str, bytes, datetime ISO, list-join, dict, fallback). Numeric döndüler değişmedi → number_format korunuyor.

2. **`core.utils.create_excel_workbook` aynı defense** (`backend/core/utils.py`): title cell + header cell + data cell hepsi `_xlsx_sanitize_str(xlsx_safe(value))` zincirinden geçiyor. company-aging/excel + diğer create_excel_workbook çağıranları (HR payroll, analytics-export) otomatik kapsama girer.

3. **`wb.save()` belt-and-suspenders retry** (her iki export route'unda): coerce katmanı tüm yolları kapsar ama bypass olursa (gelecek seed surface, third-party data shape), ilk save fail ederse `logger.exception` ile traceback'i kaydet + tüm hücreleri tek geçişte re-scrub edip tek seferlik retry. İkinci exception bilinçli olarak propagate olur → outer try/except gerçek nedeni log'lar.

### Yeni kural (Task #253)

Excel render eden tüm helper'lar **MUTLAKA** `_xlsx_sanitize_str` ile string cell value'larını filtrelemeli. Kural ihlali → `IllegalCharacterError` runtime 500. CSV path xlsx_safe için yeterli (csv grammar guard); XLSX path ek olarak control-char + length guard gerektirir.

### Regression coverage

`backend/tests/test_reports_export_excel_500_regression.py::TestCoerceExcelValueUnit` 6 yeni case:
- C0 control char string strip (`\x01\x0B\x0C\x1E\x00` hepsi temizlenir).
- bytes path control char strip.
- list-join nested control char strip.
- 40k char string → 32767 cap + `…` ellipsis sentinel.
- Normal string passthrough invariant.
- End-to-end openpyxl wb.save() round-trip control-char string ile (PK magic byte assert).

Toplam 17 unit test PASS.

## Architect review notları

İlk implementasyon turunda 2 issue düzeltildi:
- `HTTPException` import edildi (`reports.py` line 21).
- `_compute_company_aging` company lookup `tenant_id` ile scope edildi (cross-tenant disclosure guard).

## Followup'lar (bu ADR kapsamı dışında)

- `backend/routers/departments/reports.py` line ~195 `export_market_segment_excel` aynı `@cached` + StreamingResponse anti-pattern'ine sahip — ayrı task'ta düzeltilmeli.
- Diğer Excel/PDF export endpoint'leri `_coerce_excel_value` helper'ını adapt edebilir (HR payroll CSV, analytics-export `/generate`).
- `_compute_company_aging` N+1 `calculate_folio_balance` çağrıları — büyük tenant'larda export latency artarsa data-level (response-object DEĞİL) cache eklenebilir.
