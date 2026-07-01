# Pilot İlk 24 Saat İzleme Runbook'u

> **Hedef:** HR canlı CM go-live anından sonraki ilk 24 saat boyunca
> "saat kaçta neye bakmalıyım?" sorusuna kesin cevap. Operatör nöbet
> defteri.
>
> **Bu doc kimi için?** Pilot operasyon nöbetçisi (kod bilmek
> zorunda değil — sadece komut çalıştırıp output okuyacak).
>
> **Önkoşul:** Operatör `docs/REPLIT_OPS_CHEATSHEET.md` §1 health
> matrisini ve §0 acil rollback komutunu zaten biliyor.

---

## 0. Go-Live Anı (T+0)

**T-15 dk** (deploy öncesi son hazırlık):
- [ ] On-call rotation aktif: `pms-pilot-oncall` + `pms-pilot-dba`
- [ ] Slack #pms-incidents kanalı açık, 2 nöbetçi mention'da
- [ ] Sentry dashboard açık (tek tıkla erişilebilir bookmark)
- [ ] Bu doc tarayıcıda açık + `REPLIT_OPS_CHEATSHEET.md` ikinci sekmede
- [ ] `bash deploy/rollback.sh --list` çalıştırıldı, geri dönüş tag'i
      teyit edildi (önceki başarılı deploy)

**T+0** (canlı):
- [ ] Deploy tamamlandı, smoke PASS
- [ ] Müşteriye "canlıdayız" bildirimi (status-page veya manuel)
- [ ] Saat damgası kaydet: `__:__` (acil olay olursa zaman serisi)

---

## 1. T+0 → T+15 dk — Yoğun Bakım

**Frekans:** Her 5 dakikada bir, manuel.

**Kontrol matrisi:**

| # | Komut / Eylem                                          | Geçer eşik              |
| - | ------------------------------------------------------ | ----------------------- |
| 1 | `bash deploy/smoke.sh`                                 | exit 0                  |
| 2 | `curl -fsS https://<prod>/api/production-golive/readiness \| jq .verdict` | `"PASS"` |
| 3 | `python backend/scripts/cm_backlog_alert.py`           | exit 0 (OK)             |
| 4 | Sentry-UI → Issues → Last 15 min                       | Yeni CRITICAL **YOK**   |
| 5 | Sentry-UI → Performance → APDEX                        | ≥0.7                    |
| 6 | İlk müşteri login denemesi (manuel)                    | başarılı                |
| 7 | İlk rezervasyon oluşturma (manuel)                     | başarılı, folio açıldı  |

**Karar matrisi (T+0 → T+15):**
- Herhangi bir kontrol fail → **DURDURMA, 5 dk içinde rollback değerlendir**
- Sentry'de yeni "5xx burst" → **ROLLBACK** (`bash deploy/rollback.sh`)
- Sadece WARNING → izle, T+15 değerlendir

---

## 2. T+15 dk → T+1 saat — Akut Faz

**Frekans:** Her 15 dakikada bir.

**Genişletilmiş kontroller (yukarıdakilere ek olarak):**

| # | Komut / Eylem                                                  | Geçer eşik              |
| - | -------------------------------------------------------------- | ----------------------- |
| 8 | HR booking simülasyonu: HR test reservation → PMS'e düşüyor mu | <2 dk gecikme           |
| 9 | CM circuit breaker drill-down (`/api/channel-manager/unified-rate-manager/circuit-breakers`) | hepsi `CLOSED` |
| 10| Outbox detay: `cm_backlog_alert.py --json \| jq .outbox`        | `pending<10, failed=0`  |
| 11| Folio operations: 1 ödeme + 1 refund denemesi (test odası)    | başarılı                |
| 12| Mobile Web preview erişimi                                     | login + dashboard load  |
| 13| Sentry-UI → Releases → bu deploy'un crash-free rate            | ≥99.5%                  |

