# CHANGELOG


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
