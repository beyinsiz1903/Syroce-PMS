# Full Stress Suite — RED Run Triage (2026-06-15)

Kaynak: Murat'in paylastigi full stress suite logu (deploy-env, ~1.5 saat, 709 test).
Ham log: `attached_assets/Pasted-...1781539343694.txt` (846 satir).

## Run ozeti

- Sonuc: **2 failed, 8 skipped, 4 did not run, 695 passed**.
- Setup yesil: seed n=500, pilot_drift baseline, external_calls=[].
- Iki FAIL'in "did not run" devamlari ayni spec'lerdeki kalan adimlardir (gercek kok = 2 FAIL).

## Karar (tek satir)

Her iki FAIL de **deploy-env** kaynaklidir; **kod regresyonu DEGIL**, baseline **#206 DEGISMEZ**. no-fake-green: test gevsetme/skip-as-pass/assertion gevsetme YOK.

---

## FAIL #1 — `08-housekeeping-mass.spec.js:260` (G: FE render TTI /housekeeping 50/200/500 satir)

- Diger 5 HK testi (A-E) GREEN; yalniz FE-render TTI (~1.7m) FAIL.
- Siniflandirma: **BILINEN deploy-env single-worker static-starvation** (memory `stress-housekeeping-render-zerorow-triage.md` + replit.md 2026-06-13 triage). HTTP 200 doner ama tek uvicorn worker API+statik+in-process isleri ayni event-loop'ta tasidigi icin agir grid render TTI esigini asar.
- Kod degisikligi YOK. Cozum deploy-side: Caddy static-front (kodu mevcut, deploy EDILMEMIS).

---

## FAIL #2 — `64-file-upload-security.spec.js:238` (B: HR docs valid upload -> 500)

### Belirti
Test B gecerli PDF yukleyince 500 bekledigi 200/201 yerine HTTP 500/502 aldi.

### Kok neden (deployment logs ile dogrulandi)
Deploy VM'inde uvicorn worker, HR belge yukleme isteginde **Bus error (core dumped)** ile cokmustur:

- `13:35:12` POST `/api/hr/staff/{id}/documents?...&label=stress_probe` -> istek 13.7s asili kaldi -> reverse-proxy `status=502` -> hemen ardindan `backend/start.sh: line 445: 456 Bus error (core dumped) ... uvicorn` + `a supervised process exited ... tearing down for platform restart`.
- Platform restart basladi (`13:35:12-14`: Atlas baglandi, WeasyPrint native lib HAZIR, SPA 396 chunk 0 empty, middleware'ler yeniden aktif).
- Test B (`label=stress_valid`) ~194ms sonra (`13:35:13`) **restart eden** backend'e carpti -> 500/502 -> FAIL.

Bu **tek olay degil**: ayni run'da `13:33:31` POST `/api/checkin/online/{id}/id-photo` (multipart upload) de 17.3s asili kalip ayni **Bus error (core dumped)** ile worker'i cokertmis. Yani iki ayri upload yuzeyi, iki ayri core dump.

### Validator/handler mantigi saglam (kanit)
- Cokmeden hemen once (`13:34:58`) ayni HR endpoint reject vakalarini DOGRU dondurdu: **413** (oversized), **400**, **400** (bad-mime/polyglot). Yani dogrulama mantigi calisiyor.
- `validate_document_bytes`: `%PDF-` magic -> temiz `application/pdf` doner (Pillow'a girmez). Recognized degilse Pillow'a duser, tum istisnalar `except Exception -> 400` ile yakalanir. `Image.MAX_IMAGE_PIXELS` her cagri yeniden sabitlenir.
- **Lokal adversarial probe** (Pillow 12.2.0, her vaka izole subprocess, SIGBUS/SIGSEGV/OOM exit-code izlendi):

  | girdi | sonuc |
  |---|---|
  | rastgele 206B | 400 (temiz) |
  | tiny_pdf `%PDF-1.4` | DOC ok=application/pdf |
  | PNG bomb 60000x60000 (header-declared) | 400 (alloc YOK, crash YOK) |
  | PNG 7999x7999 truncated | 400 |
  | PNG 4000x4000 gercek (~48MB decode) | ok (temiz) |
  | WEBP/GIF garbage | 400 |

  **Hicbiri native crash uretmedi** (SIGBUS/SIGSEGV/OOM yok). Validator adversarial girdiyi temiz 4xx ile reddediyor.

### Neden kod fix YOK
**Bus error (SIGBUS / core dumped) native bir surec cokmesidir; Python `try/except` ile yakalanamaz.** Handler'da `try/except` eklemek bu cokmeyi engellemez. Validator zaten robust (yukaridaki kanit). Bu bir 4xx mantik hatasi degildir.

### Gercek kok katki: deploy-VM bellek baskisi
- Deploy VM'inde **Redis YOK -> in-memory cache fallback** (`Redis not available... Falling back to in-memory cache`). 1.5 saatlik surekli stress yukunde in-memory yapilar birikir.
- Tek uvicorn worker + agir in-process footprint (ML kutuphaneleri, ~189 router, 396 chunk statik servis) ayni surecte.
- Iki cokme de **upload** uclarinda (dosya baytlarini tamponlayan, en bellek-yogun istek tipi) ve **13-17s asilma** sonrasi olustu -> ani native codec segfault degil, bellek thrash/OOM-bitisik SIGBUS imzasi.

### Oneriler (deploy/infra-side; kod degil)
1. Caddy static-front (FAIL #1 ile ortak): statigi uvicorn'dan ayir -> tek-worker doygunlugu ve bellek baskisi azalir.
2. Deploy VM'ine Redis saglama veya bellek artirimi -> in-memory fallback birikimini ve OOM riskini ortadan kaldirir.
3. (Opsiyonel sertlestirme, OOM'u COZMEZ) Senkron Pillow/validate cagrilarini thread-pool'a tasimak event-loop starvation'i (13-17s asilma) ve cascade'i azaltir; ancak bellek SIGBUS'ini onlemez, bu yuzden tek basina yeterli degildir ve full-stress dogrulamasi olmadan "cozdu" iddia edilemez.

---

## Doktrin uyumu

- baseline #206 DEGISMEZ · no fake-green · assertion/skip gevsetme YOK · pilot_drift=0 · external_calls=[].
- VM dogrulamasi SADECE Murat deploy + canli probe/stress re-run ile (agent full stress dispatch edemez).