**Saat bazlı kayıt** (operatör defterine):
```
T+15: smoke=OK, readiness=PASS, sentry=0 CRITICAL, cm_outbox=pending:0
T+30: smoke=OK, readiness=PASS, sentry=__ CRITICAL, cm_outbox=pending:__
T+45: smoke=OK, readiness=PASS, sentry=__ CRITICAL, cm_outbox=pending:__
T+60: smoke=OK, readiness=PASS, sentry=__ CRITICAL, cm_outbox=pending:__
```

**Karar matrisi (T+15 → T+1h):**
- 2 ardışık kontrolde aynı WARNING → **TRIAGE** (`REPLIT_OPS_CHEATSHEET.md §3`)
- HR booking >2 dk gecikme → CM observability incele, `cm_backlog_alert --json`
- CB OPEN ≥1 → 30 dk bekle (auto-recovery 60s + retry); hala OPEN ise on-call

---

## 3. T+1 saat → T+6 saat — Stabilizasyon

**Frekans:** Her 30 dakikada bir.

**Sadeleştirilmiş kontroller** (artık manuel test yok, telemetri):

| # | Komut / Eylem                                          | Geçer eşik              |
| - | ------------------------------------------------------ | ----------------------- |
| 1 | `python backend/scripts/cm_backlog_alert.py --json`    | exit 0 (OK)             |
| 2 | Sentry-UI → Issues → Last 30 min                       | Yeni CRITICAL=0         |
| 3 | Sentry-UI → Performance → P95 latency                  | <2 sn                   |
| 4 | CM circuit breakers                                    | hepsi CLOSED            |
| 5 | Conflict Queue UI (Channel Manager → Conflicts)        | <5 unresolved           |

