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
