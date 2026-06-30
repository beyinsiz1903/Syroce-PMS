# Syroce PMS — Acente Otomasyon Uygulaması Görev Promptu (Senaryo B)

Bu dosya, AYRI bir DigitalOcean projesinde geliştirilen acente otomasyon uygulamasının
agent'ına **olduğu gibi yapıştırılacak** kendi-kendine yeten görev promptudur.

Kaynak: kilitli kontrat `docs/B2B_AGENCY_APP_HANDOFF.md`. Bu dosya o kontratın
**Senaryo B** (acente ayrı DigitalOcean projesinde; güvenlik yalnızca X-API-Key; gerçek-zaman
için Redis Streams DEĞİL, webhook aboneliği + REST polling) için sadeleştirilmiş, eksiksiz
sürümüdür. Uç adları/parametreleri/şemaları canlı OpenAPI (`/api/openapi.json`) ile
doğrulanmıştır; locked-contract'ta açık JSON gövdesi olmayan yerlerde şekil tahmin
EDİLMEMİŞ, OpenAPI'ye yönlendirilmiştir.

Senaryo A farkı (yalnızca PMS DigitalOcean'da + acente VPC/özel ağ paylaşıyorsa): ek
olarak mTLS + sabit çıkış IP allowlist ingress'te zorunludur ve gerçek-zaman için Redis
Streams (`b2b:tenant:{t}:agency:{a}:ari:v1`) kullanılabilir. Ayrı DigitalOcean projeleri
arasında Redis erişilemez; Senaryo A'yı YALNIZCA özel ağ varken uygula.

---

```
GÖREV: Syroce PMS'i yetkili (authoritative) B2B backend kabul eden, AYRI bir "acente
otomasyon uygulaması" kur ve geliştir. Uygulama PMS'e bir kanal yöneticisi (channel
manager) gibi bağlanır: müsaitlik sorgular, fiyat alır, rezervasyon oluşturur/iptal eder,
folio okur ve PMS'ten gelen iş bildirimlerini (rezervasyon/iptal vb.) webhook ile alıp
müsaitlik/fiyat değişimlerini REST polling ile kendi yerel envanterine işler.

Bu kontrat KİLİTLİDİR. Uygulamayı bu sözleşmeye göre yaz; PMS tarafı additive ve
geriye-uyumlu kalır. Tüm yazma yollarında idempotent ol, tüm hataları fail-closed işle,
hiçbir gizli değeri (X-API-Key, request_token, connect code) log'lama/ekrana yazma.

ORTAM (Senaryo B — bu uygulamanın varsayılanı)
- Güvenlik: yalnızca X-API-Key (uygulama seviyesi). mTLS / IP-allowlist YOK (bunlar yalnızca
  PMS DigitalOcean ingress'inde, Senaryo A'da zorlanır — DigitalOcean-DigitalOcean'te kurma).
- Gerçek-zaman: PMS'in Redis'i dışarıdan ERİŞİLEMEZ. Redis Streams KURMA. Bunun yerine
  webhook aboneliği + periyodik REST polling kullan.

==================================================================
0. ONBOARDING — bağlantı & API key edinme (onay-kapılı; key OTEL ONAYI olmadan basılmaz)
==================================================================
Otelden out-of-band (güvenli kanal) iki değer al:
- Otel ID (tenant_id): otel, PMS Ayarlar > B2B Entegrasyon sekmesinde görür.
- Bağlantı Kodu (connect code): aynı sekmede "üret/yenile" ile alınır; ham değer YALNIZCA o
  an BİR KEZ gösterilir. Düşük yetkilidir: yalnızca bağlantı isteği oluşturabilir ve durum
  sorgulayabilir — key BASAMAZ.

Adım 1 — bağlantı isteği oluştur
  POST /api/b2b/connect-requests            (JWT YOK; tenant connect code'dan çözülür)
  Başlık: X-Connect-Code: <bağlantı kodu>
  Gövde (ConnectRequestIn; agency_name ZORUNLU; fazladan alan gönderme):
  {
    "agency_name": "Acente Adı",
    "contact_name": "", "contact_email": "", "contact_phone": "",
    "note": "", "external_agency_id": "",
    "agency_platform_request_id": "<acente-tarafı-idempotency-id>",
    "requested_scopes": ["booking_engine", "webhooks"]
  }
  Başarı (201) — request_token SADECE BURADA bir kez döner:
  {
    "request_id": "<uuid>",
    "request_token": "<gizli>",
    "status": "pending",
    "message": "request_token yalnizca burada bir kez doner. Guvenli saklayin."
  }
  ZORUNLU: request_id + request_token İKİSİNİ DE kalıcı secret store'a yaz. Bu ikisi
  olmadan durum sorgulanamaz ve key çekilemez.
  Idempotent tekrar (aynı agency_platform_request_id): yanıt
  { "status": "...", "idempotent": true, "message": "..." } döner ve request_id /
  request_token İÇERMEZ. Bu yüzden bu değerleri ilk 201'den saklamış olmalısın.
  Yanlış/eksik connect code -> tek tip 401 (otel var/yok sızdırılmaz).

Adım 2 — durum sorgula (poll) ve key'i tek seferlik çek
  GET /api/b2b/connect-requests/{request_id}
  Başlıklar: X-Connect-Code: <kod>  VE  X-Request-Token: <201'den gelen token>
  - Token eksik -> 401 "Istek dogrulama anahtari gerekli".
  - Yanlış token VEYA olmayan request_id -> AYNI 401 "Gecersiz istek dogrulamasi"
    (id-varlık oracle'ı yok; 404/401 ayrımı yapılmaz).
  Yanıtlar:
  - Onay bekliyor:  { "status": "pending", "message": "Onay bekleniyor." }
  - Reddedildi:     { "status": "rejected", "reason": "..." }
  - ONAYLANDI + key hazır (İLK başarılı poll):
    {
      "status": "approved",
      "api_key": "<ham key>",
      "agency_id": "...",
      "scopes": ["booking_engine","webhooks"],
      "key_prefix": "...",
      "message": "API key tek seferlik teslim edildi. Guvenli saklayin."
    }
    api_key ham değeri SADECE bu ilk başarılı poll'da döner, sonra kalıcı null'lanır.
  - Onaylandı ama zaten çekilmiş:
    { "status": "approved", "key_available": false, "reason": "already_retrieved" }
  - Onaylandı ama teslim süresi geçmiş:
    { "status": "approved", "key_available": false, "reason": "delivery_expired" }
  Poll'u makul aralıkla (5-15 sn) yap; status=approved + api_key gelince DUR, api_key'i
  secret olarak sakla. Bundan sonra tüm çağrılar X-API-Key ile.

Adım 3 — kayıp token / fail-closed kurtarma & key rotasyonu
  - request_token kurtarılamaz (sunucuda yalnızca HMAC hash'i tutulur).
  - Key ÇEKİLMEDEN ÖNCE token kaybolursa: otelden isteği REDDETMESİNİ iste, sonra YENİ bir
    bağlantı isteği oluştur (yeni request_id + request_token). Eski istek sabit kalır, zararsızdır.
  - Key ZATEN çekildikten sonra token kaybı önemsizdir (anahtar elde).
  - Key üretilmiş ama hiç çekilmeden token kaybolduysa: otel reddeder + yeni istek; yeniden
    onayda acentede zaten aktif key olduğundan sistem İKİNCİ key BASMAZ
    (connected_existing_key_not_retrievable döner). Bu durumda otel, B2B sekmesinden
    "yenile/regenerate" ile yeni çekilebilir bir anahtar üretir ve sana out-of-band iletir;
    sen sakladığın X-API-Key'i bununla değiştirirsin. (Key rotasyonu otel tarafından başlatılır;
    acente kendi anahtarını döndüremez.)

==================================================================
1. GÜVENLİK (zorunlu)
==================================================================
- X-API-Key: HER REST çağrısında `X-API-Key: <agency_key>` başlığı. Gizli; ortam değişkeni /
  secret olarak tut, ASLA log'lama. Geçersiz/pasif anahtar -> 401; pasif acente -> 403.
- Scope (fail-closed): anahtara scopes atanmışsa yalnızca o alt-router'lara erişirsin;
  kapsam dışı alt-router -> 403. Geçerli scope'lar:
    booking_engine, folio, groups, guest_journey, guests, housekeeping, identity, kbs,
    lost_found, services, wake_up, webhooks
  Varsayılan oto-provision scope'ları: ["booking_engine", "webhooks"].
- Idempotency-Key (POST /reservations'ta ZORUNLU): her rezervasyon POST'unda istemci
  üretimli bir UUID `Idempotency-Key` başlığı gönder (aşağıya bkz).

==================================================================
2. KANAL A — REST kontratı (base: /api/b2b ; tarihler YYYY-MM-DD ; başlık X-API-Key)
==================================================================
GET /availability?check_in=&check_out=[&room_type=]
  (check_in + check_out ZORUNLU, room_type opsiyonel)
  Yanıt:
  {
    "check_in": "2026-07-01",
    "check_out": "2026-07-03",
    "room_types": [
      { "room_type": "Deluxe", "capacity": 2, "base_price": 1200, "amenities": [],
        "bed_type": "", "total_rooms": 10, "available_rooms": 4 }
    ]
  }

GET /rates?start_date=&end_date=[&room_type=]
  (start_date + end_date ZORUNLU, room_type opsiyonel)
  Acenteye özel fiyat takvimini (agency_rate_calendar) döner. Tam yanıt şekli için PMS
  OpenAPI'sine bak (locked-contract'ta açık JSON şeması verilmemiş — tahmin etme).

POST /reservations           (Başlık: Idempotency-Key: <uuid> ZORUNLU)
  Gövde (B2BReservationCreate; room_type/check_in/check_out/guest_name ZORUNLU):
  {
    "room_type": "Deluxe",
    "check_in": "2026-07-01",
    "check_out": "2026-07-03",
    "guest_name": "Ad Soyad",
    "guest_email": "",
    "guest_phone": "",
    "adults": 2,
    "children": 0,
    "special_requests": "",
    "total_amount": 0
  }
  Başarı (200):
  {
    "ok": true,
    "reservation": {
      "id": "<uuid>", "confirmation_code": "B2B-XXXXXXXX", "status": "confirmed",
      "room_type": "Deluxe", "room_number": "101",
      "check_in": "2026-07-01", "check_out": "2026-07-03",
      "guest_name": "Ad Soyad", "total_amount": 2400,
      "commission_rate": 12.5, "commission_amount": 300.0,
      "created_at": "..."
    },
    "message": "Rezervasyon olusturuldu: B2B-XXXXXXXX"
  }
  Idempotency davranışı (kritik):
  - Aynı Idempotency-Key + aynı gövde -> ikinci rezervasyon OLUŞTURULMAZ; orijinal yanıt
    (başarı ya da iş-kuralı hatası) AYNEN döner (replay).
  - Aynı anahtar + FARKLI gövde -> 409.
  - Aynı anahtar şu an işlenirken (in-flight) -> 429 + Retry-After: 2. Retry-After kadar
    bekle, AYNI anahtarla tekrar dene.
  - İş-kuralı 4xx kalıcıdır (aynı anahtarla tekrar -> aynı hata); beklenmeyen 5xx aynı
    anahtarla güvenle tekrar denenebilir.
  - Başlık gönderilmezse eski (idempotent olmayan) davranış korunur — ama HER ZAMAN gönder.

GET /reservations?status=&check_in_from=&check_in_to=&limit=(<=500)
  Yalnızca çağıran acentenin rezervasyonları.
GET /reservations/{reservation_id}            Tekil detay (cross-agency IDOR korumalı).
PUT /reservations/{reservation_id}/cancel     İptal. İptal, kontenjan/kredi sayaçlarını
  doğrudan geri bırakmaz — sayaçlar rezervasyon yaşam döngüsüne göre PMS tarafında yönetilir.

FOLIO (scope: folio)
  GET  /folio/{booking_id}                    Folio detayı (charges/payments/balance).
  POST /folio/{booking_id}/charge             Yeni charge ekle. Gövde (FolioChargeCreate;
       charge_type/description/amount ZORUNLU): { "charge_type", "description", "amount",
       "quantity": 1 }
  GET  /folio/{booking_id}/invoice            Salt-okunur JSON fatura/folio özeti.
  Folio yanıtlarının tam JSON şekli için OpenAPI'ye bak (locked-contract'ta açık şema yok).

DİĞER ALT-ROUTER'LAR (gerekirse, ilgili scope ile; tam liste OpenAPI'de)
  /guests/* , /groups/* , /housekeeping/* , /identity/* , /kbs/* , /lost-found ,
  /wake-up-calls , /guest-journey/* , /concierge/* , /spa/* , /webhooks*
  Güncel ve eksiksiz uç/şema kaynağı: GET /api/openapi.json (yalnızca sahip olduğun
  scope'lara erişebilirsin).

==================================================================
3. GERÇEK-ZAMAN (PMS -> acente) — Senaryo B: Webhook + REST polling
==================================================================
WEBHOOK ABONELİĞİ (olay-bazlı iş bildirimleri; scope: webhooks)
  POST   /webhooks            Gövde (WebhookRegister; url + events ZORUNLU, secret opsiyonel):
         { "url": "https://acente.../hook", "events": ["reservation.created", ...],
           "secret": "<imza-dogrulama-sirri>" }
         Acente başına en fazla 5 abonelik.
  GET    /webhooks            Mevcut abonelikleri listele.
  DELETE /webhooks/{id}       Aboneliği iptal et.
  POST   /webhooks/{id}/test  Kayıtlı URL'e test ping tetikle.
  PMS, olay anında (ör. reservation.created) kayıtlı URL'e imzalı çağrı yapar (retry + DLQ).
  Acente tarafı: gelen webhook'u secret ile imza-doğrula, hızlı 2xx dön, işi kuyruğa al,
  asenkron işle. İmza doğrulanamazsa reddet (fail-closed).

REST POLLING (müsaitlik / fiyat / stop-sale senkronu)
  - /availability ve /rates uçlarını makul aralıkla (ör. 1-5 dk, talebe göre ayarla) çek;
    yerel müsaitlik/fiyat/stop-sale tablonu güncelle.
  - PMS yetkilidir; çakışmada PMS kazanır. İdempotent uygula: (room_type, tarih aralığı)
    anahtarıyla son değeri yaz (last-write-wins).

NOT: Redis Streams (Kanal B) bu senaryoda KULLANILMAZ; PMS Redis'i public değildir ve ayrı
DigitalOcean projeleri arasında erişilemez. (Yalnızca Senaryo A / DO+VPC'de stream tüketimi
geçerlidir.)

==================================================================
4. HATA SEMANTİĞİ (REST)
==================================================================
  401  API key eksik/geçersiz/pasif           -> anahtarı kontrol et; tekrar deneme.
  403  Acente pasif veya scope yetersiz        -> yetki/scope sorunu; tekrar deneme.
  402  Kredi limiti aşıldı (credit guard)      -> ödeme/limit; rezervasyon reddedildi.
  409  Idempotency farklı gövde / allotment dolu / oda çakışması
                                               -> gövdeyi/anahtarı düzelt; allotment için
                                                  başka tarih/oda dene.
  422  Sözleşme allowed_room_types dışı oda tipi / geçersiz gövde -> istek alanlarını düzelt.
  429  Aynı Idempotency-Key işleniyor          -> Retry-After kadar bekle, aynı anahtarla tekrar.
  5xx  Geçici sunucu hatası                    -> aynı Idempotency-Key ile güvenle tekrar dene.

==================================================================
5. İŞ KURALLARI (PMS tarafında zorlanır — bilmek zorundasın)
==================================================================
- Komisyon: onaylı + tarih-geçerli sözleşme (agency_contracts) varsa komisyon oradan; yoksa
  agencies.commission_rate (varsayılan 0). Yanıttaki commission_rate/commission_amount
  bilgilendirme amaçlıdır.
- Allotment (kontenjan) — opt-in, HARD: sözleşmede (room_type, dönem) için rooms_allocated
  tanımlıysa kontenjan AŞILAMAZ; dolu -> 409. Tanımsızsa sınırsız. Oda-gece bazında tüketilir:
  3 gecelik tek-oda rezervasyon kontenjandan 3 birim düşer.
- Kredi — opt-in, HARD: acentede credit_limit tanımlıysa current_debt + tutar <= credit_limit
  sağlanmazsa -> 402. Tanımsızsa sınırsız. Sayaçlar yarış-güvenli (atomik) artırılır;
  rezervasyon oluşturulamazsa geri alınır.
- Sözleşme oda tipi kısıtı: allowed_room_types tanımlıysa dışındaki oda tipi -> 422 (misafir
  oluşturulmadan önce reddedilir).

==================================================================
6. GENEL İLKELER
==================================================================
- PMS'i yetkili kabul et; çakışmada PMS kazanır.
- Tüm yazma yollarında idempotent ol (POST /reservations'ta Idempotency-Key ZORUNLU).
- Hiçbir gizli değeri (X-API-Key, request_token, connect code) log'lama/ekrana yazma.
- Tüm hataları fail-closed işle; belirsizlikte yazma yapma, durumu PMS'ten doğrula.
- Sözleşme değişirse yeni REST alanları additive eklenir (geriye-uyumluluk korunur).
```

---

## Senaryo B'de "yapma" listesi (özet)
- Redis Streams tüketicisi kurma (PMS Redis'i ayrı DigitalOcean projesinden erişilemez).
- Uygulama kodunda mTLS / sabit IP allowlist kurma (yalnızca DO ingress / Senaryo A).
- API key'i önceden secret olarak bekleme — key, onboarding (connect-request) ile tek
  seferlik çekilir.
- Locked-contract'ta açık JSON şeması verilmeyen yanıtların (rates/folio/invoice) şeklini
  tahmin etme — OpenAPI'yi kaynak al.
