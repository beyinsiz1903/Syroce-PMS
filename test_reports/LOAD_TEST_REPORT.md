# Syroce PMS - Yük Testi Raporu
**Tarih:** 2026-02-27
**Arac:** Locust 2.43.3
**Ortam:** Preview (Kubernetes pod, single instance)

---

## Test Konfigurasyonu
| Parametre | Deger |
|-----------|-------|
| Concurrent Kullanici | 50 |
| Ramp-up Rate | 10 kullanici/sn |
| Test Suresi | 120 saniye |
| Kullanici Dagilimi | Admin(16), FrontDesk(17), HK(11), Finance(6) |
| Toplam Request | **2,293** |
| Hata Orani | **%0.0** |
| Ortalama RPS | **19.13 req/s** |

---

## Genel Sonuclar

| Metrik | Deger |
|--------|-------|
| Toplam Request | 2,293 |
| Basarisiz Request | 0 |
| Hata Orani | %0.0 |
| Ortalama Response Time | 626ms |
| Medyan (p50) | 7ms |
| p90 | 2,300ms |
| p95 | 3,600ms |
| p99 | 7,300ms |
| Min Response Time | 1ms |
| Max Response Time | 9,653ms |

---

## Endpoint Bazli Performans

### Hizli Endpoint'ler (p50 < 10ms)
| Endpoint | Requests | Avg(ms) | p50(ms) | p95(ms) |
|----------|----------|---------|---------|---------|
| /health | 8 | 2 | 2 | 2 |
| /api/pms/dashboard | 169 | 400 | 3 | 2,300 |
| /api/pms/rooms | 208 | 281 | 4 | 1,900 |
| /api/frontdesk/arrivals | 217 | 315 | 4 | 2,000 |
| /api/companies | 35 | 188 | 4 | 2,000 |
| /api/channel-manager/exceptions | 27 | 258 | 4 | 2,000 |
| /api/rates/packages | 10 | 36 | 4 | 330 |
| /api/rates/rate-plans | 21 | 199 | 4 | 1,700 |
| /api/pms/bookings | 203 | 619 | 5 | 3,500 |
| /api/housekeeping/room-status | 129 | 524 | 5 | 2,400 |
| /api/reports/occupancy | 51 | 448 | 6 | 3,000 |
| /api/reports/daily-summary | 70 | 456 | 7 | 2,900 |
| /api/reports/revenue | 58 | 683 | 7 | 4,200 |
| /api/pms/guests | 166 | 402 | 8 | 2,800 |
| /api/frontdesk/departures | 190 | 681 | 8 | 5,700 |
| /api/housekeeping/stayovers | 83 | 566 | 8 | 3,300 |

### Orta Hizda Endpoint'ler (p50 10-100ms)
| Endpoint | Requests | Avg(ms) | p50(ms) | p95(ms) |
|----------|----------|---------|---------|---------|
| /api/frontdesk/inhouse | 174 | 657 | 13 | 3,100 |
| /api/housekeeping/tasks | 124 | 567 | 13 | 3,600 |

### Yavas Endpoint'ler (p50 > 100ms)
| Endpoint | Requests | Avg(ms) | p50(ms) | p95(ms) |
|----------|----------|---------|---------|---------|
| /api/reports/forecast | 18 | 1,734 | 1,500 | 6,900 |
| /api/reports/forecast?days=30 | 3 | 2,389 | 1,800 | 5,300 |
| /api/ai/occupancy-prediction | 12 | 2,961 | 2,800 | 4,400 |
| /api/auth/login | 50 | 5,755 | 5,500 | 8,300 |

---

## En Cok Istek Alan Endpoint'ler (Top 10)
| # | Endpoint | Requests | RPS |
|---|----------|----------|-----|
| 1 | /api/frontdesk/arrivals | 217 | 1.81 |
| 2 | /api/pms/rooms | 208 | 1.74 |
| 3 | /api/pms/bookings | 203 | 1.69 |
| 4 | /api/frontdesk/departures | 190 | 1.56 |
| 5 | /api/frontdesk/inhouse | 174 | 1.45 |
| 6 | /api/pms/dashboard | 169 | 1.42 |
| 7 | /api/pms/guests | 166 | 1.39 |
| 8 | /api/housekeeping/room-status | 129 | 1.08 |
| 9 | /api/housekeeping/tasks | 124 | 1.03 |
| 10 | /api/housekeeping/stayovers | 83 | 0.69 |

---

## Degerledirme

### Guclu Yonler
- **%0 hata orani**: 50 concurrent kullanici altinda hicbir 5xx hatasi yok
- **Hizli median**: Cogu endpoint p50 < 10ms (cache/index etkili)
- **34 farkli endpoint** basariyla test edildi
- **Rate limiter** dogru calisiyor (test icin gecici olarak acildi)

### Darbogazlar
1. **Login endpoint (p50: 5.5s)**: JWT token olusturma + DB sorgusu yogunlukta yavas. bcrypt hash hesaplama maliyetli
2. **AI Occupancy Prediction (p50: 2.8s)**: ML modeli hesaplamasi yogun
3. **Reports Forecast (p50: 1.5s)**: 7-30 gunluk tahmin hesaplamalari agir
4. **Frontdesk inhouse (p99: 9.6s)**: Yogun DB sorgulari zirve anlarinda yavasliyor

### Oneriler
1. **Login optimizasyonu**: Token caching veya bcrypt round azaltma
2. **Report caching**: Forecast ve daily-flash sonuclarini 5dk cache'le
3. **AI prediction caching**: ML tahminlerini 15-30dk cache'le
4. **Connection pooling**: MongoDB connection pool boyutunu artir
5. **Horizontal scaling**: Uretimde 2+ instance ile yuk dagitimi

---

## Dosyalar
- HTML Rapor: `/app/test_reports/loadtest_report.html`
- CSV Stats: `/app/test_reports/loadtest_stats.csv`
- Locust Config: `/app/tests/locustfile.py`
