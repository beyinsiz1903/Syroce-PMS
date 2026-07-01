# Syroce PMS — Incident Playbook
## Olay Yonetimi Proseduru

**Versiyon**: 1.0
**Son Güncelleme**: Subat 2026
**Sahip**: Platform Muhendisligi

---

## 1. Olay Siniflari

| Sinif | Tanim | Ornekler | Yanit Suresi |
|-------|-------|----------|-------------|
| **SEV-1** | Sistem tamamen erislemez veya veri kaybi | API tamamen down, DB erislemez, cift rezervasyon | 15 dakika |
| **SEV-2** | Kritik is akisi bozuk ama sistem kismi calisiyor | Check-in basarisiz, OTA senkronizasyon durmus | 30 dakika |
| **SEV-3** | Fonksiyonellik azalmis ama cozum yolu var | Dashboard yavas, rapor hatali, tek endpoint down | 2 saat |
| **SEV-4** | Minör sorun, kullanici etkisi dusuk | UI kozmetik, yanlis cevirisi, log kirliligi | 8 saat |

---

## 2. Olay Tespit Kanallari

| Kanal | Aciklama | Ornek |
|-------|----------|-------|
| **Otomatik Alarm** | Prometheus/Grafana alert'leri | p99 > 5s, 5xx > %1, pod crash |
| **Synthetic Monitoring** | Periyodik health check'ler | Frontend/API uptime monitoru |
| **Musteri Bildirimi** | Destek talebi veya direkt iletisim | "Rezervasyon olusturamiyorum" |
| **Dahili Tespit** | Ekip uyesi fark ettigi sorun | Log'da tekrarlayan hata |
| **CI/CD Hatasi** | Deploy sonrasi smoke test basarisiz | Otomatik rollback tetiklendi |

---

## 3. Olay Yanit Sureci

### Faz 1: Tespit & Triage (0-15 dakika)

```
1. Alarm geldi veya sorun bildirildi
2. Nobet muhendisi 5 dakika icerisinde alarmi kabul eder
3. Ilk degerlendirme:
   a. Hangi servisler etkileniyor?
   b. Kac kullanici etkileniyor?
   c. Veri kaybi riski var mi?
4. SEV seviyesini belirle
5. Incident kanali ac: #inc-YYYY-MM-DD-<kisa-aciklama>
```

### Faz 2: Ilk Mudahale (15-60 dakika)

#### SEV-1: Sistem Down

```bash
# 1. Servis durumunu kontrol et
kubectl -n syroce get pods
kubectl -n syroce describe pod <crash-eden-pod>

# 2. Son deploy'u kontrol et
kubectl -n syroce rollout history deployment/syroce-backend

# 3. Log'lari incele
kubectl -n syroce logs deployment/syroce-backend --tail=200 --since=10m

# 4. Gerekirse aninda rollback
kubectl -n syroce rollout undo deployment/syroce-backend
kubectl -n syroce rollout undo deployment/syroce-frontend

# 5. DB baglantisini dogrula
kubectl -n syroce exec deployment/syroce-backend -- \
  python -c "from motor.motor_asyncio import AsyncIOMotorClient; import os; c=AsyncIOMotorClient(os.environ['MONGO_URL']); print('DB OK')"
```

#### SEV-2: Kritik Is Akisi Bozuk

```bash
# 1. Etkilenen endpoint'i tespit et
curl -sf "https://pms.syroce.com/api/health/" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2))"

# 2. Hata oruntusunu incele
kubectl -n syroce logs deployment/syroce-backend --tail=500 | grep -i "error\|exception\|traceback" | tail -20

# 3. Redis durumu
kubectl -n syroce exec deployment/syroce-backend -- redis-cli -u "$REDIS_URL" ping

# 4. MongoDB yavas sorgu kontrolu
# Grafana: MongoDB slow queries paneli
```

### Faz 3: Iletisim (Surec Boyunca)

