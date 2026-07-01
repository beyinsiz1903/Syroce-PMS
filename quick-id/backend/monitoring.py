"""
Monitoring & Metrik Modülü
- Scan sayısı, başarı oranı, hata izleme
- AI API maliyet takibi
- Sistem sağlık metrikleri
- Günlük/haftalık/aylık raporlar
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid


async def get_scan_statistics(db: AsyncIOMotorDatabase, days: int = 30) -> dict:
    """Tarama istatistikleri"""
    scans_col = db["scans"]
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    total_scans = await scans_col.count_documents({"created_at": {"$gte": start_date}})
    successful_scans = await scans_col.count_documents({"created_at": {"$gte": start_date}, "status": "completed"})
    failed_scans = await scans_col.count_documents({"created_at": {"$gte": start_date}, "status": "failed"})
    
    # Confidence distribution
    high_confidence = await scans_col.count_documents(
        {"created_at": {"$gte": start_date}, "confidence_level": "high"})
    medium_confidence = await scans_col.count_documents(
        {"created_at": {"$gte": start_date}, "confidence_level": "medium"})
    low_confidence = await scans_col.count_documents(
        {"created_at": {"$gte": start_date}, "confidence_level": "low"})
    
    # Needs review count
    needs_review = await scans_col.count_documents(
        {"created_at": {"$gte": start_date}, "review_status": "needs_review"})
    
    # Daily breakdown
    daily_stats = []
    for i in range(min(days, 30), -1, -1):
        day_start = (datetime.now(timezone.utc) - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_total = await scans_col.count_documents({"created_at": {"$gte": day_start, "$lt": day_end}})
        day_success = await scans_col.count_documents({"created_at": {"$gte": day_start, "$lt": day_end}, "status": "completed"})
        day_failed = await scans_col.count_documents({"created_at": {"$gte": day_start, "$lt": day_end}, "status": "failed"})
        daily_stats.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "total": day_total,
            "successful": day_success,
            "failed": day_failed,
        })
    
    success_rate = round((successful_scans / total_scans * 100), 1) if total_scans > 0 else 0
    
    return {
        "period_days": days,
        "total_scans": total_scans,
        "successful_scans": successful_scans,
        "failed_scans": failed_scans,
        "success_rate": success_rate,
        "needs_review": needs_review,
        "confidence_distribution": {
            "high": high_confidence,
            "medium": medium_confidence,
            "low": low_confidence,
        },
        "daily_stats": daily_stats,
    }


async def get_error_log(db: AsyncIOMotorDatabase, limit: int = 50, days: int = 7) -> dict:
    """Hata izleme"""
    scans_col = db["scans"]
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    cursor = scans_col.find(
        {"status": "failed", "created_at": {"$gte": start_date}}
    ).sort("created_at", -1).limit(limit)
    
    errors = []
    async for doc in cursor:
        errors.append({
            "id": str(doc["_id"]),
            "error": doc.get("error", "Bilinmeyen hata"),
            "created_at": doc.get("created_at", "").isoformat() if isinstance(doc.get("created_at"), datetime) else str(doc.get("created_at", "")),
            "scanned_by": doc.get("scanned_by", ""),
            "source": doc.get("source", "web"),
            "fallback_guidance": doc.get("fallback_guidance", []),
        })
    
    # Error type breakdown
    error_types = {}
    for err in errors:
        error_text = err.get("error", "")
        if "timeout" in error_text.lower() or "connection" in error_text.lower():
            error_type = "connection_error"
        elif "rate" in error_text.lower() or "limit" in error_text.lower():
            error_type = "rate_limit"
        elif "parse" in error_text.lower() or "json" in error_text.lower():
            error_type = "parse_error"
        elif "key" in error_text.lower() or "auth" in error_text.lower():
            error_type = "auth_error"
        else:
            error_type = "other"
        error_types[error_type] = error_types.get(error_type, 0) + 1
    
    return {
        "total_errors": len(errors),
        "period_days": days,
        "errors": errors,
        "error_types": error_types,
    }


async def track_ai_cost(db: AsyncIOMotorDatabase, model: str, operation: str,
                        input_tokens: int = 0, output_tokens: int = 0,
                        estimated_cost: float = 0.0) -> dict:
    """AI API maliyet kaydı"""
    col = db["ai_cost_tracking"]
    
    cost_doc = {
        "tracking_id": str(uuid.uuid4()),
        "model": model,
        "operation": operation,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": estimated_cost,
        "created_at": datetime.now(timezone.utc),
    }
    
    await col.insert_one(cost_doc)
    return cost_doc


async def get_ai_cost_summary(db: AsyncIOMotorDatabase, days: int = 30) -> dict:
    """AI API maliyet özeti"""
    col = db["ai_cost_tracking"]
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    cursor = col.find({"created_at": {"$gte": start_date}})
    
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    model_breakdown = {}
    operation_breakdown = {}
    daily_costs = {}
    
    async for doc in cursor:
        cost = doc.get("estimated_cost_usd", 0.0)
        total_cost += cost
        total_input_tokens += doc.get("input_tokens", 0)
        total_output_tokens += doc.get("output_tokens", 0)
        
        model = doc.get("model", "unknown")
        model_breakdown[model] = model_breakdown.get(model, 0.0) + cost
        
        operation = doc.get("operation", "unknown")
        operation_breakdown[operation] = operation_breakdown.get(operation, 0.0) + cost
        
        date_key = doc.get("created_at", datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        daily_costs[date_key] = daily_costs.get(date_key, 0.0) + cost
    
    # Sort daily costs
    daily_cost_list = [
        {"date": k, "cost": round(v, 4)}
        for k, v in sorted(daily_costs.items())
    ]
    
    return {
        "period_days": days,
        "total_cost_usd": round(total_cost, 4),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "avg_daily_cost": round(total_cost / max(days, 1), 4),
        "model_breakdown": {k: round(v, 4) for k, v in model_breakdown.items()},
        "operation_breakdown": {k: round(v, 4) for k, v in operation_breakdown.items()},
        "daily_costs": daily_cost_list,
    }


async def get_monitoring_dashboard(db: AsyncIOMotorDatabase) -> dict:
    """Tam monitoring dashboard verisi"""
    # Temel istatistikler
    guests_col = db["guests"]
    scans_col = db["scans"]
    
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)
    
    # Genel sayılar
    total_guests = await guests_col.count_documents({})
    total_scans = await scans_col.count_documents({})
    today_scans = await scans_col.count_documents({"created_at": {"$gte": today_start}})
    today_guests = await guests_col.count_documents({"created_at": {"$gte": today_start}})
    
    # Aktif misafirler
    checked_in = await guests_col.count_documents({"status": "checked_in"})
    pending = await guests_col.count_documents({"status": "pending"})
    
    # Scan başarı oranı
    week_scans = await scans_col.count_documents({"created_at": {"$gte": week_start}})
    week_success = await scans_col.count_documents({"created_at": {"$gte": week_start}, "status": "completed"})
    week_failed = await scans_col.count_documents({"created_at": {"$gte": week_start}, "status": "failed"})
    
    # Oda durumu
    rooms_col = db["rooms"]
    total_rooms = await rooms_col.count_documents({})
    available_rooms = await rooms_col.count_documents({"status": "available"})
    occupied_rooms = await rooms_col.count_documents({"status": "occupied"})
    
    # Emniyet bildirimleri
    emniyet_col = db["emniyet_bildirimleri"]
    total_bildirimi = await emniyet_col.count_documents({})
    draft_bildirimi = await emniyet_col.count_documents({"status": "draft"})
    
    # KVKK talepleri
    kvkk_col = db["kvkk_rights_requests"]
    pending_kvkk = await kvkk_col.count_documents({"status": "pending"})
    
    return {
        "overview": {
            "total_guests": total_guests,
            "total_scans": total_scans,
            "today_scans": today_scans,
            "today_guests": today_guests,
            "checked_in": checked_in,
            "pending_guests": pending,
        },
        "scan_performance": {
            "week_total": week_scans,
            "week_successful": week_success,
            "week_failed": week_failed,
            "success_rate": round((week_success / week_scans * 100), 1) if week_scans > 0 else 0,
        },
        "rooms": {
            "total": total_rooms,
            "available": available_rooms,
            "occupied": occupied_rooms,
            "occupancy_rate": round((occupied_rooms / total_rooms * 100), 1) if total_rooms > 0 else 0,
        },
        "compliance": {
            "total_emniyet_bildirimi": total_bildirimi,
            "draft_bildirimi": draft_bildirimi,
            "pending_kvkk_requests": pending_kvkk,
        },
        "generated_at": now.isoformat(),
    }
