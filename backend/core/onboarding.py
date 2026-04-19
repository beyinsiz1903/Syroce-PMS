"""
Onboarding Automation Engine
Structured per-tenant onboarding checklist with auto-detection and progress tracking.
"""
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)

# ─── Default Onboarding Steps ───
DEFAULT_STEPS = [
    {
        "step_id": "account_created",
        "label": "Hesap olusturuldu",
        "description": "Otel hesabi ve admin kullanicisi olusturuldu",
        "category": "setup",
        "auto_detect": True,
        "order": 1,
    },
    {
        "step_id": "hotel_info_completed",
        "label": "Otel bilgileri girildi",
        "description": "Mülk adı, adres, telefon ve oda kapasitesi tamamlandı",
        "category": "setup",
        "auto_detect": False,
        "order": 1,
    },
    {
        "step_id": "rooms_configured",
        "label": "Odalar tanimlandi",
        "description": "En az 1 oda tanimlandi",
        "category": "setup",
        "auto_detect": True,
        "detect_collection": "rooms",
        "detect_min_count": 1,
        "order": 2,
    },
    {
        "step_id": "room_types_set",
        "label": "Oda tipleri ayarlandi",
        "description": "Farkli oda tipleri (single, double, suite vb.) tanimlandi",
        "category": "setup",
        "auto_detect": True,
        "detect_collection": "rooms",
        "detect_distinct_field": "room_type",
        "detect_min_count": 2,
        "order": 3,
    },
    {
        "step_id": "rates_configured",
        "label": "Fiyatlar ayarlandi",
        "description": "Oda fiyatlari ve rate planlari girildi",
        "category": "setup",
        "auto_detect": True,
        "detect_collection": "rate_plans",
        "detect_min_count": 1,
        "order": 4,
    },
    {
        "step_id": "first_guest",
        "label": "Ilk misafir kaydedildi",
        "description": "Misafir veritabanina ilk kayit eklendi",
        "category": "operations",
        "auto_detect": True,
        "detect_collection": "guests",
        "detect_min_count": 1,
        "order": 5,
    },
    {
        "step_id": "first_reservation",
        "label": "Ilk rezervasyon yapildi",
        "description": "Sistemde ilk rezervasyon olusturuldu",
        "category": "operations",
        "auto_detect": True,
        "detect_collection": "bookings",
        "detect_min_count": 1,
        "order": 6,
    },
    {
        "step_id": "team_members_added",
        "label": "Ekip uyeleri eklendi",
        "description": "En az 1 ek kullanici (resepsiyon, kat hizmetleri vb.) eklendi",
        "category": "team",
        "auto_detect": True,
        "detect_collection": "users",
        "detect_min_count": 2,
        "order": 7,
    },
    {
        "step_id": "first_checkin",
        "label": "Ilk check-in yapildi",
        "description": "Bir misafir basariyla check-in edildi",
        "category": "operations",
        "auto_detect": True,
        "detect_collection": "bookings",
        "detect_query": {"status": "checked_in"},
        "detect_min_count": 1,
        "order": 8,
    },
    {
        "step_id": "channel_manager_connected",
        "label": "Kanal yoneticisi baglandi",
        "description": "En az bir OTA kanali (Booking.com, Expedia vb.) baglandi",
        "category": "channels",
        "auto_detect": True,
        "detect_collection": "provider_configs",
        "detect_min_count": 1,
        "order": 9,
        "requires_module": "channel_manager",
    },
    {
        "step_id": "night_audit_completed",
        "label": "Ilk gece kapanisi yapildi",
        "description": "Night audit basariyla tamamlandi",
        "category": "operations",
        "auto_detect": True,
        "detect_collection": "night_audit_runs",
        "detect_min_count": 1,
        "order": 10,
        "requires_module": "night_audit",
    },
    {
        "step_id": "first_invoice",
        "label": "Ilk fatura kesildi",
        "description": "Sistem uzerinden ilk fatura olusturuldu",
        "category": "finance",
        "auto_detect": True,
        "detect_collection": "invoices",
        "detect_min_count": 1,
        "order": 11,
        "requires_module": "invoices",
    },
    {
        "step_id": "report_generated",
        "label": "Ilk rapor olusturuldu",
        "description": "Raporlama modulunden ilk rapor alindi",
        "category": "reports",
        "auto_detect": True,
        "detect_collection": "reports",
        "detect_min_count": 1,
        "order": 12,
        "requires_module": "reports",
    },
]


