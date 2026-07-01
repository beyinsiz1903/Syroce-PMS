# Tenant Restore Drill — Runbook

> Pilot Readiness Checklist hard-blocker #3.
> Phase 1 (May 2026): tooling + guardrails + dry-run only. ✅ MERGED `cb52fb68`.
> Phase 2 (May 2026): sandbox-only real `mongodump` → restore → prune →
> validate → report. ✅ Local smoke PASS (24/24 tests, manual run leak=0,
> FK orphans=0). Atlas/prod hard-BLOCK guardrail koda gömüldü.
> Phase 3 (planned): periodic Celery drill + DR plan integration.

## Amaç

Tek bir tenant'ın verisini bir MongoDB backup arşivinden alıp **staging** bir
veritabanına geri yükleme prosedürünü güvenli ve tekrar edilebilir hâle
getirmek. Drill'in iki ana hedefi vardır:

1. Backup'ın gerçekten kullanılabilir olduğunu doğrulamak (bit-rot,
   eksik koleksiyon, parse hatası kontrolü).
2. Bir tenant'ın veri kümesinin diğer tenant'ların verisinden ayrı
   restore edilebildiğini ispatlamak — KVKK/GDPR perspektifinde "right
   to be forgotten" ve incident response (yanlış silme, ransomware,
   tenant migration) için kritik.

## Ne zaman kullanılır

- Quarterly DR drill (Phase 3 ile otomatik).
- Pilot go-live öncesi smoke (Phase 2).
- Tenant'tan gelen "data lost / restore please" talebi sonrası.
- Schema değişikliği veya yeni tenant-scoped koleksiyon eklendiğinde.
- Yanlış silme / yanlış migration sonrası point-in-time recovery için.

## Ne zaman kullanılmaz

- Tüm-DB restore için. Bunun yerine `docs/procedures/BACKUP_AND_RESTORE.md`
  ve `docs/procedures/DISASTER_RECOVERY.md` kullanın.
- Production DB'ye doğrudan yazmak için. Drill **staging** hedefliyor.
  Production'a uygulamak istiyorsanız ayrı bir change request + onay zinciri
  gerekir (Faz 1 kapsamında değildir).

## Ön koşullar

| Bileşen | Gereksinim |
|---|---|
| MongoDB araçları | `mongodump`, `mongorestore` PATH'te |
| Backup arşivi | `mongodump --gzip` çıktısı (klasör veya tar.gz) |
| Staging DB | Boş veya silinebilir bir hedef veritabanı |
| ENV | `MONGO_URL`, `DB_NAME` set |
| Erişim | Staging cluster'a write erişimi olan operatör |
| Onay | Restore initiator + ikinci bir onay (4-eyes) |

## Güvenlik kuralları

Drill helper (`tools/tenant_restore_drill.py`) varsayılan olarak **dry-run**
modunda çalışır. Aşağıdaki kurallar koda gömülüdür ve bypass edilemez:

1. `--backup-archive`, `--tenant-id`, `--target-db` zorunludur. Eksikse
   argparse SystemExit ile çıkar.
2. `--target-db == $DB_NAME` (production DB) ise `BLOCK` verdict üretilir;
   `--allow-prod-target` flag'i olmadan run mümkün değildir.
3. `GLOBAL_EXCLUDE` listesindeki koleksiyonlar (secret stores, controlplane)
   asla restore planına dahil edilmez. Liste:
   `_dev_secrets`, `credential_vault`, `provider_secrets`,
   `secret_access_audit`, `cp_deploy_events`, `drift_alert_events`,
   `readiness_state_log`.
4. `UNKNOWN_REVIEW_REQUIRED` listesindeki koleksiyonlar plana dahil
   edilmez ve `REVIEW` verdict tetiklenir. Schema sahibi bunların
   tenant-scope'unu netleştirene kadar drill onları atlar.
5. `--execute` verilse bile, risk verdict `BLOCK` ise `run_execute`
   çağrılmaz ve script exit 1 ile çıkar.
6. Hiçbir kod yolu production DB'yi `dropDatabase` yapmaz, çağırmaz veya
   referans almaz.
