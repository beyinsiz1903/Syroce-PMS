# Veritabanı Sharding Stratejisi

## MongoDB Sharding - tenant_id Bazlı

### 1. Genel Bakış

RoomOps PMS, multi-tenant mimari kullanır. Her otel zinciri/mülk `tenant_id` ile izole edilir.
Bu doküman, büyük ölçekli dağıtımlar için sharding stratejisini tanımlar.

### 2. Shard Key Seçimi

#### Birincil Shard Key: `tenant_id`

**Neden `tenant_id`?**
- Her query zaten `tenant_id` ile filtrelenir
- Veri izolasyonu doğal olarak sağlanır
- Cross-tenant query'ler minimumda
- Chunk migration minimize edilir

#### Shard Key Composition:
```javascript
// Ranged sharding (tenant_id bazlı)
sh.shardCollection("hotel_pms.bookings", { "tenant_id": 1, "check_in": -1 })
sh.shardCollection("hotel_pms.guests", { "tenant_id": 1, "email": 1 })
sh.shardCollection("hotel_pms.rooms", { "tenant_id": 1 })
sh.shardCollection("hotel_pms.folios", { "tenant_id": 1, "created_at": -1 })
sh.shardCollection("hotel_pms.audit_logs", { "tenant_id": 1, "timestamp": -1 })
sh.shardCollection("hotel_pms.tasks", { "tenant_id": 1 })
```

### 3. Cluster Mimarisi

```
┌─────────────────────────────────────────┐
│               mongos Router              │
│          (Application bağlantı)          │
├─────────────────────────────────────────┤
│           Config Servers (3x)            │
│    (Metadata & chunk bilgileri)          │
├────────────┬────────────┬───────────────┤
│  Shard 1   │  Shard 2   │   Shard 3     │
│  RS (3x)   │  RS (3x)   │   RS (3x)     │
│ tenant A-H │ tenant I-P │  tenant Q-Z   │
│  ~33% data │  ~33% data │  ~33% data    │
└────────────┴────────────┴───────────────┘
```

### 4. Shard Dağılım Kuralları

| Ölçek | Shard Sayısı | Tenant/Shard | Max Toplam Tenant |
|-------|-------------|--------------|-------------------|
| Small | 1 (standalone) | 1-50 | 50 |
| Medium | 3 | 50-150 | 450 |
| Large | 5 | 100-200 | 1000 |
| Enterprise | 10+ | 100-200 | 2000+ |

### 5. Zone Sharding (Coğrafi)

```javascript
// Türkiye bölgesi
sh.addShardToZone("shard0001", "turkey")
sh.updateZoneKeyRange(
  "hotel_pms.bookings",
  { tenant_id: "tr-", check_in: MinKey },
  { tenant_id: "tr~", check_in: MaxKey },
  "turkey"
)

// Avrupa bölgesi
sh.addShardToZone("shard0002", "europe")
sh.updateZoneKeyRange(
  "hotel_pms.bookings",
  { tenant_id: "eu-", check_in: MinKey },
  { tenant_id: "eu~", check_in: MaxKey },
  "europe"
)
```

### 6. Performans Hedefleri

| Metrik | Hedef | Mevcut |
|--------|-------|--------|
| Query latency (P95) | < 50ms | ~18ms |
| Insert throughput | > 10K/s | ~5K/s |
| Concurrent connections | 5000+ | 500 |
| Data per shard | < 500GB | N/A |

### 7. Migration Planı

1. **Aşama 1**: Replica Set kurulumu (HA)
2. **Aşama 2**: Config server ve mongos ekleme
3. **Aşama 3**: İlk shard'a mevcut data migration
4. **Aşama 4**: Yeni shard'lar ekleme
5. **Aşama 5**: Balancer ile otomatik dağıtım

### 8. İzleme ve Bakım

```bash
# Chunk dağılımı kontrolü
db.bookings.getShardDistribution()

# Balancer durumu
sh.getBalancerState()

# Shard istatistikleri
db.adminCommand({ listShards: 1 })
```

### 9. Shard-Readiness Denetimi (yeniden koşulabilir)

Gerçek sharding (config server, mongos, `sh.shardCollection`, balancer) bir
Atlas/DBA altyapı işidir ve bu repodaki kapsamın **dışındadır**. Bu bölüm,
o migrasyondan **önce** kodun "shard'a hazır" olduğunu kanıtlayan hazırlık
denetimini tanımlar. Denetim **salt-okunurdur**: index oluşturmaz/düşürmez,
veri değiştirmez, canlı sharding tetiklemez.

