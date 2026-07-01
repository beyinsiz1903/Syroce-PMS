# Syroce PMS — KBS Agent Uygulaması Kontratı (v2)

Bu doküman, **PMS sunucusu** (FastAPI, `https://<otel>.syroce.com/api`) ile
**otel masaüstündeki KBS Agent uygulaması** arasındaki resmi sözleşmeyi tanımlar.
Agent uygulaması bu kontrata göre yazılırsa, PMS tarafında ek geliştirme
gerektirmeden çalışır.

> **v2 değişiklikleri (2026-04-26):**
> - Login alanı `username` (email değil — backend `username` veya legacy `email` kabul eder)
> - Auto-enqueue: PMS check-in/checkout sonrası otomatik kuyruğa alıyor (KBS_AUTO_ENQUEUE=1 default)
> - 4 endpoint'te `Idempotency-Key` header desteği (queue, claim**, complete, fail)
> - GET `/queue?status=pending` lease süresi dolmuş in_progress'ı da döndürür (stuck recovery)
> - Yeni: `/api/kbs/alerts`, `/api/kbs/alerts/{id}/ack`, `/api/kbs/setup-info`
> - Test mode: `KBS_TEST_MODE=1` env iken complete `kbs_reference="TEST-..."` zorunlu
> - Enqueue zamanında payload validation (TC misafir → 11 hane id_number, yabancı → passport)

---

## 1. Yüksek seviyeli akış

```
┌─────────────────┐                                    ┌──────────────────┐
│  KBS Agent       │ 1. Login (otel kullanıcı + şifre) │  Syroce PMS API  │
│  (masaüstü)      │ ────────────────────────────────► │  /api/auth/login │
│                  │ ◄──── JWT token + tenant_id ──── │                  │
│                  │                                   │                  │
│  Polling döngüsü │ 2. GET /api/kbs/queue?status=    │                  │
│  (her 10-30 sn)  │ ─────── pending ────────────────►│                  │
│                  │                                   │                  │
│                  │ 3. POST /queue/{id}/claim        │                  │
│                  │ ────── (worker_id + lease) ─────►│                  │
│                  │ ◄──── job + payload (guest) ────│                  │
│                  │                                   │                  │
│                  │ 4. KBS resmi servisine HTTP/SOAP  │                  │
│  ────────────────┼─────► (police.gov.tr / GİKS)      │                  │
│                  │                                   │                  │
│                  │ 5a. Başarı → POST /complete      │                  │
│                  │     (kbs_reference)              │                  │
│                  │ 5b. Hata → POST /fail            │                  │
│                  │     (error, retry=true|false)    │                  │
└─────────────────┘                                    └──────────────────┘
```

**Kritik prensipler:**
- Agent **stateless** (yerelde minimum state). Tüm durum PMS'tedir.
- Bir iş **tek worker** tarafından claim edilir (atomik). Çift gönderim engellenir.
- Lease süresi içinde complete/fail çağrılmazsa, başka worker yeniden claim
  edebilir (worker çakıldığında otomatik kurtarma).
- Hata durumunda **PMS** karar verir (retry/dead). Agent sadece raporlar.

---

## 2. Authentication

### `POST /api/auth/login`

İki giriş modu var:

**Mod A — Otel personeli (önerilen, KBS bot için):** `hotel_id + username`
```jsonc
{
  "hotel_id": "100001",
  "username": "kbs-bot",         // user.username (e-posta DEĞİL)
  "password": "<güçlü şifre>"
}
```

**Mod B — Legacy (e-posta ile global):** sadece `email + password` (hotel_id yok)
```jsonc
{
  "email": "kbs-bot@otel.com",
  "password": "<güçlü şifre>"
}
```

Cevap (her iki mod):
```jsonc
// Response 200
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": { "id": "...", "tenant_id": "...", "role": "..." }
}
```