7. **Atlas hard-BLOCK (Faz 2):** `MONGO_URL` veya `--mongo-url` aşağıdaki
   pattern'lerden HERHANGİ birine **case-insensitive** uyarsa `BLOCK`
   verdict üretilir:
   - `mongodb+srv://` (her case kombinasyonu, SRV scheme her zaman
     yönetilen cluster lookup'ı demektir → fail-closed),
   - host kısmında `.mongodb.net`, `.mongodb-dev.net`, `.mongodbgov.net`
     suffix'i (`mongodb://node1.cluster.mongodb.net:27017,node2...` gibi
     çoklu-host URL'ler de yakalanır).
   Bu kural `--allow-prod-target` flag'i ile bypass EDİLEMEZ. Sandbox
   drill yalnızca lokal Mongo'ya bağlanabilir. **Bilinen sınır:** Atlas
   suffix'i içermeyen custom DNS/CNAME alias'ları string heuristic ile
   tespit edilemez — operatör sandbox drill'i böyle hostlara
   yönlendirmemelidir.
8. `run_execute` çalışmaya başlamadan önce ikinci bir Atlas-URL kontrolü
   yapar (defense-in-depth); eşleşirse exit 2 ile çıkar.
9. **Prune over-delete koruması (Faz 2):** `prune_cross_tenant`
   `tenant_id`-eksik docları SİLMEZ (`$exists: true` filter zorunlu).
   Ek olarak iki fazlı bir tarama yapar: önce TÜM koleksiyonlarda 100
   doc örnekleyerek `tenant_id` tipinin homojen ve CLI input tipiyle
   strict (`is`) eşleştiğini doğrular; herhangi birinde uyumsuzluk
   varsa hiçbir koleksiyonda `delete_many` çağrılmaz (no partial
   mutation).
   > **Eşzamanlılık notu:** Tarama-sonra-silme **atomic değildir**.
   > Sandbox drill'de yazıcı yoktur (fixture seed → mongodump →
   > restore → prune ardışıktır), bu kabul edilebilir. Sandbox dışı
   > kullanım için write quiescence (maintenance window) veya
   > transactional strateji gerekir; bu Faz 3 kapsamında ele alınacaktır.
10. **Validation `untagged` raporu:** `tenant_id`-eksik docs ayrı
    sayılır ve `untagged_total > 0` ise verdict `FAIL` olur (silinmez,
    operatör review gerektirir).
11. **Rapor dosya adı sanitize:** `tenant_id` filename'e yazılmadan
    önce `[^A-Za-z0-9._-]` karakterler `_` ile değiştirilir, max 64
    karakter, path traversal denemesi (`../`) absolute olarak
    `report_dir` dışına çıkarsa `RuntimeError`. Yazım atomic
    (temp + rename).

## Backup arşivi formatı

`backend/infra/backup_manager.py` `mongodump --gzip` ile şu yapıyı üretir:

```
<BACKUP_PATH>/bk_YYYYMMDD_HHMMSS_<8hex>/
└── <DB_NAME>/
    ├── <collection>.bson.gz
    └── <collection>.metadata.json.gz
```

Drill helper bu klasörü doğrudan tüketir. Tar arşivi olarak gelirse önce
`tar -xzf` ile açın.

> **Bilinen boşluk (Phase 1 sonu):** `BACKUP_PATH` varsayılanı
> `/tmp/backups` ephemeral'dır. Production öncesi kalıcı bir hedef
> (volume mount veya S3 senkronizasyonu) yapılandırılmalıdır. Ayrıca
> backup task'ı şu an Celery beat'te schedule edilmemiştir
> (`backend/celery_app.py`); manuel `POST /api/infra/backup/trigger`
> ile tetikleniyor. Bu boşluk hard-blocker takip kalemi olarak
> `docs/PILOT_READINESS_CHECKLIST.md`'e eklenmelidir.

## Tenant scope classification

`backend/scripts/classify_tenant_scope.py` static analiz ile her
koleksiyonu 4 gruptan birine atar:

| Kategori | Tanım | Drill davranışı |
|---|---|---|
| `TENANT_SCOPED` | Kodda `tenant_id` ile birlikte sorgulanan koleksiyon. | Plana dahil edilir, restore + tenant_id prune. |
| `GLOBAL_EXCLUDE` | Global secret store / controlplane (sabit liste). | Asla dahil edilmez. |
| `UNKNOWN_REVIEW_REQUIRED` | Tenant scoping belirsiz (channel-manager state, vs). | Dahil edilmez, `REVIEW` verdict. |
| `SYSTEM_INTERNAL` | MongoDB internal namespace (`system.*`, `fs.*`). | Atlanır. |

