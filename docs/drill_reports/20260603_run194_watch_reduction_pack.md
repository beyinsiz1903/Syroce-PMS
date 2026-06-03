# Run #194 WATCH Reduction Pack — Drill Report

- **Tarih:** 2026-06-03
- **Baseline:** Run #194 GREEN (current) — 708 test, PASS/FAIL/REVIEW/SKIP=1565/0/17/11, P0/P1/P2/P3=0/0/24/0, GO WITH WATCH.
- **Kapsam:** WATCH kalemlerinden 3 yüzeyin hardening'i + 1 by-design doğrulama. Web/backend; mobile/F10 AYRI ve açık.
- **Doğrulama yöntemi:** targeted `py_compile`/AST + temiz boot (Backend API restart) + canlı read-only probe (localhost:8000 — dev-domain port 8000 proxy'de placeholder döndü). Full stress CI-deferred, agent dispatch ETMEDİ.

## Ortak altyapı

- **YENİ:** `backend/common/json_safe.py` — paylaşılan `json_safe()` (Decimal128→str, Decimal→float, datetime/date→ISO, bytes/bytearray→`"<binary>"` REDACTED, ObjectId→str, recurse) + `ts_to_iso()` (mixed str|datetime|None normalize). `routers/audit_timeline.py` inline pattern'inin reusable hali.
- **Neden encode 500'ü handler-local try/except yakalayamaz:** FastAPI dönüş değerini handler GÖVDESİNİN DIŞINDA serialize eder; tek bir non-JSON-native alan (Decimal128/bytes/karışık-ts) encode adımında 500 üretir. Çözüm: return'den ÖNCE JSON-native'e coerce.
- **audit_timeline.py'ye DOKUNULMADI** (green baseline path); duplikasyon bilinçli — yeni util yalnızca yeni-hardened iki yüzeyde kullanıldı.

## T001 — `/api/security/audit-logs` 500-hardening (compliance.py)

- Handler `try/except` ile sarıldı: `ts_to_iso` ile timestamp normalize + `json_safe` ile total-serialize; hata halinde **500 yerine degraded** `{logs:[], count:0, degraded:true}`. RBAC gate + projection (before/after_snapshot exclude) DEĞİŞMEDİ. Exception mesajına PII/query detayı yazılmaz (traceback Sentry'ye).
- **Canlı probe:** `http=200`, count=100, degraded=None (happy path), timestamp tipi=str. 500 yok.

## T002 — `/api/hr/staff` serialization 500-hardening (hr/router.py)

- Return satırı `[json_safe(s) for s in masked]` ile total-serialize. Privileged (manage_hr/super_admin/self) satırlar UNMASKED döner ve raw Decimal128 maaş / datetime hire_date taşıyabilir → encode 500 riski. `_mask_hr_pii` gating + RBAC DEĞİŞMEDİ. `/api/hr/system-users` aynı handler'a delege ettiği için bedavaya fix aldı.
- **Canlı probe:** `http=200`, total=8. 500 yok.

## T003 — Room QR public submit 429 throttle (room_qr_requests.py)

- **Plan drift (gerekçeli):** plan `qr_badge/router.py` diyordu; gerçek stress burst hedefi spec 97-rate-limit-boundary.spec.js satır 84-87'de `/api/public/room-qr/{tid}/{room}/submit?t=garbage` → `room_qr_requests.public_submit_request`. Fix doğru dosyaya yapıldı.
- **Kök neden:** submit route'unda `_verify_token` (garbage token→403) `_rl_check`'ten ÖNCE çalışıyordu. BURST_N=60 garbage-token isteğin TÜMÜ 403'te short-circuit → `_rl_check` hiç çalışmadı → sayaç artmadı → 429 yok (DoS sentinel "no 429 observed", P2 soft).
- **Fix:** `_rl_check` (Redis-backed, `{room_id}:{client_ip}`, 20/600s, cache-down fail-open) token doğrulamadan ÖNCE'ye alındı. Auth ZAYIFLAMAZ — token aşağıda yine doğrulanır, geçersiz token yine 403; legit misafir (geçerli token, ≤20/10dk) etkilenmez. 403/429 insert'ten önce → DB yazımı yok (pilot_drift=0).
- **Canlı probe:** garbage-token 25× burst → **20×403 + 5×429**, 5xx=0. Throttle artık invalid-token burst'te tetikliyor.

## T004 — activity-PII (messaging.py) — BY-DESIGN

- `/messaging/activity` zaten `view_guest_list` arkasında çift maskeleme yapıyor: `_mask_freetext_pii` (inline email local-part + 9+ haneli telefon regex) notification title/message için; `_mask_recipient` delivery-log discrete recipient için. Regex flag'lenen email+telefon formatlarını kapsıyor.
- Stress principal (front_desk vb.) `view_guest_list`'e SAHİP → raw PII **by-design** (memory `stress-masked-pii-role-principal.md` ile tutarlı). Masking gap DEĞİL → kod fix YOK, gerekçeli kayıt.

## Doktrin teyidi

no fake-green (canlı 200/429 gözlendi) · no auth weakening (geçersiz token yine 403; endpoint'ler auth gerektiriyor) · no RBAC weakening (gate'ler sabit) · no PII weakening (json_safe bytes redacts; maskeleme sabit) · pilot_drift=0 (QR probe dummy tenant, yazma yok; audit/hr read-only) · external_calls=[] · FAIL/P0/P1=0 çizgisi korundu.

## Açık (bu pakette ele alınmadı)

night audit unresolved (200), backup posture, housekeeping soft cold-boot TTI, HR audit 500 (kalan), digital-key 404, full_24h data scarcity, rate-limit burst altında diğer public yüzeyler. Sıradaki seçenek: mobile/F10 baseline (ayrı ve açık).
