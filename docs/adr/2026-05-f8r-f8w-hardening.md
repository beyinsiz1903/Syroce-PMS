# ADR — F8R/F8S/F8U/F8V/F8W Hardening Pack (2026-05-23)

## Bağlam

2026-05-22 audit'inde F8A–F8Q kapsamı dışında kalan 5 gerçek production
saldırı yüzeyi tespit edildi (bkz. `docs/STRESS_TEST_ROADMAP.md` Hardening
Backlog). Bu ADR, audit önerilerinin spec'lere çevrilmesini ve nightly
stress suite içine entegrasyonunu kayıt altına alır.

## Karar

Aşağıdaki 5 spec eklenir ve `Full Operational Stress Suite` içine standart
katılır (Module ismiyle observability'ye düşer). Her spec final invariant
gate (`pilot_drift=0`, `external_calls=[]`) ile kapanır.

| Faz | Spec | Module | Hedef Yüzey |
| --- | --- | --- | --- |
| F8U | `98-auth-token-lifecycle.spec.js` | `auth_token_lifecycle` | JWT login/refresh/logout/revocation |
| F8V | `98B-websocket-tenant-isolation.spec.js` | `ws_tenant_isolation` | `/api/enterprise/ws/live` tenant scope |
| F8R | `91-export-artifact-idor.spec.js` | `export_artifact_idor` | 9 export endpoint cross-tenant IDOR |
| F8S | `64-file-upload-security.spec.js` | `file_upload_security` | HR staff docs + housekeeping photo upload |
| F8W | `09-ops-readiness-smoke.spec.js` | `ops_readiness` | health · backup age · CM backlog · liveness |

## Doctrine (tüm 5 spec için ortak)

1. **Mutlak kurallar:** pilot mutation=0, external_calls=[], failedTests=0,
   P0=P1=0, verdict ≥ GO WITH WATCH. Assertion gevşetme veya
   skip-as-pass YOK.
2. **Paylaşılan stress bearer'a dokunma:** F8U fresh login ile ayrı session
   açar; rotate edilen / logout edilen sadece bu fresh session'a aittir.
   `stressTokens.stress_token` kesinlikle invalidate edilmez.
3. **Module-blocked tekil scope:** her spec içinde her surface bağımsız
   block edilebilir; tek bir surface 404 → o surface SKIP, diğerleri ve
   final invariants çalışmaya devam.
4. **Sınıflandırma:**
   - **P0** — gerçek tenant isolation/auth bypass kanıtı (cross-tenant
     2xx + content, tampered/garbage token kabul, refresh token Bearer
     olarak resource erişimi, polyglot magic-bytes bypass).
   - **P1** — contract gevşemesi (5xx self-tenant download, rotation
     tekil-kullanım eksik, eşik aşımı: backup >7d / outbox >10k /
     conflict >100, sanitize bypass-but-stored).
   - **P2** — informational/observability gap (deploy yok, endpoint 404,
     env eksik, header-trust gotcha).
5. **Tek doğruluk kaynağı:** `docs/STRESS_TEST_ROADMAP.md` Hardening
   Backlog bölümü güncel kalır; bu ADR yalnızca "neden + doctrine"
   kaydıdır.

## Tasarım notları

### F8U Auth Token Lifecycle
- Serial mode (logout chain bağımlılığı).
- `tamperJwt()` real JWT signature byte-flip — header/payload geçerli,
  signature broken; "format-OK ama signature invalid" ayrı code path
  test eder.
- Cross-scope guard ayrı fresh login ile refresh token Bearer olarak
  `/auth/me` çağırır; cleanup'ta logout eder.

### F8V WebSocket Isolation
- Dynamic `import('ws')` — Node 20 native WebSocket yok; `frontend/
  node_modules/ws` bundled.
- `wsProbe()` opened/closed/closeCode/frames toplar, `collectFramesMs`
  süresince dinler. `auth_error` frame OK, herhangi başka data frame
  unauth session'da → P0.
- Cross-tenant subscribe spoof 4 farklı message shape gönderir
  (`subscribe.tenant_id`, `subscribe.room`, `join.channel`,
  `subscribe.topic`) — ws_hub schema kapalı, defansif probe.

### F8R Export IDOR
- 9 surface: 1 path-ID (`hr_payroll_run`) + 8 param-only. Path-ID
  surface'lerde pilot ID harvest → cross-tenant download attempt;
  param-only surface'lerde self-tenant smoke + unauth reject + content-type
  sanity.
- Binary-aware `downloadProbe`: `Content-Type` + `Content-Length`
  header'ları okur, body ilk 2 KB sniff (pilot marker arama). XLSX/PDF
  binary body parse etmez.
- Pilot marker = pilot_tid literal veya `PILOT_`/`PROD_` prefix; bulundu
  → severity P0, bulunmadı → severity P1 (2xx zaten suspicious).

### F8S Upload Security
- HR docs surface: backend MIME header-trust (magic-bytes verification
  YOK). Polyglot kabul edilir → P2 informational (gotcha açık-kayıt).
  Magic-bytes verification eklenmesi backlog'da.
- HK photo surface: backend Pillow magic-bytes enforce (`security/
  upload_validator.py`). Polyglot kabul edilirse P0 (validator bypass).
- Path-traversal filename: backend `safe_file_name = f"{uuid}{ext}"`
  (housekeeping L192). HR docs için filename DB'ye literal yazılır →
  Content-Disposition response yansırsa client path-traversal riski.
- Cross-tenant download iki yönlü test: stress doc → pilot token,
  pilot doc → stress token; ikisi de 403/404 zorunlu.

### F8W Ops Readiness
- Read-only nightly cron sinyal yakalayıcı.
- Eşikler:
  - backup_max_age_hours = 36 (REVIEW)
  - backup_critical_age_hours = 168 (P1)
  - cm_outbox_depth_max = 10_000 (P1)
  - cm_conflict_queue_max = 100 (P1)
- Liveness probes 5xx → P1; 4xx (404) → P2 informational. Eşikler ileride
  Production Safety Plan SLA'larına bağlanabilir.

## Sonuç

- Stress suite kapsamı 5 yeni spec ile genişler; toplam test sayısı
  ~25–30 case artar (her spec 5–7 case).
- F8R–F8W backlog entry'leri `docs/STRESS_TEST_ROADMAP.md`'de
  "✅ DONE (2026-05-23)" olarak işaretlenmiştir.
- İlk Full Operational Stress Suite çalıştırması sonrası yeni 5
  modülün her biri için drill report'ta ayrı bir bölüm beklenir;
  P0/P1=0 zorunlu, P2 informational kabul.
- F8T (HR staff self-service) ve F8X (e-fatura forbidden path source
  scan) önerileri bu pack dışında kalmıştır — ayrı backlog item.
