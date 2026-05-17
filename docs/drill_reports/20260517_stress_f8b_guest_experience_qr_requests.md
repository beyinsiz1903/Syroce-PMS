# F8B — Stress: Guest Experience / QR / Complaints / Messaging

**Tarih:** 2026-05-17
**Tenant:** stress (E2E_STRESS_TENANT_ID)
**Pilot etki:** 0 (drift gate her spec'in son test'i)
**Verdict (ön-rerun):** PRE-RERUN — CI #47 push beklemede

---

## Kapsam

F8A operasyonel stress paketinin (rooms / bookings / folios / RNL / HK)
üstüne **Guest Experience** yüzeyini eklendi. 4 yeni spec:

| Spec | Modül | Test sayısı | Hedef akış |
|------|-------|-------------|------------|
| `10-qr-requests.spec.js` | `qr_requests` | 7 | 50 public QR submit, 30 staff transition, SLA/stats, token guard, ext invariant, pilot drift |
| `11-service-requests.spec.js` | `service_requests` | 5 | List pagination, 20 bulk PATCH priority, dept/room filter, pilot drift |
| `12-complaints.spec.js` | `complaints` | 5 | 30 resolve (folio comp lokal), 10 escalate, list+stats, ext invariant, pilot drift |
| `13-messaging.spec.js` | `messaging` | 5 | 50 send (email/sms/whatsapp) lokal-only, conversations read, ext invariant, pilot drift |

Toplam **22 test**, F8A 6 spec × ~30 testi ile birlikte stress paketi
**10 spec / ~52 test** olarak büyütüldü.

## Backend seed extension (`backend/domains/admin/router/stress.py`)

Yeni `_build_f8b_docs(rooms, bookings, guests, stress_tid, prefix, now)`
factory'si 4 koleksiyon üretir:

- `room_qr_requests` — her gerçek odaya 1 open QR talebi (1/4'ü ~25h yaşlı
  → SLA/overdue dashboard sinyali). Kategori/öncelik round-robin, status
  `new`. `stress_seed:True` + `stress_prefix:<prefix>` tag'leri var.
- `service_complaints` — her 5 odadan 1 open complaint (500 odada 100
  şikayet). 1/10'u 30h yaşlı → escalation eligibility. **Kritik
  invariant**: `guest_id=None` — resolve flow'daki
  `_notify_guest_resolved` "no guest_id" guard'ında erken döner, Resend
  HTTP hiç tetiklenmez. `booking_id` saklı → folio compensation
  adjustment lokal Mongo update'i olarak gerçek path'i sınar.
- `messages` — her odaya 1 inbound + 1 outbound (kanal email/sms/whatsapp
  round-robin) → `/api/messaging/conversations` ve list endpoint'leri
  için anlamlı read load.
- `notifications` — her odaya 1 broadcast (1/7'si `complaint_escalated`
  yüksek öncelik).

`STRESS_COLLECTIONS` listesi 4 yeni koleksiyonu içerir → unified cleanup
loop hem teardown'da hem orphan-cleanup'ta otomatik tarar (kod
duplikasyonu yok). `_chunked_insert` 4 yeni koleksiyon için seed
pipeline'a eklendi; `counts` map'i yeni anahtarları döner.

## Kontrat ve invariant savunmaları

1. **external_calls = []** — F8B'nin merkez güvenlik gate'i. Üç ayrı
   savunma katmanı:
   - **Seed**: Complaint `guest_id=None` → Resend short-circuit.
     Messaging seed sadece DB yazımı; backend `send-{email,sms,whatsapp}`
     endpoint'leri `db.messages.insert_one` yapar, hiçbir provider
     çağrısı yok.
   - **Runtime**: Her destructive batch sonrası
     `assertNoExternalCallsPostBatch` çağrılır →
     `/api/admin/stress/external-calls` GET → `outbox_events` +
     `integration_afsadakat_outbox` stress tenant scope'lu sorgu.
   - **Aborted**: Legacy `whatsapp_service` (gerçek provider çağrılan)
     yolu — `/api/whatsapp/send-confirmation` — bu suite'te HİÇ
     kullanılmaz; sadece F8B-safe `/api/messaging/send-whatsapp` (yalın
     DB insert) çağrılır.

2. **Pilot drift = 0** — 4 spec'in son testi `pilotBookingsCount`
   karşılaştırması. Önceki F8A test'lerindeki regression pattern'i
   korunur.

3. **Rate-limit uyumu** — Public QR submit endpoint per (room+IP) için
   20/10min. Spec 10-A 50 farklı oda kullanır (oda başına 1 submit) →
   throttle gerekmiyor. Bulk endpoint token issuance tek `/api/rooms/{id}/qr-code`
   isteği per oda; suite süresi ~25-30s.

4. **Token guard** — Spec 10-D `bad_token` ve `empty_token` için 403
   bekler; HMAC-SHA256 verify atlanabiliyorsa P0 finding.

## Boot doğrulaması

- `backend/domains/admin/router/stress.py` import: `from datetime
  import UTC, datetime, timedelta` mevcut (line 35) → `_build_f8b_docs`
  içindeki `timedelta(minutes=…)`, `timedelta(hours=…)` çağrıları
  çalışıyor.
- Backend restart sonrası router_registry: `✅ routers.room_qr_requests`,
  hiçbir ImportError yok.

## CI re-run

Push sırasında smoke + business + stress GO/NO-GO bileşik raporu CI
#47'de doğrulanacak. PRE-RERUN gate kriterleri:
- `failedTests = 0`
- `external_calls_made = []`
- pilot bookings drift = 0
- P0 = P1 = 0 (P2/P3 izleme bilgisi olabilir)
- verdict ≥ `GO WITH WATCH`

CI sonucu bu raporun "POST-RERUN" bölümüne işlenecek; gerekirse
tur-numarası ile fix iterasyonu eklenecek (F8A tur-19..tur-22 pattern'i).