**Saatlik özet** (her saat başı Slack #pms-alerts'e yapıştır):
```
T+__h özet:
- Sentry CRITICAL: __ (önceki: __)
- CM outbox pending: __ failed: __
- CB OPEN sayısı: __
- HR last successful sync: __:__
- Aktif kullanıcı: ~__
```

**Karar matrisi (T+1h → T+6h):**
- P95 latency >2 sn ardışık 2 kontrol → index audit (`backend/scripts/index_audit.py`)
- Outbox pending >100 ardışık 30 dk → on-call (DBA değil, dev)
- CRITICAL Sentry alert → §5 eskalasyon

---

## 4. T+6 saat → T+24 saat — Sürekli İzleme

**Frekans:** Her 2 saatte bir.

**Daraltılmış kontroller:**

| # | Komut / Eylem                                          | Geçer eşik              |
| - | ------------------------------------------------------ | ----------------------- |
| 1 | `python backend/scripts/cm_backlog_alert.py`           | exit 0                  |
| 2 | `python backend/scripts/verify_atlas_backup.py --max-age-hours 26` | exit 0 (snapshot taze) |
| 3 | Sentry-UI → Issues → Last 2h                           | yeni CRITICAL=0         |
| 4 | Readiness                                              | verdict=PASS            |

**Gece nöbet kuralı (T+18h ≈ 02:00):**
- PagerDuty alert yoksa → 2 saatte bir kontrol yeterli
- PagerDuty alert varsa → §5 eskalasyon (gecede uyandırma yetkili)

**Sabah brief (T+24h):**
- Önceki 24 saatin Sentry özeti (CRITICAL/ERROR/WARNING sayıları)
- HR sync başarı oranı (% successful pushes)
- Outbox throughput (event/saat)
- En çok hata veren endpoint top-5
- Müşteri şikayeti var mı?

---

## 5. Eşik Tabloları (Quick Lookup)

### Rollback eşikleri (durdurma kararı)

| Belirti                                  | Aksiyon                  |
| ---------------------------------------- | ------------------------ |
| 5xx oranı >50% / 5dk                     | **ROLLBACK derhal**      |
| Login %0 başarı oranı / 2dk              | **ROLLBACK derhal**      |
| Müşteri verisi yazma hatası (folio loss) | **ROLLBACK + DBA on-call** |
| MongoDB connection pool exhausted        | **ROLLBACK + DBA**       |
| PII leak Sentry'de tespit edildi         | **ROLLBACK + scrub fix** |

### Sadece izleme eşikleri (rollback YOK)

| Belirti                                  | Aksiyon                  |
| ---------------------------------------- | ------------------------ |
| Tek bir CB OPEN (HR transient)           | 30 dk bekle              |
| Outbox backlog 50-100                    | İzle, throughput ölç     |
| P95 latency 2-3 sn (geçici spike)        | İzle, 15 dk sonra tekrar |
| Tek bir 500 hatası (izole, non-critical) | Sentry'de incele, fix sonra |

### Müşteriye bilgi verme eşikleri

| Durum                                    | Bildirim kanalı          |
| ---------------------------------------- | ------------------------ |
| ROLLBACK yapıldı                         | Status-page + email      |
| 15 dk+ kesinti                           | Status-page              |
| Tek özellik bozuk (örn. ödeme)           | Status-page (özellik bazlı) |
| Yavaşlık var ama erişim var              | Bildirim YOK (izle)      |

---

## 6. Operasyon Defteri Şablonu

Her kontrol turunda doldurulacak (Slack thread veya not defteri):

```
Tarih: __/__/2026
Saat: __:__
Tur: T+__h __dk

Kontroller:
[ ] smoke / readiness: ____
[ ] cm_backlog: ____
[ ] sentry CRITICAL son __dk: ____
[ ] CB durumu: ____
[ ] backup tazelik: ____ (sadece T+6h+)

Anomali var mı? Açıkla:
__________________

Aksiyon alındı mı? Hangi?:
__________________

Bir sonraki kontrol: __:__
```

---

## 7. Tatbikat Modu (Pre-Pilot)

Pilot canlı olmadan ÖNCE bu runbook'u **kuru tatbikat** yap (operatör eğitimi):

1. Sandbox env'de deploy → smoke koş → output'u oku
2. `cm_backlog_alert.py` manuel çalıştır → JSON parse et
3. Sentry-UI tarayıcıda aç, CRITICAL filter uygula
4. `verify_atlas_backup.py` çalıştır (Atlas key gerekli)
5. `bash deploy/rollback.sh --dry-run` koş → çıktıyı oku
6. Bir "fake incident" senaryosu canlandır (örn. CB OPEN simülasyonu)
   ve §5 karar matrisinden hangi aksiyonun uygulanacağını söz ile söyle

**Tatbikat geçer kriteri:** Operatör 4 senaryoda 5 dk içinde doğru
karara varabiliyor.

---

## 8. T+24h Sonrası

24 saat tamamlandığında:
- [ ] Sabah brief Slack #pms-incidents'a yapıştır
- [ ] Operasyon defteri arşive (`docs/incidents/pilot-T+24h-{tarih}.md`)
- [ ] Bu doc'tan T+24h sonrası izleme moduna geç:
  → `docs/CM_OBSERVABILITY.md` cron + Sentry alert otomasyonuna güven
  → Manuel kontrol günde 1 kez (sabah brief'i)
- [ ] Pilot retrospektif toplantısı (T+72h)

---

## 9. İlgili Dokümanlar

| Konu                          | Doküman                                |
| ----------------------------- | -------------------------------------- |
| Operatör tek-sayfa            | `docs/REPLIT_OPS_CHEATSHEET.md`        |
| Rollback senaryoları          | `docs/ROLLBACK.md`                     |
| CM observability eşikleri     | `docs/CM_OBSERVABILITY.md`             |
| Sentry alert policy           | `docs/SENTRY_ALERT_POLICY.md`          |
| Atlas backup + restore        | `docs/ATLAS_BACKUP_AND_RESTORE.md`     |
| Pilot Go/No-Go                | `docs/PILOT_GO_NO_GO.md`               |
| Disaster recovery (full)      | `docs/DISASTER_RECOVERY.md`            |

---

## 10. Sürüm

- **v1.0** (12 Mayıs 2026) — Pilot HR canlı CM ilk yayın
- **Maintainer**: Pilot operasyon ekibi
- **Geri besleme**: T+24h retrospektif sonrası güncellenir
