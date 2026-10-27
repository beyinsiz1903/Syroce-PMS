"""IC Consumer — async, guaranteed, idempotent POS -> folio posting (Task #389).

Outbox/Compensation mechanism for POS folio charges. The POS hot path writes
the order/transaction record + an internal-consistency (IC) outbox event
atomically (intent durable). This consumer applies the actual folio charge and
balance recalc asynchronously, idempotently, and guaranteed-at-least-once via
the outbox worker.

Two event types (see core.outbox_service):

- ``pos.charge.posted.v1``   — apply POS folio charge(s) + recalc balance.
- ``pos.charge.reversed.v1`` — compensation: idempotently reverse a prior post.

Invariants (doctrine):

- IC events NEVER reach the channel manager / OTA / EventSyncService; the
  dispatcher routes them here BEFORE the CM mapping. external_calls stays [].
- Balance is recalculated from the ledger (folio_charges - payments), the SAME
  single strategy as ``pos_core._folio_balance_in_session`` — never ``$inc``.
- Apply-time late-charge / AR guard: a charge is NEVER silently written to a
  non-open (closed / checked-out) folio. It is routed to an operator-visible
  ``pos_late_charges`` record instead.
- Idempotency is enforced at the DB by the partial unique index
  ``ux_folio_charges_pos_source`` on (tenant_id, source_pos_order_id, line_no).
  Re-delivery of the same event re-inserts nothing (DuplicateKey skip) and the
  derived balance recalc is naturally idempotent.
- Fail-closed: if the idempotency index cannot be ensured, the apply returns a
  retryable result rather than risk a non-deduped double post.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.business_date_service import stamp_open_business_date
from core.outbox_service import POS_CHARGE_POSTED, POS_CHARGE_REVERSED
from core.report_cache import invalidate_financial_report_caches
from core.tenant_db import get_system_db
from domains.pms.pos_extensions._idem import ensure_compound_unique

logger = logging.getLogger("core.pos_folio_consumer")

_LATE_CHARGE_COLLECTION = "pos_late_charges"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _ensure_folio_charge_index() -> None:
    """Ensure the POS folio-charge idempotency index (fail-closed).

    Mirrors ``pos_core._ensure_pos_atomicity_indexes`` for the folio_charges
    side. Raising here is intentional: the caller turns it into a retryable
    apply result so the event is retried instead of double-posting.
    """
    await ensure_compound_unique(
        get_system_db().folio_charges,
        [("tenant_id", 1), ("source_pos_order_id", 1), ("line_no", 1)],
        partial_filter={"source_pos_order_id": {"$type": "string"}},
        name="ux_folio_charges_pos_source",
    )


async def _recalc_folio_balance(db, tenant_id: str, folio_id: str) -> float:
    """Recompute folio.balance from the ledger (charges - payments).

    Single balance strategy — identical formula to
    ``pos_core._folio_balance_in_session`` / ``core.utils.calculate_folio_balance``.
    The balance is a cache; the ledger (folio_charges + payments) is the single
    source of truth. NEVER ``$inc``.
    """
    ch_pipe = [
        {"$match": {"folio_id": folio_id, "tenant_id": tenant_id, "voided": {"$ne": True}}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$total", "$amount"]}}}},
    ]
    pay_pipe = [
        {"$match": {"folio_id": folio_id, "tenant_id": tenant_id, "voided": {"$ne": True}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    ch_doc = await db.folio_charges.aggregate(ch_pipe).to_list(1)
    pay_doc = await db.payments.aggregate(pay_pipe).to_list(1)
    total_charges = float(ch_doc[0]["total"]) if ch_doc else 0.0
    total_payments = float(pay_doc[0]["total"]) if pay_doc else 0.0
    balance = round(total_charges - total_payments, 2)
    await db.folios.update_one(
        {"id": folio_id, "tenant_id": tenant_id},
        {"$set": {"balance": balance, "updated_at": _now_iso()}},
    )
    folio = await db.folios.find_one({'tenant_id': tenant_id, 'id': folio_id}, {'_id': 0, 'booking_id': 1})
    if folio and folio.get('booking_id'):
        from core.booking_payment_state import refresh_booking_payment_state

        # Do not copy this one folio's balance to the reservation: split
        # windows, future room nights, deposits and non-cash settlements use
        # the same canonical summary as reservation detail/payment status.
        await refresh_booking_payment_state(db, tenant_id, folio['booking_id'], strict=True)
    return balance


async def _route_late_charge(
    db,
    tenant_id: str,
    folio: dict,
    order_id: str,
    charges: list[dict],
    folio_status: str,
) -> None:
    """Record an operator-visible late-charge / AR entry (idempotent).

    Used when the target folio is no longer open at apply time. We do NOT write
    to the closed folio; instead we durably record the unbilled POS charge so an
    operator can resolve it (post to a reopened folio, bill to AR, etc).

    Idempotent on (tenant_id, source_pos_order_id) via upsert so event
    re-delivery does not create duplicates.
    """
    total = round(sum(float(c.get("total", c.get("amount", 0)) or 0) for c in charges), 2)
    await db[_LATE_CHARGE_COLLECTION].update_one(
        {"tenant_id": tenant_id, "source_pos_order_id": order_id},
        {
            "$set": {
                "tenant_id": tenant_id,
                "source_pos_order_id": order_id,
                "folio_id": folio.get("id"),
                "booking_id": folio.get("booking_id"),
                "guest_id": folio.get("guest_id"),
                "folio_status_at_apply": folio_status,
                "charges": charges,
                "total": total,
                "status": "pending_review",
                "updated_at": _now_iso(),
            },
            "$setOnInsert": {"created_at": _now_iso()},
        },
        upsert=True,
    )
    logger.warning(
        "POS late-charge routed: order=%s folio=%s status=%s total=%s tenant=%s",
        order_id,
        folio.get("id"),
        folio_status,
        total,
        tenant_id,
    )


async def _apply_posted(event: dict[str, Any]) -> tuple[bool, str]:
    payload = event.get("payload") or {}
    tenant_id = event.get("tenant_id") or payload.get("tenant_id")
    folio_id = payload.get("folio_id")
    order_id = payload.get("source_pos_order_id")
    charges = payload.get("charges") or []

    if not tenant_id or not folio_id or not order_id:
        return False, "permanent: malformed POS posted event (missing tenant/folio/order)"
    if not charges:
        # Nothing to post (order had no folio lines). Treat as done.
        return True, f"no charges to post for order {order_id}"

    db = get_system_db()

    # A refund may be consumed before its original posting (workers/retries
    # have no cross-event ordering guarantee). The durable reversal INTENT is
    # a tombstone: never resurrect a refunded charge on a delayed delivery.
    reversal = await db.outbox_events.find_one({
        'tenant_id': tenant_id, 'entity_id': order_id, 'event_type': POS_CHARGE_REVERSED,
    })
    if reversal:
        return await _apply_reversed({
            'tenant_id': tenant_id,
            'payload': {**(reversal.get('payload') or {}), 'folio_id': folio_id,
                        'source_pos_order_id': order_id},
        })

    # Fail-closed: without the dedup index we could double-post on re-delivery.
    try:
        await _ensure_folio_charge_index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("folio_charge idempotency index ensure failed: %r", exc)
        return False, "retryable: folio_charge idempotency index unavailable"

    folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id})
    if not folio:
        # Request-time validated the folio existed; absence here is anomalous
        # (e.g. replication lag). Retry rather than silently drop the charge.
        return False, f"retryable: folio {folio_id} not found at apply time"

    folio_status = folio.get("status") or "open"
    expected_currency = folio.get('currency')
    if folio_status == 'open' and not expected_currency and folio.get('booking_id') and any(c.get('currency') for c in charges):
        booking = await db.bookings.find_one({'tenant_id': tenant_id, 'id': folio['booking_id']}, {'currency': 1}) or {}
        expected_currency = booking.get('currency')
    currency_mismatch = expected_currency and any(c.get('currency') and c['currency'] != expected_currency for c in charges)
    if folio_status != "open" or currency_mismatch:
        # Apply-time late-charge / AR guard — NEVER silently write to a
        # non-open folio.
        await _route_late_charge(db, tenant_id, folio, order_id, charges, 'currency_mismatch' if currency_mismatch else folio_status)
        reversal = await db.outbox_events.find_one({'tenant_id': tenant_id, 'entity_id': order_id, 'event_type': POS_CHARGE_REVERSED})
        if reversal:
            return await _apply_reversed({'tenant_id': tenant_id, 'payload': {**reversal.get('payload', {}), 'folio_id': folio_id, 'source_pos_order_id': order_id}})
        return True, (f"late-charge: folio {folio_id} not open (status={folio_status}); routed order {order_id} to AR/late-charge")

    inserted = 0
    for cdoc in charges:
        try:
            charge_doc = dict(cdoc)
            await stamp_open_business_date(db, tenant_id, charge_doc)
            await db.folio_charges.insert_one(charge_doc)
            inserted += 1
        except DuplicateKeyError:
            # E11000 can also come from an unrelated/obsolete unique index.
            # Only an exact stored source line proves a harmless redelivery.
            existing = await db.folio_charges.find_one({
                'tenant_id': tenant_id, 'folio_id': folio_id,
                'source_pos_order_id': order_id, 'line_no': cdoc.get('line_no'),
            })
            fields = ('booking_id', 'charge_category', 'amount', 'total', 'currency',
                      'vat_amount', 'tax_amount', 'subtotal', 'discount_amount', 'tax_breakdown')
            if existing and all(existing.get(field) == cdoc.get(field) for field in fields):
                continue
            if existing and await _matches_partitioned_source(db, tenant_id, order_id, cdoc):
                continue
            if inserted:
                await _recalc_folio_balance(db, tenant_id, folio_id)
                invalidate_financial_report_caches(tenant_id)
            if existing:
                return False, 'permanent: POS folio source line conflicts with stored financial values'
            return False, 'retryable: POS folio unique-index conflict; no matching source line was posted'

    balance = await _recalc_folio_balance(db, tenant_id, folio_id)
    # Close the check/insert race: a reversal worker can finish between the
    # first tombstone check and our writes. Reconcile again AFTER posting and
    # balance calculation, including when the first reversal saw no charges.
    reversal = await db.outbox_events.find_one({'tenant_id': tenant_id, 'entity_id': order_id, 'event_type': POS_CHARGE_REVERSED})
    if reversal:
        return await _apply_reversed({'tenant_id': tenant_id, 'payload': {**reversal.get('payload', {}), 'folio_id': folio_id, 'source_pos_order_id': order_id}})
    # Replay can be repairing a previously failed projection/cache hook.
    invalidate_financial_report_caches(tenant_id)
    return True, (f"posted {inserted} charge(s) for order {order_id} to folio {folio_id}; balance={balance}")


async def _matches_partitioned_source(db, tenant_id, order_id, source):
    """Prove a legitimate transfer, never acknowledge an unrelated E11000.

    Require the durable original snapshot AND exact financial conservation
    across the source line and every transferred part in every room.
    """
    from decimal import Decimal

    operations = getattr(db, 'folio_operations', None)
    if operations is None or not source.get('id'):
        return False
    fields = ('booking_id', 'folio_id', 'currency', 'charge_category', 'amount', 'total',
              'subtotal', 'discount_amount', 'vat_amount', 'tax_amount', 'tax_breakdown')
    # Later splits have a smaller pre-transfer snapshot. Find the exact
    # original source, independent of query-plan/natural insertion order.
    proof = await operations.find_one({'tenant_id': tenant_id, 'operation_type': 'split',
        'original_charge.id': source['id'], 'original_charge.source_pos_order_id': order_id,
        'original_charge.line_no': source.get('line_no'),
        **{'original_charge.' + field: source.get(field) for field in fields}})
    if not proof:
        return False
    original = proof['original_charge']
    parts = await db.folio_charges.find({'tenant_id': tenant_id, 'source_pos_order_id': order_id,
        'voided': {'$ne': True}, '$or': [{'line_no': source.get('line_no')},
                                      {'source_line_no': source.get('line_no')}]}, {'_id': 0}).to_list(None)
    if not parts or any(row.get('currency') != source.get('currency') or row.get('charge_category') != source.get('charge_category') for row in parts):
        return False
    try:
        for field in ('amount', 'total', 'subtotal', 'discount_amount', 'vat_amount', 'tax_amount'):
            value = original.get(field)
            if value is None:
                if any(row.get(field) is not None for row in parts):
                    return False
            elif sum((Decimal(str(row[field])) for row in parts), Decimal(0)) != Decimal(str(value)):
                return False
        taxes = original.get('tax_breakdown')
        if taxes is None:
            return all(row.get('tax_breakdown') is None for row in parts)
        if any(set(row.get('tax_breakdown', {})) != set(taxes) for row in parts):
            return False
        return all(sum((Decimal(str(row['tax_breakdown'][name])) for row in parts), Decimal(0)) == Decimal(str(value))
                   for name, value in taxes.items())
    except (ArithmeticError, ValueError, TypeError, KeyError):
        return False


async def _apply_reversed(event: dict[str, Any]) -> tuple[bool, str]:
    payload = event.get("payload") or {}
    tenant_id = event.get("tenant_id") or payload.get("tenant_id")
    folio_id = payload.get("folio_id")
    order_id = payload.get("source_pos_order_id")
    reason = payload.get("reason") or "POS reversal"

    if not tenant_id or not order_id:
        return False, "permanent: malformed POS reversed event (missing tenant/order)"

    db = get_system_db()
    now = _now_iso()

    # A service split can move debt to several other rooms. Reversing the
    # source order must refresh EVERY affected folio, not only the first one.
    affected = await db.folio_charges.find({'tenant_id': tenant_id, 'source_pos_order_id': order_id},
        {'_id': 0, 'folio_id': 1}).to_list(None)
    folio_ids = {row['folio_id'] for row in affected if row.get('folio_id')}
    if folio_id:
        folio_ids.add(folio_id)

    if not folio_id:
        charge = await db.folio_charges.find_one({'tenant_id': tenant_id, 'source_pos_order_id': order_id})
        folio_id = (charge or {}).get('folio_id')

    # Idempotent compensation: only flip charges that are not already voided.
    # Double-reversal → modified_count 0 → no-op.
    res = await db.folio_charges.update_many(
        {"tenant_id": tenant_id, "source_pos_order_id": order_id, "voided": {"$ne": True}},
        {"$set": {"voided": True, "voided_at": now, "void_reason": reason}},
    )

    # Reverse any operator-visible late-charge record for this order too.
    await db[_LATE_CHARGE_COLLECTION].update_one(
        {"tenant_id": tenant_id, "source_pos_order_id": order_id, "status": {"$ne": "reversed"}},
        {"$set": {"status": "reversed", "reversed_at": now, "reverse_reason": reason}},
    )

    balances = {fid: await _recalc_folio_balance(db, tenant_id, fid) for fid in sorted(folio_ids)}
    invalidate_financial_report_caches(tenant_id)
    if folio_id:
        balance = balances.get(folio_id, 0)
        return True, (f"reversed {res.modified_count} charge(s) for order {order_id}; folio {folio_id} balance={balance}")
    return True, f"reversed {res.modified_count} charge(s) for order {order_id}"


async def handle_ic_pos_event(event: dict[str, Any]) -> tuple[bool, str]:
    """Entry point for the outbox dispatcher's IC branch.

    Returns (success, message) with the same contract as
    ``dispatch_outbox_event``: a False + "retryable: ..." message retries,
    False + "permanent: ..." goes to the DLQ.
    """
    event_type = event.get("event_type", "")
    try:
        if event_type == POS_CHARGE_POSTED:
            return await _apply_posted(event)
        if event_type == POS_CHARGE_REVERSED:
            return await _apply_reversed(event)
    except Exception as exc:  # durable source lines are safe to re-deliver
        logger.warning('POS folio/projection apply needs retry: %s', type(exc).__name__)
        return False, 'retryable: POS folio or reservation projection refresh failed'
    return False, f"permanent: unknown IC event_type '{event_type}'"


async def drain_pending_pos_charges(tenant_id: str, folio_id: str) -> int:
    """Apply any still-pending POS folio-charge events for a folio inline.

    Called from the checkout / folio-close flow BEFORE the folio is closed so
    queued async POS charges land on the still-open folio (and are counted in
    the outstanding-balance check) instead of being routed to late-charge/AR
    after close.

    Best-effort and idempotent: applying a charge here is DuplicateKey-safe, so
    a concurrent worker apply of the same event is a harmless no-op. Returns the
    number of events drained.
    """
    if not tenant_id or not folio_id:
        return 0
    db = get_system_db()
    cursor = db.outbox_events.find(
        {
            "tenant_id": tenant_id,
            "event_type": POS_CHARGE_POSTED,
            "payload.folio_id": folio_id,
            "status": {"$in": ["pending", "retry", "processing"]},
        },
        {"_id": 0},
    )
    drained = 0
    async for event in cursor:
        success, _msg = await _apply_posted(event)
        if success:
            await db.outbox_events.update_one(
                {"id": event.get("id"), "tenant_id": tenant_id},
                {
                    "$set": {
                        "status": "processed",
                        "processed_at": _now_iso(),
                        "updated_at": _now_iso(),
                        "last_error": None,
                    }
                },
            )
            drained += 1
    return drained
