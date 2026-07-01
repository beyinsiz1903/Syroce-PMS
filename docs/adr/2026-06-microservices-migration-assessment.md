# ADR — Mikroservis Geçiş Değerlendirmesi ve Yol Haritası (Haziran 2026)

Durum: ÖNERİ / KARAR BEKLİYOR (operatör onayına sunulmuştur)
Tür: Mimari değerlendirme + aşamalı göç yol haritası
Kapsam: Yalnızca dokümantasyon — bu turda kod, konfigürasyon, workflow, deploy veya şema değişikliği YOK.
İlgili: `docs/ARCHITECTURE_DECISIONS.md`, `docs/MODULE_INVENTORY.md`, `docs/DATABASE_SHARDING_STRATEGY.md`, `docs/adr/2026-05-cm-hardening.md`, `docs/adr/2026-05-production-hardening.md`, `digitalocean.md`, `threat_model.md`.

Bu doküman operatörün (Murat) sorduğu iki soruya net cevap vermek için yazıldı:
1. Sistem mikroservis mimarisine (POS/AI/PMS ayrı servisler, yalnızca API ile haberleşme, çökme izolasyonu) geçmeli mi? (go / no-go)
2. Geçilecekse nasıl ve hangi modülden başlanmalı?

---

## 1. Yönetici Özeti (TL;DR)

- **Mevcut durum:** Sistem mikroservis DEĞİL. Tek bir FastAPI process'inde çalışan, iyi sınırlanmış bir **modüler monolittir** (vertical-slice). POS, AI, PMS, Channel Manager hepsi aynı uygulamada router/modül olarak mount edilir; tek MongoDB kümesi + üç katmanlı `tenant_id` izolasyonu; tek gerçek ayrı servis **Quick-ID**'dir.
- **Tavsiye:** **NO-GO (şimdilik).** Tam mikroservis mimarisine geçiş, mevcut ölçek hedefi (on binlerce kullanıcı / pilot + erken büyüme) için gerekli değildir ve maliyeti faydasından açıkça yüksektir. Doğru yol, monolidi yatay ölçeklemek ve içindeki **modül sınırlarını sertleştirmektir** (in-process modular monolith → "modulith").
- **Koşullu yol:** Eğer gelecekte gerçek bir tetikleyici belirirse (aşağıda madde 3), **strangler-fig** deseniyle **tek bir modülü** çıkararak başlanmalıdır. Quick-ID zaten bunun çalışan precedent'idir. İlk aday: **AI modülü** (en zayıf transactional bağ, en ağır/izole edilebilir yük). POS ikinci adaydır.
- **Kırmızı çizgiler:** Hangi yol seçilirse seçilsin, `digitalocean.md` doktrini ve `threat_model.md` güvenceleri korunur: tenant izolasyonu zayıflatılmaz, RBAC/auth gevşetilmez, PII açığa çıkmaz, yeşil stres baseline'ı (Run #206) korunur, no fake-green.

---

## 2. Mevcut Mimari (as-is) — Gerçeğe Sadık Tespit

Aşağıdaki tespitler kod tabanı yalnızca okunarak doğrulanmıştır (fabrike iddia yok).

### 2.1 Tek FastAPI process + modüler monolit

