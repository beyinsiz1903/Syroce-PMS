# Syroce PMS - Kurulum Devralma Notu + UAT Senaryolari

Bu belge, sistemi Docker Compose ile kuracak kisiye (danisman/developer)
iletilmek uzere hazirlanmistir. Iki bolumden olusur:

1. Danismana konsolide cevap (3 uretim sorusu + secret aktarimi)
2. Canliya cikis oncesi 3 maddelik UAT (Kullanici Kabul Testi)

---

## Bolum 1 - Danismana Konsolide Cevap

### Hangi compose dosyasi kullanilacak?

Repoda 3 farkli uretim compose dosyasi var, varsayimlari farkli:

| Dosya | Icindekiler | DB (Mongo/Redis) | Ne zaman |
|---|---|---|---|
| `docker-compose.prod.yml` | nginx + uygulama servisleri | Mongo HARICI + Redis HARICI | Atlas + harici Redis kullanirken |
| `deploy/docker-compose.production.yml` | Mongo + Redis + nginx + Let's Encrypt + backup | Mongo DAHIL + Redis DAHIL | Tek sunucu, self-host DB |
| `infra/docker-compose.full-stack.yml` | uygulama + Prometheus/Grafana/Alertmanager/OTel + backup | Redis DAHIL, **Mongo HARICI** | 300 otel + gozlem; **Mongo icin Atlas veya harici Mongo SART** |

UYARI: `infra/docker-compose.full-stack.yml` MongoDB konteyneri ICERMEZ. Bu
dosyayi secerseniz `MONGO_URL` mutlaka calisan bir Atlas/harici MongoDB'ye
isaret etmelidir; aksi halde backend ve backup servisleri baglanamaz. (Redis
bu dosyada dahildir.) Self-host MongoDB istiyorsaniz
`deploy/docker-compose.production.yml` kullanin.

Ortam degiskeni sablonu: `backend/.env.example` (gruplu, Turkce, gizli deger
icermez). Bunu `backend/.env` olarak kopyalayip doldurun.

### 1) Sifir Kesinti (Zero-Downtime)

- nginx yuk dengeleyici (80/443 + SSL), her serviste 2 kopya (replica) ve
  healthcheck'ler tanimli.
- Guncellemede sifir-kesinti icin compose'a `update_config: order: start-first`
  (once yeni surumu ayaga kaldir, saglikli olunca eskiyi kapat) + hata halinde
  `failure_action: rollback` eklendi. Celery beat tekil oldugu icin bilincli
  olarak `stop-first` (cift zamanlayici olmasin).
- ONEMLI: `replicas` ve `update_config` gibi `deploy:` direktifleri yalnizca
  Docker SWARM altinda calisir. Gercek rolling-update icin sistem Swarm ile
  baslatilmalidir:

  ```bash
  docker swarm init
  docker stack deploy -c infra/docker-compose.full-stack.yml syroce
  # Guncelleme (sifir-kesinti rolling):
  docker service update --image <yeni-imaj> syroce_backend
  ```

  KRITIK UYARI: `docker stack deploy` (Swarm) `build:` bloklarini DERLEMEZ;
  yalnizca hazir `image:` referanslarini calistirir. Bu yuzden Swarm ile
  sifir-kesinti icin once imajlar derlenip bir registry'ye gonderilmeli
  (`docker build -t <registry>/syroce-backend:<tag> .` + `docker push ...`) ve
  compose'taki servisler `image:` referansina cevrilmelidir. Aksi halde
  `stack deploy` belgelendigi gibi calismaz.

  Duz `docker compose up` kullanilirsa `deploy:` blogu (replicas/update_config)
  yok sayilir (tek kopya, guncellemede kisa kesinti). Bu durumda nginx arkasinda
  blue-green onerilir.

### 2) Veri Yedekleme (Backup)

Iki yol desteklenir; birini secin:

- **(a) MongoDB Atlas yonetilen yedek (EN KOLAY):** Atlas kullaniyorsaniz yedek
  zaten bulutta/offsite tutulur. Dogrulama: `backend/scripts/verify_atlas_backup.py`,
  belge: `docs/ATLAS_BACKUP_AND_RESTORE.md`. Bu durumda asagidaki S3 servisine
  gerek yoktur.
