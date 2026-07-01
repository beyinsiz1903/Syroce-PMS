# Syroce PMS — Go-Live Runbook
## Operasyonel Deploy & Cutover Prosedürü

**Versiyon**: 1.0
**Son Güncelleme**: Subat 2026
**Sahip**: Platform Muhendisligi

---

## 1. On Kosullar (Go/No-Go Gate)

Asagidaki tum maddelerin **YESIL** olmasi gerekir. Herhangi biri KIRMIZI ise deploy DURDURULUR.

| # | Kontrol | Nasil Dogrulanir | Durum |
|---|---------|-----------------|-------|
| 1 | CI pipeline tamamen yesil (lint + test + security + build) | GitHub Actions son commit'te basarili | [ ] |
| 2 | Staging smoke test gecti | `deploy-staging` job basarili | [ ] |
| 3 | Load test son 24 saatte basarili | `pytest load_tests/ -v` 18/18 pass | [ ] |
| 4 | Veritabani yedegi alindi | `mongodump --gzip` tamamlandi | [ ] |
| 5 | Rollback proseduru test edildi | `kubectl rollout undo` staging'de dogrulandi | [ ] |
| 6 | On-call nobet cizelgesi hazir | En az 2 muhendis erisebilir durumda | [ ] |
| 7 | SLO/SLA dashboard'u canli | Grafana panelleri veri gosteriyor | [ ] |
| 8 | Musteri iletisim plani hazir | Bakim penceresi bildirimi gonderildi | [ ] |

---

## 2. Deploy Oncesi Hazirlik (T-2 saat)

### 2.1 Veritabani Yedegi

```bash
# Production DB yedegi
BACKUP_TS=$(date +%Y%m%d_%H%M%S)
mongodump --uri="$MONGO_BACKUP_URI" \
  --archive=/data/backups/pre-deploy-${BACKUP_TS}.gz \
  --gzip

# Yedegi dogrula
mongorestore --uri="$MONGO_BACKUP_URI" \
  --archive=/data/backups/pre-deploy-${BACKUP_TS}.gz \
  --gzip --dryRun
```

### 2.2 Mevcut Revizyonu Kaydet

```bash
export KUBECONFIG=/path/to/kubeconfig

# Mevcut image tag'lerini kaydet
kubectl -n syroce get deployment syroce-backend \
  -o jsonpath='{.spec.template.spec.containers[0].image}' > /tmp/rollback-backend.txt
kubectl -n syroce get deployment syroce-frontend \
  -o jsonpath='{.spec.template.spec.containers[0].image}' > /tmp/rollback-frontend.txt
kubectl -n syroce get deployment syroce-worker \
  -o jsonpath='{.spec.template.spec.containers[0].image}' > /tmp/rollback-worker.txt

echo "Rollback hedefleri kaydedildi"
```

### 2.3 Bakim Modu (Opsiyonel)

Buyuk schema degisiklikleri varsa:

```bash
# Bakim banner'i ac
kubectl -n syroce set env deployment/syroce-backend MAINTENANCE_MODE=true
# Bekle: Tum mevcut istekler tamamlansin
sleep 30
```

---

## 3. Deploy Sureci

### 3.1 Otomatik Deploy (Tercih Edilen)

```bash
# GitHub Actions uzerinden
# Option A: main branch'e push (otomatik)
git push origin main

# Option B: Manuel tetikleme
gh workflow run deploy.yml -f environment=production
```

### 3.2 Manuel Deploy (Acil Durum)

```bash
SHA="<commit-sha>"
REGISTRY="ghcr.io/<org>/syroce"

# Image'lari guncelle
kubectl -n syroce set image deployment/syroce-backend \
  backend=${REGISTRY}-backend:${SHA}
kubectl -n syroce set image deployment/syroce-frontend \
  frontend=${REGISTRY}-frontend:${SHA}
kubectl -n syroce set image deployment/syroce-worker \
  worker=${REGISTRY}-worker:${SHA}

# Rollout'u takip et
kubectl -n syroce rollout status deployment/syroce-backend --timeout=600s
kubectl -n syroce rollout status deployment/syroce-frontend --timeout=300s
kubectl -n syroce rollout status deployment/syroce-worker --timeout=300s
```

---

## 4. Deploy Sonrasi Dogrulama (T+5 dakika)

### 4.1 Smoke Test

