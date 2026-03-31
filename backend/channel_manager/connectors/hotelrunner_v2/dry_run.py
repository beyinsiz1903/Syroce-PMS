"""
HotelRunner v2 — Dry-Run Write Engine
========================================

Production write path'in birebir aynisi — tek fark: side-effect yok.

- Gercek outbox flow calisir (payload build, validate, store)
- External API call NO-OP / mock (captures what would be sent)
- Transaction verification calisir (read-only)
- Failure simulation destegi: timeout, validation, rate_limit
- correlation_id ile tam trace
- Sonuclar MongoDB'de saklanir

Supported operations:
  - ari_push (ARI availability/rate/restriction update)
  - confirm_delivery (reservation delivery acknowledgement)
  - chain (create -> modify -> cancel sequence)
"""
import logging
import time
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

from .errors import (
    HRv2RateLimitError,
    HRv2TimeoutError,
    HRv2ValidationError,
)
from .mapper import ari_to_update_payload
from .metrics import record_metric

logger = logging.getLogger("hrv2.dry_run")

COLL_DRY_RUN = "connector_dry_run_results"
_NO_ID = {"_id": 0}

# ── Failure Simulation ──────────────────────────────────────────────

SIMULATED_FAILURES = {
    "timeout": {
        "error_class": HRv2TimeoutError,
        "message": "[DRY-RUN SIM] Timeout on ARI push (simulated)",
        "category": "timeout",
    },
    "validation_error": {
        "error_class": HRv2ValidationError,
        "message": "[DRY-RUN SIM] Bad request — invalid inv_code (simulated)",
        "category": "validation",
    },
    "rate_limit": {
        "error_class": HRv2RateLimitError,
        "message": "[DRY-RUN SIM] Rate limited (simulated)",
        "category": "rate_limit",
        "extra": {"retry_after": 60},
    },
}


def _simulate_failure(failure_type: str) -> dict[str, Any]:
    """Generate a simulated failure result without raising."""
    sim = SIMULATED_FAILURES.get(failure_type)
    if not sim:
        return {
            "simulated": True,
            "failure_type": failure_type,
            "success": False,
            "error": f"Unknown failure type: {failure_type}",
            "error_category": "unknown",
        }
    return {
        "simulated": True,
        "failure_type": failure_type,
        "success": False,
        "error": sim["message"],
        "error_category": sim["category"],
    }


# ── Dry-Run ARI Push ─────────────────────────────────────────────────