| Kime | Ne Zaman | Nasil | Icerik |
|------|----------|-------|--------|
| Muhendislik ekibi | Hemen | Slack #incidents | SEV, etki, ilk bulgu |
| Urun yoneticisi | SEV-1/2 ise 15dk icerisinde | Slack DM | Musteri etkisi ozeti |
| Musteri (etkilenen) | SEV-1: 30dk, SEV-2: 1 saat | E-posta / durum sayfasi | Ne oldugu, tahmini cozum suresi |
| Yonetim | SEV-1 ise 1 saat icerisinde | E-posta | Ozet + ETA |

#### Iletisim Sablonu

```
[INCIDENT] SEV-<X> — <Baslik>

Durum: Inceleniyor / Hafifletildi / Cozuldu
Etki: <kac kullanici, hangi islevler>
Baslangic: <UTC zaman>
Son Guncelleme: <UTC zaman>

Ozet:
<1-2 cumle ne oluyor>

Sonraki Adim:
<Suan ne yapildiigi>

ETA: <tahmini cozum zamani veya "belirleniyor">
```

---

## 4. Yaygin Olay Senaryolari

### 4.1 API Tamamen Down (SEV-1)

**Belirtiler**: Health check basarisiz, frontend "sunucu hatasi" gosteriyor

**Kontrol Listesi**:
1. [ ] Pod'lar calisiyor mu? `kubectl -n syroce get pods`
2. [ ] CrashLoopBackOff var mi?
3. [ ] Son deploy ne zaman yapildi?
4. [ ] MongoDB erislebilir mi?
5. [ ] Redis erislebilir mi?
6. [ ] Disk dolu mu? `kubectl -n syroce exec <pod> -- df -h`

**Tipik Cozumler**:
- Son deploy'u geri al
- Pod'lari yeniden baslat: `kubectl -n syroce rollout restart deployment/syroce-backend`
- Kaynak limitlerini artir (OOM ise)

### 4.2 Cift Rezervasyon (SEV-1)

**Belirtiler**: Ayni oda/tarih icin iki farkli konuk rezervasyonu

**Kontrol Listesi**:
1. [ ] Her iki rezervasyonun `created_at` zamanini karsilastir
2. [ ] Atomik booking lock'u calisiyor mu?
3. [ ] `bookings` koleksiyonunda indeks var mi?
4. [ ] OTA tarafinda mi yoksa PMS tarafinda mi olusturuldu?

**Acil Aksiyon**:
1. Ikinci konuga alternatif oda ata
2. Otel yoneticisini bilgilendir
3. Root cause analizi baslat

### 4.3 OTA Senkronizasyon Durmus (SEV-2)

**Belirtiler**: Outbox queue derinligi artıyor, OTA'da eski fiyat/musaitlik

**Kontrol Listesi**:
1. [ ] Outbox worker calisiyor mu?
2. [ ] Dead letter queue'da birikmis olay var mi?
3. [ ] OTA API'si erislebilir mi? (HotelRunner, Exely)
4. [ ] Rate limiter tetiklenmis mi?

**Cozum**:
1. Worker'i yeniden baslat
2. Basarisiz olaylari tekrar isle
3. OTA saglayicisinin durum sayfasini kontrol et

### 4.4 Night Audit Basarisiz (SEV-2)

**Belirtiler**: Sabah raporlari guncel degil, gece denetimi calismmamis

**Kontrol Listesi**:
1. [ ] Celery beat worker calisiyor mu?
2. [ ] Son basarili night audit ne zaman?
3. [ ] Hata loglari: `kubectl -n syroce logs deployment/syroce-worker --tail=200 | grep audit`
4. [ ] Business date dogru mu?

**Cozum**:
1. Manuel tetikle: `POST /api/pms/night-audit/trigger`
2. Worker'i yeniden baslat
3. Folio reconciliation kontrolu

### 4.5 Yuksek Latency (SEV-3)

**Belirtiler**: p99 > 5s, kullanicilar yavaslama bildiriyor

