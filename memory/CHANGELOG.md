# CHANGELOG


## 2026-04-08 - REFACTOR: Gelismis (Advanced) Modül Konsolidasyonu (8 → 4)

### Sorun
Gelismis menüdeki 8 modülün çoğu aynı/benzer işleri yapıyordu:
- Fiyat önerisi: RMS, Revenue Engine, Revenue Autopilot, AI Modülleri (4 farklı yerde)
- Talep/doluluk tahmini: RMS, Revenue Engine, Data Intelligence, AI Modülleri (4 farklı yerde)
- Autopilot: Revenue Autopilot (v2) ve AI Modülleri (eski v1)

### Konsolidasyon
| Yeni Modül | İçerik | Eski Modüller |
|---|---|---|
| **Gelir Yönetimi** | Fiyat stratejisi + gelir motoru + autopilot | RMS + Revenue Engine + Revenue Autopilot |
| **AI & Zeka** | AI hub + veri zekası | AI Modülleri + Data Intelligence |
| **Mesajlaşma** | SMS/Email/WhatsApp | Messaging Center (değişmedi) |
| **Analitik & Raporlar** | Rapor dışa aktarma + ML zamanlayıcı | Analytics Export + ML Scheduler |

### Yeni Dosyalar
- `/app/frontend/src/pages/GelirYonetimiPage.jsx` — Tab wrapper (3 sekme)
- `/app/frontend/src/pages/AIZekaPage.jsx` — Tab wrapper (2 sekme)
- `/app/frontend/src/pages/AnalitikRaporlarPage.jsx` — Tab wrapper (2 sekme)

### Değişiklikler
- `RMSModule.jsx`: `embedded` prop desteği (Layout atlanabilir)
- `RevenueEngineDashboard.jsx`: `embedded` prop desteği
- `AIModule.jsx`: `embedded` prop desteği
- `navItems.jsx`: 8 advanced item → 4 item
- `routeDefinitions.jsx`: Yeni rotalar + legacy backward compat
- `Layout.jsx`: Yeni nav key'ler için icon mapping

### Test Sonuçları
- Frontend: 14/14 test geçti (%100)
- Legacy rotalar hâlâ erişilebilir
- Çift Layout sorunu yok

---

### Sorunlar
1. **Revenue (RMS) Modülü**: Frontend'de 5 API endpoint çağrısı yapılıyor ama `enterprise_router.py`'daki basit/statik versiyonlar gerçek `rms_router.py` endpoint'lerini eziyordu
2. **İkon Tutarsızlığı**: Gelismis menüdeki 5 modül (Data Intelligence, Messaging Center, ML Scheduler, Revenue Autopilot, Analytics Export) genel Home ikonu kullanıyordu

### Düzeltmeler
1. **`domains/pms/enterprise_router.py`**: 6 çakışan endpoint kaldırıldı (comp-set, pricing-strategy GET/PUT, demand-forecast, price-adjustments, apply-recommendations)
2. **`domains/revenue/rms_router.py`**: 
   - `GET /rms/pricing-strategy` — Gerçek ADR hesaplama, ML önerileri, pazar pozisyonu
   - `PUT /rms/pricing-strategy` — auto_pricing_enabled DB'de güncelleme
   - `GET /rms/price-adjustments` — Uygulanan öneri geçmişi
   - `POST /rms/apply-recommendations` — Toplu öneri uygulama + audit trail
   - `GET /rms/demand-forecast` — `days` parametresi desteği + canlı booking verisi
   - `GET /rms/comp-set` — Zenginleştirilmiş yanıt (avg_rate, revpar, occupancy_rate)
3. **`pages/RMSModule.jsx`**: Response key uyumsuzlukları düzeltildi (competitors/comp_set, forecast/forecasts)
4. **`components/Layout.jsx`**: 5 yeni ikon eklendi (BrainCircuit, MessageSquare, Clock, Rocket, Download)

### Test Sonuçları
- Backend: 17/17 test geçti (%100)
- Frontend: Tüm UI testleri geçti (%100)

