"""
PMS Advanced Analytics Router
Channel Loss Analysis, Overbooking Heatmap, Rule Engine (Light), No-Show Prediction (Basic)
"""
import uuid
from modules.pms_core.role_permission_service import require_op  # v100 DW
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api", tags=["pms-analytics"])


# ────────────────────────────────────────────────────────
# 1) CHANNEL LOSS ANALYTICS (FULL)
# ────────────────────────────────────────────────────────

@router.get("/pms/channel-loss-analytics")
async def get_channel_loss_analytics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
):
    """Full channel-based no-show loss analysis with trends and data quality."""
    tenant_id = current_user.tenant_id
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    # Get ALL bookings in period for rate calculation
    total_bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "created_at": {"$gte": cutoff},
            "status": {"$ne": "cancelled"},
        },
        {"_id": 0, "source_channel": 1, "channel": 1},
    ).to_list(10000)

    # Count bookings per channel for rate calculation
    channel_booking_counts = defaultdict(int)
    for b in total_bookings:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        channel_booking_counts[ch] += 1

    # Get no-show bookings
    no_shows = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": "no_show",
            "no_show_at": {"$gte": cutoff},
        },
        {
            "_id": 0,
            "id": 1,
            "no_show_at": 1,
            "source_channel": 1,
            "channel": 1,
            "total_amount": 1,
            "room_type": 1,
            "no_show_reason": 1,
        },
    ).to_list(5000)

    # --- Channel breakdown ---
    ch_data = defaultdict(lambda: {"count": 0, "total_loss": 0.0, "dates": []})
    for b in no_shows:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        amt = b.get("total_amount") or 0
        ch_data[ch]["count"] += 1
        ch_data[ch]["total_loss"] += amt
        day = (b.get("no_show_at") or "")[:10]
        if day:
            ch_data[ch]["dates"].append(day)

    channels = []
    for ch, info in ch_data.items():
        total_ch_bookings = channel_booking_counts.get(ch, 0)
        rate = round((info["count"] / total_ch_bookings * 100), 1) if total_ch_bookings > 0 else 0
        avg_loss = round(info["total_loss"] / info["count"], 2) if info["count"] > 0 else 0
        channels.append({
            "channel": ch,
            "no_show_count": info["count"],
            "total_loss": round(info["total_loss"], 2),
            "avg_loss": avg_loss,
            "no_show_rate": rate,
            "total_bookings": total_ch_bookings,
        })

    channels.sort(key=lambda x: -x["total_loss"])

    # Top 3 worst channels
    top3_worst = channels[:3]

    # --- Channel trend over time ---
    ch_trend = defaultdict(lambda: defaultdict(int))
    for b in no_shows:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        day = (b.get("no_show_at") or "")[:10]
        if day:
            ch_trend[day][ch] += 1

    trend_dates = sorted(ch_trend.keys())
    all_channels = sorted({ch for d in ch_trend.values() for ch in d.keys()})
    trend_data = []
    for d in trend_dates:
        entry = {"date": d}
        for ch in all_channels:
            entry[ch] = ch_trend[d].get(ch, 0)
        trend_data.append(entry)

    # --- Data quality / confidence ---
    data_days = len({(b.get("no_show_at") or "")[:10] for b in no_shows if b.get("no_show_at")})
    total_data_points = len(no_shows)

    if total_data_points < 5:
        confidence = "low"
        confidence_note = "Veri yetersiz — sonuclar gosterge niteligindedir"
    elif data_days < 7:
        confidence = "medium"
        confidence_note = f"Son {data_days} gune gore hesaplandi — daha fazla veri ile guvenilirlik artar"
    else:
        confidence = "high"
        confidence_note = f"Son {data_days} gunluk veriye dayanmaktadir"

    return {
        "channels": channels,
        "top3_worst": top3_worst,
        "trend": trend_data,
        "trend_channels": all_channels,
        "period_days": days,
        "total_no_shows": len(no_shows),
        "total_loss": round(sum(b.get("total_amount") or 0 for b in no_shows), 2),
        "data_quality": {
            "confidence": confidence,
            "note": confidence_note,
            "data_points": total_data_points,
            "data_days": data_days,
        },
    }


