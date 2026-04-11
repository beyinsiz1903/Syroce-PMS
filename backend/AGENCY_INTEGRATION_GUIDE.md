# Agency Booking Request System - Entegrasyon Rehberi

## 📦 OLUŞTURULAN DOSYALAR

1. `/app/backend/agency_models.py` - Pydantic modelleri
2. `/app/backend/agency_endpoints.py` - API endpoints
3. `/app/backend/AGENCY_INTEGRATION_GUIDE.md` - Bu dosya

---

## 🔧 ENTEGRASYON ADIMLARI

### Adım 1: server.py'ye Import Ekle

**Konum:** server.py, satır ~110 civarı (diğer import'lardan sonra)

```python
# Import agency booking request endpoints
try:
    from agency_endpoints import agency_router
    print("✅ Agency booking request endpoints imported successfully")
except ImportError as e:
    print(f"⚠️ Agency endpoints not available: {e}")
    agency_router = None
```

### Adım 2: Router'ı FastAPI'ye Ekle

**Konum:** server.py, satır ~3250 civarı (diğer router include'lardan sonra)

```python
# Include agency booking request router
if agency_router:
    app.include_router(agency_router)
```

### Adım 3: MongoDB Index'leri Oluştur (Startup Event)

**Konum:** server.py, `@app.on_event("startup")` fonksiyonuna ekle

```python
@app.on_event("startup")
async def startup_event():
    # Existing indexes...
    
    # Agency booking requests indexes
    try:
        col = db.agency_booking_requests
        await col.create_index([("idempotency_key", 1)], unique=True, name="uniq_idempotency_key")
        await col.create_index([("status", 1), ("hotel_id", 1)], name="idx_status_hotel")
        await col.create_index([("agency_id", 1), ("status", 1)], name="idx_agency_status")
        await col.create_index([("expires_at", 1)], name="idx_expires_at")
        await col.create_index([("created_at", -1)], name="idx_created_at_desc")
        print("✅ Agency booking request indexes created")
    except Exception as e:
        print(f"⚠️ Agency indexes error: {e}")
```

---

## 🔌 HELPER FONKSIYONLARI BAĞLAMA

### TODO 1: Availability Check

**Dosya:** `agency_endpoints.py`  
**Fonksiyon:** `compute_soft_availability_and_restrictions()`

**Ne yapmalısın:**
Mevcut availability helper'ını buraya bağla. Örnek:

```python
async def compute_soft_availability_and_restrictions(db, hotel_id, room_type_id, check_in, check_out):
    # Senin mevcut fonksiyonun - örnek:
    from booking_availability import check_availability_soft  # veya server.py'den import
    from server import get_restrictions_from_rate_periods  # veya benzeri
    
    available = await check_availability_soft(db, hotel_id, room_type_id, check_in, check_out)
    restrictions = await get_restrictions_from_rate_periods(db, hotel_id, room_type_id, check_in, check_out)
    
    return available, restrictions
```

### TODO 2: Pricing Calculation

**Dosya:** `agency_endpoints.py`  
**Fonksiyon:** `compute_price_snapshot()`

**Ne yapmalısın:**
Mevcut rate_periods helper'ını buraya bağla:

```python
async def compute_price_snapshot(db, hotel_id, room_type_id, rate_plan_id, check_in, check_out):
    # Senin mevcut rate hesaplama fonksiyonun
    # server.py'de rate_periods'tan fiyat okuyan kısım var
    
    ci = datetime.fromisoformat(check_in)
    co = datetime.fromisoformat(check_out)
    nights = (co - ci).days
    
    # Mevcut rate_periods logic'ini kullan
    periods = await db.rate_periods.find({
        "hotel_id": hotel_id,
        "room_type_id": room_type_id,
        "rate_plan_id": rate_plan_id,
        "start_date": {"$lte": check_out},
        "end_date": {"$gte": check_in}
    }).to_list(100)
    
    # Calculate average or per-night rates
    # ... senin mevcut logic
    
    return price_per_night, total_price, currency, nights
```

### TODO 3: Commission Link

**Dosya:** `agency_endpoints.py`  
**Fonksiyon:** `get_commission_pct_for_link()`

**Ne yapmalısın:**
Agency-Hotel link collection'ı ekle (optional - ilk sprint'te sabit 15% yeterli):

```python
async def get_commission_pct_for_link(db, agency_id, hotel_id):
    # İlk MVP'de sabit döndürebilirsin:
    return 15.0
    
    # İleride agency_hotel_links collection eklenirse:
    # link = await db.agency_hotel_links.find_one({"agency_id": agency_id, "hotel_id": hotel_id})
    # return link.get("commission_pct_default", 15.0) if link else 15.0
```

---

## 🔐 AUTH ENTEGRASYONU

### User Model'e `agency_id` Ekle (Optional)

**Konum:** server.py, `class User(BaseModel):`

```python
class User(BaseModel):
    id: str
    tenant_id: Optional[str] = None  # Hotel için
    agency_id: Optional[str] = None  # Agency için - YENİ
    email: EmailStr
    name: str
    role: UserRole
    # ... rest
```

### Endpoint'lerdeki Auth Yorumlarını Aç

**Dosya:** `agency_endpoints.py`

Her endpoint'te şu satırları uncomment et:

```python
# current_user: User = Depends(get_current_user)  # Uncomment after integration
```

Sonra auth logic'ini aktive et:

```python
# Agency endpoints için:
if current_user.role not in ["AGENCY_ADMIN", "AGENCY_AGENT"]:
    raise HTTPException(403, "Agency role required")
agency_id = current_user.agency_id or current_user.tenant_id
user_id = current_user.id

# Hotel endpoints için:
if current_user.role not in ["ADMIN", "SUPERVISOR", "FRONT_DESK"]:
    raise HTTPException(403, "Hotel role required")
hotel_id = current_user.tenant_id
user_id = current_user.id
```

---

## ✅ TEST ETME

### 1. Server'ı Başlat

```bash
cd /app/backend
sudo supervisorctl restart backend
```

### 2. Index'lerin Oluştuğunu Kontrol Et

```bash
# Mongo shell'den:
use your_db_name
db.agency_booking_requests.getIndexes()
```

### 3. Endpoint'leri Test Et

```bash
# Create request (idempotent)
curl -X POST http://localhost:8001/api/agency/booking-requests \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "hotel_id": "hotel-uuid",
    "room_type_id": "deluxe",
    "rate_plan_id": "standard",
    "check_in": "2026-01-10",
    "check_out": "2026-01-12",
    "adults": 2,
    "customer_name": "Ali Veli",
    "customer_phone": "+905551234567"
  }'

# List hotel requests
curl http://localhost:8001/api/hotel/booking-requests \
  -H "Authorization: Bearer HOTEL_TOKEN"

# Approve
curl -X POST http://localhost:8001/api/hotel/booking-requests/{request_id}/approve \
  -H "Authorization: Bearer HOTEL_TOKEN"

# Reject
curl -X POST http://localhost:8001/api/hotel/booking-requests/{request_id}/reject \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer HOTEL_TOKEN" \
  -d '{"reason": "Price mismatch"}'
```

---

## 📋 ENTEGRASYON CHECKLIST

- [ ] `agency_models.py` ve `agency_endpoints.py` dosyaları backend'e kopyalandı
- [ ] server.py'ye import eklendi
- [ ] Router app'e include edildi
- [ ] MongoDB indexes oluşturuldu (startup event)
- [ ] `compute_soft_availability_and_restrictions()` gerçek fonksiyona bağlandı
- [ ] `compute_price_snapshot()` gerçek rate logic'e bağlandı
- [ ] `get_commission_pct_for_link()` düzenlendi (sabit 15% veya collection'dan)
- [ ] Auth yorumları açıldı ve current_user.agency_id/tenant_id eklendi
- [ ] User model'e agency_id field eklendi (optional)
- [ ] Backend restart edildi
- [ ] Test edildi (create, list, approve, reject)

---

## 🐛 SORUN GİDERME

### Import Error: "No module named agency_models"

**Çözüm:**
```bash
cd /app/backend
python -c "import agency_models"  # Test import
```

### Duplicate Key Error: idempotency_key

**Neden:** Aynı Idempotency-Key ile 2 kez request gönderildi  
**Beklenen Davranış:** Bu NORMAL - sistem duplicate'i algılar ve mevcut request'i döner

### "No availability" - But Rooms Exist

**Neden:** `compute_soft_availability_and_restrictions()` placeholder kullanıyor  
**Çözüm:** Bu fonksiyonu gerçek availability check'e bağla (TODO 1)

### Booking Created But Request Not Updated

**Neden:** Conditional update race condition  
**Çözüm:** Approve endpoint'teki `status: {"$in": list(PENDING_STATUSES)}` conditional check zaten var

---

## 📊 DATABASE COLLECTIONS

### Yeni Collection: `agency_booking_requests`

**Örnek Document:**
```json
{
  "request_id": "uuid",
  "idempotency_key": "uuid",
  "agency_id": "uuid",
  "hotel_id": "uuid",
  "room_type_id": "deluxe",
  "rate_plan_id": "standard",
  "check_in": "2026-01-10",
  "check_out": "2026-01-12",
  "nights": 2,
  "adults": 2,
  "customer_name": "Ali Veli",
  "customer_phone": "+905551234567",
  "price_per_night": 1500.0,
  "total_price": 3000.0,
  "currency": "TRY",
  "commission_pct": 15.0,
  "commission_amount": 450.0,
  "net_to_hotel": 2550.0,
  "status": "approved",
  "booking_id": "booking-uuid",
  "created_at": "2026-01-05T10:30:00Z",
  "expires_at": "2026-01-05T11:00:00Z",
  "resolved_at": "2026-01-05T10:45:00Z",
  "audit_events": [...]
}
```

---

## 🚀 SONRAKI ADIMLAR (2. Sprint)

1. **Frontend Ekranları:**
   - Acenta: Otellerim + Arama + Talep Gönder
   - Otel: Gelen Talepler + Onay/Red

2. **Bildirimler:**
   - WhatsApp: Yeni talep geldi (otele)
   - WhatsApp: Talep onaylandı/reddedildi (acentaya)

3. **Hotel Content:**
   - `hotel_content` collection
   - PUT /api/hotel/content (description + photos)
   - GET /api/agency/hotels/{id}/content

4. **Background Job:**
   - Expire sweep (her 1 dakika - optional)

5. **Rate Limiter:**
   - Acenta per-hotel request limit (örn: 100/saat)

---

## 💡 PRO TIPS

1. **Idempotency Key Generation:**
   ```javascript
   // Client-side (React)
   import { v4 as uuidv4 } from 'uuid';
   const idempotencyKey = uuidv4();
   ```

2. **Expire Background Job (Optional):**
   ```python
   # server.py - add to celery tasks or scheduler
   async def sweep_expired_requests():
       now = iso(now_utc())
       await db.agency_booking_requests.update_many(
           {"status": {"$in": ["submitted", "hotel_review"]}, "expires_at": {"$lt": now}},
           {"$set": {"status": "expired", "status_updated_at": now, "resolved_at": now}}
       )
   ```

3. **Monitoring:**
   ```python
   # Metrics to track:
   # - Request create rate
   # - Approval rate (approved / total)
   # - Average time to approve
   # - Expire rate
   ```

---

## 📞 DESTEK

Bu entegrasyon ile ilgili sorularınız için:
- Kod içi TODOs'lara bakın
- Test endpoint'leri yukarıdaki örneklerle deneyin
- Auth ve availability helper'larını kendi implementasyonunuza uyarlayın

**Başarılar!** 🎉
