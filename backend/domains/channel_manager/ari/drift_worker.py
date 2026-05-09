"""
ARI Drift Worker.

Periodically compares PMS snapshot vs provider snapshot.
On mismatch: generates corrective delta → push queue.
"""
import logging
from datetime import UTC, datetime

from . import repositories as repo
from .repositories import compute_outbound_delta_hash

logger = logging.getLogger(__name__)

# Alert thresholds
CONSECUTIVE_DRIFT_ALERT = 3
WIDE_PARITY_LOSS_THRESHOLD = 5  # rooms with drift

# Field-level diff scopes we surface to the UI
_DIFF_FIELDS = ("availability", "rate", "min_stay", "max_stay", "closed", "stop_sell", "restrictions")


def _diff_fields(pms_item: dict | None, provider_item: dict | None) -> list[str]:
    """Return list of field names that differ between PMS and provider snapshot."""
    if not pms_item or not provider_item:
        return ["__missing__"]
    out: list[str] = []
    for f in _DIFF_FIELDS:
        a = pms_item.get(f)
        b = provider_item.get(f)
        if a != b:
            out.append(f)
    # Catch any nested restriction sub-fields the caller flattened
    if isinstance(pms_item.get("restrictions"), dict) and isinstance(provider_item.get("restrictions"), dict):
        ra, rb = pms_item["restrictions"], provider_item["restrictions"]
        for k in set(ra.keys()) | set(rb.keys()):
            if ra.get(k) != rb.get(k) and f"restrictions.{k}" not in out:
                out.append(f"restrictions.{k}")
    return out or ["__unknown__"]