async def _auto_detect_step(tenant_id: str, step: dict) -> bool:
    """Auto-detect if a step is completed based on collection counts."""
    coll_name = step.get("detect_collection")
    if not coll_name:
        return False

    try:
        collection = db[coll_name]
        query = {"tenant_id": tenant_id}

        # Merge additional query conditions
        extra_q = step.get("detect_query", {})
        query.update(extra_q)

        # Check distinct field
        distinct_field = step.get("detect_distinct_field")
        if distinct_field:
            values = await collection.distinct(distinct_field, query)
            return len(values) >= step.get("detect_min_count", 1)

        count = await collection.count_documents(query)
        return count >= step.get("detect_min_count", 1)
    except Exception:
        return False


async def get_onboarding_progress(tenant_id: str) -> dict[str, Any]:
    """Get onboarding progress for a tenant. Auto-detects completed steps."""
    # Get or create progress doc
    progress = await db.onboarding_progress.find_one(
        {"tenant_id": tenant_id}, {"_id": 0}
    )

    completed_steps = {}
    if progress:
        completed_steps = progress.get("completed_steps", {})

    # Get tenant modules for filtering
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "modules": 1, "subscription_tier": 1})
    from core.helpers import get_tenant_modules
    modules = get_tenant_modules(tenant) if tenant else {}

    steps_result = []
    total = 0
    done = 0

    for step in DEFAULT_STEPS:
        # Skip steps that require modules the tenant doesn't have
        req_module = step.get("requires_module")
        if req_module and not modules.get(req_module, False):
            continue

        total += 1
        is_completed = completed_steps.get(step["step_id"], False)

        # Auto-detect if not manually completed
        if not is_completed and step.get("auto_detect"):
            is_completed = await _auto_detect_step(tenant_id, step)
            if is_completed:
                # Save auto-detected completion
                completed_steps[step["step_id"]] = True

        if is_completed:
            done += 1

        steps_result.append({
            "step_id": step["step_id"],
            "label": step["label"],
            "description": step["description"],
            "category": step["category"],
            "order": step["order"],
            "completed": is_completed,
        })

    # Update stored progress
    now = datetime.now(UTC).isoformat()
    await db.onboarding_progress.update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {
                "completed_steps": completed_steps,
                "total_steps": total,
                "completed_count": done,
                "progress_pct": round((done / total * 100) if total > 0 else 0),
                "updated_at": now,
            },
            "$setOnInsert": {"tenant_id": tenant_id, "created_at": now},
        },
        upsert=True,
    )

    return {
        "tenant_id": tenant_id,
        "steps": sorted(steps_result, key=lambda s: s["order"]),
        "total": total,
        "completed": done,
        "progress_pct": round((done / total * 100) if total > 0 else 0),
    }


async def mark_step_complete(tenant_id: str, step_id: str) -> bool:
    """Manually mark an onboarding step as complete."""
    now = datetime.now(UTC).isoformat()
    await db.onboarding_progress.update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {
                f"completed_steps.{step_id}": True,
                "updated_at": now,
            },
            "$setOnInsert": {"tenant_id": tenant_id, "created_at": now},
        },
        upsert=True,
    )
    return True


async def reset_onboarding(tenant_id: str) -> bool:
    """Reset onboarding progress for a tenant."""
    await db.onboarding_progress.delete_one({"tenant_id": tenant_id})
    return True


async def get_all_onboarding_status() -> list[dict[str, Any]]:
    """Get onboarding status for all tenants (admin overview).
    Uses raw DB to bypass tenant isolation since this is a super_admin cross-tenant view.
    """
    from core.database import _raw_db

    tenants = await _raw_db.tenants.find({}, {"_id": 0, "id": 1, "property_name": 1, "subscription_tier": 1}).to_list(1000)

    # Batch-fetch all onboarding progress docs
    all_progress = await _raw_db.onboarding_progress.find({}, {"_id": 0}).to_list(1000)
    progress_map = {p["tenant_id"]: p for p in all_progress}

    results = []
    for t in tenants:
        progress = progress_map.get(t["id"])
        results.append({
            "tenant_id": t["id"],
            "property_name": t.get("property_name", "?"),
            "tier": t.get("subscription_tier", "basic"),
            "progress_pct": progress.get("progress_pct", 0) if progress else 0,
            "completed": progress.get("completed_count", 0) if progress else 0,
            "total": progress.get("total_steps", 0) if progress else 0,
        })

    return sorted(results, key=lambda r: r["progress_pct"])
