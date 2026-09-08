# MongoDB Atlas Backup & Restore — Pilot Rehberi

## Kısa cevap

MongoDB Atlas M10+ planı Cloud Backup ve point-in-time restore (PITR)
özelliklerini **destekler**, fakat plan seviyesi bu özelliklerin açık olduğuna
dair kanıt değildir. Atlas konsolunda Cloud Backup ve Continuous Cloud Backup
ayrı ayrı etkinleştirilmeli; son snapshot yaşı Atlas Admin API ile
doğrulanmalıdır.

> Atlas plan'ı kullanıcı tarafından **M10 veya üstü** olarak onaylandı
> (12 Mayıs 2026). Backup/PITR anahtarlarının açık olduğu ayrıca
> doğrulanmadan production readiness sonucu PASS sayılmaz.

## Ne korunuyor?

| Veri                                | Atlas Backup'ta var mı? | Notlar                              |
| ----------------------------------- | ----------------------- | ----------------------------------- |
| Tüm MongoDB veritabanı (production) | Yapılandırmaya bağlı      | Cloud Backup/PITR ve gerçek retention konsolda doğrulanır |
| `bookings`, `tenants`, `users` vb.  | Yapılandırmaya bağlı      | Cluster snapshot'ı bütün veritabanını kapsar |
| Audit log koleksiyonu               | Yapılandırmaya bağlı      | Cluster snapshot kapsamındadır      |
| File uploads (fotoğraflar vb.)      | ❌                       | MongoDB değil — ayrı volume         |
| Redis cache                         | ❌                       | Geçici; restore'a gerek yok         |
| Sentry events                       | ❌                       | Sentry kendi tutar (90 gün ücretsiz plan) |

> **Eksik kapsam:** File uploads. Ayrı bir backup gerekli — pilot için
> DigitalOcean volume snapshot yeterli, sonra S3/R2 sync. Bkz. ileri adımlar.

## Örnek snapshot politikası (Atlas konsolunda doğrulanmalı)

| Sıklık       | Saklama   | Amaç                                |
| ------------ | --------- | ----------------------------------- |
| Continuous   | 7 gün     | Point-in-time restore (saniye hassasiyet) |
| Saatlik      | 7 gün     | Yakın geçmişe hızlı dönüş           |
| Günlük       | 7 gün     | Operasyonel restore                 |
| Haftalık     | 4 hafta   | Aylık denetim noktaları             |
| Aylık        | 12 ay     | Yıllık compliance                   |

Bu çizelge Atlas console'dan **Backup → Policy** sekmesinden değiştirilebilir.
Bu değerler hedef politikadır; gerçek zamanlama ve saklama süreleri Atlas
konsolundaki **Backup Policy** ekranından doğrulanır.

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
   - DigitalOcean Secrets → `MONGO_URL` (veya `MONGO_ATLAS_URI`) güncelle
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
# DigitalOcean Secrets'a ekle (üretimde zorunlu doğrulama için):
#   ATLAS_API_PUBLIC_KEY
#   ATLAS_API_PRIVATE_KEY
#   ATLAS_PROJECT_ID
#   ATLAS_CLUSTER_NAME
#   ATLAS_CLOUD_BACKUP_ENABLED=true
#   ATLAS_PITR_ENABLED=true

python backend/scripts/verify_atlas_backup.py --max-age-hours 26
```

Çıktı:
- `FRESH — newest snapshot 4.2h old (threshold 26h)` → tamam
- `STALE — newest snapshot 30.1h old` → Atlas'ı kontrol et, plan
  aktif mi?
- Production'da API key yoksa exit **2** → doğrulama yapılmadı ve readiness
  fail-closed kalır

Readiness validator URI'den Atlas kullanımını algılar; yalnızca tier
bilgisiyle yeşile dönmez. DigitalOcean'a aşağıdaki non-secret durum
değişkenleri ve yukarıdaki Atlas API kimlik bilgileri birlikte girilmelidir:

```
ATLAS_TIER=M10
ATLAS_CLOUD_BACKUP_ENABLED=true     # Atlas konsolundaki gerçek durum
ATLAS_PITR_ENABLED=true             # Atlas konsolundaki gerçek durum
```

## Readiness check'inde nasıl görünür?

`GET /api/production-golive/readiness` → `checks.backup`:

```json
{
  "status": "atlas_managed",
  "atlas": {
    "atlas_managed": true,
    "tier": "M10",
    "cloud_backup_enabled": true,
    "pitr_enabled": true,
    "has_continuous_backup": true,
    "has_snapshot_only": false,
    "verified_at": "2026-09-09T01:30:00+00:00",
    "verification_fresh": true,
    "verification_source": "atlas_admin_api"
  },
  "local_backup_enabled": false,
  "rpo_target": "continuous (PITR)",
  "rto_target": "minutes (Atlas restore)"
}
```

`status="atlas_managed"` ve `verification_fresh=true` ise score **1.0**.
`atlas_backup_not_declared` veya `atlas_backup_unverified` production'da
**0.0** olur; bayrak ya da tier bilgisinin sahte güven üretmesi engellenir.

## Yerel mongodump fallback (opsiyonel ikinci katman)

Eğer "Atlas dahi gitse elimde lokal yedek olsun" diyorsanız:

```bash
# .env / DigitalOcean Secrets:
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

Atlas doğrulaması başarıyla geçiyorsa bu ikinci katmandır; aksi hâlde yerel
container diski production yedeği yerine geçmez.

## Maliyet

Backup maliyeti bulut sağlayıcısı, bölge, snapshot boyutu, saklama politikası
ve restore/trafik kullanımına göre değişir. Güncel tutar Atlas konsolundaki
cost explorer ve resmi fiyatlandırma ekranından doğrulanmalıdır; bu rehberde
sabit bir fiyat varsayılmaz.

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