Araç: `backend/scripts/audit_shard_readiness.py`
(birim testi: `backend/tests/test_audit_shard_readiness.py`).

Denetim üç şeyi raporlar:

1. **Shard-key index kapsaması** — yukarıdaki §2'de önerilen her shard-key
   için (öncül `tenant_id`), prefix'i shard-key ile eşleşen bir bileşik
   index'in var olup olmadığı. Eksik kapsama raporlanır, asla oluşturulmaz.
2. **Sorgu shard-uyumu** — shardlanabilir bir koleksiyonda `tenant_id`
   filtresi olmadan, doğrudan ham (`_raw_db`) handle üzerinden yapılan
   okumaların statik taraması. Sharded cluster'da bu sorgular tüm shard'lara
   yayılır (scatter-gather). Tenant-aware proxy (`db`) üzerinden giden
   okumalar `tenant_id`'yi otomatik enjekte ettiği için yapısal olarak
   shard-routable'dır; tarama yalnızca `_raw_db` kaçış yolunu inceler.
3. **Hazırlık özeti** — operatörün sharding migrasyonu için go/no-go
   referansı olarak kullanabileceği PASS / REVIEW / FAIL kararı.

```bash
# Tam denetim (index kapsaması canlı cluster ister; sorgu taraması statiktir)
MONGO_URL="$MONGO_ATLAS_URI" DB_NAME=syroce-pms \
    python backend/scripts/audit_shard_readiness.py

# Sadece statik sorgu taraması (DB gerektirmez — CI/offline)
python backend/scripts/audit_shard_readiness.py --query-only

# REVIEW (uyarı) durumunu da hata say (deploy/CI kapısı)
python backend/scripts/audit_shard_readiness.py --strict
```

Çıkış kodları: `0` = PASS/REVIEW, `1` = FAIL (BLOCKER veya `--strict` altında
REVIEW), `2` = kullanım/bağlantı hatası. Makine-okunur kuyruk satırı:
`SUMMARY blockers=N warnings=M info=K verdict=PASS|REVIEW|FAIL`.

#### Hazırlık durumu (canlı denetim, 2026-06-11)

| Koleksiyon | Önerilen shard-key | Durum | Not |
|------------|--------------------|-------|-----|
| `bookings` | `{tenant_id:1, check_in:-1}` | HAZIR | `idx_bookings_tenant_checkin_checkout` prefix'i eşleşir; yön (`check_in`) ters → sharding anında tam yönlü index önerilir |
| `guests` | `{tenant_id:1, email:1}` | HAZIR | `idx_guests_tenant_email_unique` birebir (yön dâhil) |
| `rooms` | `{tenant_id:1}` | HAZIR | `idx_room_status` vb. öncül `tenant_id` |
| `folios` | `{tenant_id:1, created_at:-1}` | REVIEW | `tenant_id` öncüllü index'ler var (`idx_folio_*`) ama `{tenant_id, created_at}` prefix'ini destekleyen index **yok** → sharding'den önce eklenmeli (ya da `{tenant_id}` shard-key'i seçilmeli) |
| `audit_logs` | `{tenant_id:1, timestamp:-1}` | HAZIR | `idx_audit_log_timestamp` birebir (yön dâhil) |
| `tasks` | `{tenant_id:1}` | HAZIR | Kod tabanında `tasks` koleksiyonu **yok**; karşılığı `housekeeping_tasks` (`idx_hk_*`) ve `task_queue` (`idx_task_queue_poll`) — ikisi de öncül `tenant_id`. §2'deki `hotel_pms.tasks` satırı bu iki koleksiyona göre uyarlanmalı |

**Sorgu taraması:** doğrudan `_raw_db.<koleksiyon>` üzerinden yapılan
shardlanabilir okumaların tümü `tenant_id` taşıyor — `tenant_id`'siz
scatter-gather riski tespit edilmedi. (Sınırlama: tarama yalnızca doğrudan
`_raw_db.<koleksiyon>` zincirlerini görür; takma değişkene atanmış handle'lar
veya `get_system_db()` sonucu üzerinden yapılan okumalar kapsanmaz.)

**Genel karar:** `REVIEW` — tek açık kalem `folios` için önerilen bileşik
shard-key index'inin eksikliği. Bu bir BLOCKER değildir: `folios` `tenant_id`
öncüllü olduğundan `{tenant_id}` shard-key'i ile zaten shardlanabilir; yalnızca
`{tenant_id, created_at}` bileşik anahtarı seçilecekse sharding'den önce ilgili
index eklenmelidir.
