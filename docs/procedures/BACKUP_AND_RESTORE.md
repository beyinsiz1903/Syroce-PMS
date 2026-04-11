# 💾 RoomOps - Backup & Restore Prosedürü

## 📋 İçindekiler
1. [Backup Stratejisi](#backup-stratejisi)
2. [Otomatik Backup](#otomatik-backup)
3. [Manuel Backup](#manuel-backup)
4. [Restore İşlemleri](#restore-işlemleri)
5. [Disaster Recovery](#disaster-recovery)
6. [Test ve Doğrulama](#test-ve-doğrulama)

---

## Backup Stratejisi

### Backup Türleri

#### 1. 📦 Full Backup (Tam Yedek)
**Ne Zaman:** Haftalık (Pazar 03:00)
**İçerik:**
- ✅ Tüm database (MongoDB)
- ✅ Tüm collections
- ✅ User data
- ✅ System configurations
- ✅ Audit logs
- ✅ File uploads

**Retention:** 4 hafta (son 4 full backup)

---

#### 2. 📁 Incremental Backup (Artımlı Yedek)
**Ne Zaman:** Günlük (Her gün 02:00)
**İçerik:**
- ✅ Son 24 saatteki değişiklikler
- ✅ Modified documents
- ✅ New bookings
- ✅ Transaction logs

**Retention:** 7 gün

---

#### 3. 🔄 Real-time Backup (Anlık Yedek)
**Ne Zaman:** Continuous (MongoDB replica set)
**İçerik:**
- ✅ Real-time replication
- ✅ All database changes
- ✅ Automatic failover

**Retention:** Sürekli (replica set üzerinde)

---

### 3-2-1 Backup Rule

```
📦 3 Copies (3 Kopya)
   ├─ Production Database (Primary)
   ├─ Local Backup Storage
   └─ Cloud Backup Storage

💾 2 Different Media (2 Farklı Ortam)
   ├─ Local Disk Storage
   └─ Cloud Storage (AWS S3 / Google Cloud)

🌍 1 Off-site Copy (1 Uzak Kopya)
   └─ Cloud Storage (Farklı region)
```

---

## Otomatik Backup

### Günlük Otomatik Backup

**Backup Script:** `/app/backend/scripts/backup_daily.sh`

```bash
#!/bin/bash
# Daily Automated Backup Script

# Configuration
BACKUP_DIR="/var/backups/roomops"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="roomops_backup_${DATE}"
MONGO_URI="${MONGO_URL}"
DB_NAME="roomops"
RETENTION_DAYS=7

# Create backup directory
mkdir -p ${BACKUP_DIR}

echo "🔄 Starting backup: ${BACKUP_NAME}"
echo "📅 Date: $(date)"

# MongoDB Backup
echo "📦 Backing up MongoDB..."
mongodump --uri="${MONGO_URI}" \
  --db="${DB_NAME}" \
  --out="${BACKUP_DIR}/${BACKUP_NAME}" \
  --gzip

if [ $? -eq 0 ]; then
    echo "✅ MongoDB backup completed"
else
    echo "❌ MongoDB backup failed"
    exit 1
fi

# Create tarball
echo "📦 Creating archive..."
cd ${BACKUP_DIR}
tar -czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}"
rm -rf "${BACKUP_NAME}"

if [ $? -eq 0 ]; then
    echo "✅ Archive created: ${BACKUP_NAME}.tar.gz"
else
    echo "❌ Archive creation failed"
    exit 1
fi

# Calculate backup size
BACKUP_SIZE=$(du -sh "${BACKUP_NAME}.tar.gz" | cut -f1)
echo "📊 Backup size: ${BACKUP_SIZE}"

# Upload to cloud (optional)
if [ ! -z "${AWS_S3_BUCKET}" ]; then
    echo "☁️ Uploading to S3..."
    aws s3 cp "${BACKUP_NAME}.tar.gz" \
      "s3://${AWS_S3_BUCKET}/backups/${BACKUP_NAME}.tar.gz"
    
    if [ $? -eq 0 ]; then
        echo "✅ Cloud upload completed"
    else
        echo "⚠️ Cloud upload failed (backup saved locally)"
    fi
fi

# Clean old backups (keep last 7 days)
echo "🧹 Cleaning old backups..."
find ${BACKUP_DIR} -name "roomops_backup_*.tar.gz" \
  -type f -mtime +${RETENTION_DAYS} -delete

echo "✅ Backup process completed"
echo "================================================"

# Send notification
curl -X POST "http://localhost:8001/api/system/backup-notification" \
  -H "Content-Type: application/json" \
  -d '{
    "backup_name": "'${BACKUP_NAME}'",
    "backup_size": "'${BACKUP_SIZE}'",
    "status": "success",
    "timestamp": "'$(date -Iseconds)'"
  }'

exit 0
```

---

### Cron Job Setup

**Dosya:** `/etc/cron.d/roomops-backup`

```cron
# RoomOps Automated Backup Schedule

# Daily Incremental Backup (02:00 AM)
0 2 * * * root /app/backend/scripts/backup_daily.sh >> /var/log/roomops/backup_daily.log 2>&1

# Weekly Full Backup (Sunday 03:00 AM)
0 3 * * 0 root /app/backend/scripts/backup_full.sh >> /var/log/roomops/backup_full.log 2>&1

# Backup verification (Daily at 04:00 AM)
0 4 * * * root /app/backend/scripts/verify_backup.sh >> /var/log/roomops/backup_verify.log 2>&1
```

**Kurulum:**
```bash
# Cron job'u aktif et
sudo cp /app/backend/scripts/cron/roomops-backup /etc/cron.d/
sudo chmod 644 /etc/cron.d/roomops-backup
sudo service cron reload

# Log dizini oluştur
sudo mkdir -p /var/log/roomops
sudo chmod 755 /var/log/roomops
```

---

## Manuel Backup

### Web UI Üzerinden Backup

**Adımlar:**

1. **Admin paneline giriş yapın**
   - URL: `http://your-hotel.com/admin`
   - Role: ADMIN veya IT_MANAGER

2. **System → Backup & Restore** menüsüne gidin

3. **"Create Backup" butonuna tıklayın**
   
4. **Backup seçeneklerini belirleyin:**
   ```
   □ Full Database Backup
   □ Include Audit Logs
   □ Include File Uploads
   □ Include System Config
   
   Backup Name: [roomops_manual_20250115]
   
   [Create Backup] [Cancel]
   ```

5. **Backup tamamlanınca download linki gelecek**
   ```
   ✅ Backup completed successfully!
   
   📦 Backup File: roomops_manual_20250115.tar.gz
   📊 Size: 245 MB
   📅 Created: 2025-01-15 14:30:00
   
   [Download Backup] [View Details]
   ```

---

### API ile Manuel Backup

**Endpoint:** `POST /api/system/backup/create`

**Request:**
```bash
curl -X POST "http://localhost:8001/api/system/backup/create" \
  -H "Authorization: Bearer {admin_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "backup_type": "full",
    "include_audit_logs": true,
    "include_files": true,
    "description": "Pre-migration backup"
  }'
```

**Response:**
```json
{
  "success": true,
  "backup_id": "backup-20250115-143000",
  "backup_file": "roomops_backup_20250115_143000.tar.gz",
  "size": "245 MB",
  "status": "completed",
  "download_url": "/api/system/backup/download/backup-20250115-143000",
  "created_at": "2025-01-15T14:30:00Z",
  "metadata": {
    "collections_backed_up": 15,
    "documents_count": 125834,
    "compressed_size": "245 MB",
    "uncompressed_size": "1.2 GB"
  }
}
```

---

### Command Line (Direkt MongoDB)

**Full Database Backup:**
```bash
# Tüm database'i yedekle
mongodump --uri="mongodb://localhost:27017" \
  --db="roomops" \
  --out="/tmp/backup_$(date +%Y%m%d)" \
  --gzip

# Compress
tar -czf roomops_backup_$(date +%Y%m%d).tar.gz \
  /tmp/backup_$(date +%Y%m%d)

echo "✅ Backup saved: roomops_backup_$(date +%Y%m%d).tar.gz"
```

**Specific Collection Backup:**
```bash
# Sadece bookings collection
mongodump --uri="mongodb://localhost:27017" \
  --db="roomops" \
  --collection="bookings" \
  --out="/tmp/bookings_backup" \
  --gzip
```

**Export to JSON:**
```bash
# Bookings'i JSON olarak export et
mongoexport --uri="mongodb://localhost:27017" \
  --db="roomops" \
  --collection="bookings" \
  --out="bookings_$(date +%Y%m%d).json" \
  --jsonArray
```

---

## Restore İşlemleri

### ⚠️ ÖNEMLİ UYARILAR

```
🛑 RESTORE İŞLEMİNDEN ÖNCE:

1. ✅ Mevcut database'in yedeiğini alın
2. ✅ Tüm kullanıcıları sistemden çıkarın
3. ✅ Application'ı durdurun
4. ✅ Restore edilecek backup'ın doğruluğunu kontrol edin
5. ✅ IT Manager veya GM'den onay alın

❌ RESTORE SIRASINDA:
- Sistem kullanıma kapalıdır
- Tüm data overwrite edilecek
- Transaction logs kaybolacak
- Son backup'tan sonraki data kaybolacak
```

---

### Web UI Üzerinden Restore

**Adımlar:**

1. **Maintenance mode aktif edin**
   ```
   System → Maintenance Mode → Enable
   Message: "System maintenance - Restore in progress"
   Duration: 1 hour
   ```

2. **System → Backup & Restore → Restore** sekmesine gidin

3. **Backup dosyasını seçin**
   ```
   Available Backups:
   
   📦 roomops_backup_20250114_020000.tar.gz
      Size: 238 MB
      Date: 2025-01-14 02:00:00
      Type: Full Backup
      Status: Verified ✅
      [Restore] [Download] [Details]
   
   📦 roomops_backup_20250113_020000.tar.gz
      Size: 235 MB
      Date: 2025-01-13 02:00:00
      Type: Full Backup
      Status: Verified ✅
      [Restore] [Download] [Details]
   ```

4. **Restore confirmation**
   ```
   ⚠️ WARNING: Database Restore
   
   This action will:
   - Stop all services
   - Overwrite current database
   - Restore from: roomops_backup_20250114_020000.tar.gz
   - Data loss: Last 1 day
   
   Type "CONFIRM RESTORE" to proceed:
   [                     ]
   
   [Proceed] [Cancel]
   ```

5. **Restore progress**
   ```
   🔄 Restore in Progress...
   
   ✅ Services stopped
   ✅ Current database backed up
   ✅ Backup file extracted
   🔄 Restoring collections... (8/15)
   ⏳ Estimated time: 5 minutes
   
   [View Logs]
   ```

6. **Restore tamamlandı**
   ```
   ✅ Restore Completed Successfully!
   
   📊 Statistics:
   - Collections restored: 15
   - Documents restored: 124,567
   - Duration: 8 minutes 32 seconds
   - Data restored from: 2025-01-14 02:00:00
   
   Next Steps:
   1. Verify data integrity
   2. Test critical functions
   3. Disable maintenance mode
   4. Notify users
   
   [Verify Data] [Disable Maintenance] [View Logs]
   ```

---

### Command Line Restore

**Full Database Restore:**
```bash
#!/bin/bash
# Full Database Restore Script

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore.sh <backup_file.tar.gz>"
    exit 1
fi

echo "🛑 WARNING: This will overwrite the current database!"
read -p "Type 'YES' to continue: " confirm

if [ "$confirm" != "YES" ]; then
    echo "❌ Restore cancelled"
    exit 0
fi

# Stop services
echo "🛑 Stopping services..."
sudo supervisorctl stop backend frontend

# Backup current database (safety)
echo "💾 Backing up current database..."
mongodump --uri="${MONGO_URL}" \
  --db="roomops" \
  --out="/tmp/pre_restore_backup_$(date +%Y%m%d_%H%M%S)" \
  --gzip

# Extract backup
echo "📦 Extracting backup..."
TEMP_DIR="/tmp/restore_$(date +%Y%m%d_%H%M%S)"
mkdir -p ${TEMP_DIR}
tar -xzf ${BACKUP_FILE} -C ${TEMP_DIR}

# Drop current database
echo "🗑️ Dropping current database..."
mongo ${MONGO_URL}/roomops --eval "db.dropDatabase()"

# Restore from backup
echo "🔄 Restoring database..."
BACKUP_DIR=$(find ${TEMP_DIR} -name "roomops" -type d)
mongorestore --uri="${MONGO_URL}" \
  --db="roomops" \
  --gzip \
  ${BACKUP_DIR}

if [ $? -eq 0 ]; then
    echo "✅ Database restored successfully"
else
    echo "❌ Restore failed! Reverting..."
    # Restore from safety backup
    mongorestore --uri="${MONGO_URL}" \
      --db="roomops" \
      --gzip \
      /tmp/pre_restore_backup_*/roomops
    exit 1
fi

# Cleanup
rm -rf ${TEMP_DIR}

# Start services
echo "🚀 Starting services..."
sudo supervisorctl start backend frontend
sleep 10

# Verify services
echo "🔍 Verifying services..."
sudo supervisorctl status

echo "✅ Restore completed successfully!"
echo "⚠️ Please verify data integrity before enabling production access"

exit 0
```

**Kullanım:**
```bash
chmod +x restore.sh
./restore.sh roomops_backup_20250114_020000.tar.gz
```

---

### Selective Restore (Belirli Collection)

```bash
# Sadece bookings collection'ı restore et
mongorestore --uri="mongodb://localhost:27017" \
  --db="roomops" \
  --collection="bookings" \
  --drop \
  --gzip \
  /path/to/backup/roomops/bookings.bson.gz

echo "✅ Bookings collection restored"
```

---

## Disaster Recovery

### Senaryolar ve Çözümler

#### Senaryo 1: Veri Kaybı (Yanlış Silme)

**Durum:** Bir personel yanlışlıkla tüm bugünkü rezervasyonları sildi.

**Çözüm:**
```
1. Derhal sistemi durdur (Maintenance mode)
2. Son backup'ı kontrol et
3. Selective restore yap (bookings collection)
4. Silinen data'yı geri getir
5. Silme işlemini audit log'dan bul
6. Prosedür düzelt (delete confirmation ekle)
```

**Recovery Time:** ~15 dakika

---

#### Senaryo 2: Database Corruption

**Durum:** MongoDB crash oldu, database bozuldu.

**Çözüm:**
```
1. MongoDB repair komutunu dene:
   mongod --repair --dbpath /var/lib/mongodb

2. Eğer repair başarısız:
   - Stop MongoDB
   - Full database restore
   - Restart services

3. Data loss calculate et:
   - Son backup: Dün gece 02:00
   - Current time: Bugün 15:00
   - Data loss: ~13 saat

4. Manuel data entry (kritik reservations):
   - Bugünkü check-in'leri manuel gir
   - Bugünkü bookings'leri manuel gir
```

**Recovery Time:** 1-2 saat

---

#### Senaryo 3: Ransomware Attack

**Durum:** Sistem ransomware'e maruz kaldı, tüm data şifrelendi.

**Çözüm:**
```
1. IMMEDIATELY:
   - Tüm sistemleri shutdown et
   - Network bağlantısını kes
   - IT Security'yi ara

2. Clean System Preparation:
   - Yeni server veya VM hazırla
   - OS'yi sıfırdan kur
   - Sadece essentials install et

3. Restore from Off-site Backup:
   - Cloud backup'tan son clean backup'ı al
   - Fresh system'e restore et
   - Verify integrity

4. Security Audit:
   - Access logs kontrol et
   - Şifreleri değiştir
   - 2FA aktif et
   - Security patches uygula
```

**Recovery Time:** 4-8 saat

---

## Test ve Doğrulama

### Backup Verification (Otomatik)

**Script:** `/app/backend/scripts/verify_backup.sh`

```bash
#!/bin/bash
# Automated Backup Verification

LATEST_BACKUP=$(ls -t /var/backups/roomops/*.tar.gz | head -1)

echo "🔍 Verifying backup: ${LATEST_BACKUP}"

# Extract to temp
TEMP_DIR="/tmp/verify_$(date +%Y%m%d_%H%M%S)"
mkdir -p ${TEMP_DIR}
tar -xzf ${LATEST_BACKUP} -C ${TEMP_DIR}

# Check integrity
if [ $? -eq 0 ]; then
    echo "✅ Archive integrity: OK"
else
    echo "❌ Archive corrupted!"
    # Send alert
    exit 1
fi

# Check collections
BACKUP_DIR=$(find ${TEMP_DIR} -name "roomops" -type d)
COLLECTIONS=$(ls ${BACKUP_DIR}/*.bson.gz 2>/dev/null | wc -l)

if [ ${COLLECTIONS} -ge 10 ]; then
    echo "✅ Collections count: ${COLLECTIONS}"
else
    echo "❌ Missing collections! Found: ${COLLECTIONS}"
    exit 1
fi

# Check file sizes
MIN_SIZE=50000000  # 50 MB
BACKUP_SIZE=$(stat -f%z ${LATEST_BACKUP} 2>/dev/null || stat -c%s ${LATEST_BACKUP})

if [ ${BACKUP_SIZE} -gt ${MIN_SIZE} ]; then
    echo "✅ Backup size: $(($BACKUP_SIZE / 1024 / 1024)) MB"
else
    echo "❌ Backup too small! Size: $(($BACKUP_SIZE / 1024 / 1024)) MB"
    exit 1
fi

# Cleanup
rm -rf ${TEMP_DIR}

echo "✅ Backup verification completed"
exit 0
```

---

### Restore Test (Aylık)

**Test Prosedürü:**

1. **Test Environment Hazırla**
   - Ayrı bir test server/VM
   - MongoDB kurulu
   - RoomOps application kurulu

2. **Restore Test**
   ```bash
   # Son production backup'ı al
   scp production:/var/backups/roomops/latest.tar.gz /tmp/
   
   # Test environment'a restore et
   ./restore.sh /tmp/latest.tar.gz
   ```

3. **Verification Checklist**
   ```
   ✅ Database restore successful
   ✅ Services start correctly
   ✅ Login works
   ✅ Bookings visible
   ✅ Financial data intact
   ✅ Reports generate
   ✅ User permissions correct
   ```

4. **Document Results**
   ```
   Restore Test Report - 2025-01-15
   ================================
   
   Backup File: roomops_backup_20250114_020000.tar.gz
   Test Environment: test-server-01
   
   Results:
   - Restore Time: 12 minutes
   - Data Integrity: ✅ Pass
   - Application Startup: ✅ Pass
   - Critical Functions: ✅ Pass
   
   Issues: None
   
   Tested By: IT Manager
   Date: 2025-01-15
   ```

---

## Backup Monitoring

### Dashboard Metrics

```
📊 Backup System Status
══════════════════════════════════════════════════════

✅ Last Successful Backup
   Date: 2025-01-15 02:00:00
   Type: Daily Incremental
   Size: 242 MB
   Duration: 8 minutes
   Status: Verified ✅

📅 Backup Schedule
   Next Backup: 2025-01-16 02:00:00 (Daily)
   Next Full: 2025-01-19 03:00:00 (Weekly)

💾 Storage Status
   Local Storage: 2.1 GB / 50 GB (4%)
   Cloud Storage: 8.5 GB / 100 GB (8%)
   
📈 Statistics (Last 30 Days)
   Total Backups: 34
   Success Rate: 100%
   Average Size: 238 MB
   Failed Backups: 0
   
⚠️ Alerts
   No active alerts
```

---

## Troubleshooting

### Backup Başarısız

**Hata:** "Disk space full"
```bash
# Eski backupları temizle
find /var/backups/roomops -name "*.tar.gz" \
  -type f -mtime +30 -delete

# Disk kullanımını kontrol et
df -h /var/backups
```

**Hata:** "MongoDB connection failed"
```bash
# MongoDB durumunu kontrol et
sudo systemctl status mongodb

# Restart MongoDB
sudo systemctl restart mongodb

# Connection test
mongo --eval "db.runCommand({ ping: 1 })"
```

---

### Restore Başarısız

**Hata:** "Backup file corrupted"
```bash
# Backup integrity test
tar -tzf backup_file.tar.gz > /dev/null

# Eğer corrupted: Alternatif backup kullan
ls -lth /var/backups/roomops/*.tar.gz
```

**Hata:** "Insufficient disk space for restore"
```bash
# Gerekli alanı hesapla
REQUIRED=$(tar -tzf backup.tar.gz | \
  xargs -I {} stat -c%s {} | \
  awk '{s+=$1} END {print s/1024/1024 " MB"}')

echo "Required space: ${REQUIRED}"
df -h /var/lib/mongodb
```

---

## İletişim ve Destek

**Backup/Restore Sorunları:**
- IT Support: support@hotel.com
- Emergency: +1-555-0100
- Extension: 100

**Dokümantasyon güncellenme tarihi:** 15 Ocak 2025
