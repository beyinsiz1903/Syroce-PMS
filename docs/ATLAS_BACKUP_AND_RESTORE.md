# MongoDB Atlas Backup & Restore — Pilot Rehberi

## Kısa cevap

**Yedek alma derdiniz YOK.** MongoDB Atlas M10+ planı continuous cloud
backup + point-in-time restore (PITR) hizmetini otomatik sağlıyor. Veri
S3'e şifreli yazılır, retention konfigüre edilebilir, restore tek tıkla.

> Atlas plan'ı kullanıcı tarafından **M10 veya üstü** olarak onaylandı
> (12 Mayıs 2026). Bu doküman bu varsayıma göre yazılmıştır.

## Ne korunuyor?

| Veri                                | Atlas Backup'ta var mı? | Notlar                              |
| ----------------------------------- | ----------------------- | ----------------------------------- |
| Tüm MongoDB veritabanı (production) | ✅ continuous            | Default retention M10: 7 gün PITR + 24 saatlik snapshot 7 gün + günlük 7 gün + haftalık 4 hafta |
| `bookings`, `tenants`, `users` vb.  | ✅                       | Kritik 23 koleksiyon (bkz. backup_manager.py:23-27) |
| Audit log koleksiyonu               | ✅                       | KVKK uyumluluğu için kritik         |
| File uploads (FotograFlar, vs.)     | ❌                       | MongoDB değil — ayrı volume         |
| Redis cache                         | ❌                       | Geçici; restore'a gerek yok         |
| Sentry events                       | ❌                       | Sentry kendi tutar (90 gün ücretsiz plan) |

> **Eksik kapsam:** File uploads. Ayrı bir backup gerekli — pilot için
> Replit volume snapshot yeterli, sonra S3/R2 sync. Bkz. ileri adımlar.

## Atlas otomatik snapshot zamanlaması (M10 default)

| Sıklık       | Saklama   | Amaç                                |
| ------------ | --------- | ----------------------------------- |
| Continuous   | 7 gün     | Point-in-time restore (saniye hassasiyet) |
| Saatlik      | 7 gün     | Yakın geçmişe hızlı dönüş           |
| Günlük       | 7 gün     | Operasyonel restore                 |
| Haftalık     | 4 hafta   | Aylık denetim noktaları             |
| Aylık        | 12 ay     | Yıllık compliance                   |

Bu çizelge Atlas console'dan **Backup → Policy** sekmesinden değiştirilebilir.
Pilot için default önerilir.

## Restore senaryoları (Atlas console)

### Senaryo 1 — "5 dakika önceye dön" (PITR)

**Ne zaman:** Yanlış toplu silme, veri bozulması, kötü sorgu.