- Uygulama, **Application Factory** (`backend/app.py`) ile **Orchestrator** (`backend/server.py`) arasında bölünmüştür. `server.py` uvicorn giriş noktasıdır; factory `FastAPI` örneğini kurar.
- **Deferred bootstrap + warm-up gate:** `DEFER_STARTUP_BOOTSTRAP=1` iken (deploy modu) app, ağır init arka planda çalışırken dinamik route'lara (API/GraphQL/WS) `503` döndürür; health-check ve statik SPA asset'leri geçer. Bunun nedeni: ~260+ router'ın senkron import'u 20-30 sn sürer; DigitalOcean platformunun ~60 sn port-açma timeout'unu kaçırmamak için bu gate gereklidir. Bu, monolidin "ağır" olduğunun dürüst göstergesidir.
- **Router mounting:** `backend/bootstrap/router_registry.py` tek merkezi manifesto. `_EXTRACTED_ROUTERS` listesi ~260+ modülü tutar; her giriş modül yolu, router attribute'ü, OpenAPI tag'leri ve opsiyonel prefix override içerir. `_safe_import` sarmalayıcısı sayesinde tek bir modülün ImportError/syntax hatası tüm sunucuyu düşürmez (import-time izolasyon — ama runtime izolasyonu DEĞİL).
- **Domain yerleşimi:** Kod `backend/domains/` (iş mantığı: ai, pms, pos, channel_manager, guest...) ve `backend/modules/` (teknik kapasiteler: event_bus...) altında dikey dilimlere ayrılmıştır. POS `domains.pms.pos_router`/`pos_fnb_router`, AI `domains.ai.router`, PMS çekirdeği `routers.pms*` + `domains.pms*`, Channel Manager hem legacy domain router hem v2 connector'larından mount edilir.
- **Önemli gerçek:** Modüller iyi ayrılmış olsa da hepsi **aynı process içinde aynı bellek/CPU/event-loop'u paylaşır**. Bir modülün event-loop'u bloke eden ağır işi (ör. AI inference, ağır rapor) tüm process'i yavaşlatabilir; bir modülün kontrolsüz exception'ı ya da bellek baskısı diğerlerini etkileyebilir. Çökme izolasyonu **process seviyesinde YOKTUR**.

### 2.2 Tek Mongo kümesi + üç katmanlı tenant izolasyonu

Tenant izolasyonu `backend/core/database.py` ve `backend/core/tenant_db.py` üzerinden üç katmanda uygulanır:

- **Katman 1 — DB Proxy (`TenantAwareDBProxy`):** Global `db` ham Mongo client değil, bir proxy'dir. `ContextVar` ile aktif `tenant_id`'yi izler (middleware her istekte set eder). Koleksiyon erişiminde `TenantScopedCollection` döner; tüm sorgulara (`find`/`update`/`aggregate`...) otomatik `{"tenant_id": "..."}` enjekte eder ve yazıların tenant sınırını aşmadığını doğrular.
- **Katman 2 — Runtime guard (`STRICT_TENANT_MODE`):** Aktif tenant context'i olmadan tenant-scoped koleksiyona erişim `SchemaOnlyCollection` döner; CRUD'u bloke eder ama index oluşturma gibi şema işlemlerine (startup için gerekli) izin verir.
- **Katman 3 — Açık scoping + sistem erişimi:** Worker'lar `get_db_for_tenant(tenant_id)` ile açıkça scoped DB alır. Sistem/cross-tenant işlemler `get_system_db()` (`_raw_db`) kullanır ve router seviyesinde `super_admin` ile sınırlıdır.
- **Atlas 500-koleksiyon limiti:** Mongo Atlas shared-tier 500-koleksiyon limiti gerçek bir kısıttır. `backend/routers/db_admin.py` super_admin-only teşhis + allowlist'li drop (`*_test`/`*_tmp`/`legacy_*`/`__obsolete__`) sağlar; `PROTECTED_PREFIXES` (tenants/bookings/users...) çekirdek veriyi korur; drop iki-faktörlü onay ister. **Piggybacking gerçeği:** bazı koleksiyonlar (ör. `mice_accounts` banquet-competitor satırlarını taşır — bkz. `digitalocean.md` CRM dup-guard) koleksiyon sayısını düşük tutmak için çoklu kayıt türünü paylaşır. Bu, "database-per-service" tartışmasını doğrudan etkiler (madde 5).

### 2.3 Event yapısı — SXI/Outbox + Celery/Redis

- **Outbox worker (`backend/core/outbox_worker.py`):** `outbox_events` koleksiyonunda **atomic claim** (`find_one_and_update`) ile pending event'leri tek seferde sahiplenir (duplicate processing önlenir). Exponential backoff retry yaşam döngüsü + timeout'u aşmış "stuck processing" event'lerinin kurtarımı vardır. Bu, transactional outbox desenidir — at-least-once teslimat + idempotency anahtarı (`tenant:event:entity:payload_hash`).
- **Event bus abstraction (`backend/modules/event_bus/abstraction.py`):** Birleşik publish/subscribe arabirimi; tenant-aware kanal yönlendirme (`events:{tenant_id}`) + rol-bazlı filtreleme (ör. housekeeping yalnızca ilgili event türlerini görür).
- **Redis pub/sub (`backend/modules/event_bus/redis_pubsub.py`):** Production backend; çok-instance ölçekleme, backpressure (buffer > 10.000 olunca drop) ve Redis düşerse **in-memory fallback**.
- **Celery (`backend/celery_app.py`, `backend/celery_tasks.py`):** Redis hem broker hem result backend'dir. Celery Beat kritik bakımları yürütür (Night Audit ~02:00, haftalık arşivleme, self-healing örn. RNL duplicate auto-resolve). Task'lar `asyncio.run()` ile senkron Celery worker'ı async Motor sürücüsüne köprüler.
- **SXI (Syroce Xchange) bus:** Güvenilir, idempotent event dağıtımı + SSRF korumalı outbound. Mevcut asenkron iletişim omurgası budur — mikroservis iletişim deseninin **hazır temelidir** (madde 6).

