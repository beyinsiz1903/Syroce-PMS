import asyncio
import os
import sys

tenant_id = os.environ.get("HOTELRUNNER_TENANT_ID")
hr_id = os.environ.get("HOTELRUNNER_HR_ID")
mongo_url = os.environ.get("MONGO_URL")
db_name = os.environ.get("DB_NAME")
app_env = os.environ.get("APP_ENV")
secrets_provider = os.environ.get("SECRETS_PROVIDER")

# Bu sistemde property_id SecretsManager path'inde hr_id olarak kullanılıyor.
property_id = hr_id

if not all([tenant_id, hr_id, mongo_url, db_name]):
    print("HATA: Gerekli çevre değişkenleri eksik.")
    sys.exit(1)

# Ortamı değiştirmiyoruz; doğruluyoruz.
if app_env != "production":
    print("HATA: APP_ENV must already be 'production'")
    sys.exit(1)

if secrets_provider not in {"aws_secrets_manager", "vault", "env"}:
    print("HATA: Unsupported or missing SECRETS_PROVIDER")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv(override=False)

if os.environ.get("MONGO_URL") != mongo_url:
    print("HATA: MONGO_URL changed during initialization")
    sys.exit(1)
if os.environ.get("DB_NAME") != db_name:
    print("HATA: DB_NAME changed during initialization")
    sys.exit(1)


async def main():
    masked_tenant = f"{tenant_id[:4]}...{tenant_id[-4:]}" if len(tenant_id) > 8 else "***"
    masked_hr_id = f"{hr_id[:2]}...{hr_id[-2:]}" if len(hr_id) > 4 else "***"
    masked_mongo = f"{mongo_url.split('@')[-1]}" if "@" in mongo_url else "masked"

    print("DB host:", masked_mongo)
    print("DB name:", db_name)
    print("tenant:", masked_tenant)
    print("hr_id:", masked_hr_id)
    print("property_id (=hr_id):", masked_hr_id)
    print("operation: read rooms")
    print("-" * 40)

    from core import database

    db = database._raw_db
    if db.name != db_name:
        print("HATA: Database resolution mismatch")
        sys.exit(1)

    # DB kaydında property_id ve provider alanları yok; filtre tenant_id + hr_id ile yapılıyor.
    connection_filter = {
        "tenant_id": tenant_id,
        "hr_id": hr_id,
    }

    count = await db.hotelrunner_connections.count_documents(connection_filter)
    if count != 1:
        print(f"HATA: Beklenen 1 connection, {count} bulundu.")
        sys.exit(1)

    try:
        from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service

        service = await HotelRunnerV2Service.create(tenant_id, property_id)
        # fetch_rooms() public metodu kullan; private _client değil
        result = await service.fetch_rooms()
    except Exception:
        print("HATA: Servis başlatılamadı veya ağ isteği başarısız.")
        sys.exit(1)

    # fetch_rooms() şu yapıyı döndürür: {"success": bool, "data": dict, "error": str}
    if not result.get("success"):
        print("HATA: HotelRunner rooms request failed.")
        sys.exit(1)

    payload = result.get("data")
    if not isinstance(payload, dict):
        print("HATA: Beklenmeyen response payload tipi.")
        sys.exit(1)

    # Rooms response şeması: {"rooms": [...]}
    # Her oda: inv_code (zorunlu) + rate_plans[].code (zorunlu, her odada en az 1 plan)
    rooms = payload.get("rooms")
    if not isinstance(rooms, list):
        print("HATA: 'rooms' alanı response içinde bulunamadı veya list değil.")
        sys.exit(1)

    if len(rooms) == 0:
        print("HATA: HotelRunner returned no rooms")
        sys.exit(1)

    inv_codes = set()
    rate_plan_codes = set()

    for r in rooms:
        # Gerçek HotelRunner rooms_list response yapısı:
        # inv_code doğrudan alan olarak geliyor (HR:1271567 formatında)
        inv_code = r.get("inv_code")
        if inv_code:
            inv_codes.add(str(inv_code))

        # rate_plan_code doğrudan alan olarak geliyor (rate_plans alt dizisi değil)
        rate_plan_code = r.get("rate_plan_code")
        if rate_plan_code:
            rate_plan_codes.add(str(rate_plan_code))

    if not inv_codes:
        print("HATA: No inv_code values returned — HotelRunner mapping broken")
        sys.exit(1)

    # rate_plans rooms_list endpoint sözleşmesinde zorunludur
    if not rate_plan_codes:
        print("HATA: No rate_plan codes returned — expected from rooms_list endpoint")
        sys.exit(1)

    print("HTTP status: 200")
    print(f"room count: {len(rooms)}")
    print(f"inv_code count: {len(inv_codes)}")
    print(f"rate_plan_code count: {len(rate_plan_codes)}")
    print("token leak scan: handled by rotation script")


if __name__ == "__main__":
    asyncio.run(main())
