# Pilot Hotel Go-Live Playbook
## Syroce PMS — Channel Manager Production Checklist

> Bu doküman, otel PMS'lerinin canlıya çıkarken kullandığı operasyon planıdır.
> HotelRunner + Exely entegrasyonları için production-ready kontrol listesi.

---

## Phase 1: Pre-Go-Live Readiness (T-7 gün)

### 1.1 Provider Credential Doğrulama

| Kontrol | HotelRunner | Exely | Durum |
|---------|-------------|-------|-------|
| API Token/Credentials | `token` + `hr_id` | `username` + `password` + `hotel_code` | ☐ |
| Connection Test | REST /infos/channels | SOAP OTA_HotelAvailRQ (WSSE) | ☐ |
| Room Discovery | GET /rooms | OTA_HotelAvailRQ → room types | ☐ |
| Rate Plan Discovery | GET /rooms → rate_plans | OTA_HotelAvailRQ → rate plans | ☐ |
| Reservation Pull Test | GET /reservations | OTA_ReadRQ | ☐ |
| ARI Push Test | PUT /rooms/~ | OTA_HotelAvailNotifRQ | ☐ |

### 1.2 Mapping Tamamlığı

| Kontrol | Açıklama | Durum |
|---------|----------|-------|
| PMS Oda → HR Oda | Tüm oda tipleri eşleştirildi | ☐ |
| PMS Oda → Exely Oda | Tüm oda tipleri eşleştirildi | ☐ |
| PMS Rate → HR Rate | Tüm fiyat planları eşleştirildi | ☐ |
| PMS Rate → Exely Rate | Tüm fiyat planları eşleştirildi | ☐ |
| Eksik mapping tespiti | Unmapped room/rate = 0 | ☐ |

### 1.3 Teknik Hazırlık

| Kontrol | Açıklama | Durum |
|---------|----------|-------|
| MongoDB indexleri | Tüm collection'lar optimize | ☐ |
| Rate limiter aktif | HR: 5/min, 250/day | ☐ |
| Error retry policy | Max 3 retry, exponential backoff | ☐ |
| Encryption key | CM_ENCRYPTION_KEY veya JWT_SECRET set | ☐ |
| Monitoring worker | 60s interval, otomatik başlatılıyor | ☐ |
| Alert threshold'lar | 14 metrik tipi tanımlı | ☐ |

---

## Phase 2: Sandbox Validation (T-5 gün)

### 2.1 HotelRunner Sandbox Doğrulaması

```
✅ connection test (GET /infos/channels)
✅ room list (GET /rooms)
✅ rate plan list (GET /rooms → rate_plans)
✅ mapping doğruluk kontrolü
✅ reservation pull (GET /reservations?undelivered=true)
✅ webhook ingest (POST reservation delivered)
✅ ARI push (PUT /rooms/~)
✅ duplicate prevention (aynı payload hash)
✅ cancellation (GET /reservations?modified=true)
```

### 2.2 Exely SOAP Doğrulaması

```
✅ WSSE auth (Username + Nonce + Timestamp)
✅ OTA_ReadRQ (reservation pull)
✅ OTA_HotelAvailRQ (room + rate discovery)
✅ OTA_HotelAvailNotifRQ (ARI push)
✅ OTA_HotelRateAmountNotifRQ (rate update)
✅ reservation update (status change detection)
✅ duplicate prevention (payload hash)
```

### 2.3 Data Integrity Kontrolleri

| Test | Beklenen Sonuç | Durum |
|------|----------------|-------|
| Aynı reservasyon 2x pull | Duplicate olarak tespit | ☐ |
| Modified reservation | Lineage version artışı | ☐ |
| Cancelled reservation | Status = cancelled | ☐ |
| ARI push → drift check | Drift = 0 | ☐ |
| Reconciliation run | Open cases = expected | ☐ |

---

## Phase 3: Stress Testing (T-3 gün)

### 3.1 24-Hour Soak Test

**Amaç:** Sistemin 24 saat kesintisiz çalıştığını doğrulamak.

```
Başlangıç: T-3, 10:00
Bitiş:     T-3+1, 10:00

İzleme:
- Worker uptime (hotelrunner_pull, exely_pull, ingest_processor, replay)
- Memory kullanımı (MongoDB + backend)
- Error rate (<1% hedef)
- Queue depth (max 100 pending event)
- Alert count (0 critical hedef)

Başarı Kriteri:
✅ Worker'lar takılmadı
✅ No critical alerts
✅ Memory leak yok
✅ Reservation ingest düzenli çalışıyor
✅ ARI push success rate >99%
```

### 3.2 Reservation Burst Test

**Amaç:** Checkout saatinde oluşan yükü simüle etmek.

```
Senaryo: 50 reservation 5 dakika içinde

Adımlar:
1. Test reservasyonları oluştur (HotelRunner + Exely karışık)
2. Ingest worker'ı tetikle
3. Processing süresini ölç
4. Lineage oluşturma doğruluğunu kontrol et
5. Reconciliation çalıştır

Başarı Kriteri:
✅ Tüm 50 reservation 5 dk içinde process edildi
✅ Duplicate yok
✅ Lineage doğru
✅ No error in logs
✅ Queue depth 0'a döndü
```

