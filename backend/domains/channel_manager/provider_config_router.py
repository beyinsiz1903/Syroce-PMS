"""
Channel Manager — Provider Configuration & Validation Router
==============================================================

Endpoints for:
- Credential management (store, view masked, delete)
- Automated provider validation (connection, discovery, readiness)
- Provider overview with health status

Prefix: /api/channel-manager/config/
"""
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User

from . import credential_vault as vault
from . import unified_repository as repo
from .data_model import (
    COLL_PROVIDER_CONNECTIONS,
    COLL_RATE_PLAN_MAPPINGS,
    COLL_ROOM_MAPPINGS,
    ConnectionStatus,
    ConnectorProvider,
    ProviderConnection,
)

logger = logging.getLogger("channel_manager.provider_config_router")

router = APIRouter(
    prefix="/api/channel-manager/config",
    tags=["Channel Manager — Provider Config"],
)

_NO_ID = {"_id": 0}

# ── Provider field definitions ────────────────────────────────────────

PROVIDER_FIELDS = {
    "hotelrunner": {
        "display_name": "HotelRunner",
        "fields": [
            {"key": "token", "label": "API Token", "type": "password", "required": True},
            {"key": "hr_id", "label": "HR ID (Hotel ID)", "type": "text", "required": True},
        ],
        "docs_url": "https://developers.hotelrunner.com/custom-apps/rest-api",
    },
    "exely": {
        "display_name": "Exely",
        "fields": [
            {"key": "username", "label": "SOAP Username", "type": "text", "required": True},
            {"key": "password", "label": "SOAP Password", "type": "password", "required": True},
            {"key": "hotel_code", "label": "Hotel Code", "type": "text", "required": True},
            {"key": "endpoint_url", "label": "SOAP Endpoint URL", "type": "text", "required": False},
        ],
        "docs_url": "https://www.exely.com/en/ota-api",
    },
}

VALIDATION_CHECKS = {
    "hotelrunner": [
        "connection_test", "room_list", "rate_plan_list", "reservation_pull",
    ],
    "exely": [
        "connection_test", "room_discovery", "reservation_pull",
    ],
}


# ── Request/Response Models ───────────────────────────────────────────

class SaveCredentialsRequest(BaseModel):
    credentials: dict[str, str]
    property_id: str = ""


class ValidationResult(BaseModel):
    check: str
    status: str  # passed, failed, skipped
    message: str
    duration_ms: int = 0
    data: dict[str, Any] | None = None


# ── Provider Overview ─────────────────────────────────────────────────

@router.get("/providers")
async def get_providers_overview(
    current_user: User = Depends(get_current_user),
):
    """Get overview of all provider configurations with health status."""
    tenant_id = current_user.tenant_id
    providers_out = []

    for provider_key, provider_def in PROVIDER_FIELDS.items():
        # Check if credentials exist
        masked = await vault.get_masked_credentials(tenant_id, provider_key, "")
        has_credentials = masked is not None

        # Get connection
        conn = await db[COLL_PROVIDER_CONNECTIONS].find_one(
            {"tenant_id": tenant_id, "provider": provider_key},
            _NO_ID,
        )

        # Count mappings
        room_count = await db[COLL_ROOM_MAPPINGS].count_documents(
            {"tenant_id": tenant_id, "provider": provider_key},
        )
        rate_count = await db[COLL_RATE_PLAN_MAPPINGS].count_documents(
            {"tenant_id": tenant_id, "provider": provider_key},
        )

        providers_out.append({
            "provider": provider_key,
            "display_name": provider_def["display_name"],
            "docs_url": provider_def["docs_url"],
            "fields": provider_def["fields"],
            "has_credentials": has_credentials,
            "credentials": masked,
            "connection": {
                "id": conn.get("id", "") if conn else "",
                "status": conn.get("status", "not_configured") if conn else "not_configured",
                "last_successful_sync": conn.get("last_successful_sync") if conn else None,
                "last_error": conn.get("last_error") if conn else None,
                "consecutive_failures": conn.get("consecutive_failures", 0) if conn else 0,
            },
            "mappings": {
                "rooms": room_count,
                "rate_plans": rate_count,
            },
            "validation_checks": VALIDATION_CHECKS.get(provider_key, []),
        })

    return {"providers": providers_out}


# ── Credential Management ─────────────────────────────────────────────