async def check_drift(
    tenant_id: str,
    property_id: str,
    provider: str,
    pms_snapshot: list[dict],
    provider_snapshot: list[dict],
) -> dict:
    """
    Compare PMS state vs provider state and detect drift.

    pms_snapshot: list of {room_type_code, rate_plan_code, date, availability, rate, restrictions}
    provider_snapshot: same structure from provider's API

    Returns drift report.
    """
    pms_index = {}
    for item in pms_snapshot:
        key = f"{item['room_type_code']}|{item.get('rate_plan_code', '')}|{item['date']}"
        pms_index[key] = item

    provider_index = {}
    for item in provider_snapshot:
        key = f"{item['room_type_code']}|{item.get('rate_plan_code', '')}|{item['date']}"
        provider_index[key] = item

    all_keys = set(pms_index.keys()) | set(provider_index.keys())
    drifts = []
    matched = 0

    for key in all_keys:
        pms_item = pms_index.get(key)
        provider_item = provider_index.get(key)

        if not pms_item or not provider_item:
            parts = key.split("|")
            drifts.append({
                "key": key,
                "room_type_code": parts[0],
                "rate_plan_code": parts[1] if len(parts) > 1 else "",
                "date": parts[2] if len(parts) > 2 else "",
                "drift_type": "missing_in_provider" if not provider_item else "missing_in_pms",
                "drift_fields": _diff_fields(pms_item, provider_item),
                "pms_value": pms_item,
                "provider_value": provider_item,
            })
            continue

        pms_hash = compute_outbound_delta_hash(
            provider=provider,
            property_id=property_id,
            room_type_code=pms_item.get("room_type_code", ""),
            rate_plan_code=pms_item.get("rate_plan_code", ""),
            date_from=pms_item.get("date", ""),
            date_to=pms_item.get("date", ""),
            payload=pms_item,
        )
        provider_hash = compute_outbound_delta_hash(
            provider=provider,
            property_id=property_id,
            room_type_code=provider_item.get("room_type_code", ""),
            rate_plan_code=provider_item.get("rate_plan_code", ""),
            date_from=provider_item.get("date", ""),
            date_to=provider_item.get("date", ""),
            payload=provider_item,
        )

        if pms_hash != provider_hash:
            parts = key.split("|")
            drifts.append({
                "key": key,
                "room_type_code": parts[0],
                "rate_plan_code": parts[1] if len(parts) > 1 else "",
                "date": parts[2] if len(parts) > 2 else "",
                "drift_type": "value_mismatch",
                "drift_fields": _diff_fields(pms_item, provider_item),
                "pms_hash": pms_hash,
                "provider_hash": provider_hash,
                "pms_value": pms_item,
                "provider_value": provider_item,
            })
        else:
            matched += 1

    # Update drift state in DB
    for drift in drifts:
        await repo.upsert_drift_state({
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "room_type_code": drift["room_type_code"],
            "rate_plan_code": drift.get("rate_plan_code", ""),
            "date_from": drift.get("date", ""),
            "date_to": drift.get("date", ""),
            "pms_hash": drift.get("pms_hash", ""),
            "provider_hash": drift.get("provider_hash", ""),
            "drift_detected": True,
            "drift_type": drift["drift_type"],
            "drift_fields": drift.get("drift_fields", []),
        })

    # Mark non-drifting items as reconciled
    drift_keys = {d["key"] for d in drifts}
    for key in all_keys - drift_keys:
        parts = key.split("|")
        pms_item = pms_index.get(key, {})
        provider_item = provider_index.get(key, {})
        await repo.upsert_drift_state({
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "room_type_code": parts[0],
            "rate_plan_code": parts[1] if len(parts) > 1 else "",
            "date_from": parts[2] if len(parts) > 2 else "",
            "date_to": parts[2] if len(parts) > 2 else "",
            "pms_hash": compute_outbound_delta_hash(
                provider=provider, property_id=property_id,
                room_type_code=parts[0],
                rate_plan_code=parts[1] if len(parts) > 1 else "",
                date_from=parts[2] if len(parts) > 2 else "",
                date_to=parts[2] if len(parts) > 2 else "",
                payload=pms_item,
            ),
            "provider_hash": compute_outbound_delta_hash(
                provider=provider, property_id=property_id,
                room_type_code=parts[0],
                rate_plan_code=parts[1] if len(parts) > 1 else "",
                date_from=parts[2] if len(parts) > 2 else "",
                date_to=parts[2] if len(parts) > 2 else "",
                payload=provider_item,
            ),
            "drift_detected": False,
            "last_reconciled_at": datetime.now(UTC).isoformat(),
        })

    # Generate alerts
    alerts = []
    if len(drifts) >= WIDE_PARITY_LOSS_THRESHOLD:
        alerts.append({
            "level": "critical",
            "message": f"Wide parity loss: {len(drifts)} items drifted for {provider}/{property_id}",
        })

    report = {
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": provider,
        "total_checked": len(all_keys),
        "matched": matched,
        "drifts_found": len(drifts),
        "drifts": drifts[:50],  # limit response size
        "alerts": alerts,
        "checked_at": datetime.now(UTC).isoformat(),
    }

    logger.info(
        f"Drift check: {provider}/{property_id} — "
        f"{matched} matched, {len(drifts)} drifts"
    )
    return report


async def reconcile_drift(
    tenant_id: str,
    property_id: str,
    provider: str,
) -> dict:
    """
    Generate corrective change sets for detected drifts.
    These will be picked up by the push worker.
    """
    drift_states = await repo.get_drift_states(
        tenant_id, property_id, provider, drift_only=True, limit=100
    )

    corrective_count = 0
    for ds in drift_states:
        # Create a corrective change set from PMS truth
        cs = {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "coalescing_key": f"{tenant_id}|{property_id}|{provider}|{ds['room_type_code']}|{ds.get('rate_plan_code', '')}|{ds['date_from']}:{ds['date_to']}|corrective",
            "room_type_code": ds["room_type_code"],
            "rate_plan_code": ds.get("rate_plan_code"),
            "date_from": ds["date_from"],
            "date_to": ds["date_to"],
            "change_scope": "availability",  # will need to detect actual scope
            "compacted_payload": ds.get("pms_value", {}),
            "provider_delta_hash": ds.get("pms_hash", ""),
        }
        await repo.upsert_change_set(cs)
        corrective_count += 1

    logger.info(f"Drift reconcile: generated {corrective_count} corrective change sets for {provider}/{property_id}")
    return {
        "corrective_change_sets": corrective_count,
        "provider": provider,
        "property_id": property_id,
    }