### 2.4 Quick-ID — tek gerçek ayrı servis (çalışan precedent)

- **Ayrı process:** `quick-id/backend/server.py` bağımsız bir FastAPI app'tir; `quick-id/start.sh` kendi portunda (default `8099`) başlatır, kendi Mongo bağlantısını yönetir. Ana backend'den (`5000`/`8000`) ayrı porttadır → aynı host ya da farklı konteyner/sunucuda çalışabilir.
- **İletişim (proxy deseni):** Ana backend `backend/routers/quick_id_proxy.py` ile `httpx` üzerinden çağırır. `/api/quick-id/scan` ve `/api/quick-id/biometric/*` ince sarmalayıcılardır.
- **Servisler arası kimlik:** Paylaşılan `QUICKID_SERVICE_KEY` `X-Service-Key` header'ında; eyleyen kullanıcı `X-Acting-User` ile denetim için iletilir; şifreli sağlayıcı anahtarları yalnızca güvenli taşımada (loopback/HTTPS) iletilir.
- **Neden ayrıldı:** Ağır/izole iş (görüntü işleme + AI/OCR çağrıları) ve modüler kimlik katmanı. **Bu, gelecekteki herhangi bir ekstraksiyon için kanıtlanmış şablondur** (ayrı process + service-key auth + httpx proxy + kendi Mongo bağlantısı).

### 2.5 Dayanıklılık primitifleri — zaten mevcut (process-içi)