@router.post("/providers/{provider}/credentials")
async def save_credentials(
    provider: str,
    req: SaveCredentialsRequest,
    current_user: User = Depends(get_current_user),
):
    """Save encrypted provider credentials and create/update connection."""
    if provider not in PROVIDER_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    tenant_id = current_user.tenant_id
    property_id = req.property_id or "default"

    # Validate required fields
    provider_def = PROVIDER_FIELDS[provider]
    for field in provider_def["fields"]:
        if field["required"] and not req.credentials.get(field["key"]):
            raise HTTPException(
                status_code=400,
                detail=f"Required field missing: {field['label']}",
            )

    # Store encrypted credentials
    secret_id = await vault.store_secret(tenant_id, provider, property_id, req.credentials)

    # Ensure a provider_connection exists
    existing_conn = await db[COLL_PROVIDER_CONNECTIONS].find_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
        _NO_ID,
    )
    if not existing_conn:
        conn = ProviderConnection(
            tenant_id=tenant_id,
            property_id=property_id,
            provider=ConnectorProvider(provider),
            status=ConnectionStatus.DRAFT,
            display_name=f"{provider_def['display_name']} - {property_id}",
            credentials=req.credentials,
            credentials_ref=secret_id,
        )
        conn_doc = conn.to_doc()
        conn_doc["credentials_ref"] = secret_id
        await repo.upsert_connection(conn_doc)
    else:
        # Update credentials on connection + set credentials_ref
        await db[COLL_PROVIDER_CONNECTIONS].update_one(
            {"tenant_id": tenant_id, "provider": provider, "property_id": property_id},
            {"$set": {
                "credentials": req.credentials,
                "credentials_ref": secret_id,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
        )

    return {
        "success": True,
        "secret_id": secret_id,
        "provider": provider,
        "message": f"{provider_def['display_name']} credentials saved successfully",
    }


@router.get("/providers/{provider}/credentials")
async def get_credentials(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Get masked credentials for display."""
    if provider not in PROVIDER_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    masked = await vault.get_masked_credentials(current_user.tenant_id, provider, "")
    if not masked:
        masked = await vault.get_masked_credentials(current_user.tenant_id, provider, "default")
    return {"credentials": masked}


@router.delete("/providers/{provider}/credentials")
async def delete_credentials(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Delete stored credentials."""
    if provider not in PROVIDER_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    deleted = await vault.delete_secret(current_user.tenant_id, provider, "")
    if not deleted:
        deleted = await vault.delete_secret(current_user.tenant_id, provider, "default")
    return {"success": deleted, "provider": provider}


# ── Validation Endpoints ──────────────────────────────────────────────

@router.post("/providers/{provider}/validate")
async def run_full_validation(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Run the complete automated validation checklist for a provider."""
    if provider not in PROVIDER_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    tenant_id = current_user.tenant_id
    results: list[dict[str, Any]] = []

    # Get credentials
    creds = await vault.get_decrypted_credentials(tenant_id, provider, "default")
    if not creds:
        creds = await vault.get_decrypted_credentials(tenant_id, provider, "")
    if not creds:
        # Try from connection directly
        conn = await db[COLL_PROVIDER_CONNECTIONS].find_one(
            {"tenant_id": tenant_id, "provider": provider}, _NO_ID,
        )
        if conn:
            creds = conn.get("credentials", {})

    if not creds:
        return {
            "provider": provider,
            "overall_status": "no_credentials",
            "results": [{
                "check": "credentials",
                "status": "failed",
                "message": "No credentials configured. Please save credentials first.",
                "duration_ms": 0,
            }],
            "readiness": _compute_readiness([], provider, tenant_id),
        }

    if provider == "hotelrunner":
        results = await _validate_hotelrunner(creds, tenant_id)
    elif provider == "exely":
        results = await _validate_exely(creds, tenant_id)

    passed = sum(1 for r in results if r["status"] == "passed")
    total = len(results)
    overall = "passed" if passed == total else ("partial" if passed > 0 else "failed")

    # Update connection status based on results
    new_status = "active" if overall == "passed" else ("error" if overall == "failed" else "draft")
    await db[COLL_PROVIDER_CONNECTIONS].update_one(
        {"tenant_id": tenant_id, "provider": provider},
        {"$set": {
            "status": new_status,
            "last_validation_at": datetime.now(UTC).isoformat(),
            "validation_results": results,
        }},
    )

    # Get readiness
    readiness = await _compute_readiness_async(results, provider, tenant_id)

    return {
        "provider": provider,
        "overall_status": overall,
        "passed": passed,
        "total": total,
        "results": results,
        "readiness": readiness,
    }


@router.post("/providers/{provider}/test-connection")
async def test_connection(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Quick connection test for a provider."""
    tenant_id = current_user.tenant_id

    creds = await vault.get_decrypted_credentials(tenant_id, provider, "default")
    if not creds:
        creds = await vault.get_decrypted_credentials(tenant_id, provider, "")
    if not creds:
        conn = await db[COLL_PROVIDER_CONNECTIONS].find_one(
            {"tenant_id": tenant_id, "provider": provider}, _NO_ID,
        )
        if conn:
            creds = conn.get("credentials", {})

    if not creds:
        raise HTTPException(status_code=400, detail="No credentials configured")

    if provider == "hotelrunner":
        result = await _test_hotelrunner_connection(creds)
    elif provider == "exely":
        result = await _test_exely_connection(creds)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # Update connection health
    if result.get("connected"):
        await db[COLL_PROVIDER_CONNECTIONS].update_one(
            {"tenant_id": tenant_id, "provider": provider},
            {"$set": {
                "last_successful_sync": datetime.now(UTC).isoformat(),
                "consecutive_failures": 0,
                "last_error": None,
            }},
        )
    else:
        await db[COLL_PROVIDER_CONNECTIONS].update_one(
            {"tenant_id": tenant_id, "provider": provider},
            {"$set": {
                "last_error": result.get("error", "Connection failed"),
                "last_error_at": datetime.now(UTC).isoformat(),
            },
            "$inc": {"consecutive_failures": 1}},
        )

    return result


@router.get("/providers/{provider}/readiness")
async def get_readiness(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Get readiness score for a provider."""
    if provider not in PROVIDER_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    tenant_id = current_user.tenant_id

    # Get last validation results
    conn = await db[COLL_PROVIDER_CONNECTIONS].find_one(
        {"tenant_id": tenant_id, "provider": provider}, _NO_ID,
    )
    results = conn.get("validation_results", []) if conn else []

    readiness = await _compute_readiness_async(results, provider, tenant_id)
    return readiness


# ── HotelRunner Validation ────────────────────────────────────────────

async def _test_hotelrunner_connection(creds: dict[str, str]) -> dict[str, Any]:
    from .providers.hotelrunner import HotelRunnerProvider
    token = creds.get("token") or creds.get("api_key", "")
    hr_id = creds.get("hr_id") or creds.get("hotel_id", "")
    if not token or not hr_id:
        return {"connected": False, "error": "Missing token or hr_id"}
    provider = HotelRunnerProvider(token=token, hr_id=hr_id)
    result = await provider.test_connection()
    if result.success:
        return {"connected": True, **(result.data or {})}
    return {"connected": False, "error": result.error}


async def _validate_hotelrunner(creds: dict[str, str], tenant_id: str) -> list[dict[str, Any]]:
    import time

    from .providers.hotelrunner import HotelRunnerProvider

    token = creds.get("token") or creds.get("api_key", "")
    hr_id = creds.get("hr_id") or creds.get("hotel_id", "")
    results = []

    if not token or not hr_id:
        return [{"check": "connection_test", "status": "failed", "message": "Missing token or hr_id", "duration_ms": 0}]

    provider = HotelRunnerProvider(token=token, hr_id=hr_id)

    # 1. Connection test
    t0 = time.time()
    try:
        conn_result = await provider.test_connection()
        ms = int((time.time() - t0) * 1000)
        if conn_result.success:
            data = conn_result.data or {}
            results.append({
                "check": "connection_test",
                "status": "passed",
                "message": f"Connected successfully ({ms}ms latency)",
                "duration_ms": ms,
                "data": {"channels": data.get("channel_count", 0)},
            })
        else:
            results.append({
                "check": "connection_test",
                "status": "failed",
                "message": conn_result.error or "Connection failed",
                "duration_ms": ms,
            })
            return results  # No point continuing if connection fails
    except Exception as e:
        results.append({"check": "connection_test", "status": "failed", "message": str(e), "duration_ms": int((time.time() - t0) * 1000)})
        return results

    # 2. Room list
    t0 = time.time()
    try:
        rooms_result = await provider.get_rooms()
        ms = int((time.time() - t0) * 1000)
        if rooms_result.get("success"):
            rooms_data = rooms_result.get("data", {})
            room_list = rooms_data.get("rooms", [])
            results.append({
                "check": "room_list",
                "status": "passed",
                "message": f"Found {len(room_list)} rooms",
                "duration_ms": ms,
                "data": {"room_count": len(room_list), "rooms": [{"code": r.get("inv_code", ""), "name": r.get("name", "")} for r in room_list[:10]]},
            })
        else:
            results.append({"check": "room_list", "status": "failed", "message": rooms_result.get("error", "Failed to fetch rooms"), "duration_ms": ms})
    except Exception as e:
        results.append({"check": "room_list", "status": "failed", "message": str(e), "duration_ms": int((time.time() - t0) * 1000)})

    # 3. Rate plan list (via rooms endpoint — HotelRunner returns rooms with rate plans)
    t0 = time.time()
    try:
        # Rate plans come from rooms endpoint in HotelRunner
        if rooms_result.get("success"):
            rooms_data = rooms_result.get("data", {})
            room_list = rooms_data.get("rooms", [])
            rate_plans = set()
            for room in room_list:
                for rp in room.get("rate_plans", []):
                    rate_plans.add(rp.get("code") or rp.get("id", ""))
            ms = int((time.time() - t0) * 1000)
            results.append({
                "check": "rate_plan_list",
                "status": "passed",
                "message": f"Found {len(rate_plans)} rate plans",
                "duration_ms": ms,
                "data": {"rate_plan_count": len(rate_plans)},
            })
        else:
            results.append({"check": "rate_plan_list", "status": "skipped", "message": "Skipped — room list failed", "duration_ms": 0})
    except Exception as e:
        results.append({"check": "rate_plan_list", "status": "failed", "message": str(e), "duration_ms": int((time.time() - t0) * 1000)})

    # 4. Reservation pull test
    t0 = time.time()
    try:
        res_result = await provider.get_reservations(undelivered=False, per_page=5, page=1)
        ms = int((time.time() - t0) * 1000)
        if res_result.get("success"):
            data = res_result.get("data", {})
            res_count = len(data.get("reservations", []))
            total_pages = data.get("pages", 0)
            results.append({
                "check": "reservation_pull",
                "status": "passed",
                "message": f"Pull OK — {res_count} reservations (page 1 of {total_pages})",
                "duration_ms": ms,
                "data": {"sample_count": res_count, "total_pages": total_pages},
            })
        else:
            results.append({"check": "reservation_pull", "status": "failed", "message": res_result.get("error", "Failed"), "duration_ms": ms})
    except Exception as e:
        results.append({"check": "reservation_pull", "status": "failed", "message": str(e), "duration_ms": int((time.time() - t0) * 1000)})

    return results


# ── Exely Validation ──────────────────────────────────────────────────

async def _test_exely_connection(creds: dict[str, str]) -> dict[str, Any]:
    from .providers.exely import ExelyProvider
    username = creds.get("username", "")
    password = creds.get("password", "")
    hotel_code = creds.get("hotel_code") or creds.get("hotel_id", "")
    endpoint_url = creds.get("endpoint_url") or creds.get("soap_url", "")
    if not username or not password or not hotel_code:
        return {"connected": False, "error": "Missing username, password, or hotel_code"}
    kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    provider = ExelyProvider(**kwargs)
    return await provider.legacy_test_connection()


async def _validate_exely(creds: dict[str, str], tenant_id: str) -> list[dict[str, Any]]:
    import time

    from .providers.exely import ExelyProvider

    username = creds.get("username", "")
    password = creds.get("password", "")
    hotel_code = creds.get("hotel_code") or creds.get("hotel_id", "")
    endpoint_url = creds.get("endpoint_url") or creds.get("soap_url", "")
    results = []

    if not username or not password or not hotel_code:
        return [{"check": "connection_test", "status": "failed", "message": "Missing username, password, or hotel_code", "duration_ms": 0}]

    kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    provider = ExelyProvider(**kwargs)

    # 1. Connection + WSSE auth test
    t0 = time.time()
    try:
        conn_result = await provider.legacy_test_connection()
        ms = int((time.time() - t0) * 1000)
        if conn_result.get("connected"):
            room_types = conn_result.get("room_types", [])
            rate_plans = conn_result.get("rate_plans", [])
            results.append({
                "check": "connection_test",
                "status": "passed",
                "message": f"WSSE auth OK, SOAP connected ({ms}ms)",
                "duration_ms": ms,
                "data": {"room_types": len(room_types), "rate_plans": len(rate_plans)},
            })
        else:
            results.append({
                "check": "connection_test",
                "status": "failed",
                "message": conn_result.get("error", "SOAP connection failed"),
                "duration_ms": ms,
            })
            return results
    except Exception as e:
        results.append({"check": "connection_test", "status": "failed", "message": str(e), "duration_ms": int((time.time() - t0) * 1000)})
        return results

    # 2. Room discovery (OTA_HotelAvailRQ)
    t0 = time.time()
    try:
        from datetime import datetime as dt
        from datetime import timedelta
        checkin = dt.now().strftime("%Y-%m-%d")
        checkout = (dt.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        discover_result = await provider.legacy_discover_rooms(checkin, checkout)
        ms = int((time.time() - t0) * 1000)
        if discover_result.get("success"):
            room_types = discover_result.get("room_types", [])
            rate_plans = discover_result.get("rate_plans", [])
            results.append({
                "check": "room_discovery",
                "status": "passed",
                "message": f"OTA_HotelAvailRQ OK — {len(room_types)} rooms, {len(rate_plans)} rates",
                "duration_ms": ms,
                "data": {"room_types": room_types[:10], "rate_plans": rate_plans[:10]},
            })
        else:
            results.append({"check": "room_discovery", "status": "failed", "message": discover_result.get("error", "Discovery failed"), "duration_ms": ms})
    except Exception as e:
        results.append({"check": "room_discovery", "status": "failed", "message": str(e), "duration_ms": int((time.time() - t0) * 1000)})

    # 3. Reservation pull (OTA_ReadRQ)
    t0 = time.time()
    try:
        from datetime import datetime as dt
        from datetime import timedelta
        from_date = (dt.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        to_date = dt.now().strftime("%Y-%m-%d")
        pull_result = await provider.legacy_pull_reservations(from_date=from_date, to_date=to_date)
        ms = int((time.time() - t0) * 1000)
        if pull_result.get("success"):
            reservations = pull_result.get("reservations", [])
            results.append({
                "check": "reservation_pull",
                "status": "passed",
                "message": f"OTA_ReadRQ OK — {len(reservations)} reservations (last 7 days)",
                "duration_ms": ms,
                "data": {"reservation_count": len(reservations)},
            })
        else:
            results.append({"check": "reservation_pull", "status": "failed", "message": pull_result.get("error", "Pull failed"), "duration_ms": ms})
    except Exception as e:
        results.append({"check": "reservation_pull", "status": "failed", "message": str(e), "duration_ms": int((time.time() - t0) * 1000)})

    return results


# ── Readiness Calculator ──────────────────────────────────────────────

def _compute_readiness(results, provider, tenant_id):
    """Sync readiness — used when we don't need async db calls."""
    checks = {r["check"]: r["status"] for r in results}
    auth_ok = checks.get("connection_test") == "passed"
    pull_ok = checks.get("reservation_pull") == "passed"
    return {
        "auth_ok": auth_ok,
        "pull_ok": pull_ok,
        "mapping_readiness_pct": 0,
        "reservation_import_ready": auth_ok and pull_ok,
    }


async def _compute_readiness_async(results, provider, tenant_id):
    """Full readiness with mapping data from DB."""
    checks = {r["check"]: r["status"] for r in results}
    auth_ok = checks.get("connection_test") == "passed"
    pull_ok = checks.get("reservation_pull") == "passed"

    # Count mappings
    room_count = await db[COLL_ROOM_MAPPINGS].count_documents(
        {"tenant_id": tenant_id, "provider": provider},
    )
    rate_count = await db[COLL_RATE_PLAN_MAPPINGS].count_documents(
        {"tenant_id": tenant_id, "provider": provider},
    )

    # Discover how many rooms/rates the provider has
    discovered_rooms = 0
    discovered_rates = 0
    for r in results:
        if r.get("data"):
            if r["check"] in ("room_list", "room_discovery"):
                discovered_rooms = r["data"].get("room_count", r["data"].get("room_types", 0))
                if isinstance(discovered_rooms, list):
                    discovered_rooms = len(discovered_rooms)
            if r["check"] == "rate_plan_list":
                discovered_rates = r["data"].get("rate_plan_count", 0)
            if r["check"] == "room_discovery":
                rp = r["data"].get("rate_plans", 0)
                discovered_rates = len(rp) if isinstance(rp, list) else rp

    total_needed = max(discovered_rooms + discovered_rates, 1)
    mapped = room_count + rate_count
    mapping_pct = min(round((mapped / total_needed) * 100), 100) if total_needed > 0 else 0

    return {
        "auth_ok": auth_ok,
        "pull_ok": pull_ok,
        "rooms_discovered": discovered_rooms,
        "rates_discovered": discovered_rates,
        "rooms_mapped": room_count,
        "rates_mapped": rate_count,
        "mapping_readiness_pct": mapping_pct,
        "reservation_import_ready": auth_ok and pull_ok,
        "fully_ready": auth_ok and pull_ok and mapping_pct >= 80,
    }