```bash
PROD_URL="https://pms.syroce.com"

# 1. Health endpoint
curl -sf "${PROD_URL}/api/health/" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok', f'FAIL: {d}'; print('Health: OK')"

# 2. Auth flow
TOKEN=$(curl -sf -X POST "${PROD_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke-test@syroce.com","password":"<smoke-pw>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "Auth: OK (token received)"

# 3. Core PMS endpoint
curl -sf "${PROD_URL}/api/pms/dashboard" \
  -H "Authorization: Bearer ${TOKEN}" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(f'Dashboard: OK ({len(d)} keys)')"

# 4. Frontend
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${PROD_URL}/")
[ "$HTTP_CODE" = "200" ] && echo "Frontend: OK" || echo "Frontend: FAIL ($HTTP_CODE)"
```

### 4.2 Metrik Kontrolu

| Metrik | Beklenen | Komut |
|--------|----------|-------|
| Pod'lar hazir | backend=2/2, frontend=2/2 | `kubectl -n syroce get pods` |
| HTTP 5xx orani | 0 | Grafana dashboard |
| Ortalama latency | < 200ms | Grafana dashboard |
| MongoDB baglantilari | < 80% pool | `db.serverStatus().connections` |

---

## 5. Rollback Proseduru

### 5.1 Otomatik Rollback (CI/CD)

CI/CD pipeline'da smoke test basarisiz olursa otomatik rollback tetiklenir.

### 5.2 Manuel Rollback

```bash
# Secenk A: Kubernetes rollout undo (son basarili revizyona)
kubectl -n syroce rollout undo deployment/syroce-backend
kubectl -n syroce rollout undo deployment/syroce-frontend
kubectl -n syroce rollout undo deployment/syroce-worker

# Rollback'in tamamlanmasini bekle
kubectl -n syroce rollout status deployment/syroce-backend --timeout=300s
kubectl -n syroce rollout status deployment/syroce-frontend --timeout=300s

# Secenk B: Belirli bir image'a geri don
kubectl -n syroce set image deployment/syroce-backend \
  backend=$(cat /tmp/rollback-backend.txt)
kubectl -n syroce set image deployment/syroce-frontend \
  frontend=$(cat /tmp/rollback-frontend.txt)
```

### 5.3 Veritabani Rollback (Sadece Kritik Durum)

```bash
# UYARI: Bu islem veri kaybi yaratir!
# Sadece CTO onayi ile yapilir.
mongorestore --uri="$MONGO_BACKUP_URI" \
  --archive=/data/backups/pre-deploy-${BACKUP_TS}.gz \
  --gzip --drop
```

---

## 6. Rollback Karar Matrisi

| Durum | Aksiyon | Karar Verici |
|-------|---------|-------------|
| Smoke test basarisiz (health down) | Aninda rollback | Otomatik (CI/CD) |
| 5xx orani > %1 (5 dk icerisinde) | Aninda rollback | Nobet muhendisi |
| Latency > 2s (p99, 10 dk) | Inceleme, gerekirse rollback | Nobet muhendisi |
| Tek endpoint basarisiz | Izle, 15 dk icinde duzelmezse rollback | Takim lideri |
| Veri tutarsizligi | DB rollback + kod rollback | CTO |
| UI kozmetik hata | Rollback YAPILMAZ, hotfix cikarilir | Gelistirici |

---

## 7. Iletisim Protokolu

### Deploy Baslangici
```
Kanal: #ops-deploys (Slack)
Mesaj: "[DEPLOY BASLADI] Production v<version> - SHA: <short-sha> - Operator: <isim>"
```

### Deploy Basarili
```
Kanal: #ops-deploys
Mesaj: "[DEPLOY BASARILI] Production v<version> - Tum smoke testler gecti - Suresi: <dakika>dk"
```

### Rollback Tetiklendi
```
Kanal: #ops-deploys + #incidents
Mesaj: "[ROLLBACK] Production - Sebep: <aciklama> - Onceki versiyon: <sha>"
```

---

## 8. Periyodik Kontroller

| Zamanlama | Kontrol | Sorumlu |
|-----------|---------|---------|
| Deploy + 15dk | Metrik anomali taramasi | Nobet muhendisi |
| Deploy + 1 saat | Musteri sikayet kontrolu | Destek ekibi |
| Deploy + 24 saat | Night audit basarili calistimi? | Platform muhendisi |
| Deploy + 72 saat | Performans trend analizi | Takim lideri |