**Kontrol Listesi**:
1. [ ] Hangi endpoint'ler yavas? (Grafana)
2. [ ] MongoDB slow query log'u
3. [ ] CPU/Memory kullanimi normal mi?
4. [ ] Baglanti havuzu dolu mu?

**Cozum**:
1. Yavas sorgulari tespit et ve optimize et
2. Indeks eksiklerini gider
3. Gerekirse pod sayisini artir (HPA)

---

## 5. Post-Mortem Sureci

Her SEV-1 ve SEV-2 olayi icin 48 saat icerisinde post-mortem ZORUNLUDUR.

### 5.1 Post-Mortem Sablonu

```markdown
# Post-Mortem: <Olay Basligi>

## Ozet
- Tarih: <YYYY-MM-DD>
- Sure: <baslangic> — <bitis> (<toplam dakika>)
- SEV: <1|2>
- Etki: <kac kullanici, hangi islevler>

## Zaman Cizelgesi
| Zaman (UTC) | Olay |
|-------------|------|
| HH:MM | Ilk alarm |
| HH:MM | Nobet muhendisi devir aldi |
| HH:MM | Kök neden tespit edildi |
| HH:MM | Düzeltme uygulandı |
| HH:MM | Normal isleyise donuldu |

## Kök Neden
<Teknik aciklama>

## Etki Analizi
- Etkilenen kullanici sayisi: X
- Kaybedilen islem sayisi: Y
- Gelir etkisi: ~Z TL

## Alinacak Aksiyonlar
| # | Aksiyon | Oncelik | Sorumlu | Teslim Tarihi |
|---|---------|---------|---------|---------------|
| 1 | ... | P0 | ... | ... |
| 2 | ... | P1 | ... | ... |

## Ders Cikarimlar
- Iyi giden: ...
- Kotu giden: ...
- Sans: ...
```

### 5.2 Post-Mortem Toplantisi

| Adim | Sure | Icerik |
|------|------|--------|
| Zaman cizelgesi incelemesi | 15 dk | Ne zaman ne oldu? |
| Kok neden tartismasi | 20 dk | Neden oldu? 5 Why's |
| Aksiyon maddeleri | 15 dk | Ne yapacagiz ki tekrar olmasin? |
| Surec iyilestirmesi | 10 dk | Yanit surecimiz nasil daha iyi olabilir? |

**Kurallar**:
- Blameless (suclama yok)
- Aksiyonlar somut ve tarihli olmali
- Aksiyon maddeleri takip edilmeli (JIRA/Linear)

---

## 6. Eskalasyon Matrisi

| Seviye | Kim | Ne Zaman |
|--------|-----|----------|
| L1 | Nobet muhendisi | Ilk alarm |
| L2 | Kidemli muhendis | 30 dk icerisinde cozulemezse |
| L3 | Takim lideri / Mimar | 1 saat icerisinde cozulemezse veya SEV-1 |
| L4 | CTO | Veri kaybi, guvenlik ihlali, 2+ saat downtime |

---

## 7. Nobet Cizelgesi

| Parametre | Deger |
|-----------|-------|
| Nobet suresi | 1 hafta (Pazartesi 09:00 → Pazartesi 09:00) |
| Yanit suresi | 15 dakika (SEV-1), 30 dakika (SEV-2) |
| Yedek | Her zaman 1 yedek nobet muhendisi |
| Araclar | PagerDuty (alarm), Slack (iletisim), Grafana (izleme) |
| Telafi | Nobet basina ek ucret + olay basina bonus |

---

## 8. Araclar & Erisim

| Arac | URL | Amac |
|------|-----|------|
| Grafana | `https://grafana.syroce.com` | Metrik & dashboard |
| PagerDuty | Ekip sayfasi | Alarm yonetimi |
| Slack #incidents | Workspace | Olay iletisimi |
| kubectl | Yerel terminal | K8s cluster yonetimi |
| MongoDB Compass | `MONGO_URL` | DB inceleme |
| Sentry | `https://sentry.io/syroce` | Hata izleme |
