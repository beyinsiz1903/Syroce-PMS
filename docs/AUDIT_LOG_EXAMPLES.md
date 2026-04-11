# 📊 RoomOps - Audit Log Örnekleri ve Kullanımı

## 📋 İçindekiler
1. [Audit Log Nedir?](#audit-log-nedir)
2. [Log Kategorileri](#log-kategorileri)
3. [Gerçek Senaryolar ve Log Örnekleri](#gerçek-senaryolar-ve-log-örnekleri)
4. [Log Arama ve Filtreleme](#log-arama-ve-filtreleme)
5. [Kritik Olaylar ve Alarmlar](#kritik-olaylar-ve-alarmlar)

---

## Audit Log Nedir?

Audit log, sistemde gerçekleştirilen **tüm kritik işlemlerin** kaydını tutar. Bu sayede:
- ✅ Kim, ne zaman, ne yaptı takibi
- ✅ Güvenlik ihlallerinin tespiti
- ✅ Hatalı işlemlerin geri izlenmesi
- ✅ Compliance gereksinimleri
- ✅ Personel performans değerlendirmesi

**Log Retention:** 2 yıl (730 gün)
**Backup Frequency:** Günlük
**Immutable:** Loglar değiştirilemez

---

## Log Kategorileri

### 1. Authentication & Authorization (Kimlik Doğrulama)
- Login attempts (başarılı/başarısız)
- Logout events
- Password changes
- Permission checks

### 2. Reservations & Bookings (Rezervasyonlar)
- Booking creation
- Booking modification
- Booking cancellation
- Rate overrides

### 3. Financial Operations (Finansal İşlemler)
- Charge posting
- Payment posting
- Charge void
- Folio operations
- Invoice generation

### 4. Guest Operations (Misafir İşlemleri)
- Check-in
- Check-out
- Room changes
- Guest profile updates

### 5. System Operations (Sistem İşlemleri)
- User management
- Configuration changes
- Backup operations
- Data exports

---

## Gerçek Senaryolar ve Log Örnekleri

### Senaryo 1: Başarılı Check-in İşlemi

**Durum:** Front desk görevlisi Sarah, misafir John Smith'in check-in işlemini gerçekleştiriyor.

**İşlem Adımları:**
1. Rezervasyon bulundu
2. Oda 205 tahsis edildi
3. Guest folio oluşturuldu
4. Room status: available → occupied
5. Check-in tamamlandı

**Audit Log Kayıtları:**

```json
[
  {
    "log_id": "log-20250115-001",
    "timestamp": "2025-01-15T14:30:00Z",
    "user_id": "sarah-fd-001",
    "user_name": "Sarah Johnson",
    "user_role": "front_desk",
    "action": "CHECK_IN",
    "entity_type": "booking",
    "entity_id": "booking-12345",
    "changes": {
      "booking_status": "checked_in",
      "room_number": "205",
      "checked_in_at": "2025-01-15T14:30:00Z",
      "guest_name": "John Smith"
    },
    "metadata": {
      "ip_address": "192.168.1.105",
      "terminal": "FD-Terminal-01",
      "session_id": "sess-abc123"
    }
  },
  {
    "log_id": "log-20250115-002",
    "timestamp": "2025-01-15T14:30:05Z",
    "user_id": "sarah-fd-001",
    "user_name": "Sarah Johnson",
    "user_role": "front_desk",
    "action": "CREATE_FOLIO",
    "entity_type": "folio",
    "entity_id": "folio-F-2025-00123",
    "changes": {
      "folio_type": "guest",
      "folio_number": "F-2025-00123",
      "booking_id": "booking-12345",
      "initial_balance": 0.0
    }
  },
  {
    "log_id": "log-20250115-003",
    "timestamp": "2025-01-15T14:30:10Z",
    "user_id": "sarah-fd-001",
    "user_name": "Sarah Johnson",
    "user_role": "front_desk",
    "action": "UPDATE_ROOM_STATUS",
    "entity_type": "room",
    "entity_id": "room-205",
    "changes": {
      "old_status": "available",
      "new_status": "occupied",
      "current_booking_id": "booking-12345"
    }
  }
]
```

**Görünüm (UI):**
```
🟢 14:30:00 | CHECK_IN | Sarah Johnson (Front Desk)
   ↳ Booking ID: booking-12345
   ↳ Guest: John Smith
   ↳ Room: 205
   ↳ Folio: F-2025-00123 created
   ↳ Room status: available → occupied
```

---

### Senaryo 2: Rate Override (Yetki Aşımı Girişimi)

**Durum:** Front desk görevlisi Mike, bir rezervasyon için %25 indirim uygulamaya çalışıyor ancak yetkisi sadece %10'a kadar.

**İşlem Adımları:**
1. Mike rezervasyon oluşturuyor
2. Base rate: $200
3. %25 indirim denemesi ($150)
4. ⛔ Sistem reddediyor (yetki yok)
5. Supervisor approval request

**Audit Log Kayıtları:**

```json
[
  {
    "log_id": "log-20250115-050",
    "timestamp": "2025-01-15T16:45:00Z",
    "user_id": "mike-fd-003",
    "user_name": "Mike Davis",
    "user_role": "front_desk",
    "action": "RATE_OVERRIDE_ATTEMPT",
    "entity_type": "booking",
    "entity_id": "booking-12350",
    "status": "DENIED",
    "changes": {
      "base_rate": 200.0,
      "requested_rate": 150.0,
      "discount_percent": 25.0,
      "reason": "VIP customer request",
      "max_allowed_discount": 10.0
    },
    "security_alert": "PERMISSION_VIOLATION",
    "metadata": {
      "ip_address": "192.168.1.108",
      "terminal": "FD-Terminal-04"
    }
  },
  {
    "log_id": "log-20250115-051",
    "timestamp": "2025-01-15T16:46:00Z",
    "user_id": "mike-fd-003",
    "user_name": "Mike Davis",
    "user_role": "front_desk",
    "action": "REQUEST_APPROVAL",
    "entity_type": "approval_request",
    "entity_id": "approval-req-789",
    "changes": {
      "approval_type": "rate_override",
      "requested_from": "supervisor",
      "booking_id": "booking-12350",
      "amount": 150.0
    }
  },
  {
    "log_id": "log-20250115-052",
    "timestamp": "2025-01-15T16:50:00Z",
    "user_id": "lisa-sup-001",
    "user_name": "Lisa Chen",
    "user_role": "supervisor",
    "action": "APPROVE_RATE_OVERRIDE",
    "entity_type": "booking",
    "entity_id": "booking-12350",
    "status": "APPROVED",
    "changes": {
      "base_rate": 200.0,
      "approved_rate": 150.0,
      "approval_note": "Approved for repeat VIP guest",
      "approved_by": "lisa-sup-001"
    }
  }
]
```

**Görünüm (UI):**
```
⚠️ 16:45:00 | RATE_OVERRIDE_ATTEMPT (DENIED) | Mike Davis (Front Desk)
   ↳ Booking ID: booking-12350
   ↳ Base Rate: $200 → Requested: $150 (25% off)
   ↳ Max Allowed: 10%
   ↳ Status: PERMISSION DENIED
   
🟡 16:46:00 | APPROVAL_REQUEST | Mike Davis
   ↳ Request Type: Rate Override
   ↳ Requested From: Supervisor
   
✅ 16:50:00 | APPROVAL_GRANTED | Lisa Chen (Supervisor)
   ↳ Approved Rate: $150
   ↳ Note: "Approved for repeat VIP guest"
```

---

### Senaryo 3: Charge Void (İade İşlemi)

**Durum:** Muhasebe departmanından Emily, yanlış postalanmış bir minibar charge'ı iptal ediyor.

**İşlem Adımları:**
1. Folio'da charge bulundu
2. Void reason girildi
3. Manager approval (>$50)
4. Charge void edildi
5. Balance yeniden hesaplandı

**Audit Log Kayıtları:**

```json
[
  {
    "log_id": "log-20250115-100",
    "timestamp": "2025-01-15T11:20:00Z",
    "user_id": "emily-acc-001",
    "user_name": "Emily Rodriguez",
    "user_role": "finance",
    "action": "VOID_CHARGE",
    "entity_type": "folio_charge",
    "entity_id": "charge-987654",
    "changes": {
      "charge_category": "minibar",
      "charge_amount": 75.50,
      "void_reason": "Posted to wrong room - Guest dispute",
      "voided_by": "emily-acc-001",
      "voided_at": "2025-01-15T11:20:00Z",
      "folio_id": "folio-F-2025-00089"
    },
    "metadata": {
      "original_posting": {
        "posted_by": "sarah-fd-001",
        "posted_at": "2025-01-14T22:15:00Z"
      },
      "approval_required": true,
      "approval_threshold": 50.0
    }
  },
  {
    "log_id": "log-20250115-101",
    "timestamp": "2025-01-15T11:20:05Z",
    "user_id": "emily-acc-001",
    "user_name": "Emily Rodriguez",
    "user_role": "finance",
    "action": "FOLIO_BALANCE_UPDATE",
    "entity_type": "folio",
    "entity_id": "folio-F-2025-00089",
    "changes": {
      "old_balance": 425.50,
      "new_balance": 350.00,
      "adjustment_amount": -75.50,
      "adjustment_reason": "Charge void - minibar charge-987654"
    }
  }
]
```

**Görünüm (UI):**
```
🔴 11:20:00 | VOID_CHARGE | Emily Rodriguez (Finance)
   ↳ Folio: F-2025-00089
   ↳ Charge: Minibar - $75.50
   ↳ Reason: "Posted to wrong room - Guest dispute"
   ↳ Originally posted by: Sarah Johnson (2025-01-14 22:15)
   ↳ Balance: $425.50 → $350.00
   
💡 Tip: Charge >$50 - Manager approval required
```

---

### Senaryo 4: Toplu Check-out (Night Audit)

**Durum:** Night auditor Alex, gün sonu işlemlerini gerçekleştiriyor.

**İşlem Adımları:**
1. Night audit başlatıldı
2. Room charges posted (15 oda)
3. Due out check-outs (8 misafir)
4. Reports generated
5. Audit closed

**Audit Log Kayıtları:**

```json
[
  {
    "log_id": "log-20250116-001",
    "timestamp": "2025-01-16T02:00:00Z",
    "user_id": "alex-na-001",
    "user_name": "Alex Turner",
    "user_role": "front_desk",
    "action": "NIGHT_AUDIT_START",
    "entity_type": "system",
    "entity_id": "night-audit-20250115",
    "changes": {
      "audit_date": "2025-01-15",
      "business_date": "2025-01-15",
      "occupied_rooms": 35,
      "arrivals": 12,
      "departures": 8
    }
  },
  {
    "log_id": "log-20250116-002",
    "timestamp": "2025-01-16T02:05:00Z",
    "user_id": "alex-na-001",
    "user_name": "Alex Turner",
    "user_role": "front_desk",
    "action": "POST_ROOM_CHARGES",
    "entity_type": "bulk_operation",
    "entity_id": "bulk-op-001",
    "changes": {
      "operation_type": "room_charge_posting",
      "bookings_processed": 15,
      "charges_posted": 15,
      "total_amount": 2850.00,
      "failed_postings": 0
    },
    "details": [
      {"booking_id": "booking-12345", "room": "205", "amount": 200.00},
      {"booking_id": "booking-12346", "room": "301", "amount": 180.00}
      // ... 13 more entries
    ]
  },
  {
    "log_id": "log-20250116-003",
    "timestamp": "2025-01-16T02:30:00Z",
    "user_id": "alex-na-001",
    "user_name": "Alex Turner",
    "user_role": "front_desk",
    "action": "NIGHT_AUDIT_COMPLETE",
    "entity_type": "system",
    "entity_id": "night-audit-20250115",
    "changes": {
      "status": "completed",
      "duration_minutes": 30,
      "room_revenue": 2850.00,
      "total_revenue": 4250.00,
      "occupancy_rate": 87.5
    }
  }
]
```

**Görünüm (UI):**
```
🌙 02:00:00 | NIGHT_AUDIT_START | Alex Turner (Night Auditor)
   ↳ Audit Date: 2025-01-15
   ↳ Occupied Rooms: 35
   ↳ Arrivals: 12 | Departures: 8
   
💰 02:05:00 | POST_ROOM_CHARGES | Alex Turner
   ↳ Bookings Processed: 15
   ↳ Charges Posted: 15
   ↳ Total Amount: $2,850.00
   ↳ Failed: 0
   
✅ 02:30:00 | NIGHT_AUDIT_COMPLETE | Alex Turner
   ↳ Duration: 30 minutes
   ↳ Room Revenue: $2,850.00
   ↳ Total Revenue: $4,250.00
   ↳ Occupancy: 87.5%
```

---

### Senaryo 5: Güvenlik İhlali Girişimi (Failed Login)

**Durum:** Bilinmeyen bir IP adresinden sürekli başarısız login denemeleri.

**İşlem Adımları:**
1. 5 başarısız login denemesi
2. Account otomatik kilitleme
3. Security alert gönderildi
4. IT notification

**Audit Log Kayıtları:**

```json
[
  {
    "log_id": "log-20250115-200",
    "timestamp": "2025-01-15T03:15:10Z",
    "user_id": null,
    "user_name": null,
    "user_role": null,
    "action": "LOGIN_FAILED",
    "entity_type": "authentication",
    "entity_id": "login-attempt-001",
    "status": "FAILED",
    "changes": {
      "attempt_number": 1,
      "email": "admin@test.com",
      "failure_reason": "Invalid password"
    },
    "security_alert": "LOGIN_FAILURE",
    "metadata": {
      "ip_address": "203.45.12.88",
      "user_agent": "Mozilla/5.0...",
      "location": "Unknown"
    }
  },
  // ... 4 more failed attempts ...
  {
    "log_id": "log-20250115-205",
    "timestamp": "2025-01-15T03:15:50Z",
    "user_id": null,
    "user_name": null,
    "user_role": null,
    "action": "ACCOUNT_LOCKED",
    "entity_type": "security",
    "entity_id": "admin@test.com",
    "status": "LOCKED",
    "changes": {
      "lock_reason": "Too many failed login attempts",
      "failed_attempts": 5,
      "lock_duration_minutes": 30,
      "unlock_at": "2025-01-15T03:45:50Z"
    },
    "security_alert": "CRITICAL_SECURITY_EVENT",
    "metadata": {
      "ip_address": "203.45.12.88",
      "ip_blocked": true,
      "notification_sent": true,
      "notification_recipients": ["security@hotel.com", "it@hotel.com"]
    }
  }
]
```

**Görünüm (UI):**
```
🚨 03:15:10 | LOGIN_FAILED (1/5) | Unknown User
   ↳ Email: admin@test.com
   ↳ IP: 203.45.12.88
   ↳ Reason: Invalid password
   
🚨 03:15:20 | LOGIN_FAILED (2/5) | Unknown User
🚨 03:15:30 | LOGIN_FAILED (3/5) | Unknown User
🚨 03:15:40 | LOGIN_FAILED (4/5) | Unknown User
🚨 03:15:50 | LOGIN_FAILED (5/5) | Unknown User

🔒 03:15:50 | ACCOUNT_LOCKED | CRITICAL SECURITY EVENT
   ↳ Account: admin@test.com
   ↳ Reason: Too many failed attempts
   ↳ Lock Duration: 30 minutes
   ↳ Unlock at: 03:45:50
   ↳ IP Blocked: 203.45.12.88
   ↳ Notifications: Security team, IT team
```

---

## Log Arama ve Filtreleme

### UI'dan Log Arama

**Filtreler:**
```
📅 Date Range: [2025-01-10] to [2025-01-15]
👤 User: [Select User] (All, Sarah Johnson, Mike Davis...)
🏷️ Action Type: [Select Action] (All, CHECK_IN, VOID_CHARGE...)
📦 Entity Type: [Select Entity] (All, booking, folio, room...)
⚠️ Security Alerts: [Show Only] (Yes/No)
```

**Örnek Arama:**
```
Arama: "Tüm rate override işlemlerini göster (Son 7 gün)"

Filtreler:
- Date Range: Last 7 days
- Action Type: RATE_OVERRIDE, RATE_OVERRIDE_ATTEMPT
- Security Alerts: All

Sonuç: 15 kayıt bulundu
- 12 başarılı rate override
- 3 reddedilen (yetki aşımı)
```

---

### API ile Log Sorgulama

**Endpoint:** `GET /api/audit-logs`

**Örnek 1: Belirli kullanıcının tüm işlemleri**
```bash
curl -X GET "http://localhost:8001/api/audit-logs?user_id=sarah-fd-001&start_date=2025-01-15&limit=50" \
  -H "Authorization: Bearer {token}"
```

**Örnek 2: Finansal işlemler (Charge void)**
```bash
curl -X GET "http://localhost:8001/api/audit-logs?action=VOID_CHARGE&entity_type=folio_charge" \
  -H "Authorization: Bearer {token}"
```

**Örnek 3: Güvenlik olayları**
```bash
curl -X GET "http://localhost:8001/api/audit-logs?entity_type=security&start_date=2025-01-01" \
  -H "Authorization: Bearer {token}"
```

---

## Kritik Olaylar ve Alarmlar

### Otomatik Alarmlar

#### 🚨 Kritik (Immediate Action Required)

**1. Multiple Failed Login Attempts**
```
Trigger: 5 başarısız login (10 dakika içinde)
Action: Account lock, IP block, Security team notification
Log: ACCOUNT_LOCKED, CRITICAL_SECURITY_EVENT
```

**2. Unauthorized Access Attempt**
```
Trigger: Yetkisi olmayan modül erişimi
Action: Access denied, Security alert, Manager notification
Log: PERMISSION_VIOLATION, UNAUTHORIZED_ACCESS
```

**3. Large Financial Transaction**
```
Trigger: Charge void >$500 veya Payment >$5000
Action: Manager approval required, Finance notification
Log: LARGE_TRANSACTION_ALERT
```

---

#### ⚠️ Uyarı (Review Required)

**1. Unusual Activity Pattern**
```
Trigger: Aynı kullanıcıdan 1 saat içinde 50+ işlem
Action: Supervisor review
Log: UNUSUAL_ACTIVITY_PATTERN
```

**2. Off-Hours Activity**
```
Trigger: Gece 00:00-06:00 arası finansal işlem
Action: Manager review (ertesi gün)
Log: OFF_HOURS_TRANSACTION
```

**3. Rate Override Frequency**
```
Trigger: Bir kullanıcı 1 gün içinde 10+ rate override
Action: Supervisor review
Log: HIGH_OVERRIDE_FREQUENCY
```

---

### Rapor ve Analizler

**Günlük Özet Raporu (Daily Digest)**
```
📊 Audit Log Summary - 2025-01-15
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 Activity Overview:
- Total Actions: 1,247
- Unique Users: 23
- Security Alerts: 2 ⚠️

🏨 Operations:
- Check-ins: 12
- Check-outs: 8
- Reservations Created: 15
- Reservations Modified: 7
- Reservations Cancelled: 2

💰 Financial:
- Charges Posted: 145 ($8,450.00)
- Payments Posted: 67 ($12,300.00)
- Charges Voided: 3 ($175.50)
- Invoices Generated: 8

🔐 Security:
- Failed Logins: 12
- Account Locks: 1 🚨
- Permission Violations: 1 ⚠️

👥 Top Active Users:
1. Sarah Johnson (Front Desk) - 187 actions
2. Mike Davis (Front Desk) - 156 actions
3. Emily Rodriguez (Finance) - 89 actions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Best Practices

### ✅ Do's (Yapılması Gerekenler)

1. **Her kritik işleme açıklama ekleyin**
   ```
   ✅ İyi: "Void charge - Guest complaint, minibar items incorrect"
   ❌ Kötü: "Void"
   ```

2. **Düzenli log review yapın**
   - Daily: Security alerts
   - Weekly: Financial transactions
   - Monthly: User activity patterns

3. **Anormal pattern'leri rapor edin**
   - IT departmanına bildirin
   - Supervisor'e escalate edin

---

### ⛔ Don'ts (Yapılmaması Gerekenler)

1. **Logları asla silmeyin**
   - Immutable (değiştirilemez)
   - Legal requirement

2. **Başkasının hesabını kullanmayın**
   - Her işlem kişiye özel
   - Audit trail bozulur

3. **Generic reason kullanmayın**
   ```
   ❌ "Manager request"
   ✅ "GM approval - VIP guest John Smith, corporate rate extension"
   ```

---

## Yardım ve Destek

**Audit Log ile ilgili sorular:**
- IT Support: support@hotel.com
- Security Team: security@hotel.com
- Extension: 100

**Dokümantasyon güncellenme tarihi:** 15 Ocak 2025