Classification report üretmek için:

```bash
python backend/scripts/classify_tenant_scope.py --format text
python backend/scripts/classify_tenant_scope.py --output /tmp/scope.json
```

## Dry-run adımları

```bash
python tools/tenant_restore_drill.py \
  --backup-archive /var/backups/bk_20260511_020000_abc123 \
  --tenant-id 64a1b2c3d4e5f6789abcdef0 \
  --target-db hotel_pms_drill_staging
```

Bu komut:

1. Classification raporunu üretir.
2. Plan'ı oluşturur (kaynak, tenant, hedef, tenant-scoped koleksiyonlar,
   excluded globals, unknown review-required, system internal).
3. Risk verdict üretir (`OK` / `REVIEW` / `BLOCK`).
4. Hiçbir mongorestore subprocess'i çağırmaz, hiçbir DB'ye yazmaz.

Beklenen çıktı (örnek):

```
=== Tenant Restore Drill Plan ===
- source backup archive: /var/backups/bk_20260511_020000_abc123
- target tenant_id: 64a1b2c3d4e5f6789abcdef0
- target database: hotel_pms_drill_staging
- mode: dry-run
- collections discovered: 42
- tenant-scoped collections (28): [...]
- excluded global collections (7): [...]
- unknown collections requiring review (6): [...]
- system internal skipped (1): [...]

- planned restore strategy: ...
- validation queries: ...

- risk verdict: REVIEW
- risk findings:
    * 6 collection(s) are UNKNOWN_REVIEW_REQUIRED — confirm tenant scoping...
```

## Execute adımları (Phase 2 — sandbox-only smoke)

