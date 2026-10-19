"""
PMS Advanced Analytics Router
Channel Loss Analysis, Overbooking Heatmap, Rule Engine (Light), No-Show Prediction (Basic)
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from models.schemas import User
from modules.pms_core.noshow_reporting import arrival_cohort, booking_channel, build_channel_report, build_heatmap_report, is_no_show
from modules.pms_core.report_money import add_amount, currency_code, rounded_totals, single_amount
from modules.pms_core.reservation_reporting import reservation_value
from modules.pms_core.role_permission_service import require_op  # v100 DW
from modules.pms_core.stay_night_metrics import as_date

router = APIRouter(prefix="/api", tags=["pms-analytics"])


def _arrival_period(days):
    """One arrival cohort for both numerator and denominator, ISO or BSON."""
    last = datetime.now(UTC).date()
    first = last - timedelta(days=days - 1)
    after = last + timedelta(days=1)
    return first, last, {"$or": [
        {"check_in": {"$gte": first.isoformat(), "$lt": after.isoformat()}},
        {"check_in": {"$gte": datetime.combine(first, datetime.min.time(), UTC), "$lt": datetime.combine(after, datetime.min.time(), UTC)}},
    ]}


def _day(value):
    return str(value or "")[:10]


# ────────────────────────────────────────────────────────
# 1) CHANNEL LOSS ANALYTICS (FULL)
# ────────────────────────────────────────────────────────


@router.get("/pms/channel-loss-analytics")
async def get_channel_loss_analytics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
):
    """Arrival-cohort no-show counts and booked reference values, not cash loss."""
    first, last, _ = _arrival_period(days)
    rows, invalid_dates = await arrival_cohort(db, current_user.tenant_id, first, last)
    currency, _ = await get_tenant_currency(current_user.tenant_id)
    return build_channel_report(rows, first, last, currency, invalid_dates=invalid_dates)


@router.get("/pms/overbooking-heatmap")
async def get_overbooking_heatmap(
    days: int = Query(default=90, ge=7, le=365),
    current_user: User = Depends(get_current_user),
):
    """Daily OVERBOOKING reference values reconcile with the overbooking total."""
    first, last, _ = _arrival_period(days)
    rows, invalid_dates = await arrival_cohort(db, current_user.tenant_id, first, last)
    currency, _ = await get_tenant_currency(current_user.tenant_id)
    return build_heatmap_report(rows, first, last, currency, invalid_dates=invalid_dates)


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
    result = await db.alert_rules.delete_one({"id": rule_id, "tenant_id": current_user.tenant_id})
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
    rules = await db.alert_rules.find(
        {"tenant_id": tenant_id, "is_active": True},
        {"_id": 0},
    ).to_list(50)

    if not rules:
        return {"alerts": [], "rules_evaluated": 0}

    # One arrival cohort is shared with the read-only report. A no-show alias
    # must enter both the numerator and the eligible denominator.
    first, last, _ = _arrival_period(days)
    all_bookings, invalid_dates = await arrival_cohort(db, tenant_id, first, last)
    no_shows = [booking for booking in all_bookings if is_no_show(booking)]
    total_bookings = len(all_bookings)
    overbooking_count = sum(1 for booking in no_shows if booking.get("no_show_reason") == "overbooking")
    noshow_count = len(no_shows)
    noshow_rate = round(noshow_count / total_bookings * 100, 1) if total_bookings else 0
    ch_metrics = defaultdict(lambda: {"noshow": 0, "total": 0, "overbooking": 0})
    for booking in all_bookings:
        entry = ch_metrics[booking_channel(booking)]
        entry["total"] += 1
        if is_no_show(booking):
            entry["noshow"] += 1
            entry["overbooking"] += int(booking.get("no_show_reason") == "overbooking")

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
        if ch_filter:
            ch_info = ch_metrics.get(booking_channel({"channel": ch_filter}), {"noshow": 0, "total": 0, "overbooking": 0})
            filtered_metrics = {"noshow_rate": round(ch_info["noshow"] / ch_info["total"] * 100, 1) if ch_info["total"] else 0,
                "noshow_count": ch_info["noshow"], "overbooking_count": ch_info["overbooking"]}
            metric_value = filtered_metrics.get(metric_key, 0)
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
                {"id": rule["id"], "tenant_id": tenant_id},
                {"$inc": {"trigger_count": 1}, "$set": {"last_triggered": now_iso}},
            )

            # Save to alert history
            await db.alert_history.insert_one({**alert})

    return {
        "alerts": alerts,
        "rules_evaluated": len(rules),
        "metrics": metrics,
        "period_days": days,
        "data_quality": {"invalid_dates": invalid_dates},
    }


@router.get("/pms/alert-rules/history")
async def get_alert_history(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Get alert trigger history."""
    history = (
        await db.alert_history.find(
            {"tenant_id": current_user.tenant_id, "rule_name": {"$exists": True}},
            {"_id": 0},
        )
        .sort("triggered_at", -1)
        .to_list(limit)
    )
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
    lookahead = now.date() + timedelta(days=days_ahead)

    # Historical data for patterns (last 90 days)
    hist_cutoff = now.date() - timedelta(days=90)

    # Get upcoming bookings
    upcoming = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "$or": [{"check_in": {"$gte": now.date().isoformat(), "$lt": lookahead.isoformat()}},
                    {"check_in": {"$gte": datetime.combine(now.date(), datetime.min.time(), UTC), "$lt": datetime.combine(lookahead, datetime.min.time(), UTC)}}],
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
            "is_complimentary": 1,
            "total": 1,
            "rate_per_night": 1,
            "check_out": 1,
            "ota_channel": 1,
            "currency": 1,
        },
    ).to_list(None)

    # Use exactly the same eligible arrival cohort and legacy status aliases.
    hist_bookings, invalid_history_dates = await arrival_cohort(db, tenant_id, hist_cutoff, now.date() - timedelta(days=1))
    currency, _ = await get_tenant_currency(tenant_id)

    # Channel-based no-show rates
    ch_totals = defaultdict(int)
    ch_noshows = defaultdict(int)
    # Day-of-week based rates
    dow_totals = defaultdict(int)
    dow_noshows = defaultdict(int)

    for b in hist_bookings:
        ch = booking_channel(b)
        ch_totals[ch] += 1
        if is_no_show(b):
            ch_noshows[ch] += 1

        ci = _day(b.get("check_in"))
        if ci:
            try:
                dow = datetime.fromisoformat(ci).weekday()
                dow_totals[dow] += 1
                if is_no_show(b):
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
    valid_upcoming = [booking for booking in upcoming if (day := as_date(booking.get("check_in"))) and now.date() <= day < lookahead]
    for b in valid_upcoming:
        ch = booking_channel(b)
        ci = _day(b.get("check_in"))

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

        # Raw amounts in unlike currencies are not comparable risk evidence.
        amount = reservation_value(b)
        amt = float(amount) if amount is not None else None
        amt_score = 0

        # Total risk score (0-100)
        risk_score = min(round(ch_score + dow_score + amt_score), 100)

        # Classify
        if risk_score >= 60:
            risk_level = "high"
        elif risk_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"

        predictions.append(
            {
                "booking_id": b["id"],
                "guest_name": b.get("guest_name") or "Bilinmiyor",
                "channel": ch,
                "check_in": ci,
                "room_type": b.get("room_type") or "-",
                "total_amount": amt,
                "currency": currency_code(b.get("currency"), currency),
                "risk_score": risk_score,
                "risk_level": risk_level,
                "factors": {
                    "channel_rate": ch_rate,
                    "channel_score": round(ch_score, 1),
                    "dow_score": round(dow_score, 1),
                    "amount_score": amt_score,
                },
            }
        )

    predictions.sort(key=lambda x: -x["risk_score"])

    # Summary
    high_risk = sum(1 for p in predictions if p["risk_level"] == "high")
    medium_risk = sum(1 for p in predictions if p["risk_level"] == "medium")
    low_risk = sum(1 for p in predictions if p["risk_level"] == "low")
    potential_loss = {}
    for prediction in predictions:
        if prediction["risk_level"] in ("high", "medium") and prediction["total_amount"] is not None:
            add_amount(potential_loss, prediction["currency"], prediction["total_amount"])

    # Data quality
    total_hist = len(hist_bookings)
    if total_hist < 20:
        confidence = "low"
        confidence_note = "Veri yetersiz — tahminler gösterge niteliğindedir"
    elif total_hist < 100:
        confidence = "medium"
        confidence_note = f"{total_hist} geçmiş rezervasyona dayanmaktadır"
    else:
        confidence = "high"
        confidence_note = f"{total_hist} geçmiş rezervasyon analiz edildi"

    return {
        "predictions": predictions[:50], "matched_count": len(predictions), "truncated": len(predictions) > 50, "limit": 50,
        "risk_model": "rule_based_not_a_probability",
        "currency": currency,
        "start_date": now.date().isoformat(), "end_date": (lookahead - timedelta(days=1)).isoformat(),
        "value_basis": "high_and_medium_risk_gross_booking_value_not_expected_loss",
        "summary": {
            "total_upcoming": len(valid_upcoming),
            "high_risk": high_risk,
            "medium_risk": medium_risk,
            "low_risk": low_risk,
            "potential_loss": None if not potential_loss and any(row["total_amount"] is None and row["risk_level"] in ("high", "medium") for row in predictions) else single_amount(potential_loss),
            "potential_loss_by_currency": rounded_totals(potential_loss),
        },
        "historical_rates": {
            "by_channel": ch_rates,
            "by_day_of_week": {str(k): v for k, v in dow_rates.items()},
        },
        "days_ahead": days_ahead,
        "data_quality": {
            "confidence": confidence,
            "note": confidence_note,
            "historical_bookings": total_hist,
            "invalid_amounts": sum(row["total_amount"] is None for row in predictions),
            "invalid_dates": len(upcoming) - len(valid_upcoming), "invalid_history_dates": invalid_history_dates,
        },
    }