### Düzeltilen Dosyalar
- `/app/backend/domains/revenue/rms_router.py`
- `/app/backend/domains/pms/enterprise_router.py`
- `/app/frontend/src/pages/RMSModule.jsx`
- `/app/frontend/src/components/Layout.jsx`

---


## 2026-04-06 - FEATURE: Rate Manager Provider Toggle (P1)

### Özellik
Exely ve HotelRunner rate manager sayfaları arasında hızlı geçiş toggle'ı eklendi. Her iki sayfanın üst kısmında segmented control tarzı toggle ile tek tıkla provider değiştirme.

### Yeni Dosyalar
- `/app/frontend/src/pages/rate-manager/ProviderToggle.jsx` — Provider toggle bileşeni

### Değişiklikler
- `RateManager.jsx`: ProviderToggle import + active="exely" ile eklendi
- `HRRateManager.jsx`: ProviderToggle import + active="hotelrunner" ile eklendi

### Test Sonuçları
- Frontend: 10/10 test geçti (%100)

---

## 2026-04-06 - BUGFIX: pipeline.py Lint Hatası Düzeltmesi

### Düzeltme
`domains/channel_manager/ingest/pipeline.py` dosyasındaki inline import'lar (uuid, core.database, data_model) dosyanın üst kısmına taşındı. Ruff I001 lint hatası giderildi.

---

## 2026-04-06 - FEATURE: VCC (Sanal Kredi Kartı) Güvenli Görüntüleme

### Özellik
OTA/Acente sanal kart bilgileri AES-256-GCM ile şifreli saklanır. Otelci kart detaylarını **en fazla 3 kez** görüntüleyebilir. Backend seviyesinde zorunlu.

### Yeni Dosyalar
- `/app/backend/routers/vcc_router.py` — VCC CRUD + reveal (3-view limit) endpoint'leri
- `/app/frontend/src/pages/reservation-detail/OnlinePaymentTab.jsx` — Online Ödeme sekmesi

### Değişiklikler
- `ReservationDetailModal.jsx`: "Online Odeme" sekmesi eklendi, CreditCard import düzeltildi
- `bootstrap/router_registry.py`: VCC router kaydedildi

### API Endpoint'leri
- `POST /api/pms/reservations/{id}/vcc` — Kart kaydet (şifreli)
- `GET /api/pms/reservations/{id}/vcc/status` — Durum sorgula
- `POST /api/pms/reservations/{id}/vcc/reveal` — Kart aç (1/3 hak)
- `DELETE /api/pms/reservations/{id}/vcc` — Kart sil

### Güvenlik
- AES-256-GCM şifreleme (FieldEncryptionService)
- Atomic view counter ($lt koşulu, race condition koruması)
- 3 hak dolunca kalıcı kilitleme
- Her işlem activity log'a kaydedilir

### Test Sonuçları
- Backend: 13/13 test geçti (%100)
- Frontend: Tüm UI testleri geçti (%100)

---

## 2026-04-06 - BUGFIX: Bildirim Sistemi Kapsamlı Düzeltme

### Sorunlar
1. **Bildirimler okundu yapılamıyordu**: HR sync `is_read: False` kullanırken, frontend/API `read` kullanıyordu → alan uyuşmazlığı
2. **Tekrarlayan isim değişikliği bildirimleri**: Dedup mekanizması yoktu, her polling döngüsünde aynı değişiklik için yeni bildirim oluşturuluyordu
3. **İsim değişikliği ping-pong**: Eski payload ile booking geri alınıyordu, sonra yeni payload ile tekrar güncelleniyordu (A→B, B→A döngüsü)
4. **İptal bildirimleri gelmiyordu**: Pipeline `_propagate_cancellation_to_booking` iptali yapıyordu ama bildirim oluşturmuyordu
5. **İki bildirim ikonu**: Alt kısımdaki NotificationCenter gereksiz ve boştu
6. **Okundu işaretleme zorluğu**: Manuel olarak hepsini tek tek okundu yapma gerekiyordu

