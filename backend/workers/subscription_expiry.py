"""Subscription expiry worker.

Hourly: marks subscriptions whose end_date has passed as expired.
Sends a heads-up email at 7/3/1 days remaining (best-effort).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from core.transient_db_guard import TransientFailureTracker

logger = logging.getLogger(__name__)

_transient_tracker = TransientFailureTracker("sub-expiry")


def _db():
    from server import db

    return db


async def _expire_due() -> int:
    db = _db()
    now_iso = datetime.now(UTC).isoformat()
    res = await db.tenant_subscriptions.update_many(
        {
            "status": "active",
            "end_date": {"$ne": None, "$lte": now_iso},
        },
        {"$set": {"status": "expired", "expired_at": now_iso}},
    )
    if res.modified_count:
        logger.info("[sub-expiry] marked %d subscriptions expired", res.modified_count)
    return res.modified_count


async def _send_warnings() -> None:
    """Best-effort heads-up emails for subs ending in 7/3/1 day(s)."""
    try:
        from core.email import send_email
    except Exception:
        return
    db = _db()
    now = datetime.now(UTC)
    for days in (7, 3, 1):
        target = now + timedelta(days=days)
        window_start = target - timedelta(hours=1)
        window_end = target
        cur = db.tenant_subscriptions.find(
            {
                "status": "active",
                "end_date": {
                    "$gte": window_start.isoformat(),
                    "$lt": window_end.isoformat(),
                },
            },
            {"_id": 0},
        )
        async for sub in cur:
            tenant = await db.tenants.find_one({"id": sub["tenant_id"]}, {"_id": 0, "email": 1, "property_name": 1})
            email = (tenant or {}).get("email")
            if not email:
                continue
            try:
                # Bug CN (architect Round-1 ek bulgu): tenant.property_name ve
                # sub.product_key tenant-controlled — raw f-string HTML
                # injection olur. safe_html_value ile escape ediyoruz.
                from core.mailing_safe import safe_html_value, safe_subject_value

                hotel_html = safe_html_value((tenant or {}).get("property_name") or "Otelimiz")
                product_html = safe_html_value(sub["product_key"])
                product_subj = safe_subject_value(sub["product_key"])
                await send_email(
                    to=email,
                    subject=f"{product_subj} aboneliğinizin sona ermesine {days} gün kaldı",
                    html=f"""
                    <p>Merhaba {hotel_html},</p>
                    <p><b>{product_html}</b> aboneliğinizin sona ermesine
                    <b>{days} gün</b> kaldı.</p>
                    <p>Modülün kesintisiz çalışması için Modül Pazarı sayfasından
                    yenileyebilirsiniz.</p>
                    """,
                )
            except Exception as e:
                logger.warning("[sub-expiry] warn email failed: %s", e)


async def run_loop(interval_seconds: int = 3600) -> None:
    logger.info("[sub-expiry] worker started, interval=%ss", interval_seconds)
    while True:
        try:
            await _expire_due()
            await _send_warnings()
            _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
        except Exception as e:
            _transient_tracker.log_exception(
                logger,
                e,
                TransientFailureTracker.OUTER_LOOP_KEY,
                context="tick",
                non_transient_msg="%s tick failed: %s",
            )
        await asyncio.sleep(interval_seconds)
