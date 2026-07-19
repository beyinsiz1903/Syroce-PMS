import logging
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, HTTPException, Request

from core.tenant_db import get_system_db
from core.security import JWT_ALGORITHM, JWT_SECRET

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/access-control", tags=["IoT Access Control"])

# Basit bir cihaz doğrulama token'ı (ESP32 için sabit bir şifre)
# Gerçekte bunu DB'den alabiliriz ama şimdilik hızlı prototip için sabit
IOT_DEVICE_SECRET = "super_secret_esp32_token_2026"

@router.post("/verify")
async def verify_qr_access(request: Request):
    """
    ESP32'den gelen QR kodu doğrular ve kapıyı açıp açmamaya karar verir.
    """
    # 1. Cihaz Yetkilendirmesi (Cihazın kendi token'ı var mı?)
    device_token = request.headers.get("x-device-token")
    if device_token != IOT_DEVICE_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized IoT Device")

    try:
        body = await request.json()
        qr_data = body.get("qr_data")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not qr_data:
        raise HTTPException(status_code=400, detail="Missing qr_data")

    # 2. QR Kodunun Çözülmesi ve Geçerliliğinin Kontrolü
    try:
        # JWT token'ı decode etmeye çalışalım
        payload = jwt.decode(qr_data, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        booking_id = payload.get("booking_id")

        if not booking_id:
            logger.warning("QR Code is valid JWT but missing booking_id")
            return {"action": "deny", "reason": "invalid_payload"}

        # 3. Veritabanından Booking kontrolü
        db = get_system_db()
        booking = await db.bookings.find_one({"id": booking_id})

        if not booking:
            return {"action": "deny", "reason": "booking_not_found"}

        # Misafirin şu an otelde kalıp kalmadığını kontrol edelim
        # (Status 'inhouse' veya check-in yapmış olması lazım)
        if booking.get("status") not in ["inhouse", "checked_in"]:
            return {"action": "deny", "reason": "not_checked_in"}

        # Geçiş Başarılı!
        logger.info(f"Access GRANTED for booking_id: {booking_id}")

        # Geçiş logu oluştur (Opsiyonel)
        await db.access_logs.insert_one({
            "booking_id": booking_id,
            "device": "main_door_qr",
            "action": "granted",
            "timestamp": datetime.now(UTC)
        })

        return {"action": "grant", "message": "Access Granted"}

    except jwt.ExpiredSignatureError:
        logger.warning("Expired QR Code scanned")
        return {"action": "deny", "reason": "expired"}
    except jwt.InvalidTokenError:
        logger.warning("Invalid QR Code scanned")
        return {"action": "deny", "reason": "invalid_qr"}
    except Exception as e:
        logger.error(f"Error processing QR: {e}")
        return {"action": "deny", "reason": "server_error"}