### Düzeltmeler
1. **`notifications_router.py`**: 
   - `is_read` → `read` alan normalizasyonu eklendi (list endpoint'inde)
   - `unread_count` sorgusu `{"$ne": True}` ile güncellendi (hem eksik `read` hem `is_read` yakalıyor)
   - `PUT /api/notifications/mark-all-read` endpoint'i eklendi (toplu okundu işaretleme)
2. **`hotelrunner_sync.py` — `_sync_reservation_update`**: 
   - `dedup_key` ile bildirim tekrarı engellendi
   - Stale update guard: `last_synced_from_provider_at` ile karşılaştırma → ping-pong önlendi
   - Bildirim formatı düzeltildi: `title`, `priority`, `category` eklendi
3. **`pipeline.py` — `_propagate_cancellation_to_booking`**: 
   - İptal bildirimi oluşturma eklendi (dedup_key ile)
4. **`App.jsx`**: Alt kısımdaki NotificationCenter (2 adet) kaldırıldı
5. **`NotificationBell.jsx`**: Dialog açıldığında otomatik `mark-all-read` çağrısı

### Yeni Özellik: Rezervasyon Detayında Zaman Bilgileri
- `InfoTabs.jsx`: "Sisteme düşme zamanı" (created_at) gösteriliyor
- `ReservationDetailModal.jsx`: Sidebar'da "Oluşturulma" zamanı eklendi
- `helpers.jsx`: `fmtDateTime` yardımcı fonksiyonu eklendi

### Test Sonuçları
- Backend: 8/8 test geçti (%100)
- Frontend: Tüm UI testleri geçti (%100)

### Düzeltilen Dosyalar
- `/app/backend/domains/notifications_router.py`
- `/app/backend/domains/channel_manager/providers/hotelrunner_sync.py`
- `/app/backend/domains/channel_manager/ingest/pipeline.py`
- `/app/frontend/src/components/NotificationBell.jsx`
- `/app/frontend/src/App.jsx`
- `/app/frontend/src/pages/reservation-detail/InfoTabs.jsx`
- `/app/frontend/src/pages/ReservationDetailModal.jsx`
- `/app/frontend/src/pages/reservation-detail/helpers.jsx`

---

## 2026-04-06 - BUGFIX: Çoklu Oda Kısmi İptalinde Kademeli İptal Yayılması

### Sorun
Çoklu oda rezervasyonunda TEK bir oda iptal edildiğinde, sonraki polling döngülerinde kalan TÜM odalar da tek tek iptal ediliyordu.

### Kök Neden (3 katmanlı)
1. **`explode_multi_room_reservation`**: `{**raw_reservation}` ile üst seviye `state="cancelled"` ve `cancel_reason` TÜM odalara kopyalanıyordu. `else` dalı sadece `_room_cancelled=False` atıyordu ama sızmış `state` ve `cancel_reason` TEMİZLENMİYORDU.
2. **Phase A/A.5**: `bool(sub_res.get("cancel_reason"))` kontrolü, üst seviyeden sızan `cancel_reason` yüzünden AKTİF odaları da iptal olarak algılıyordu.
3. **Phase B**: `timestamp_changed` yolunda, üst seviye `effective_state="canceled"` olan rezervasyonlarda herhangi bir timestamp değişikliğinde (isim/tarih) TÜM odaları iptal ediyordu.

### Düzeltmeler
1. **`hotelrunner_shared.py` — `explode_multi_room_reservation`**: `else` dalında üst seviyeden sızan `state` ve `cancel_reason` temizleniyor
2. **`hotelrunner_sync.py` — Phase B**: Aktif odalar `stored_status`'larını koruyor
3. **`hotelrunner_sync.py` — Phase A.5 Paginasyon**: Tüm sayfalar dolaşılıyor

### Düzeltilen Dosyalar
- `/app/backend/domains/channel_manager/providers/hotelrunner_shared.py`
- `/app/backend/domains/channel_manager/providers/hotelrunner_sync.py`