> Faz 2 execute path **sandbox-only**'dir. Atlas/prod URL'lere
> bağlanma denemesi guardrail tarafından BLOCK edilir (kural #7-8).
> Production tenant restore senaryosu Faz 3'te ayrı change-control
> ile yönetilecektir.

### Sandbox smoke koşusu (lokal Mongo)

```bash
# 1. Lokal mongo başlat (alt port, ayrı dbpath)
DBPATH=$(mktemp -d -t drill_mongo_XXX)
mongod --dbpath "$DBPATH" --port 27018 --bind_ip 127.0.0.1 \
  --logpath /tmp/drill_mongod.log --fork

# 2. Fake 3-tenant fixture seed et (T1, T2, T3 × 7 koleksiyon)
python backend/scripts/seed_drill_fixture.py \
  --mongo-url mongodb://127.0.0.1:27018 \
  --db-name drill_source

# 3. mongodump al
ARCH=$(mktemp -d -t drill_archive_XXX)
mongodump --uri=mongodb://127.0.0.1:27018 --db=drill_source \
  --out="$ARCH" --gzip

# 4. Drill --execute (Atlas BLOCK guard aktif; lokal URL geçer)
unset DB_NAME
MONGO_URL=mongodb://127.0.0.1:27018 \
python tools/tenant_restore_drill.py \
  --backup-archive "$ARCH" \
  --tenant-id T1 \
  --target-db drill_staging \
  --source-db-name drill_source \
  --execute

# 5. Rapor: docs/drill_reports/<TS>_T1_drill.md
```

Helper sırasıyla:

1. Plan + risk verdict üretir. `BLOCK` (Atlas / prod-target / boş plan) ise
   exit 1.
2. Atlas-URL ikinci kontrolü (`run_execute` içinde, defense-in-depth).
3. Her TENANT_SCOPED koleksiyon için `mongorestore --gzip
   --nsInclude=<DB>.<col> --nsFrom=<DB>.<col> --nsTo=<TARGET_DB>.<col>
   <archive>` komutunu çalıştırır. Arşivde olmayan koleksiyonlar
   `SKIP` mesajıyla atlanır (klasifikasyon kapsamlı, fixture küçük).
4. Post-restore prune (`motor`): her restore edilen koleksiyonda
   `deleteMany({tenant_id: {$ne: <TENANT_ID>}})`.
5. Validation: per-collection `target_count > 0` + `leak_count == 0` +
   FK integrity (booking → guest, booking → room, folio → booking).
6. Drill report'u `docs/drill_reports/<YYYYMMDDTHHMMSS>_<TENANT>_drill.md`
   olarak yazar. Verdict `PASS` ise exit 0; `FAIL` (leak veya FK orphan)
   ise exit 2.

### Otomatik smoke testi

```bash
cd backend && pytest tests/test_tenant_restore_drill_smoke.py -v
```

Bu test mongod'u kendisi spawn eder (`mongod`/`mongodump`/`mongorestore`
PATH'te değilse skip), tüm akışı koşar, leak=0 + FK=0 + rapor dosyası
yazıldığını assert eder. Atlas-URL guardrail testleri ayrıca koşar
(`mongodb+srv://` ve `.mongodb.net` hostname için exit 1).

### Faz 2 ilk smoke sonucu (referans)

İlk başarılı manuel koşu:

- Tarih: 2026-05-11 16:43 UTC
- Backup: lokal mongodump (3 tenant × 7 koleksiyon, ~38 doc)
- Target tenant: T1
- Target DB: `drill_staging_manual`
- Restore edilen koleksiyon sayısı: 7 (tenants, users, guests, rooms,
  bookings, folios, payments)
- Leak total: **0** (T2 + T3 verisi prune ile temizlendi)
- FK orphan total: **0**
- Verdict: **PASS**
- Rapor: `docs/drill_reports/20260511T164309_T1_drill.md`

## Validation queries

Restore tamamlandıktan sonra staging DB'de çalıştırılır. **Hepsi pass
olmalıdır.**

```javascript
// Per-collection target tenant doc count
db.<col>.countDocuments({tenant_id: "<TENANT_ID>"})  // > 0

// Cross-tenant leak guard (KRİTİK)
db.<col>.countDocuments({tenant_id: {$ne: "<TENANT_ID>"}})  // == 0

// Foreign-key integrity (booking → guest)
db.bookings.aggregate([
  {$match: {tenant_id: "<TENANT_ID>"}},
  {$lookup: {from: "guests", localField: "guest_id", foreignField: "_id", as: "g"}},
  {$match: {g: {$size: 0}}}
]).toArray()  // == [] (orphan booking yok)

// Foreign-key integrity (booking → folio)
db.folios.aggregate([
  {$match: {tenant_id: "<TENANT_ID>"}},
  {$lookup: {from: "bookings", localField: "booking_id", foreignField: "_id", as: "b"}},
  {$match: {b: {$size: 0}}}
]).toArray()  // == []
```

## Leak check

Cross-tenant leak = drill'in **tek hard fail kriteridir**. Her
TENANT_SCOPED koleksiyon için staging DB'de `tenant_id != X` olan tek
bir doc bile bulunması drill'in başarısız sayılması anlamına gelir.

Otomatik leak check sorgusu:

```javascript
const target = "<TENANT_ID>";
const colls = db.getCollectionNames();
const leaks = colls.map(c => ({
  collection: c,
  leak_count: db[c].countDocuments({tenant_id: {$ne: target}})
})).filter(r => r.leak_count > 0);
print(JSON.stringify(leaks, null, 2));
// leaks.length must == 0
```

## Foreign-key integrity check

Restore sonrası tenant veri grafının kapalı olduğunu doğrulayın. Tipik
zincirler:

- `bookings.guest_id → guests._id`
- `bookings._id → folios.booking_id`
- `folios._id → invoices.folio_id`
- `bookings.room_id → rooms._id`
- `bookings.company_id → companies._id` (varsa)

Orphan referans varsa = backup'ın incremental olduğu veya tenant verisinin
parçalı kaldığı anlamına gelir; root cause araştırması gerekir.

## Rollback

Staging DB üzerinde drill yapıldığı için "rollback" basittir:

```bash
# Hedef staging DB'yi tamamen düşür
mongosh "$MONGO_URL" --eval 'db.getSiblingDB("hotel_pms_drill_staging").dropDatabase()'
```

Yanlışlıkla `--allow-prod-target` ile production'a yazıldıysa:

1. **Derhal** uygulamayı maintenance moda alın.
2. En son known-good backup'tan tam DB restore yapın
   (`docs/procedures/BACKUP_AND_RESTORE.md`).
3. Audit log + post-mortem tetikleyin (4-eyes ihlali analizi).

## RTO / RPO hedefleri

| Metrik | Hedef | Kaynak |
|---|---|---|
| RPO | 24 saat | `docs/procedures/DISASTER_RECOVERY.md` |
| RTO (tenant restore) | 4 saat | DR plan ile uyumlu |
| Drill duration | < 1 saat | dev/staging küçük tenant için |
| Leak count | 0 | hard fail kriteri |

## Drill report template

Drill her koşuda aşağıdaki formatta bir rapor üretmelidir
(Faz 2 implementasyonu):

```markdown
# Tenant Restore Drill Report — YYYY-MM-DD

- Operator: <name>
- Reviewer (4-eyes): <name>
- Backup archive: <path>
- Backup created at: <iso8601>
- Target tenant_id: <id>
- Target database: <name>
- Mode: execute
- Started: <iso8601>
- Completed: <iso8601>
- Duration: <Xm Ys>

## Plan
- Tenant-scoped collections: N
- Excluded globals: M
- Unknown review-required: K (listelenir)

## Restore results
| Collection | Restored docs | Pruned (cross-tenant) | Final count | Status |
|---|---|---|---|---|
| bookings | 1234 | 7821 | 1234 | OK |
| folios   | 456  | 2912 | 456  | OK |
| ...      |      |      |      |    |

## Validation
- Per-tenant counts match expected: PASS / FAIL
- Cross-tenant leak count: 0 (PASS)
- Foreign-key orphan count: 0 (PASS)

## Verdict
PASS / FAIL

## Notes
- ...
```

## Known gaps (Phase 1 → Phase 2 takibi)

1. **Backup automation Celery'de schedule edilmemiş.** `backend/celery_app.py`
   beat schedule'ında backup task'ı yok. Restore drill'in işe yaraması için
   gerçek backup'ın alınıyor olması şarttır. Ayrı hard-blocker takibi:
   *"Backup automation currently not scheduled and default `BACKUP_PATH` is
   ephemeral. Restore drill cannot fully close until a durable backup
   destination and scheduled backup job are verified."*
2. **`BACKUP_PATH=/tmp/backups`** container ephemeral. Production için
   kalıcı volume + off-site sync (S3/GCS) gerekir.
3. **Post-restore prune** ✅ Faz 2'de `motor` ile implement edildi
   (`prune_cross_tenant`).
4. **Drill report yazıcısı** ✅ Faz 2'de eklendi (`write_drill_report`,
   markdown çıktısı `docs/drill_reports/`).