- **Failure taxonomy (`backend/controlplane/failure_model.py`):** RETRYABLE / PERMANENT / PROVIDER_ERROR / DATA_ERROR / SECURITY_ERROR sınıflandırması + severity eşlemesi + context sanitizasyonu (sır/PII sızdırmaz). Circuit-breaker kararlarının (back-off vs fail-fast) temelidir.
- **ARI hard-fail gate (`backend/domains/channel_manager/ari/hard_fail_gate.py`):** ARI push öncesi room/rate-plan mapping + connection-status doğrular; başarısızsa push'u bloke eder, değişikliği karantinaya alır, reconciliation incident'i açar. Kötü bir change-set'in ana push döngüsünü tıkamasını önler (bulkhead/quarantine).
- **Provider circuit breaker** (CM-Hardening Turu #4, bkz. `docs/adr/2026-05-cm-hardening.md`): per-connection breaker (`{provider}:{connection_id}`), fail-fast + recovery_timeout. Bunlar **mevcut** çökme-izolasyon iyileştirmeleridir — process-içi olsalar da mikroservis öncesi en yüksek getirili dayanıklılık katmanıdır.

### 2.6 DigitalOcean deploy gerçeği

- **Reserved VM (autoscale DEĞİL):** Stateful yerel Mongo/Redis + in-process worker + ağır ML build (xgboost → ~286MB CUDA) Reserved VM gerektirir; autoscale build kaynak yetersizliğinden SIGKILL alır (bkz. `digitalocean.md` gotcha "Syroce deploy target = VM"). Bu, "her servis ayrı autoscale" varsayımını doğrudan kısıtlar.
- **İki ayrı deploy:** Mobil statik (`-1`) ile web+backend (`-1-syroce`) ayrı syroce.com deploy'larıdır. Backend, COMMIT'lenmiş React `frontend/build`'i servis eder. Bu zaten "iki deployable" gerçeğidir; ama her ikisi de tek backend process'ine bağlıdır.
- **Orkestrasyon sınırı:** DigitalOcean, Kubernetes/service-mesh tarzı çoklu-servis orkestrasyonu için birinci-sınıf bir ortam değildir. N tane bağımsız servis çalıştırmak ya N ayrı Reserved VM (N× maliyet + N× operasyon) ya da harici bir bulut sağlayıcısına taşınmayı gerektirir. Bu, mikroservis maliyetinin DigitalOcean'e özgü en sert kalemidir.

---

## 3. Mikroservis İhtiyacı — Dürüst Trade-off Değerlendirmesi

### 3.1 Mikroservise geçişin GERÇEK tetikleyicileri

Mikroservis, aşağıdakilerden biri gerçek bir acı haline geldiğinde haklı çıkar:

1. **Bağımsız ölçekleme:** Bir modülün kaynak profili diğerlerinden çok farklı ve onu ayrı ölçeklemek zorundasınız (ör. AI inference GPU/CPU yerken PMS CRUD hafif). Tek process'te en pahalı modül tüm uygulamanın kaynak tabanını belirler.
2. **Bağımsız deploy + ekip ayrımı:** Farklı ekipler farklı kadanslarla deploy etmek istiyor ve monolit deploy'u bir darboğaz; ya da bir modülün deploy'u tümünün riskini taşıyor.
3. **Çökme/hata izolasyonu:** Bir modülün çökmesi (memory leak, sonsuz döngü, event-loop bloğu) diğerlerini düşürmemeli. Bu, tek process modolitinin **en gerçek zayıflığıdır** ve operatörün asıl endişesidir.
4. **Teknoloji çeşitliliği:** Bir modülün farklı bir runtime/dil/DB'ye ihtiyacı var (bu projede güçlü bir sinyal yok — tek Python/Mongo yığını yeterli).

### 3.2 Mikroservisin GERÇEK maliyetleri

- **Dağıtık transaction:** Bugün atomik MongoDB işlemleri ve unique compound index'lerle korunan akışlar (örn. `room_night_locks` overbooking guard, folio tutarlılığı) servis sınırını aştığında **artık tek bir DB transaction'ı içinde değildir**. Saga/compensation gerekir — daha karmaşık, hata-eğilimli ve test edilmesi zor.
- **Ağ gecikmesi + kısmi başarısızlık:** Bugün in-process fonksiyon çağrıları (mikrosaniye) ağ çağrılarına (milisaniye + timeout + retry) dönüşür. Her servis-arası bağ yeni bir başarısızlık modu ekler.
- **Ayrı gözlemlenebilirlik/deploy:** Her servis için ayrı log/metric/trace toplama, ayrı deploy pipeline, ayrı sağlık-kontrolü, dağıtık tracing (bugün tek process'te basit) gerekir.
- **Operasyon yükü:** N servis = N× deploy, N× monitoring, N× secret yönetimi, servis keşfi/gateway, sürüm uyumluluğu. Küçük ekip için bu, ürün geliştirmeden çalınan zamandır.
- **DigitalOcean'e özgü maliyet (madde 2.6):** Çoklu Reserved VM maliyeti + orkestrasyon eksikliği bu yükü ek olarak büyütür.

### 3.3 "On binlerce kullanıcı" için yeterlilik değerlendirmesi (dürüst)

Çoğu PMS iş yükü I/O-bağımlıdır (DB okuma/yazma), CPU-bağımlı değil. On binlerce kullanıcı, **iyi indekslenmiş tek bir Mongo kümesi + yatay ölçeklenen birden çok monolit instance'ı (stateless web katmanı) + Redis önbellek/pub-sub + Celery worker havuzu** ile rahatça karşılanabilir. Kanıt sinyalleri:

- Sistem zaten **stateless web instance'ları için tasarlanmış** (Redis pub/sub çok-instance ölçekleme + auth invalidation; outbox atomic claim çoklu worker güvenli). Yani **yatay ölçekleme yolu bugün açık** ve mikroservis gerektirmiyor.
- Darboğazlar tipik olarak DB'de oluşur (query targeting); çözüm mikroservis değil, **doğru index + okuma replikaları + sharding stratejisidir** (bkz. `docs/DATABASE_SHARDING_STRATEGY.md`). Mikroservise bölmek DB darboğazını çözmez, sadece dağıtır.
- Mikroservis ölçeği çözmez; **örgütsel ve operasyonel bağımsızlığı** çözer. Tek/küçük ekip + tek yığın varken bu faydanın bedeli henüz haklı değil.

**Sonuç:** Ölçek tek başına mikroservis gerekçesi değildir. Operatörün asıl haklı endişesi **çökme izolasyonudur** — ve bu, tam mikroservise geçmeden de büyük ölçüde iyileştirilebilir (madde 7).

---

## 4. Hedef Mimari ve Aday Servis Sınırları

Eğer/ne zaman geçilirse, sınırlar **domain sınırlarına** göre çizilmelidir (mevcut `backend/domains/` yapısı bunu büyük ölçüde hazırlamıştır):

| Aday servis | Domain karşılığı | Bağımsızlık | Transactional bağ (monolide) | Ekstraksiyon zorluğu |
|---|---|---|---|---|
| **Quick-ID / Kimlik** | `quick-id/` (zaten ayrı) | Yüksek | Yok (proxy + service-key) | TAMAMLANMIŞ (precedent) |
| **AI** | `domains/ai/` | Yüksek | Zayıf (çoğu okuma + öneri üretimi) | Düşük-Orta |
| **POS / F&B** | `domains/pms/pos_router`, `pos_fnb_router` | Orta | Orta (folio'ya yazar; pos_orders/pos_transactions) | Orta |
| **Channel Manager** | `domains/channel_manager/` + `backend/channel_manager/` | Orta | Orta (booking/inventory event'leriyle bağlı; outbox üzerinden) | Orta-Yüksek |
| **PMS çekirdeği** | `routers/pms*`, `domains/pms*`, atomic_booking, folio | Düşük (merkez) | Çok yüksek (booking↔folio↔room_night_locks atomik) | Yüksek — EN SON |

Bağımlılık yönü gerçeği:
- **PMS çekirdeği merkezdir**; booking↔folio↔inventory atomik işlemleri tek DB transaction'ına dayanır → **en son çıkarılmalı ya da hiç çıkarılmamalıdır** (kalan "core monolith").
- **AI çoğunlukla PMS verisini okur** ve öneri/skor üretir; yazma bağı zayıf → **en kolay ilk aday**.
- **POS folio'ya yazar** ama `close_order` envanteri otomatik düşürmez (bkz. `digitalocean.md` POS transaction semantiği) → orta bağ; folio yazımı async event'e dönüştürülebilirse çıkarılabilir.
- **Channel Manager zaten outbox/SXI ile gevşek bağlı** (booking event → outbox → EventSyncService → provider push) → iletişim deseni hazır ama iki paralel CM kod tabanı (bkz. CM-Hardening #3c) önce birleştirilmeli.

İki paralel CM kod tabanı uyarısı: `backend/channel_manager/` (event sync) ve `backend/domains/channel_manager/` (provider push) iki farklı `ConnectorProvider` enum'u ve farklı koleksiyonlar kullanır (`connector_accounts` vs `hotelrunner_connections`/`exely_connections`). CM'yi servis olarak çıkarmadan önce bu birleştirilmelidir (CM-Hardening #3c Strategy B), yoksa servis sınırı içinde tutarsızlık taşınır.

---

## 5. Veri Stratejisi

### 5.1 Database-per-service mi, paylaşımlı küme mi?

- **Saf mikroservis doktrini** database-per-service ister (her servis kendi verisinin tek sahibi; başka servis doğrudan okumaz). Bu, en güçlü izolasyonu verir ama bu projede en pahalı seçimdir çünkü:
  - PMS verisi yoğun şekilde ilişkilidir (booking↔folio↔guest↔room); bunları ayrı DB'lere bölmek dağıtık join + saga gerektirir.
  - Atlas 500-koleksiyon limiti ve mevcut piggybacking, koleksiyonları zaten sıkıştırmıştır; bunları servislere bölmek yeni şema-sahiplik kararları gerektirir.
- **Önerilen pragmatik yol (aşamalı):**
  1. **Faz boyunca paylaşımlı küme + mantıksal sahiplik:** Her servis yalnızca kendi koleksiyon-kümesine yazar; başka servisin verisine yalnızca API/event üzerinden erişir (kod disiplini, fiziksel ayrım değil). `tenant_id` izolasyonu (üç katman) **değişmeden** korunur.
  2. **Yalnızca gerçekten bağımsız servisler için fiziksel ayrım:** Quick-ID zaten kendi Mongo bağlantısını yönetiyor — bu model AI için tekrarlanabilir (AI çıktıları/feature store ayrı DB'ye gidebilir; kaynak PMS verisini event/API ile alır).

### 5.2 Her iki senaryoda `tenant_id` izolasyonunun korunması (zorunlu)

- Üç katmanlı izolasyon (`TenantAwareDBProxy` + `STRICT_TENANT_MODE` + açık scoping) **her servis içinde aynen** uygulanmalıdır. Çıkarılan her servis kendi DB erişim katmanında aynı proxy/scoping disiplinini taşımalıdır — bu pazarlık konusu değildir (`threat_model.md` tenant boundary).
- Servisler-arası çağrılarda `tenant_id` **güvenilir token'dan** türetilmeli, client input'tan ASLA. Quick-ID'nin `X-Acting-User` + service-key deseni bunun şablonudur; ek olarak her servis-arası istek tenant context'ini imzalı token'dan taşımalı.
- WebSocket uyarısı (bkz. `digitalocean.md` "WS auth has no tenant context"): WS handler'lar HTTP-only tenant middleware'i bypass eder; servis ayrımında bu tuzak her serviste tekrar ele alınmalı.

### 5.3 Tutarlılık — saga / outbox

- Servis sınırını aşan iş akışları (ör. booking → folio → channel push) **mevcut transactional outbox** üzerine kurulu saga/compensation ile yürütülmelidir. Outbox zaten at-least-once + idempotency anahtarı sağlıyor; bu, dağıtık tutarlılığın hazır temelidir.
- Tek-DB atomikliği gereken çekirdek invariant'lar (overbooking guard `room_night_locks` unique index, folio tutar tutarlılığı) **tek servis içinde tutulmalıdır** — bunları servis sınırından geçirmek saga ile telafi edilemeyecek yarış koşulları doğurur. Bu, PMS çekirdeğini bütün tutmanın ana gerekçesidir.

---

## 6. İletişim Deseni

- **Asenkron olay (varsayılan):** Mevcut **SXI/Outbox + Redis pub/sub** temel alınır. Servisler-arası durum değişiklikleri (booking.created/cancelled/no_show vb.) event olarak yayılır; bu, gevşek bağ + dayanıklılık (outbox retry) sağlar ve bugün zaten çalışmaktadır.
- **Senkron (REST), yalnızca gerektiğinde:** Anlık yanıt gereken sorgular (ör. Quick-ID scan sonucu) için httpx tabanlı REST proxy — Quick-ID deseni. Senkron bağlar minimumda tutulmalı; her senkron bağ bir başarısızlık modudur.
- **Servisler-arası kimlik:** Ortak `JWT_SECRET` ile imzalı token doğrulaması her serviste tekrarlanır + servis-servis için paylaşılan service-key (Quick-ID `X-Service-Key` deseni). Kullanıcı kimliği + tenant context her hop'ta taşınır ve **server-side doğrulanır** (`threat_model.md` spoofing/EoP).
- **API gateway ihtiyacı:** Erken fazlarda gateway ZORUNLU değildir (ana backend zaten Quick-ID için ince proxy görevi görüyor — facade deseni). Servis sayısı 3-4'ü aşarsa ve dış istemciler çoğalırsa hafif bir gateway (auth + rate-limit + routing tek yerde; CORS outermost kuralı korunarak) değerlendirilir. Şimdilik **ana backend = facade** yeterli.

---

## 7. Çökme İzolasyonu / Dayanıklılık — Mikroservise GEREK KALMADAN

Operatörün asıl endişesi çökme izolasyonu olduğundan, **en yüksek getirili adım mikroservis değil, mevcut monolitte izolasyonu sertleştirmektir.** Sıralı öneriler:

1. **Yatay ölçekleme + stateless web instance'ları (en yüksek öncelik):** Birden çok backend instance çalıştır (Redis pub/sub + outbox atomic claim zaten çoklu-instance güvenli). Bir instance çökse diğerleri hizmet verir → en ucuz "izolasyon".
2. **Worker/web ayrımı:** Celery worker'ları web process'inden **ayrı çalıştır** (zaten ayrı deployable olabilir). Ağır arka-plan işi (Night Audit, AI batch, arşivleme) web request path'inden tamamen izole edilir → bir batch işi front-desk'i yavaşlatmaz. Bu, "mini-ekstraksiyon"dur ve en düşük riskli kazanımdır.
3. **Circuit breaker + bulkhead yaygınlaştırma:** Mevcut provider circuit breaker (CM #4) + ARI hard-fail gate desenini diğer dış bağımlılıklara (e-posta, Quick-ID, ödeme) genişlet. `failure_model.py` taxonomy zaten temel.
4. **Event-loop bloğu koruması:** Ağır senkron/CPU işini thread pool'a ya da ayrı worker'a taşı (event-loop'u bloke eden tek bir AI çağrısı tüm process'i donduramamalı).
5. **Retry/outbox parity:** Tüm idempotency yazıcılarının tek ortak yardımcı kullanması (bu zaten ayrı bir görev) dağıtık geleceğe de zemin hazırlar.

Bu beş adım, tam mikroservis maliyetine girmeden operatörün izolasyon endişesinin büyük kısmını karşılar.

---

## 8. Strangler-Fig Aşamalı Göç Planı (eğer/ne zaman tetiklenirse)

Tam göç YALNIZCA madde 3.1'deki bir tetikleyici gerçek acı haline gelirse başlatılır. O zaman strangler-fig (tek tek çıkar, monolit küçülür) izlenir. Big-bang yeniden yazım YASAK.

**Faz 0 — Hazırlık (kod değişikliği gerektiren ama düşük riskli):**
- İki paralel CM kod tabanını birleştir (CM #3c Strategy B).
- Worker/web ayrımını netleştir (madde 7.2).
- Servis-arası kimlik için ortak token-doğrulama yardımcısını standartlaştır.
- Kabul kriteri: yeşil stres baseline (Run #206) korunur; FAIL=0, P0=P1=0; tenant izolasyon testleri yeşil.

**Faz 1 — AI servisi (ilk aday):**
- `domains/ai/` Quick-ID şablonuyla ayrı process'e çıkarılır (ayrı FastAPI app + service-key + httpx proxy ana backend'de facade). AI kaynak verisini event/REST ile okur; çıktıları ayrı koleksiyon/DB'ye yazar.
- Kabul kriteri: AI endpoint'leri proxy üzerinden eski davranışla bire bir; AI servisi çökse PMS/POS/CM hizmet vermeye devam eder (izolasyon kanıtı); tenant izolasyonu her iki tarafta yeşil; external_calls=[] doktrini korunur.
- **Rollback:** Facade'ı tekrar in-process router'a çevir (feature-flag ile A/B); AI servisi kaldırılınca sistem monolit davranışına döner. Quick-ID precedent'i bunun geri-dönülebilir olduğunu gösterir.

**Faz 2 — POS servisi (ikinci aday):**
- POS çıkarılmadan önce folio yazımı senkron çağrıdan async event'e (outbox) dönüştürülür; saga ile folio tutarlılığı korunur.
- Kabul kriteri: POS→folio akışı saga ile tutarlı (kayıp/duplicate charge yok); POS çökse front-desk + PMS çalışır; closed-folio guard korunur.
- **Rollback:** Event-tabanlı folio yazımını senkron in-process çağrıya geri al; POS router'ı tekrar mount et.

**Faz 3 — Channel Manager servisi (koşullu):**
- Yalnızca Faz 0'da CM birleştirmesi tamamlandıysa. CM zaten outbox/SXI ile gevşek bağlı olduğundan iletişim deseni hazır.
- Kabul kriteri: OTA push/pull parity (HR + Exely); booking event → CM push akışı bozulmaz; provider circuit breaker per-connection korunur.
- **Rollback:** CM event consumer'ı tekrar in-process dispatcher'a bağla.

**PMS çekirdeği:** Çıkarılmaz (ya da en son). booking↔folio↔inventory atomikliği tek servis/DB içinde kalır.

Her fazda mutlak doktrin (her faz için kabul kriterinin parçası): no fake-green, no RBAC/auth weakening, no PII exposure, pilot_drift=0, external_calls=[], failedTests=0, P0=P1=0, yeşil stres baseline korunur, verdict ≥ GO WITH WATCH.

---

## 9. Riskler, Gözlemlenebilirlik, Baseline Koruması

- **Dağıtık tracing:** Servis ayrımı, bugün tek process'te basit olan hata-ayıklamayı zorlaştırır. Herhangi bir ekstraksiyondan ÖNCE dağıtık tracing (trace-id her hop'ta taşınan; `failure_model.py` sanitizasyonu korunarak) kurulmalıdır. Aksi halde kısmi-başarısızlıkların kök-neden analizi körleşir.
- **Baseline koruması (kritik):** Tek doğruluk kaynağı yeşil stres baseline'ıdır (şu an Run #206: 708 test, FAIL=0, P0=P1=0, P2=16/REVIEW=9/SKIP=8). Her faz bu baseline'ı korumak ZORUNDA; ekstraksiyon regresyonu bu baseline'da görünür olmalı. Agent full stress dispatch edemez — doğrulama targeted pytest / `node --check` / canlı read-only probe ile CI-deferred kalır.
- **PII/tenant riski:** Her yeni servis-arası bağ, tenant izolasyonu ve PII için yeni bir saldırı yüzeyidir (`threat_model.md` cross-tenant disclosure = en yüksek risk). Ekstraksiyon, izolasyonu **güçlendirmeli**, asla zayıflatmamalı.
- **DigitalOcean maliyet/orkestrasyon riski:** Çoklu Reserved VM maliyeti + orkestrasyon eksikliği (madde 2.6) gerçek bir kısıttır. 2-3 servisten fazlası muhtemelen harici bulut sağlayıcısına taşımayı gerektirir — bu ayrı ve büyük bir karardır.
- **Operasyonel olgunluk riski:** Küçük ekip için N servis operasyonu, ürün hızını yavaşlatabilir. Bu, "henüz değil" tavsiyesinin ana gerekçesidir.

---

## 10. Karar ve Tavsiye

**Karar: NO-GO (tam mikroservis geçişi şimdilik başlatılmaz).**

Gerekçe:
- Mevcut ölçek hedefi monolit + yatay ölçekleme + DB optimizasyonu ile karşılanabilir; ölçek tek başına mikroservis gerektirmiyor.
- Mikroservisin gerçek maliyeti (dağıtık transaction, ağ, gözlemlenebilirlik, operasyon, DigitalOcean çoklu-VM) mevcut fayda eşiğini aşıyor.
- Operatörün asıl endişesi (çökme izolasyonu) madde 7'deki adımlarla mikroservise girmeden büyük ölçüde karşılanabilir.

**Bunun yerine yapılacaklar (öncelik sırası):**
1. Yatay ölçekleme + stateless web instance'ları doğrula (madde 7.1).
2. Worker/web ayrımını netleştir (madde 7.2).
3. Circuit breaker + bulkhead + event-loop bloğu korumasını yaygınlaştır (madde 7.3-7.4).
4. Faz 0 hazırlığını (CM birleştirme, servis-arası kimlik standardı, dağıtık tracing) tamamla — bu, ileride ekstraksiyon gerekirse maliyeti büyük ölçüde düşürür.

**Koşullu go (gelecekte yeniden değerlendirme tetikleyicileri):** Aşağıdakilerden biri gerçek acı olursa bu ADR yeniden açılır ve ilk olarak **AI servisi** (Quick-ID precedent'i ile, Faz 1) çıkarılır:
- Bir modülün kaynak profili tüm uygulamanın ölçeklemesini ekonomik olmaktan çıkarırsa,
- Bir modülün çökmesi tekrar tekrar tüm sistemi düşürürse (madde 7 adımlarına rağmen),
- Ayrı ekipler bağımsız deploy kadansı için darboğaz yaşarsa.

**Başlangıç modülü (go olursa): AI** (en zayıf transactional bağ, en izole edilebilir yük, çalışan Quick-ID şablonu). İkinci: POS. PMS çekirdeği çıkarılmaz.

---

## Ek — Bu turun ürettiği değişiklikler

- **Kod:** 0 satır (yalnızca değerlendirme + yol haritası dokümanı).
- **Doküman:** bu dosya (`docs/adr/2026-06-microservices-migration-assessment.md`).
- Kapsam notu: Bu doküman web/backend mimarisi içindir; mobil/F10 kapsamı ayrı ve açıktır (bkz. `docs/TEST_COVERAGE_SCORECARD_100.md`). Değerlendirme `digitalocean.md` doktrini ve `threat_model.md` ile tutarlıdır; hiçbir öneri tenant izolasyonu / RBAC / PII güvencelerini zayıflatmaz.
