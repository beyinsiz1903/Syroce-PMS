# Syroce PMS - Production Deployment Rehberi

## Sunucu Bilgileri

| Bilgi | Deger |
|-------|-------|
| IP | 31.186.24.133 |
| Backend Domain | api.syroce.com |
| Frontend Domain | pms.syroce.com (mevcut, degismiyor) |
| OS | Ubuntu 22.04 x64 |

---

## 1. DNS Kaydi (Turkticaret)

Turkticaret DNS panelinde su kaydi ekleyin (zaten ekli ise kontrol edin):

```
Tip:    A
Ad:     api
Deger:  31.186.24.133
TTL:    3600
```

Dogrulama:
```bash
dig api.syroce.com +short
```
Cikti `31.186.24.133` olmali.

---

## 2. Dosyalari Sunucuya Kopyalama

Yerel makinenizden sunucuya su dosyalari kopyalayin:

```bash
scp -r deploy/ root@31.186.24.133:/opt/syroce-pms/
```

Sunucudaki dizin yapisi su sekilde olmali:

```
/opt/syroce-pms/
  docker-compose.production.yml
  .env.production.example
  .env                          (siz olusturacaksiniz)
  deploy.sh
  ssl-setup.sh
  nginx/
    api.conf
  backend/                      (proje backend/ klasoru)
    Dockerfile
    requirements.txt
    server.py
    ...
  worker/                       (proje worker/ klasoru)
    Dockerfile
  backups/
```

Tam proje dosyalarini kopyalama:

```bash
rsync -avz --exclude='node_modules' --exclude='.git' --exclude='__pycache__' \
    --exclude='test_reports' --exclude='frontend/build' --exclude='.emergent' \
    ./ root@31.186.24.133:/opt/syroce-pms/
```

Ardindan deploy dosyalarini ana dizine tasiyin:

```bash
ssh root@31.186.24.133
cd /opt/syroce-pms
cp deploy/docker-compose.production.yml .
cp deploy/.env.production.example .
cp deploy/deploy.sh .
cp deploy/ssl-setup.sh .
cp -r deploy/nginx .
chmod +x deploy.sh ssl-setup.sh
```

---

## 3. .env Dosyasini Olusturma

```bash
cd /opt/syroce-pms
cp .env.production.example .env
nano .env
```

Asagidaki degerleri doldurun:

| Degisken | Aciklama | Ornek |
|----------|----------|-------|
| `DB_NAME` | MongoDB veritabani adi | `syroce_production` |
| `JWT_SECRET` | JWT imzalama anahtari | `openssl rand -base64 48` komutu ile olusturun |
| `CORS_ORIGINS` | Frontend domainleri | `https://pms.syroce.com` |
| `CM_CREDENTIAL_KEY` | Channel Manager sifreleme anahtari | Mevcut degeriniz |
| `CM_MASTER_KEY_CURRENT` | KMS master key | Mevcut degeriniz |

JWT_SECRET olusturmak icin:
```bash
openssl rand -base64 48
```

---

## 4. SSL Sertifikasi Alma

```bash
cd /opt/syroce-pms
sudo ./ssl-setup.sh email@syroce.com
```

Bu komut:
- Certbot kurar
- api.syroce.com icin Let's Encrypt sertifikasi alir
- Otomatik yenileme icin cron job ekler

---

## 5. Deploy

```bash
cd /opt/syroce-pms
sudo ./deploy.sh
```

Bu komut:
1. Docker ve Docker Compose kurar (yoksa)
2. .env dosyasini kontrol eder
3. SSL sertifikasini kontrol eder
4. Docker imajlarini build eder
5. Tum servisleri baslatir
6. Dogrulama testlerini calistirir

---

## 6. Dogrulama

Deploy basarili olduktan sonra:

```bash
# Health check
curl https://api.syroce.com/api/health/liveness

# Detayli health
curl https://api.syroce.com/api/health/

# HotelRunner callback (GET)
curl https://api.syroce.com/api/integrations/hotelrunner/callback

# HotelRunner webhook (POST)
curl -X POST https://api.syroce.com/api/integrations/hotelrunner/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

---

## 7. Islem Sonrasi

### Loglari Izleme
```bash
cd /opt/syroce-pms

# Tum loglar
docker compose -f docker-compose.production.yml logs -f

# Sadece backend
docker compose -f docker-compose.production.yml logs -f backend

# Sadece nginx
docker compose -f docker-compose.production.yml logs -f nginx
```

### Servisleri Yonetme
```bash
# Durum kontrolu
docker compose -f docker-compose.production.yml ps

# Yeniden baslatma
docker compose -f docker-compose.production.yml restart backend

# Durdurma
docker compose -f docker-compose.production.yml down

# Guncelleme (yeni kod deploy)
git pull
docker compose -f docker-compose.production.yml build backend worker
docker compose -f docker-compose.production.yml up -d backend worker
```

### MongoDB Backup
```bash
# Manuel backup
docker compose -f docker-compose.production.yml exec mongo \
  mongodump --db=syroce_production --out=/backups/$(date +%Y%m%d)

# Backup listele
ls -la /opt/syroce-pms/backups/
```

---

## 8. Frontend Baglantisi

pms.syroce.com uzerindeki frontend'in backend URL'ini guncelleyin:

```
VITE_BACKEND_URL=https://api.syroce.com
```

veya frontend kodunda REACT_APP_BACKEND_URL kullaniliyorsa:
```
REACT_APP_BACKEND_URL=https://api.syroce.com
```

---

## Guvenlik Kontrol Listesi

- [x] MongoDB sadece Docker internal network'te (dis erisim yok)
- [x] Redis sadece Docker internal network'te
- [x] Backend sadece Nginx uzerinden erisiliyor (port disari acik degil)
- [x] HTTPS zorunlu (HTTP -> HTTPS redirect)
- [x] Rate limiting aktif (auth: 10/dk, API: 60/sn, webhook: 30/sn)
- [x] Security header'lar (HSTS, X-Frame-Options, CSP)
- [x] .env, .git, .docker path'leri engellenmis
- [x] Log masking aktif (PII sanitization)
- [x] SSL otomatik yenileme (cron)
- [x] Container restart policy (unless-stopped)
- [x] Resource limits tanimli

---

## Onemli URL'ler

| Endpoint | URL |
|----------|-----|
| API Base | `https://api.syroce.com` |
| Health Check | `https://api.syroce.com/api/health/liveness` |
| HotelRunner Callback | `https://api.syroce.com/api/integrations/hotelrunner/callback` |
| HotelRunner Webhook | `https://api.syroce.com/api/integrations/hotelrunner/webhook` |
| Frontend | `https://pms.syroce.com` |

---

## Sorun Giderme

### Backend baslamiyor
```bash
docker compose -f docker-compose.production.yml logs backend
```

### MongoDB baglanti hatasi
```bash
docker compose -f docker-compose.production.yml exec mongo mongosh --eval "db.adminCommand('ping')"
```

### SSL sertifika yenileme
```bash
sudo certbot renew --dry-run
```

### Disk doluyorsa
```bash
docker system prune -a --volumes
```