Agent her isteğe `Authorization: Bearer <token>` ekler. Token süresi yaklaşık
24 saat; 401 alınırsa yeniden login çağırır.

**Önerilen kurulum (kbs-bot kullanıcısı):**
1. PMS'te **Yönetim → Kullanıcılar → Yeni kullanıcı**
2. E-posta: `kbs-bot@<oteldomain>` (insan operatör değil; sadece ajan kullanır)
3. Rol: `frontdesk` (KBS izni içerir) veya `view_reports`
4. Güçlü parola üret (min 16 karakter), parola yöneticisinde sakla
5. Parola rotasyonu: 90 günde bir
6. İlk login sonrası `GET /api/kbs/me` 200 dönmeli; doğrulama yap
7. Detaylı kurulum bilgisi: `GET /api/kbs/setup-info` (login sonrası çağrılır)

### `GET /api/kbs/me`
Login doğrulaması; cevap: `{user_id, email, tenant_id, role}`. Agent başlangıçta
bunu çağırıp doğru otele bağlandığını teyit eder.

---

## 3. Faz 1 — Kuyruk Endpoint'leri

Tüm endpoint'ler `Authorization: Bearer <jwt>` zorunlu. `tenant_id` token'dan
otomatik çözülür — agent göndermek zorunda değil.

### 3.1 `POST /api/kbs/queue` — İş ekle

```jsonc
// Request
{
  "booking_id": "uuid-of-booking",     // zorunlu, mevcut rezervasyon
  "action": "checkin",                  // "checkin" | "checkout", default "checkin"
  "force": false,                       // true: aktif iş varsa bile yeni iş aç
  "max_attempts": 5,                    // 1-20, default 5
  "notes": ""
}
// Response 201
{
  "job": {
    "id": "uuid",
    "tenant_id": "...",
    "booking_id": "...",
    "guest_id": "...",
    "action": "checkin",
    "status": "pending",
    "attempts": 0,
    "max_attempts": 5,
    "worker_id": null,
    "leased_until": null,
    "next_retry_at": null,
    "last_error": null,
    "kbs_reference": null,
    "payload": {
      "guest_name": "Ahmet Yılmaz",
      "room_number": "101",
      "check_in": "2026-04-26T14:00:00",
      "check_out": "2026-04-28T12:00:00",
      "nationality": "TC",
      "id_number": "12345678901",
      "passport_number": "",
      "birth_date": "1985-03-12",
      "gender": "M",
      "father_name": "...",
      "mother_name": "...",
      "birth_place": "İstanbul",
      "address": "..."
    },
    "created_at": "2026-04-26T13:00:00+00:00"
  },
  "created": true
}
```

**Idempotency:** Aynı `booking_id` + `action` için zaten `pending` veya
`in_progress` bir iş varsa, yeni iş açılmaz; mevcut iş döner ve `created: false`
olur. `force: true` bunu by-pass eder (örn. kullanıcı el ile yeniden tetikledi).