# ────────────────────────────────────────────────────────
# 2) OVERBOOKING HEATMAP (FULL)
# ────────────────────────────────────────────────────────

@router.get("/pms/overbooking-heatmap")
async def get_overbooking_heatmap(
    days: int = Query(default=90, ge=7, le=365),
    current_user: User = Depends(get_current_user),
):
    """Overbooking heatmap data with peak days, weekly pattern, channel overlay."""
    tenant_id = current_user.tenant_id
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    # Get overbooking no-shows
    overbookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": "no_show",
            "no_show_reason": "overbooking",
            "no_show_at": {"$gte": cutoff},
        },
        {
            "_id": 0,
            "no_show_at": 1,
            "check_in": 1,
            "source_channel": 1,
            "channel": 1,
            "total_amount": 1,
            "room_type": 1,
        },
    ).to_list(5000)

    # Also get ALL no-shows for broader heatmap context
    all_no_shows = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": "no_show",
            "no_show_at": {"$gte": cutoff},
        },
        {
            "_id": 0,
            "no_show_at": 1,
            "check_in": 1,
            "no_show_reason": 1,
            "source_channel": 1,
            "channel": 1,
            "total_amount": 1,
        },
    ).to_list(5000)

    # --- Heatmap: date → overbooking count ---
    date_map = defaultdict(lambda: {"overbooking": 0, "total_noshow": 0, "loss": 0.0, "channels": defaultdict(int)})

    for b in all_no_shows:
        # Use check_in date or no_show_at date
        day = (b.get("check_in") or b.get("no_show_at") or "")[:10]
        if not day:
            continue
        date_map[day]["total_noshow"] += 1
        date_map[day]["loss"] += b.get("total_amount") or 0
        if b.get("no_show_reason") == "overbooking":
            date_map[day]["overbooking"] += 1
            ch = b.get("source_channel") or b.get("channel") or "direct"
            date_map[day]["channels"][ch] += 1

    heatmap = []
    for d, info in sorted(date_map.items()):
        heatmap.append({
            "date": d,
            "overbooking_count": info["overbooking"],
            "total_noshow": info["total_noshow"],
            "loss": round(info["loss"], 2),
            "channel_breakdown": dict(info["channels"]),
        })

    # --- Peak days (top 5 riskiest) ---
    peak_days = sorted(heatmap, key=lambda x: -x["overbooking_count"])[:5]

    # --- Weekly pattern ---
    weekday_names = ["Pazartesi", "Sali", "Carsamba", "Persembe", "Cuma", "Cumartesi", "Pazar"]
    weekday_data = defaultdict(lambda: {"overbooking": 0, "total_noshow": 0, "count": 0})

    for d, info in date_map.items():
        try:
            dt = datetime.fromisoformat(d)
            wd = dt.weekday()
            weekday_data[wd]["overbooking"] += info["overbooking"]
            weekday_data[wd]["total_noshow"] += info["total_noshow"]
            weekday_data[wd]["count"] += 1
        except (ValueError, TypeError):
            pass

    weekly_pattern = []
    for wd in range(7):
        info = weekday_data[wd]
        weekly_pattern.append({
            "day_index": wd,
            "day_name": weekday_names[wd],
            "overbooking_total": info["overbooking"],
            "noshow_total": info["total_noshow"],
            "avg_overbooking": round(info["overbooking"] / max(info["count"], 1), 2),
            "avg_noshow": round(info["total_noshow"] / max(info["count"], 1), 2),
            "is_weekend": wd >= 5,
        })

    # --- Channel contribution for overbookings ---
    ch_contrib = defaultdict(int)
    for b in overbookings:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        ch_contrib[ch] += 1

    channel_overlay = [
        {"channel": ch, "count": cnt}
        for ch, cnt in sorted(ch_contrib.items(), key=lambda x: -x[1])
    ]

    # --- Data quality ---
    total_ob = len(overbookings)
    data_days = len({(b.get("no_show_at") or "")[:10] for b in overbookings if b.get("no_show_at")})

    if total_ob < 3:
        confidence = "low"
        confidence_note = "Overbooking verisi yetersiz — sonuclar gosterge niteligindedir"
    elif data_days < 14:
        confidence = "medium"
        confidence_note = f"Son {data_days} gune dayanmaktadir"
    else:
        confidence = "high"
        confidence_note = f"{total_ob} overbooking, {data_days} gun uzerinden analiz edildi"

    return {
        "heatmap": heatmap,
        "peak_days": peak_days,
        "weekly_pattern": weekly_pattern,
        "channel_overlay": channel_overlay,
        "total_overbookings": total_ob,
        "total_loss": round(sum(b.get("total_amount") or 0 for b in overbookings), 2),
        "period_days": days,
        "data_quality": {
            "confidence": confidence,
            "note": confidence_note,
            "data_points": total_ob,
            "data_days": data_days,
        },
    }


