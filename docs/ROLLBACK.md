# Rollback Rehberi

Kod bilmeyen pilot lead için tek-sayfa, kopyala-yapıştır rollback rehberi.
Yarın canlıda bir şey ters gidince **bu sayfayı aç, ilgili senaryonun
komutunu çalıştır.**

> **Önemli:** Veri kaybı şüphesi varsa Önce Atlas restore (Senaryo C),
> sonra deploy rollback (Senaryo A). Atlas continuous backup yapılandırılı
> (M10+) — kaybedilebilecek azami süre dakikalar içinde.

---

## Senaryo A — Önceki Sürüme Dön (kod hatası, %95 vakanın çözümü)

Yeni deploy sonrası site açılmıyor / login çalışmıyor / 5xx oranı yükseldi.

```bash
bash deploy/rollback.sh
```

Bu komut **git-based rebuild** yapar (compose `build:` direktifi
kullanıyor, image registry tag'leri yok):
1. `deploy/.last_good_tag` dosyasından önceki başarılı **commit SHA**'yı okur
2. Working tree kirliyse `git stash push` ile mevcut değişiklikleri saklar
3. `git checkout <SHA>` ile o commit'e döner
4. `docker compose build --no-cache → up -d` ile rebuild + restart
5. Otomatik olarak `deploy/smoke.sh` koşar (6 adım)
6. Smoke PASS ise `last_good_tag`'i günceller + `.rollback_from` siler
7. Smoke FAIL ise `.rollback_from` sidecar'ı bırakır (`--resume` ile sürdürülür)

**Süre:** ~5-10 dk (build cache'siz, plain pull değil — bu pilot
mimarisi için önerilen yaklaşım).

**Belirli bir commit'e dönmek için:**
```bash
bash deploy/rollback.sh abc1234
```

**Son commit'leri görmek için:**
```bash
bash deploy/rollback.sh --list
```

**Yarı-kalmış rollback'i sürdürmek için (önceki çalıştırma build/up FAIL ettiyse):**
```bash
bash deploy/rollback.sh --resume
```

**Sadece ne yapacağını görmek için (komut çalışmaz):**
```bash
bash deploy/rollback.sh --dry-run
```

**Stash uyarısı:** Eğer working tree kirliyse stash'lenir; rollback
sonrası geri uygulanmaz. Manuel: `git stash list` → `git stash pop`.

**Çıkış kodları:**
- `0` → Rollback başarılı + smoke PASS
- `1` → Build / smoke FAIL (manuel inceleyin, `--resume` deneyin)
- `2` → Kullanım hatası (git yok, docker yok, commit yok)

---

## Senaryo B — Auto-Rollback Tetiklendi (sistem kendi kararını verdi)

`backend/ops/auto_rollback_engine.py` aşağıdaki eşiklerden birini görürse
otomatik olarak rollback başlatır:

| Tetikleyici             | Eşik                       | Pencere | Aksiyon         |
| ----------------------- | -------------------------- | ------- | --------------- |
| 5xx hata oranı          | %5                         | 5 dk    | auto_rollback   |
| Health endpoint down    | 1+ başarısız               | 2 dk    | auto_rollback   |
| MongoDB ping başarısız  | 1+                         | 1 dk    | auto_rollback   |
| Outbox backlog          | 500+ event                 | 10 dk   | alert_and_pause |
| Import failure rate     | 20+                        | —       | alert_and_pause |

**Tetiklenirse ne yapılır:**
1. Sentry'den uyarı maili gelir (Kapsam #4 yapılınca routing aktif)
2. Engine `smoke_test_runner.run_all()` koşar
3. Smoke FAIL ise rollback otomatik tamamlanır
4. Smoke PASS ise rollback iptal — yanlış alarm sayılır

**Manuel doğrulama:**
```bash
curl -s "$BASE_URL/health/ready" | jq
bash deploy/smoke.sh
```

---

## Senaryo C — Atlas Veri Restore (veri bozulması, yanlış silme)

Yanlış bir toplu silme, veri bozulması, ya da "5 dakika önceki haline dön"
ihtiyacı. **Atlas continuous backup ile point-in-time restore yapılır —
kod tarafında hiçbir komut yok.**

### Adımlar (Atlas dashboard üzerinden):

1. https://cloud.mongodb.com/ → giriş yap
2. Sol menüde projenizi seç
3. Cluster adının yanında **"…"** (üç nokta) → **Back Up Now** veya
   **Restore Data**
4. **"Continuous Cloud Backup"** sekmesi → **"Point in Time"**
5. Tarih + saat seçin (UTC), önerilen: olay öncesi son 5 dakika
6. **"Restore to a new cluster"** — ÖNCE yeni cluster'a restore edin
   (production'ı bozmamak için). Adı: `syroce-pms-restore-YYYYMMDD`
7. Yeni cluster ayağa kalkana kadar bekleyin (~10-15 dakika)
8. Restore'u doğrulayın: yeni cluster'ın connection string'i ile
   `mongo "<uri>"` → bozulmadan önceki veri orada olmalı
9. Doğrulandıysa: app'i yeni cluster'a **connection string cutover**
   ile yönlendir:
   - Replit Secrets → `MONGO_URL` (veya `MONGO_ATLAS_URI`) değerini
     yeni cluster'ın connection string'i ile güncelle
   - `bash deploy/deploy.sh` ile yeniden başlat (smoke koşar)
   - Smoke PASS olduktan sonra eski cluster'ı Atlas console'dan
     **Terminate** et (saatlik fiyatlandırma — geciktirme!)

> Atlas console'da tek tıkla "swap cluster" eylemi YOK. Cutover
> yapmanın tek yolu app tarafında connection string güncellemesidir.

### Önemli kararlar:

| Durum                                         | Karar                                       |
| --------------------------------------------- | ------------------------------------------- |
| Sadece 1-2 booking yanlış silinmiş            | Restore → ihtiyacı manuel kopyala → swap yapma |
| Tüm bookings koleksiyonu bozuk                | Full restore + swap                         |
| Hangi anda bozulduğu belirsiz                 | Atlas activity log'una bak, en son healthy state'i seç |

### Atlas plan'ınızda PITR yoksa (M2/M5):

Daily snapshot'tan en yakın olana restore. PITR yok, en kötü 24 saat
veri kaybı.

### Atlas plan'ınız M0 ise:

**Backup yok.** Mevcut M0 ise pilota çıkmadan önce mutlaka M10'a
yükseltin (~$57/ay).

---

## Senaryo D — Tam Felaket (Atlas + uygulama hep birden gitti)

Bu senaryo gerçekleşmemeli (Atlas SLA %99.95) ama yine de:

1. Atlas Status: https://status.mongodb.com — outage var mı?
2. Replit Status: https://status.replit.com — platform sorunu mu?
3. Eğer Atlas region outage'ı: Atlas dashboard → cluster ayarları →
   region failover (eğer multi-region yapılandırıldıysa)
4. Eğer Replit outage'ı: bekleme dışında seçenek yok; müşteri iletişimi
5. Hiçbiri değilse: `docs/procedures/DISASTER_RECOVERY.md` (71 satır)

---

## Doğrulama komutları (rollback sonrası elle)

```bash
# Sağlık
curl -s "$BASE_URL/health/ready" | jq '.status'

# Login + bookings okur mu?
TOKEN=$(curl -sX POST "$BASE_URL/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@hotel.com","password":"..."}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" \
    "$BASE_URL/api/pms/bookings?limit=1" | jq

# Channel manager + outbox sağlığı
curl -s -H "Authorization: Bearer $TOKEN" \
    "$BASE_URL/api/channel-manager/monitoring/overview" | jq

# Circuit breaker durumu
curl -s -H "Authorization: Bearer $TOKEN" \
    "$BASE_URL/api/channel-manager/unified-rate-manager/circuit-breakers" \
    | jq '.breakers[] | {key, state}'
```

---

## Sık karşılaşılan hatalar

| Hata                                            | Çözüm                                                              |
| ----------------------------------------------- | ------------------------------------------------------------------ |
| `last_good_tag` yok                             | `bash deploy/rollback.sh --list` → tag'i el ile geç                |
| Smoke FAIL ama site açılıyor                    | Manuel doğrulama yap; `last_good_tag` el ile güncelle              |
| Atlas restore 10+ dk sürüyor                    | Normal — bekleyin, müşteri iletişimi başlatın                      |
| Rollback sonrası yine eski hata                 | Sorun veride; Senaryo C (Atlas restore) gerekli                    |
| Docker pull "image not found"                   | Tag silinmiş olabilir; `docker images` ile kontrol, `--list` dene  |

---

## İlgili dosyalar

- `deploy/rollback.sh` — bu rehberin kaynak betiği
- `deploy/.last_good_tag` — son başarılı deploy'un imaj tag'i
- `deploy/smoke.sh` — 6 adımlı doğrulama (rollback sonrası otomatik koşar)
- `backend/ops/auto_rollback_engine.py` — metric-based otomatik rollback
- `docs/ATLAS_BACKUP_AND_RESTORE.md` — veri restore detayları
- `docs/procedures/INCIDENT_PLAYBOOK.md` — geniş kapsamlı olay yönetimi