5. **UNKNOWN_REVIEW_REQUIRED** koleksiyonlarının schema sahipleriyle
   görüşülüp tenant-scope'larının netleştirilmesi gerekiyor:
   `connector_dlq`, `connector_outbox`, `connector_metrics`,
   `cm_webhook_events`, `raw_channel_events`, `reservation_lineage`.
6. **Periodic drill (Phase 3)** Celery beat ile quarterly çalıştırılacak;
   Faz 1/2'de schedule entry yok.
7. **Production tenant restore** Faz 2 sandbox-only'dir; gerçek tenant
   verisi restore senaryosu Faz 3 change-control kapsamına aittir
   (4-eyes onay + maintenance window + post-restore audit).

## İlişkili dosyalar

- `tools/tenant_restore_drill.py` — drill helper (Faz 1+2)
- `backend/scripts/classify_tenant_scope.py` — collection classifier
- `backend/scripts/seed_drill_fixture.py` — sandbox fake 3-tenant seeder
- `backend/tests/test_tenant_restore_drill.py` — Faz 1 guardrail testleri (20)
- `backend/tests/test_tenant_restore_drill_smoke.py` — Faz 2 sandbox smoke (4)
- `backend/infra/backup_manager.py` — backup mantığı
- `docs/drill_reports/` — drill rapor çıktısı klasörü
- `docs/procedures/BACKUP_AND_RESTORE.md` — tam-DB backup/restore
- `docs/procedures/DISASTER_RECOVERY.md` — DR plan
- `docs/PILOT_READINESS_CHECKLIST.md` — hard-blocker listesi