# ────────────────────────────────────────────────────────
# 3) ALERT RULE ENGINE (LIGHT)
# ────────────────────────────────────────────────────────

class AlertRuleCreate(BaseModel):
    rule_name: str
    rule_type: str  # "overbooking_high", "noshow_rate_high"
    condition_metric: str  # "overbooking_count", "noshow_rate"
    condition_operator: str  # "gt", "gte"
    condition_value: float
    action_suggestion: str  # "rate_dusur", "prepaid_zorunlu"
    channel_filter: str | None = None  # Optional: apply only to specific channel
    is_active: bool = True


@router.get("/pms/alert-rules")
async def list_alert_rules(current_user: User = Depends(get_current_user)):
    """List all alert rules for this tenant."""
    rules = await db.alert_rules.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).to_list(100)
    return {"rules": rules}


@router.post("/pms/alert-rules")
async def create_alert_rule(
    req: AlertRuleCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Create a new alert rule."""
    rule = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "rule_name": req.rule_name,
        "rule_type": req.rule_type,
        "condition_metric": req.condition_metric,
        "condition_operator": req.condition_operator,
        "condition_value": req.condition_value,
        "action_suggestion": req.action_suggestion,
        "channel_filter": req.channel_filter,
        "is_active": req.is_active,
        "trigger_count": 0,
        "last_triggered": None,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }
    await db.alert_rules.insert_one({**rule})
    return rule


@router.delete("/pms/alert-rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Delete an alert rule."""
    result = await db.alert_rules.delete_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Kural bulunamadi")
    return {"message": "Kural silindi"}


@router.patch("/pms/alert-rules/{rule_id}/toggle")
async def toggle_alert_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Toggle active/inactive state of a rule."""
    rule = await db.alert_rules.find_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id},
        {"_id": 0, "is_active": 1},
    )
    if not rule:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Kural bulunamadi")

    new_state = not rule.get("is_active", True)
    await db.alert_rules.update_one(
        {"id": rule_id},
        {"$set": {"is_active": new_state}},
    )
    return {"is_active": new_state}


@router.post("/pms/alert-rules/evaluate")
async def evaluate_alert_rules(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Evaluate all active rules against recent data and generate alerts."""
    tenant_id = current_user.tenant_id
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    rules = await db.alert_rules.find(
        {"tenant_id": tenant_id, "is_active": True},
        {"_id": 0},
    ).to_list(50)

    if not rules:
        return {"alerts": [], "rules_evaluated": 0}

    # Gather metrics
    no_shows = await db.bookings.find(
        {"tenant_id": tenant_id, "status": "no_show", "no_show_at": {"$gte": cutoff}},
        {"_id": 0, "no_show_reason": 1, "source_channel": 1, "channel": 1, "total_amount": 1},
    ).to_list(5000)

    total_bookings = await db.bookings.count_documents(
        {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}, "status": {"$ne": "cancelled"}}
    )

    overbooking_count = sum(1 for b in no_shows if b.get("no_show_reason") == "overbooking")
    noshow_count = len(no_shows)
    noshow_rate = round((noshow_count / max(total_bookings, 1)) * 100, 1)

    # Per-channel metrics
    ch_metrics = defaultdict(lambda: {"noshow": 0, "total": 0})
    for b in no_shows:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        ch_metrics[ch]["noshow"] += 1

    # Get total per channel
    all_bookings = await db.bookings.find(
        {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}, "status": {"$ne": "cancelled"}},
        {"_id": 0, "source_channel": 1, "channel": 1},
    ).to_list(10000)
    for b in all_bookings:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        ch_metrics[ch]["total"] += 1

    metrics = {
        "overbooking_count": overbooking_count,
        "noshow_count": noshow_count,
        "noshow_rate": noshow_rate,
    }

    alerts = []
    now_iso = datetime.now(UTC).isoformat()

    for rule in rules:
        metric_key = rule.get("condition_metric", "")
        operator = rule.get("condition_operator", "gt")
        threshold = rule.get("condition_value", 0)
        ch_filter = rule.get("channel_filter")

        # Determine metric value
        if ch_filter and metric_key == "noshow_rate":
            ch_info = ch_metrics.get(ch_filter, {"noshow": 0, "total": 0})
            metric_value = round((ch_info["noshow"] / max(ch_info["total"], 1)) * 100, 1)
        else:
            metric_value = metrics.get(metric_key, 0)

        # Evaluate
        triggered = False
        if operator == "gt" and metric_value > threshold:
            triggered = True
        elif operator == "gte" and metric_value >= threshold:
            triggered = True

        if triggered:
            alert = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "rule_id": rule["id"],
                "rule_name": rule["rule_name"],
                "rule_type": rule["rule_type"],
                "metric_value": metric_value,
                "threshold": threshold,
                "action_suggestion": rule["action_suggestion"],
                "channel_filter": ch_filter,
                "triggered_at": now_iso,
                "period_days": days,
            }
            alerts.append(alert)

            # Update trigger count
            await db.alert_rules.update_one(
                {"id": rule["id"]},
                {"$inc": {"trigger_count": 1}, "$set": {"last_triggered": now_iso}},
            )

            # Save to alert history
            await db.alert_history.insert_one({**alert})

    return {
        "alerts": alerts,
        "rules_evaluated": len(rules),
        "metrics": metrics,
        "period_days": days,
    }


