import logging

from domains.channel_manager.ari.provider_snapshot_contract import (
    CredentialsMissing,
    ProviderSnapshotAdapter,
    ProviderSnapshotUnavailable,
)
from domains.channel_manager.providers.hotelrunner import endpoints as ep
from domains.channel_manager.providers.hotelrunner.client import HotelRunnerHttpClient

logger = logging.getLogger("hotelrunner.snapshot_adapter")


def _parse_int(value, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError) as e:
        raise ProviderSnapshotUnavailable(f"Malformed HotelRunner field '{field_name}': expected int, got {value!r}") from e


def _parse_float(value, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError) as e:
        raise ProviderSnapshotUnavailable(f"Malformed HotelRunner field '{field_name}': expected float, got {value!r}") from e


def _parse_bool(value, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    raise ProviderSnapshotUnavailable(f"Malformed HotelRunner field '{field_name}': expected boolean-compatible value, got {value!r}")


class HotelRunnerSnapshotAdapter(ProviderSnapshotAdapter):
    async def fetch_snapshot(
        self,
        tenant_id: str,
        property_id: str,
        credentials: dict,
        *,
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        token = credentials.get("token")
        hr_id = credentials.get("hr_id")
        if not token or not hr_id:
            raise CredentialsMissing("HotelRunner credentials 'token' and 'hr_id' are required.")

        base_url = credentials.get("api_url") or ep.BASE_URL

        try:
            client = HotelRunnerHttpClient(token=token, hr_id=hr_id, base_url=base_url)
        except Exception as e:
            raise ProviderSnapshotUnavailable(f"Failed to initialize HotelRunner client: {e}") from e

        try:
            avail_res = await client.get(ep.ARI_AVAILABILITY, params={"start_date": date_from, "end_date": date_to})
            rates_res = await client.get(ep.ARI_RATES, params={"start_date": date_from, "end_date": date_to})
        except Exception as e:
            raise ProviderSnapshotUnavailable(f"HotelRunner API connection failed: {e}") from e
        finally:
            await client.close()

        if not avail_res.success or not rates_res.success:
            err_msg = avail_res.error or rates_res.error or "Unknown error pulling snapshot"
            raise ProviderSnapshotUnavailable(f"HotelRunner API returned error: {err_msg}")

        avail_data = avail_res.data
        rates_data = rates_res.data
        if not isinstance(avail_data, dict) or "availability" not in avail_data:
            raise ProviderSnapshotUnavailable("Malformed response from HotelRunner availability API.")
        if not isinstance(rates_data, dict) or "rates" not in rates_data:
            raise ProviderSnapshotUnavailable("Malformed response from HotelRunner rates API.")

        avail_map = {}
        for item in avail_data.get("availability", []):
            rc = item.get("room_code")
            dt = item.get("date")
            qty = item.get("quantity")
            if rc and dt:
                avail_map[(rc, dt)] = _parse_int(qty, "quantity")

        normalized = []
        for rate_item in rates_data.get("rates", []):
            rc = rate_item.get("room_code")
            dt = rate_item.get("date")
            rate_code = rate_item.get("rate_code")
            if not rc or not dt or not rate_code:
                continue

            normalized.append(
                {
                    "room_type_code": str(rc),
                    "rate_plan_code": str(rate_code),
                    "date": str(dt),
                    "availability": avail_map.get((rc, dt)),
                    "rate": _parse_float(rate_item.get("price"), "price"),
                    "restrictions": {
                        "min_stay_through": _parse_int(rate_item.get("min_stay"), "min_stay"),
                        "stop_sell": _parse_bool(rate_item.get("stop_sell"), "stop_sell"),
                    },
                }
            )

        if not normalized:
            raise ProviderSnapshotUnavailable("HotelRunner returned an empty ARI snapshot; refusing to clear drift state.")

        return normalized