**Hatalar:**
- `404` — booking bulunamadı veya başka tenant'a ait.
- `403` — kullanıcının `tenant_id`'si yok.
- `422` — body validasyonu (action enum'ı yanlış vs).

---

### 3.2 `GET /api/kbs/queue` — Listele + stat

```
GET /api/kbs/queue?status=pending,in_progress&limit=50
GET /api/kbs/queue?date_from=2026-04-26&date_to=2026-04-26
GET /api/kbs/queue?booking_id=<uuid>
```

```jsonc
// Response 200
{
  "jobs": [ /* en yeniden eskiye sıralı, içerik 3.1'deki job ile aynı */ ],
  "total": 50,
  "stats": {                  // tüm tenant için, filtre uygulanmaz
    "pending": 12,
    "in_progress": 1,
    "done": 145,
    "failed": 0,
    "dead": 2
  }
}
```

Stats alanı status bar için tasarlandı; filtreden bağımsız tüm-zaman sayımıdır.

**Agent polling pattern:**
```python
while True:
    r = client.get("/api/kbs/queue", params={"status": "pending", "limit": 20})
    for job in r.json()["jobs"]:
        if not job.get("next_retry_at") or now() >= parse(job["next_retry_at"]):
            try_to_claim(job["id"])
    sleep(15)  # 10-30 sn arası önerilir
```

---

### 3.3 `POST /api/kbs/queue/{job_id}/claim` — Atomik claim

```jsonc
// Request
{
  "worker_id": "agent-pc01-mehmet",   // zorunlu, 1-120 char
  "lease_seconds": 300                 // 30-3600, default 300
}
// Response 200 (başarılı claim)
{
  "job": { /* status="in_progress", worker_id, leased_until set */ }
}
// Response 409 — başka worker tutuyor veya iş kapanmış
{ "detail": "İş başka bir worker tarafından işleniyor: agent-pc02" }
{ "detail": "İş zaten kapanmış (done)" }
// Response 404 — iş yok
{ "detail": "İş bulunamadı" }
```

**Atomicity garantisi:** MongoDB `update_one` ile pending→in_progress geçişi
atomik. İki worker aynı anda aynı işi claim edemez. Stuck-worker kurtarma:
`leased_until < now` olan `in_progress` işler de claim edilebilir.

**`attempts` counter:** Her başarılı claim'de +1. `attempts > max_attempts`
olduğunda iş otomatik `dead` durumuna düşer ve 409 döner.

---

### 3.4 `POST /api/kbs/queue/{job_id}/complete` — Başarı

```jsonc
// Request
{
  "worker_id": "agent-pc01-mehmet",   // claim'i alan worker olmalı
  "kbs_reference": "KBS-2026-04-26-XXX",  // zorunlu, 1-200 char
  "notes": ""
}
// Response 200
{ "job": { /* status="done", kbs_reference, completed_at */ },
  "report_id": "uuid" }                // legacy /reports listesine de yazıldı
// Response 403 — worker_id eşleşmiyor
{ "detail": "Bu işi farklı worker claim etmiş: ..." }
// Response 409 — iş zaten kapanmış
{ "detail": "Sadece in_progress işler tamamlanabilir (mevcut: done)" }
```

**Side-effects:**
- `bookings` koleksiyonunda `kbs_reported=true`, `kbs_reference`, `kbs_reported_at` set edilir.
- `kbs_reports` koleksiyonuna legacy uyumluluk için bir özet kaydı yazılır
  (PMS UI'sindeki Gönderilenler listesi için).

---

### 3.5 `POST /api/kbs/queue/{job_id}/fail` — Hata raporu

```jsonc
// Request
{
  "worker_id": "agent-pc01-mehmet",   // claim'i alan worker
  "error": "POL_ERR_INVALID_TC: TC kimlik doğrulanamadı",  // 1-2000 char
  "retry": true                        // false: hemen dead
}
// Response 200
{
  "job": { /* status="pending" veya "dead" */ },
  "will_retry": true,
  "next_retry_at": "2026-04-26T13:31:00+00:00"   // pending ise dolu
}
```

**Retry mantığı:**
| Koşul | Sonuç |
|-------|-------|
| `retry=true` ve `attempts < max_attempts` | `status=pending`, `next_retry_at = now + backoff` |
| `retry=false` | `status=dead`, `failed_at` set |
| `attempts >= max_attempts` | `status=dead` (retry değeri ne olursa olsun) |

**Exponential backoff:** `60 * 2^(attempts-1)` saniye, üst sınır 1 saat.
Örn: 1.deneme→60s, 2→120s, 3→240s, 4→480s, 5→960s, 6+→3600s.

**Agent davranışı önerisi:**
- HTTP 5xx, timeout, ağ hatası → `retry=true`
- HTTP 4xx (geçersiz veri, 401 vs.) → `retry=false` (dead'e düşsün, operatör müdahale etsin)
- Belirsiz hatalarda → `retry=true` (PMS karar verir; max_attempts limit korur)

---

## 4. Önerilen Agent Mimarisi

```python
class KBSAgent:
    def __init__(self, base_url, hotel_id, email, password, worker_id):
        self.base = base_url.rstrip('/')
        self.token = None
        self.creds = (hotel_id, email, password)
        self.worker_id = worker_id  # benzersiz, sabit (host adı + uuid)

    def login(self):
        r = httpx.post(f"{self.base}/api/auth/login", json={
            "hotel_id": self.creds[0], "email": self.creds[1],
            "password": self.creds[2],
        })
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def poll_loop(self, interval=15):
        while True:
            try:
                r = httpx.get(f"{self.base}/api/kbs/queue",
                              params={"status": "pending", "limit": 20},
                              headers=self._headers())
                if r.status_code == 401:
                    self.login(); continue
                r.raise_for_status()
                for job in r.json()["jobs"]:
                    self.try_process(job)
            except Exception as e:
                log.warning("poll error: %s", e)
            time.sleep(interval)

    def try_process(self, job):
        # 1) Claim
        c = httpx.post(f"{self.base}/api/kbs/queue/{job['id']}/claim",
                       json={"worker_id": self.worker_id, "lease_seconds": 300},
                       headers=self._headers())
        if c.status_code == 409:
            return  # başkası aldı, sıradakine geç
        c.raise_for_status()
        job = c.json()["job"]

        # 2) KBS resmi servisine gönder (uygulamanın özel kısmı)
        try:
            kbs_ref = self.send_to_police(job["payload"])
        except RetryableError as e:
            self._fail(job["id"], str(e), retry=True); return
        except FatalError as e:
            self._fail(job["id"], str(e), retry=False); return

        # 3) Başarı
        httpx.post(f"{self.base}/api/kbs/queue/{job['id']}/complete",
                   json={"worker_id": self.worker_id,
                         "kbs_reference": kbs_ref},
                   headers=self._headers()).raise_for_status()

    def _fail(self, job_id, err, retry):
        httpx.post(f"{self.base}/api/kbs/queue/{job_id}/fail",
                   json={"worker_id": self.worker_id,
                         "error": err[:2000], "retry": retry},
                   headers=self._headers())
```

**Worker ID kuralı:** `<host>-<random4>` veya `<host>-<install-uuid>` —
makineye sabit, restart'larda değişmesin. PMS UI'sinde "kim işliyor"
göstermek için kullanılır.

**Çoklu agent:** Aynı otelde 2+ agent çalıştırılabilir. Atomik claim sayesinde
çift gönderim olmaz; throughput artar.

---

## 5. Hata Sınıflandırma Önerisi

| KBS hata | Agent davranışı | Retry |
|----------|-----------------|-------|
| Connection refused / timeout | `retry=true` | ✅ |
| HTTP 5xx | `retry=true` | ✅ |
| HTTP 429 (rate limit) | `retry=true` (uzun backoff) | ✅ |
| HTTP 401/403 (yetki) | `retry=false` + operatöre uyarı | ❌ |
| HTTP 400 (geçersiz veri) | `retry=false` (PMS'te eksik bilgi düzeltilmeli) | ❌ |
| Schema mismatch | `retry=false` | ❌ |
| Polis servisinde "duplicate" | `retry=false` (ama complete olarak işaretle) | — |

---

## 6. Eksik Kalan Şeyler (Agent tarafında geliştirilmesi gereken)

GitHub'daki `beyinsiz1903/kbs` reposu mevcut olmadığı için agent uygulamasının
yazılması gerekenleri listeliyorum:

### 6.1 KBS resmi servisi entegrasyonu (PMS dışında, agent tarafında)
- Polis/Jandarma servisinin gerçek SOAP veya REST endpoint'i (TÜRSAB sertifikası
  gerektirir, üretim için TC-Devlet kanalı).
- Servisin XSD/WSDL'ine göre mesaj çevirimi: PMS'teki `payload` → KBS XML.
- Sertifika yönetimi (mTLS), client certificate dosyası okuma.
- Servis tarafından dönen `referans_no` çıkarımı → bunu `complete` çağrısında
  `kbs_reference` olarak gönder.

### 6.2 Operatör arayüzü (opsiyonel ama tavsiye)
- Tray-icon Windows uygulaması, sistemden çıkışta otomatik başlatma.
- Login formu (kalıcı kimlik bilgileri Windows Credential Manager'da).
- Son 50 işin görsel listesi (status renkleri, hata detayı).
- Manuel "Yeniden gönder" butonu (PMS'te `force=true` ile enqueue).
- Bağlantı durumu gösterimi (PMS'e ping, KBS servisine ping).

### 6.3 Loglama ve gözlemlenebilirlik
- Yerel rotating log dosyası (PII maskelenmiş).
- Her başarısız bildirimden sonra Windows Event Log'a yazma.
- Opsiyonel Sentry/dosya senkronizasyonu.

### 6.4 Güvenlik
- JWT'yi diskte saklarken işletim sistemi keychain'i (Windows DPAPI).
- Kullanıcı şifresini bellekte tutma; sadece login anında alıp hemen unutma.
- Güncel TLS, sertifika pinning (PMS sunucusunun cert'i için).

---

## 7. Test çağrıları (curl)

```bash
TOKEN=$(curl -sS -X POST https://otel.syroce.com/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"hotel_id":"100001","email":"kbs-bot@otel.com","password":"..."}' \
  | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# 1. Kuyruk listele
curl -H "$AUTH" https://otel.syroce.com/api/kbs/queue

# 2. İş ekle
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"booking_id":"<uuid>","action":"checkin"}' \
  https://otel.syroce.com/api/kbs/queue

# 3. Claim
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"worker_id":"test-worker","lease_seconds":300}' \
  https://otel.syroce.com/api/kbs/queue/<job_id>/claim

# 4. Complete
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"worker_id":"test-worker","kbs_reference":"KBS-XXX"}' \
  https://otel.syroce.com/api/kbs/queue/<job_id>/complete

# 5. Fail (retry)
curl -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"worker_id":"test-worker","error":"timeout","retry":true}' \
  https://otel.syroce.com/api/kbs/queue/<job_id>/fail
```

---

## 8. Yol Haritası

| Faz | İçerik | Durum |
|-----|--------|-------|
| **1** | Backend kuyruk altyapısı (5 endpoint + collection) | ✅ Tamamlandı (2026-04) |
| 2 | Agent referans uygulaması (Python httpx + Tray UI) | Sende geliştirilecek |
| **3** | PMS UI: durum çubuğu + kuyruk sekmesi + manuel buton | ✅ Tamamlandı (2026-04) |
| **4** | Auto-enqueue: check-in/checkout sonrası otomatik kuyruğa | ✅ Tamamlandı (2026-04, v2) |
| **4b** | Idempotency-Key, payload validation, alarm, test mode | ✅ Tamamlandı (2026-04, v2) |
| 5 | Webhook/SSE ile agent'a anlık tetikleme (polling yerine) | Opsiyonel |

---

## 9. v2'de eklenen davranışlar (2026-04-26)

### Auto-enqueue (PMS → KBS otomatik kuyruk)
- `core.atomic_checkin_checkout.check_in_booking_atomic()` başarıyla tamamlandığında
  PMS otomatik olarak `kbs_jobs` koleksiyonuna `action="checkin"` job ekler.
- Aynı şey `check_out_booking_atomic()` için `action="checkout"` ile yapılır.
- Eksik veriyle (TC numarası yok, pasaport yok, doğum tarihi yok) iş açılmaz —
  yerine `kbs_alerts` koleksiyonuna `kind="missing_data"` alarmı yazılır.
- Kapama: `KBS_AUTO_ENQUEUE=0` env değişkeni.

### Idempotency-Key (ağ retry koruması)
4 endpoint **opsiyonel** olarak `Idempotency-Key` header destekler:
- `POST /api/kbs/queue` — scope: `kbs:queue:{booking_id}:{action}`
- `POST /api/kbs/queue/{id}/complete` — scope: `kbs:complete:{job_id}`
- `POST /api/kbs/queue/{id}/fail` — scope: `kbs:fail:{job_id}`
- (claim endpoint'i CAS ile zaten doğal idempotent; key gereksiz)

Aynı key ile gelen ikinci istek **aynı yanıtı** döner (replay). Hâlâ işleniyorsa
409 döner — agent kısa bekledikten sonra retry edebilir. UUID önerilir.

### GET /queue?status=pending — stuck recovery
Pending listesinde lease süresi dolmuş `in_progress` işler de görünür. Agent
ek sorgu yapmadan otomatik olarak çakılmış worker işlerini görür. (Claim
endpoint'i bunları zaten kabul ediyordu; eksik olan görünürlüktü.)

### Payload validation (enqueue zamanında)
`POST /queue` çağrıldığında polise gönderilemeyecek eksik veri tespit
edilirse 422 dönülür:
```json
{
  "detail": {
    "error": "kbs_payload_incomplete",
    "missing_fields": ["id_number", "birth_date"],
    "message": "..."
  }
}
```
Operatör eksik bilgiyi tamamlayıp tekrar dener veya `force=true` ile
bilinçli olarak bypass eder (geç düzeltme senaryoları).

### Test mode
`KBS_TEST_MODE=1` env iken complete çağrısında `kbs_reference` mutlaka
`TEST-` prefix'i ile başlamalı. Booking üzerinde `kbs_test=true` bayrağı
yazılır — sertifika gelmeden ajanı end-to-end test etmek için kullanılır.

### Alarmlar
- `GET /api/kbs/alerts?acknowledged=false` — okunmamış alarmlar (GM rozet)
- `POST /api/kbs/alerts/{id}/ack` — alarm görüldü işaretle
- Alarm tipleri:
  - `dead_letter` — iş `dead` durumuna düştü (fail retry yok, veya claim sırasında
    `attempts > max_attempts` aşımı tespit edildi). Operatör manuel müdahale eder.
  - `missing_data` — auto-enqueue eksik veriden bloke oldu (TC misafir →
    `id_number` 11 hane yok, yabancı → `passport`/`birth_date` yok). Operatör
    rezervasyondaki misafir kartını tamamlar, sonra manuel "Kuyruğa Ekle" basabilir.

### Atomik tekillik garantisi
PMS server tarafında MongoDB partial unique index (`_open_lock`) ile aynı
`(tenant_id, booking_id, action)` üçlüsü için **aynı anda en fazla 1 açık iş**
(pending|in_progress) garanti edilir. Eşzamanlı (race) enqueue çağrısı
DuplicateKeyError yakalanır, mevcut açık iş döner — agent için fark yaratmaz,
hep tek job kuyruğa girer.

### Setup-info endpoint
`GET /api/kbs/setup-info` ajan kurulumu için merkezi bilgi paketi döner
(önerilen bot user formatı, gerekli rol, izinler, header şablonları, env flag'ler).
Ajan ilk login sonrası bunu çağırıp ekrana gösterebilir.

---

## Kontak & Sürüm

- **Şema sürümü:** v2 (2026-04-26)
- **Geriye uyumluluk:** Tüm v1 endpoint'leri ve şemaları korundu. v2 eklemeleri
  opsiyonel (Idempotency-Key, alarmlar, setup-info). Eski v1 ajan çalışmaya
  devam eder.