@router.get("/pms/alert-rules/history")
async def get_alert_history(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Get alert trigger history."""
    history = await db.alert_history.find(
        {"tenant_id": current_user.tenant_id, "rule_name": {"$exists": True}},
        {"_id": 0},
    ).sort("triggered_at", -1).to_list(limit)
    return {"history": history}


# ────────────────────────────────────────────────────────
# 4) NO-SHOW PREDICTION (BASIC / RULE-BASED)
# ────────────────────────────────────────────────────────

@router.get("/pms/noshow-prediction")
async def get_noshow_prediction(
    days_ahead: int = Query(default=7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
):
    """Rule-based no-show prediction for upcoming bookings."""
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC)
    lookahead = (now + timedelta(days=days_ahead)).isoformat()
    now_iso = now.isoformat()

    # Historical data for patterns (last 90 days)
    hist_cutoff = (now - timedelta(days=90)).isoformat()

    # Get upcoming bookings
    upcoming = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$gte": now_iso[:10], "$lte": lookahead[:10]},
        },
        {
            "_id": 0,
            "id": 1,
            "guest_name": 1,
            "room_type": 1,
            "check_in": 1,
            "source_channel": 1,
            "channel": 1,
            "total_amount": 1,
        },
    ).to_list(500)

    # Historical no-show patterns
    hist_bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "created_at": {"$gte": hist_cutoff},
            "status": {"$ne": "cancelled"},
        },
        {"_id": 0, "source_channel": 1, "channel": 1, "status": 1, "check_in": 1},
    ).to_list(10000)

    # Channel-based no-show rates
    ch_totals = defaultdict(int)
    ch_noshows = defaultdict(int)
    # Day-of-week based rates
    dow_totals = defaultdict(int)
    dow_noshows = defaultdict(int)

    for b in hist_bookings:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        ch_totals[ch] += 1
        if b.get("status") == "no_show":
            ch_noshows[ch] += 1

        ci = b.get("check_in", "")[:10]
        if ci:
            try:
                dow = datetime.fromisoformat(ci).weekday()
                dow_totals[dow] += 1
                if b.get("status") == "no_show":
                    dow_noshows[dow] += 1
            except (ValueError, TypeError):
                pass

    ch_rates = {}
    for ch in ch_totals:
        ch_rates[ch] = round((ch_noshows[ch] / max(ch_totals[ch], 1)) * 100, 1)

    dow_rates = {}
    for dow in range(7):
        dow_rates[dow] = round((dow_noshows[dow] / max(dow_totals[dow], 1)) * 100, 1)

    # Score each upcoming booking
    predictions = []
    for b in upcoming:
        ch = b.get("source_channel") or b.get("channel") or "direct"
        ci = b.get("check_in", "")[:10]

        # Channel factor (0-50)
        ch_rate = ch_rates.get(ch, 0)
        ch_score = min(ch_rate * 2.5, 50)

        # Day-of-week factor (0-30)
        dow_score = 0
        if ci:
            try:
                dow = datetime.fromisoformat(ci).weekday()
                dow_rate = dow_rates.get(dow, 0)
                dow_score = min(dow_rate * 1.5, 30)
            except (ValueError, TypeError):
                pass

        # Amount factor — lower amounts slightly more risky (0-20)
        amt = b.get("total_amount") or 0
        amt_score = 20 if amt < 200 else (10 if amt < 500 else 5)

        # Total risk score (0-100)
        risk_score = min(round(ch_score + dow_score + amt_score), 100)

        # Classify
        if risk_score >= 60:
            risk_level = "high"
        elif risk_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"

        predictions.append({
            "booking_id": b["id"],
            "guest_name": b.get("guest_name") or "Bilinmiyor",
            "channel": ch,
            "check_in": ci,
            "room_type": b.get("room_type") or "-",
            "total_amount": amt,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "factors": {
                "channel_rate": ch_rate,
                "channel_score": round(ch_score, 1),
                "dow_score": round(dow_score, 1),
                "amount_score": amt_score,
            },
        })

    predictions.sort(key=lambda x: -x["risk_score"])

    # Summary
    high_risk = sum(1 for p in predictions if p["risk_level"] == "high")
    medium_risk = sum(1 for p in predictions if p["risk_level"] == "medium")
    low_risk = sum(1 for p in predictions if p["risk_level"] == "low")
    potential_loss = sum(p["total_amount"] for p in predictions if p["risk_level"] in ("high", "medium"))

    # Data quality
    total_hist = len(hist_bookings)
    if total_hist < 20:
        confidence = "low"
        confidence_note = "Veri yetersiz — tahminler gosterge niteligindedir"
    elif total_hist < 100:
        confidence = "medium"
        confidence_note = f"{total_hist} gecmis rezervasyona dayanmaktadir"
    else:
        confidence = "high"
        confidence_note = f"{total_hist} gecmis rezervasyon analiz edildi"

    return {
        "predictions": predictions[:50],  # Top 50
        "summary": {
            "total_upcoming": len(upcoming),
            "high_risk": high_risk,
            "medium_risk": medium_risk,
            "low_risk": low_risk,
            "potential_loss": round(potential_loss, 2),
        },
        "historical_rates": {
            "by_channel": ch_rates,
            "by_day_of_week": {
                str(k): v for k, v in dow_rates.items()
            },
        },
        "days_ahead": days_ahead,
        "data_quality": {
            "confidence": confidence,
            "note": confidence_note,
            "historical_bookings": total_hist,
        },
    }