1. https://cloud.mongodb.com → projenizi açın
2. Cluster → **Back Up Now** veya cluster yanı **…** menü
3. **Restore** sekmesi → **Continuous Cloud Backup** → **Point in Time**
4. Tarih + saat seçin (UTC) — önerilen: olaydan 1-2 dakika önce
5. **Restore to a new cluster** seçin (production'ı bozmamak için)
6. Yeni cluster adı: `syroce-pms-restore-YYYYMMDD`
7. **Restore** → ~10-15 dakika bekle
8. Yeni cluster'ın connection string'ini al, içeriği doğrula
9. **Connection string cutover** ile app'i yeni cluster'a yönlendir:
   - Replit Secrets → `MONGO_URL` (veya `MONGO_ATLAS_URI`) güncelle
   - `bash deploy/deploy.sh` çalıştır (smoke koşar)
   - Smoke PASS sonrası eski cluster'ı Atlas console → Terminate
   > **Not:** Atlas console'da "swap cluster" tek-tık eylemi YOK —
   > cutover sadece app tarafından yapılır.

### Senaryo 2 — "Dün sabah 09:00'a dön" (Snapshot)

**Ne zaman:** PITR penceresinden eski (>7 gün), günlük snapshot var.

1. Atlas console → Backup → **Snapshots** sekmesi
2. İhtiyaç duyulan snapshot'ı seç
3. **Restore** → yeni cluster'a aynı şekilde

### Senaryo 3 — "Cluster tamamen gitti" (Disaster)

**Ne zaman:** Region outage (Atlas SLA %99.95, çok nadir).

1. Atlas console → **Multi-Region Configuration** (önceden
   yapılandırılmışsa)
2. Failover region'ına otomatik geçer
3. Yapılandırılmamışsa: yeni region'da restore + DNS güncellemesi

## Manuel doğrulama (operasyonel)

Atlas Admin API key'leri ile son snapshot'ın tazeliğini script'le kontrol:

```bash
# Replit Secrets'a ekle (opsiyonel, doğrulama için):
#   ATLAS_API_PUBLIC_KEY
#   ATLAS_API_PRIVATE_KEY
#   ATLAS_PROJECT_ID
#   ATLAS_CLUSTER_NAME

python backend/scripts/verify_atlas_backup.py --max-age-hours 26
```

Çıktı:
- `FRESH — newest snapshot 4.2h old (threshold 26h)` → tamam
- `STALE — newest snapshot 30.1h old` → Atlas'ı kontrol et, plan
  aktif mi?
- `api_keys_unset (no-op, exit 0)` → API key tanımlı değil, doğrulama
  pas geçildi

API key'siz çalışıyorsa readiness validator zaten URI'den Atlas
yapılandırmasını algılıyor (`backend/infra/atlas_backup_check.py`)
ve `ATLAS_TIER` env-var'ından plan'ı okuyor. **Replit Secrets'a şunları
eklemek yeterli:**

```
ATLAS_TIER=M10                      # veya M20, M30 vs.
```

## Readiness check'inde nasıl görünür?

`GET /api/production-golive/readiness` → `checks.backup`:

```json
{
  "status": "atlas_managed",
  "atlas": {
    "atlas_managed": true,
    "tier": "M10",
    "has_continuous_backup": true,
    "has_snapshot_only": false,
    "verified_at": null
  },
  "local_backup_enabled": false,
  "rpo_target": "continuous (PITR)",
  "rto_target": "minutes (Atlas restore)"
}
```

`status="atlas_managed"` ise score **1.0** (tam puan). Pilot
deploy'unda `BACKUP_ENABLED=true` set etmek **gerek değil** — Atlas
zaten yedek alıyor.

## Yerel mongodump fallback (opsiyonel ikinci katman)

Eğer "Atlas dahi gitse elimde lokal yedek olsun" diyorsanız:

```bash
# .env / Replit Secrets:
BACKUP_ENABLED=true
BACKUP_PATH=/var/backups/syroce
BACKUP_RETENTION_DAYS=7

# Celery beat'e backup task ekle (gelecek tur'da yapılacak):
# backend/celery_app.py:54 beat_schedule içine:
#   'backup-daily': {
#       'task': 'celery_tasks.backup_task',
#       'schedule': crontab(hour=2, minute=0),
#   }
```

**Pilot için tavsiye edilmez** — Atlas zaten yedekliyor, ek karmaşa.
Pilot sonrası "defense in depth" ekleme paketi olarak değerlendirin.

## Maliyet

M10 backup dahil. Eğer retention'ı uzatmak isterseniz:

| Ek depolama  | Aylık ek maliyet (yaklaşık) |
| ------------ | --------------------------- |
| +10 GB       | ~$0.25                       |
| +100 GB      | ~$2.50                       |

Pilot 6 ay için ek depolama gerekmez — default policy yeterli.

## İlgili dosyalar

- `backend/infra/atlas_backup_check.py` — URI-based Atlas detection
- `backend/scripts/verify_atlas_backup.py` — Atlas Admin API ile snapshot
  tazeliği doğrulama
- `backend/infra/readiness_validator.py:94` — backup readiness check
- `docs/ROLLBACK.md` — restore senaryoları rollback rehberi içinde
- `docs/procedures/BACKUP_AND_RESTORE.md` — eski (mongodump-odaklı) rehber

## Önemli notlar

- Atlas snapshot'ları **şifreli S3'te** tutulur (Atlas managed).
  Müşteriden ayrı bir KVKK consent ihtiyacı yok (PMS T&C zaten kapsar).
- Restore yapılan yeni cluster'lar saatlik fiyatlandırılır — **doğrulama
  bittikten sonra silmek unutmayın** (Atlas → Cluster → Terminate).
- M10 → M20 yükseltmesi pilot süresince trafik artarsa: Atlas console
  → Cluster → Edit Configuration → Tier. Downtime YOK (rolling resize).
