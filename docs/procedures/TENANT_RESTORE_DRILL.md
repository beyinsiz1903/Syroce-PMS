# Tenant Restore Drill — Runbook

> Pilot Readiness Checklist hard-blocker #3.
> Phase 1 (May 2026): tooling + guardrails + dry-run only.
> Phase 2 (planned): real backup → staging restore smoke.
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

## Execute adımları (Phase 2)

> **Faz 1'de execute path test edilmez.** Aşağıdaki adımlar Faz 2'de
> dev/staging cluster üzerinde valide edilecektir.

```bash
python tools/tenant_restore_drill.py \
  --backup-archive /var/backups/bk_20260511_020000_abc123 \
  --tenant-id 64a1b2c3d4e5f6789abcdef0 \
  --target-db hotel_pms_drill_staging \
  --execute
```

Helper sırasıyla:

1. Plan + risk verdict üretir. `BLOCK` ise exit 1.
2. Her TENANT_SCOPED koleksiyon için `mongorestore --gzip --nsInclude=
   <DB>.<col> --nsFrom=<DB>.<col> --nsTo=<TARGET_DB>.<col> <archive>`
   komutunu çalıştırır.
3. Post-restore prune (Faz 2 takibinde implement edilecek):
   her koleksiyonda `deleteMany({tenant_id: {$ne: <TENANT_ID>}})`.
4. Drill report'u stdout + `drill_report_<timestamp>.md` olarak yazar.

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
3. **Post-restore prune** Faz 2'de `motor` ile implement edilecek; Faz 1
   sadece restore subprocess'lerini çalıştırır, prune'u çağırmaz.
4. **Drill report yazıcısı** Faz 2'de eklenecek; Faz 1 sadece stdout plan
   üretir.
5. **UNKNOWN_REVIEW_REQUIRED** koleksiyonlarının schema sahipleriyle
   görüşülüp tenant-scope'larının netleştirilmesi gerekiyor:
   `connector_dlq`, `connector_outbox`, `connector_metrics`,
   `cm_webhook_events`, `raw_channel_events`, `reservation_lineage`.
6. **Periodic drill (Phase 3)** Celery beat ile quarterly çalıştırılacak;
   Faz 1'de schedule entry yok.

## İlişkili dosyalar

- `tools/tenant_restore_drill.py` — drill helper
- `backend/scripts/classify_tenant_scope.py` — collection classifier
- `backend/tests/test_tenant_restore_drill.py` — guardrail testleri
- `backend/infra/backup_manager.py` — backup mantığı
- `docs/procedures/BACKUP_AND_RESTORE.md` — tam-DB backup/restore
- `docs/procedures/DISASTER_RECOVERY.md` — DR plan
- `docs/PILOT_READINESS_CHECKLIST.md` — hard-blocker listesi