### 3.3 ARI Storm Test

**Amaç:** Toplu ARI güncellemesinin sorunsuz işlenmesini doğrulamak.

```
Senaryo: 100 oda × 30 gün = 3000 ARI update

Adımlar:
1. Bulk ARI update oluştur
2. Rate limiter davranışını izle
3. Provider timeout'larını kontrol et
4. Drift check sonrasında parity doğrula

Başarı Kriteri:
✅ Rate limit aşılmadı
✅ Tüm update'ler başarılı
✅ Drift = 0
✅ Provider latency <5s p95
```

---

## Phase 4: Go-Live Day (T-0)

### 4.1 Go-Live Checklist

| Sıra | Adım | Sorumlu | Durum |
|------|------|---------|-------|
| 1 | Production credentials'ı kaydet | Ops | ☐ |
| 2 | Connection test çalıştır | Ops | ☐ |
| 3 | Full validation çalıştır | Ops | ☐ |
| 4 | Room/rate mapping doğrula | Ops | ☐ |
| 5 | İlk reservation pull tetikle | Ops | ☐ |
| 6 | İlk ARI push tetikle | Ops | ☐ |
| 7 | Monitoring dashboard kontrol | Ops | ☐ |
| 8 | Slack alert webhook aktifle | Ops | ☐ |
| 9 | Reconciliation ilk çalıştırma | Ops | ☐ |
| 10 | Worker otomatik moda geçir | Dev | ☐ |

### 4.2 İlk 4 Saat İzleme

```
T+0h: Connection status kontrol
T+1h: İlk reservation pull sonucu kontrol
T+2h: ARI push başarı oranı kontrol
T+3h: İlk reconciliation sonucu kontrol
T+4h: İlk durum raporu hazırla
```

### 4.3 Geri Dönüş Planı (Rollback)

```
Koşul: 3+ critical alert VEYA provider bağlantı kaybı >30dk

Adımlar:
1. Worker'ları durdur (POST /ingest/workers/stop)
2. ARI push'u kapat (connection status → paused)
3. Provider'a bildir
4. Root cause analizi yap
5. Fix → test → yeniden aktifle
```

---

## Phase 5: Post-Go-Live (T+1 → T+7)

### 5.1 Günlük Kontrol Listesi

| Kontrol | Sıklık | Açıklama |
|---------|--------|----------|
| Provider health | Günlük | Connection status = healthy |
| Ingest metrics | Günlük | events/hour normal aralıkta |
| ARI push rate | Günlük | >99% success rate |
| Recon cases | Günlük | Open critical cases = 0 |
| Worker status | Günlük | No stalled workers |
| Alert inbox | Günlük | Tüm critical/high resolved |

### 5.2 Haftalık Rapor Şablonu

```
Hafta: [Tarih Aralığı]
Provider Uptime: HR: __% | Exely: __%
Reservation Import: ___ toplam, __% başarılı
ARI Push: ___ toplam, __% başarılı
Open Recon Cases: ___ (critical: __, high: __)
Resolved Cases: ___
Worker Uptime: ___%
Critical Alerts: ___ (resolved: ___)
```

---

## Phase 6: Ölçeklenme Planı (T+30)

### 6.1 İkinci Otel Ekleme

```
1. Yeni tenant + property_id oluştur
2. Provider credentials kaydet
3. Room/rate mapping yap
4. Sandbox validation çalıştır
5. Go-live checklist uygula
```

### 6.2 Yeni Provider Ekleme

```
1. Provider adapter yaz (REST veya SOAP client)
2. Normalizer ekle (ingest pipeline)
3. Snapshot collector ekle (reconciliation)
4. ARI adapter ekle (push engine)
5. Monitoring domain'e ekle
6. Full validation suite oluştur
```

---

## Kritik Metrikler ve Eşik Değerler

| Metrik | Warning | Critical |
|--------|---------|----------|
| Provider latency p95 | >3000ms | >10000ms |
| Ingest error rate | >5% | >20% |
| ARI push failure rate | >2% | >10% |
| Queue depth | >50 | >200 |
| Open recon cases (critical) | >5 | >20 |
| Worker stall duration | >5min | >15min |
| Consecutive auth failures | >3 | >10 |

---

## İletişim ve Eskalasyon

| Seviye | Koşul | Aksiyon |
|--------|-------|---------|
| L1 - Info | Medium alert | Slack bildirim, sonraki iş günü kontrol |
| L2 - Warning | High alert | Slack + email, 4 saat içinde müdahale |
| L3 - Critical | Critical alert | Slack + email + telefon, anında müdahale |
| L4 - Outage | Provider down >30dk | Rollback planı aktifle, provider'a acil ticket |

---

> **Son Güncelleme:** Mart 2026
> **Doküman Sahibi:** Syroce PMS Operasyon Ekibi