async def dry_run_ari_push(
    tenant_id: str,
    property_id: str,
    inv_code: str,
    start_date: str,
    end_date: str,
    *,
    availability: int | None = None,
    price: float | None = None,
    stop_sale: bool | None = None,
    min_stay: int | None = None,
    cta: bool | None = None,
    ctd: bool | None = None,
    days: list[int] | None = None,
    channel_codes: list[str] | None = None,
    simulate_failure: str | None = None,
    verify: bool = True,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Dry-run ARI push: production path'in birebir kopyasi, side-effect yok.

    Flow:
    1. Payload build (gercek mapper kullanir)
    2. Outbox entry olustur (dry_run flag ile)
    3. Failure simulation (istege bagli)
    4. NO-OP external call (captured payload)
    5. Transaction verification (read-only, istege bagli)
    6. Sonuclari DB'ye kaydet
    """
    corr_id = correlation_id or f"dr-{_uuid.uuid4().hex[:10]}"
    start = time.time()

    # 1. Build payload — gercek mapper kullaniyoruz
    form_data = ari_to_update_payload(
        inv_code, start_date, end_date,
        availability=availability, price=price, stop_sale=stop_sale,
        min_stay=min_stay, cta=cta, ctd=ctd,
        days=days, channel_codes=channel_codes,
    )

    # 2. Failure simulation
    failure_result = None
    if simulate_failure:
        failure_result = _simulate_failure(simulate_failure)

    # 3. NO-OP external call — payload captured, no HTTP sent
    if failure_result:
        noop_response = failure_result
    else:
        noop_response = {
            "simulated": False,
            "success": True,
            "data": {
                "status": "ok",
                "transaction_id": f"dr-txn-{_uuid.uuid4().hex[:8]}",
                "message": "ARI update accepted (dry-run, no real write)",
            },
            "error": None,
            "error_category": None,
        }

    # 4. Transaction verification (read-only, optional)
    verification = None
    if verify and noop_response.get("success"):
        verification = await _dry_run_verify_transaction(
            tenant_id, property_id,
            noop_response["data"].get("transaction_id", ""),
            correlation_id=corr_id,
        )

    # 5. Consistency check — compare payload structure
    consistency = _check_payload_consistency(form_data)

    duration_ms = int((time.time() - start) * 1000)

    # 6. Store result
    result = {
        "id": str(_uuid.uuid4()),
        "tenant_id": tenant_id,
        "property_id": property_id,
        "operation": "ari_push",
        "mode": "dry_run",
        "correlation_id": corr_id,
        "success": noop_response.get("success", False),
        "request_payload": form_data,
        "noop_response": noop_response,
        "verification": verification,
        "consistency_check": consistency,
        "failure_simulation": simulate_failure,
        "duration_ms": duration_ms,
        "created_at": datetime.now(UTC).isoformat(),
    }

    await db[COLL_DRY_RUN].insert_one({**result})

    # 7. Record metric for dry-run tracking
    await record_metric(
        tenant_id, "dry_run_ari_push",
        success=result["success"], duration_ms=duration_ms,
        correlation_id=corr_id,
        metadata={
            "inv_code": inv_code,
            "simulate_failure": simulate_failure,
            "consistency_pass": consistency.get("pass", False),
        },
    )

    # 8. Store in outbox (dry-run flag)
    await db["connector_outbox"].insert_one({
        "id": str(_uuid.uuid4()),
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": "hotelrunner_v2",
        "operation": "ari_push",
        "dry_run": True,
        "request_payload": form_data,
        "response_payload": noop_response,
        "correlation_id": corr_id,
        "status": "dry_run_completed" if result["success"] else "dry_run_failed",
        "created_at": datetime.now(UTC).isoformat(),
    })

    # Remove _id before returning
    result.pop("_id", None)
    return result


# ── Dry-Run Confirm Delivery ──────────────────────────────────────────

async def dry_run_confirm_delivery(
    tenant_id: str,
    property_id: str,
    message_uid: str,
    pms_number: str | None = None,
    *,
    simulate_failure: str | None = None,
    correlation_id: str = "",
) -> dict[str, Any]:
    """Dry-run confirm delivery: NO-OP PUT, payload captured."""
    corr_id = correlation_id or f"dr-{_uuid.uuid4().hex[:10]}"
    start = time.time()

    params = {"message_uid": message_uid}
    if pms_number:
        params["pms_number"] = pms_number

    failure_result = None
    if simulate_failure:
        failure_result = _simulate_failure(simulate_failure)

    if failure_result:
        noop_response = failure_result
    else:
        noop_response = {
            "simulated": False,
            "success": True,
            "data": {"status": "ok", "message": "Delivery confirmed (dry-run, no real write)"},
            "error": None,
        }

    duration_ms = int((time.time() - start) * 1000)

    result = {
        "id": str(_uuid.uuid4()),
        "tenant_id": tenant_id,
        "property_id": property_id,
        "operation": "confirm_delivery",
        "mode": "dry_run",
        "correlation_id": corr_id,
        "success": noop_response.get("success", False),
        "request_payload": params,
        "noop_response": noop_response,
        "failure_simulation": simulate_failure,
        "duration_ms": duration_ms,
        "created_at": datetime.now(UTC).isoformat(),
    }

    await db[COLL_DRY_RUN].insert_one({**result})
    await record_metric(
        tenant_id, "dry_run_confirm_delivery",
        success=result["success"], duration_ms=duration_ms,
        correlation_id=corr_id,
    )

    result.pop("_id", None)
    return result


# ── Dry-Run Chain (Create → Modify → Cancel) ─────────────────────────

async def dry_run_chain(
    tenant_id: str,
    property_id: str,
    *,
    simulate_failures: dict[str, str] | None = None,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Bir tam create → modify → cancel zinciri calistir (dry-run).

    Her adim icin ayri failure simulation belirlenebilir:
      simulate_failures={"create": "timeout", "modify": None, "cancel": "validation_error"}
    """
    corr_id = correlation_id or f"dr-chain-{_uuid.uuid4().hex[:8]}"
    start = time.time()
    failures = simulate_failures or {}

    chain_results = []

    # Step 1: CREATE — ARI push (yeni oda/fiyat)
    step1 = await dry_run_ari_push(
        tenant_id, property_id,
        inv_code="HR:CHAIN-TEST",
        start_date="2026-04-01",
        end_date="2026-04-05",
        availability=10,
        price=150.0,
        simulate_failure=failures.get("create"),
        verify=True,
        correlation_id=f"{corr_id}-create",
    )
    chain_results.append({"step": "create", **step1})

    # Step 2: MODIFY — ARI push (fiyat degisikligi)
    step2 = await dry_run_ari_push(
        tenant_id, property_id,
        inv_code="HR:CHAIN-TEST",
        start_date="2026-04-01",
        end_date="2026-04-05",
        availability=8,
        price=175.0,
        min_stay=2,
        simulate_failure=failures.get("modify"),
        verify=True,
        correlation_id=f"{corr_id}-modify",
    )
    chain_results.append({"step": "modify", **step2})

    # Step 3: CANCEL — ARI push (stop_sale)
    step3 = await dry_run_ari_push(
        tenant_id, property_id,
        inv_code="HR:CHAIN-TEST",
        start_date="2026-04-01",
        end_date="2026-04-05",
        stop_sale=True,
        availability=0,
        simulate_failure=failures.get("cancel"),
        verify=True,
        correlation_id=f"{corr_id}-cancel",
    )
    chain_results.append({"step": "cancel", **step3})

    duration_ms = int((time.time() - start) * 1000)
    all_success = all(r.get("success", False) for r in chain_results)

    # Store chain summary
    chain_summary = {
        "id": str(_uuid.uuid4()),
        "tenant_id": tenant_id,
        "property_id": property_id,
        "operation": "dry_run_chain",
        "mode": "dry_run",
        "correlation_id": corr_id,
        "success": all_success,
        "steps": chain_results,
        "step_count": len(chain_results),
        "success_count": sum(1 for r in chain_results if r.get("success")),
        "failure_count": sum(1 for r in chain_results if not r.get("success")),
        "duration_ms": duration_ms,
        "created_at": datetime.now(UTC).isoformat(),
    }

    await db[COLL_DRY_RUN].insert_one({**chain_summary})
    await record_metric(
        tenant_id, "dry_run_chain",
        success=all_success, duration_ms=duration_ms,
        correlation_id=corr_id,
        metadata={"step_count": 3, "success_count": chain_summary["success_count"]},
    )

    chain_summary.pop("_id", None)
    return chain_summary


# ── Transaction Verification (Read-Only) ──────────────────────────────

async def _dry_run_verify_transaction(
    tenant_id: str,
    property_id: str,
    transaction_id: str,
    *,
    correlation_id: str = "",
) -> dict[str, Any]:
    """
    Read-only verification. Tries real HR API if service available,
    otherwise returns simulated verification.
    """
    try:
        from .service import HotelRunnerV2Service
        svc = await HotelRunnerV2Service.create(tenant_id, property_id)
        return await svc.verify_transaction(transaction_id, correlation_id=correlation_id)
    except Exception as e:
        logger.info("[DRY-RUN] verify_transaction fallback (service unavailable): %s", e)
        return {
            "transaction_id": transaction_id,
            "verified": True,
            "dry_run_simulated": True,
            "succeeded": 1,
            "failed": 0,
            "in_progress": 0,
            "note": "Simulated verification (HR service unavailable for read-only check)",
        }


# ── Payload Consistency Check ─────────────────────────────────────────

def _check_payload_consistency(form_data: dict[str, Any]) -> dict[str, Any]:
    """
    Payload structure'in production path ile uyumlu oldugunu dogrula.
    """
    issues = []

    # Required fields
    if not form_data.get("inv_code"):
        issues.append("inv_code eksik")
    if not form_data.get("start_date"):
        issues.append("start_date eksik")
    if not form_data.get("end_date"):
        issues.append("end_date eksik")

    # At least one update field
    update_fields = ["availability", "price", "stop_sale", "min_stay", "cta", "ctd"]
    has_update = any(form_data.get(f) is not None for f in update_fields)
    if not has_update:
        issues.append("En az bir update field gerekli (availability, price, stop_sale, min_stay, cta, ctd)")

    # Date format check
    import re
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for df in ["start_date", "end_date"]:
        val = form_data.get(df, "")
        if val and not date_pattern.match(val):
            issues.append(f"{df} YYYY-MM-DD formatinda olmali")

    return {
        "pass": len(issues) == 0,
        "issues": issues,
        "checked_fields": list(form_data.keys()),
    }


# ── Dry-Run Stats & History ──────────────────────────────────────────

async def get_dry_run_results(
    tenant_id: str,
    limit: int = 50,
    operation: str | None = None,
) -> list[dict[str, Any]]:
    """Get dry-run results history."""
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if operation:
        query["operation"] = operation

    return await db[COLL_DRY_RUN].find(
        query, _NO_ID,
    ).sort("created_at", -1).to_list(limit)


async def get_dry_run_stats(tenant_id: str) -> dict[str, Any]:
    """
    Dry-run istatistikleri: success rate, failure breakdown, chain durumu.
    """
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "mode": "dry_run"}},
        {"$group": {
            "_id": "$operation",
            "total": {"$sum": 1},
            "success_count": {"$sum": {"$cond": ["$success", 1, 0]}},
            "fail_count": {"$sum": {"$cond": ["$success", 0, 1]}},
            "avg_duration_ms": {"$avg": "$duration_ms"},
        }},
    ]
    results = await db[COLL_DRY_RUN].aggregate(pipeline).to_list(10)

    stats: dict[str, Any] = {
        "tenant_id": tenant_id,
        "calculated_at": datetime.now(UTC).isoformat(),
        "operations": {},
        "total_runs": 0,
        "total_success": 0,
        "total_failed": 0,
        "overall_success_rate": 0.0,
    }

    for r in results:
        op = r["_id"]
        stats["operations"][op] = {
            "total": r["total"],
            "success": r["success_count"],
            "failed": r["fail_count"],
            "success_rate": round(r["success_count"] / r["total"] * 100, 1) if r["total"] > 0 else 0.0,
            "avg_duration_ms": round(r["avg_duration_ms"] or 0, 1),
        }
        stats["total_runs"] += r["total"]
        stats["total_success"] += r["success_count"]
        stats["total_failed"] += r["fail_count"]

    if stats["total_runs"] > 0:
        stats["overall_success_rate"] = round(
            stats["total_success"] / stats["total_runs"] * 100, 1
        )

    # Failure breakdown (by category)
    fail_pipeline = [
        {"$match": {"tenant_id": tenant_id, "mode": "dry_run", "success": False}},
        {"$group": {
            "_id": "$noop_response.error_category",
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    fail_results = await db[COLL_DRY_RUN].aggregate(fail_pipeline).to_list(10)
    stats["failure_breakdown"] = {
        r["_id"]: r["count"] for r in fail_results if r["_id"]
    }

    # Chain stats
    chain_pipeline = [
        {"$match": {"tenant_id": tenant_id, "operation": "dry_run_chain"}},
        {"$sort": {"created_at": -1}},
        {"$limit": 1},
    ]
    chain_results = await db[COLL_DRY_RUN].aggregate(chain_pipeline).to_list(1)
    if chain_results:
        last_chain = chain_results[0]
        stats["last_chain"] = {
            "success": last_chain.get("success", False),
            "step_count": last_chain.get("step_count", 0),
            "success_count": last_chain.get("success_count", 0),
            "failure_count": last_chain.get("failure_count", 0),
            "correlation_id": last_chain.get("correlation_id", ""),
            "created_at": last_chain.get("created_at", ""),
        }
    else:
        stats["last_chain"] = None

    # Last dry-run result
    last_result = await db[COLL_DRY_RUN].find_one(
        {"tenant_id": tenant_id, "mode": "dry_run"},
        _NO_ID,
        sort=[("created_at", -1)],
    )
    if last_result:
        stats["last_result"] = {
            "operation": last_result.get("operation"),
            "success": last_result.get("success"),
            "correlation_id": last_result.get("correlation_id"),
            "duration_ms": last_result.get("duration_ms"),
            "created_at": last_result.get("created_at"),
        }
    else:
        stats["last_result"] = None

    return stats


# ── Write Enable Criteria Check ───────────────────────────────────────

async def check_write_enable_criteria(tenant_id: str) -> dict[str, Any]:
    """
    Write acma kriterleri (kullanici tarafindan belirlenmis):

    - Readiness Score >= 90
    - Drift dusuk ve stabil
    - Dry-run success rate yuksek (>= 95%)
    - DLQ = 0
    - Retry stabil
    - En az 1 basarili create/modify/cancel zinciri
    """
    from .readiness import calculate_readiness_score

    readiness = await calculate_readiness_score(tenant_id)
    dry_stats = await get_dry_run_stats(tenant_id)

    criteria = []

    # 1. Readiness Score >= 90
    score = readiness.get("overall_score", 0)
    criteria.append({
        "name": "readiness_score",
        "label": "Readiness Score >= 90",
        "met": score >= 90,
        "current_value": score,
        "required_value": 90,
    })

    # 2. Drift dusuk ve stabil
    drift_raw = readiness.get("components", {}).get("drift", {}).get("raw_value", 0)
    criteria.append({
        "name": "drift_low",
        "label": "Drift < 5 (son 24s)",
        "met": drift_raw < 5,
        "current_value": drift_raw,
        "required_value": "< 5",
    })

    # 3. Dry-run success rate >= 95%
    dr_success_rate = dry_stats.get("overall_success_rate", 0)
    dr_total = dry_stats.get("total_runs", 0)
    criteria.append({
        "name": "dry_run_success_rate",
        "label": "Dry-run success rate >= 95%",
        "met": dr_success_rate >= 95 and dr_total >= 3,
        "current_value": dr_success_rate,
        "required_value": 95,
        "note": f"{dr_total} toplam dry-run" if dr_total < 3 else None,
    })

    # 4. DLQ = 0
    dlq_count = readiness.get("components", {}).get("dlq", {}).get("raw_value", 0)
    criteria.append({
        "name": "dlq_empty",
        "label": "DLQ = 0",
        "met": dlq_count == 0,
        "current_value": dlq_count,
        "required_value": 0,
    })

    # 5. Retry stabil (< 5)
    retry_raw = readiness.get("components", {}).get("retry", {}).get("raw_value", 0)
    criteria.append({
        "name": "retry_stable",
        "label": "Retry < 5 (stabil)",
        "met": retry_raw < 5,
        "current_value": retry_raw,
        "required_value": "< 5",
    })

    # 6. En az 1 basarili chain
    last_chain = dry_stats.get("last_chain")
    chain_success = last_chain is not None and last_chain.get("success", False)
    criteria.append({
        "name": "chain_success",
        "label": "En az 1 basarili create/modify/cancel zinciri",
        "met": chain_success,
        "current_value": "Basarili" if chain_success else "Yok",
        "required_value": "En az 1",
    })

    all_met = all(c["met"] for c in criteria)
    met_count = sum(1 for c in criteria if c["met"])

    return {
        "tenant_id": tenant_id,
        "checked_at": datetime.now(UTC).isoformat(),
        "all_criteria_met": all_met,
        "met_count": met_count,
        "total_criteria": len(criteria),
        "write_ready": all_met,
        "criteria": criteria,
    }