- **(b) Offsite S3 yedek konteyneri (self-host Mongo):** `infra/backup/` altinda
  ayri bir yedek servisi eklendi. Her gece `BACKUP_TIME` (varsayilan 03:00)
  saatinde `mongodump --archive --gzip` alip S3'e yukler, yerel kopyayi siler.
  Gerekli env: `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
  `AWS_REGION` (S3 uyumlu alternatif depo icin `AWS_S3_EXTRA_ARGS=--endpoint-url ...`).
  Eski yedeklerin silinmesi icin S3 tarafinda **lifecycle kurali** tanimlayin
  (script bilincli olarak S3'ten obje SILMEZ).

  Full-stack compose secildiyse backup, backend ile AYNI `MONGO_URL`'yi kullanir
  (yani Atlas/harici Mongo). Self-host Mongo icin `deploy/...production.yml`
  backup'i `mongo` konteynerine baglanir.

  Yedek dogrulama (smoke-test, kurulumdan sonra bir kez calistirin):

  ```bash
  # Konteyner icinden:
  mongodump --version                      # arac mevcut mu
  mongosh "$MONGO_URL" --eval 'db.runCommand({ping:1})'   # Mongo erisilebilir mi
  aws s3 ls "$S3_BUCKET/"                   # S3 kimlik/erisim dogru mu
  # Ilk yedegi elle tetiklemek icin: BACKUP_RUN_ON_START=true ile baslatin.
  ```

`S3_BUCKET` bos birakilirsa yedek konteyneri fail-closed davranir (baslamaz),
boylece Atlas kullananlar icin sorun cikarmaz.

### 3) Monitoring (Gozlem)

`infra/docker-compose.full-stack.yml` icinde tam gozlem yigini hazir:

- Prometheus (`:9090`) - metrik toplama + alert kurallari (`infra/prometheus/alerts.yml`)
- Grafana (`:3001`) - 3 hazir pano: isletme / altyapi / operasyon.
  GUVENLIK: Grafana admin parolasi icin `GRAFANA_ADMIN_PASSWORD` mutlaka
  ayarlanmalidir. Ayarlanmazsa compose bilinen bir VARSAYILAN parolaya duser;
  Grafana :3001'de aciksa bu ciddi risktir. Canlidan once kendi guclu
  parolanizi `.env`'e girin (ve panele disaridan erisimi guvenlik duvariyla
  kisitlayin).
- Alertmanager (`:9093`) - Slack / PagerDuty / OPS webhook'a alarm yonlendirme
- OpenTelemetry Collector (`:4317/:4318`)

Alarm hedeflerini ayarlamak icin: `SLACK_WEBHOOK_URL`, `PAGERDUTY_WEBHOOK_URL`,
`OPS_WEBHOOK_URL`. Bu yigin yalnizca **full-stack** compose'da gelir; diger
compose dosyalari secilirse monitoring kurulmaz.

### Gizli anahtarlarin (secrets) aktarimi

Gizli degerler (JWT_SECRET, e-posta anahtari, AWS/entegrasyon token'lari vb.)
mesajla/dosyayla acik gonderilmez. Kuran kisi bunlari sunucuda dogrudan
`backend/.env` dosyasina girer veya sifreli bir kanal (orn. Bitwarden Send)
uzerinden alir. `backend/.env.example` yalnizca degisken ISIMLERIDIR, gizli
deger icermez ve repoda durabilir.

Canliya cikmadan ZORUNLU ayarlanacak gizli/parola degiskenleri (eksikse
varsayilana duser veya fail-closed olur): `JWT_SECRET`, S3 yedek kullaniliyorsa
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`S3_BUCKET`, gozlem (full-stack)
kullaniliyorsa `GRAFANA_ADMIN_PASSWORD`. Varsayilan parolalarla canliya
CIKMAYIN.

### Kaynak gereksinimi (uyari)

Sistem agirdir (MongoDB + Redis + Celery + ML). Tek sunucuda en az ~4 GB bos
RAM onerilir; full-stack (gozlem dahil) icin daha fazlasi gerekir.

---

## Bolum 2 - Canliya Cikis Oncesi UAT (3 Senaryo)

Pilot otel verisiyle canliya cikmadan once kuran kisi asagidaki 3 testi
calistirip sonucu raporlamali. Uc senaryo da sistemde desteklenmektedir.

### Senaryo A - Internet kesilince sistem calismaya devam ediyor mu?

- **Amac:** Resepsiyon tarayicisinin internet/ag baglantisi gecici kesildiginde
  islemlerin kaybolmamasi.
- **Adimlar:**
  1. PMS'te bir ekran ac (orn. on buro / housekeeping).
  2. Tarayici gelistirici aracindan (Network: Offline) veya ag kablosunu cekerek
     baglantiyi kes.
  3. Bir islem yap (orn. oda durumu guncelle / not ekle).
  4. Baglantiyi geri ac.
- **Beklenen:** Cevrimdisi yapilan islem kuyruga alinir; baglanti gelince
  otomatik senkronize olur, veri kaybolmaz.

### Senaryo B - Cifte odeme denendiginde sistem reddediyor mu?

- **Amac:** Ayni odemenin iki kez islenmesinin (cift tahsilat) engellenmesi.
- **Adimlar:**
  1. Bir folyoya odeme ekle.
  2. Ayni odemeyi kisa sure icinde tekrar gondermeyi dene (cift tikla / hizli
     tekrar gonder).
- **Beklenen:** Ikinci kayit reddedilir (odeme tekrar-engelleme penceresi +
  kapali-folyo korumasi). Folyo bakiyesi yalnizca bir kez degisir.

### Senaryo C - Gece audit (gunluk kapanis) hatasiz bitiyor mu?

- **Amac:** Gece kapanis surecinin tek seferde, eksiksiz ve hatasiz tamamlanmasi.
- **Adimlar:**
  1. Birkac aktif rezervasyon/folyo olan bir pilot gun hazirla.
  2. Gece audit'i calistir (zamanlanmis veya manuel tetikleme).
- **Beklenen:** Surec hata vermeden tamamlanir; gunluk oda gelirleri/vergiler
  islenir. Es zamanli iki tetikleme olsa bile (eszamanlilik kilidi +
  idempotency) islem yalnizca bir kez uygulanir.

### Onay

Uc senaryo da "Beklenen" sonucu verdiyse pilot canliya cikis icin teknik on
kosul saglanmistir. Sonuclari (ekran goruntusu/loglar ile) bu belgeye ek olarak
raporlayin.
