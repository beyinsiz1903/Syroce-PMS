"""
Night Audit — Financial Service (Production-Grade)
Provides financial reporting, revenue reconciliation, and payment integrity checks.
"""
import asyncio
import logging

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)

# NOT: Konaklama vergisi oranı artık tek doğruluk kaynağı olarak
# `routers.finance.konaklama_vergisi_core.get_accommodation_tax_rate`
# fonksiyonundan çözülür. Bu modülde tax breakdown zaten `tax_breakdown`
# alanlarından aggregate edilir; sabit tanım gerekli değildir.
DEFAULT_VAT_RATE = 0.10


class FinancialService:
    """Financial reporting and reconciliation for night audit."""

    def __init__(self):
        from core.database import db
        self._db = db

    async def get_daily_financial_summary(
        self, ctx: OperationContext, business_date: str,
    ) -> ServiceResult:
        """Generate comprehensive daily financial summary.

        Perf: 6 bağımsız aggregation/lookup paralel çalışır (asyncio.gather);
        seri await chain'i kaldırıldı. Hata izolasyonu için return_exceptions=True;
        tek bir alt sorgu başarısız olsa bile diğerleri sonuç döndürmeye devam eder.
        """
        # Revenue by category from folio_charges
        charge_pipeline = [
            {"$match": {
                "tenant_id": ctx.tenant_id,
                "date": business_date,
                "voided": {"$ne": True},
            }},
            {"$group": {
                "_id": "$charge_category",
                "total_amount": {"$sum": "$amount"},
                "total_tax": {"$sum": "$tax_amount"},
                "total_with_tax": {"$sum": "$total"},
                "count": {"$sum": 1},
            }},
        ]

        # Payments received today
        payment_pipeline = [
            {"$match": {
                "tenant_id": ctx.tenant_id,
                "status": {"$ne": "voided"},
                "$or": [
                    {"date": business_date},
                    {"payment_date": business_date},
                ],
            }},
            {"$group": {
                "_id": "$payment_method",
                "total_amount": {"$sum": "$amount"},
                "count": {"$sum": 1},
            }},
        ]

        # Also check inline folio payments
        folio_payment_pipeline = [
            {"$match": {"tenant_id": ctx.tenant_id, "status": "open"}},
            {"$unwind": {"path": "$payments", "preserveNullAndEmptyArrays": False}},
            {"$match": {
                "$or": [
                    {"payments.date": business_date},
                    {"payments.posted_at": {"$regex": f"^{business_date}"}},
                ],
            }},
            {"$group": {
                "_id": "$payments.payment_method",
                "total_amount": {"$sum": "$payments.amount"},
                "count": {"$sum": 1},
            }},
        ]

        # Tax breakdown
        tax_pipeline = [
            {"$match": {
                "tenant_id": ctx.tenant_id,
                "date": business_date,
                "voided": {"$ne": True},
                "tax_breakdown": {"$exists": True},
            }},
            {"$group": {
                "_id": None,
                "total_vat": {"$sum": "$tax_breakdown.vat"},
                "total_accommodation_tax": {"$sum": "$tax_breakdown.accommodation_tax"},
            }},
        ]

        # Open balance pipeline (combines count + balance aggregation)
        open_balance_pipeline = [
            {"$match": {"tenant_id": ctx.tenant_id, "status": "open"}},
            {"$group": {
                "_id": None,
                "total_balance": {"$sum": "$balance"},
                "positive_balance": {
                    "$sum": {"$cond": [{"$gt": ["$balance", 0]}, "$balance", 0]}
                },
                "negative_balance": {
                    "$sum": {"$cond": [{"$lt": ["$balance", 0]}, "$balance", 0]}
                },
                "count": {"$sum": 1},
            }},
        ]

        async def _agg(coll, pipeline):
            return await coll.aggregate(pipeline).to_list(length=None)

        # Parallel fan-out — 6 bağımsız sorgu tek round-trip penceresinde
        (
            charge_docs,
            payment_docs,
            folio_payment_docs,
            tax_docs,
            open_balance_docs,
            audit_run,
        ) = await asyncio.gather(
            _agg(self._db.folio_charges, charge_pipeline),
            _agg(self._db.payments, payment_pipeline),
            _agg(self._db.folios, folio_payment_pipeline),
            _agg(self._db.folio_charges, tax_pipeline),
            _agg(self._db.folios, open_balance_pipeline),
            self._db.night_audit_runs.find_one(
                {"tenant_id": ctx.tenant_id, "business_date": business_date},
                {"_id": 0},
            ),
            return_exceptions=True,
        )

        def _ok(result, default):
            if isinstance(result, BaseException):
                logger.warning("financial_summary subquery failed: %s", result)
                return default
            return result

        charge_docs = _ok(charge_docs, [])
        payment_docs = _ok(payment_docs, [])
        folio_payment_docs = _ok(folio_payment_docs, [])
        tax_docs = _ok(tax_docs, [])
        open_balance_docs = _ok(open_balance_docs, [])
        audit_run = _ok(audit_run, None)

        # In-memory reduce
        revenue_by_category: dict = {}
        total_revenue = 0.0
        total_tax = 0.0
        total_charges_count = 0
        for doc in charge_docs:
            cat = doc["_id"] or "other"
            revenue_by_category[cat] = {
                "amount": round(doc["total_amount"], 2),
                "tax": round(doc["total_tax"], 2),
                "total": round(doc["total_with_tax"], 2),
                "count": doc["count"],
            }
            total_revenue += doc["total_amount"]
            total_tax += doc["total_tax"]
            total_charges_count += doc["count"]

        payments_by_method: dict = {}
        total_payments = 0.0
        total_payments_count = 0
        for doc in payment_docs:
            method = doc["_id"] or "other"
            payments_by_method[method] = {
                "amount": round(doc["total_amount"], 2),
                "count": doc["count"],
            }
            total_payments += doc["total_amount"]
            total_payments_count += doc["count"]

        for doc in folio_payment_docs:
            method = doc["_id"] or "other"
            if method in payments_by_method:
                payments_by_method[method]["amount"] = round(
                    payments_by_method[method]["amount"] + doc["total_amount"], 2
                )
                payments_by_method[method]["count"] += doc["count"]
            else:
                payments_by_method[method] = {
                    "amount": round(doc["total_amount"], 2),
                    "count": doc["count"],
                }
            total_payments += doc["total_amount"]
            total_payments_count += doc["count"]

        tax_breakdown = {"vat": 0.0, "accommodation_tax": 0.0}
        for doc in tax_docs:
            tax_breakdown["vat"] = round(doc.get("total_vat", 0), 2)
            tax_breakdown["accommodation_tax"] = round(doc.get("total_accommodation_tax", 0), 2)

        open_balance = {"total": 0.0, "receivable": 0.0, "overpayment": 0.0}
        open_folios_count = 0
        for doc in open_balance_docs:
            open_balance["total"] = round(doc.get("total_balance", 0), 2)
            open_balance["receivable"] = round(doc.get("positive_balance", 0), 2)
            open_balance["overpayment"] = round(abs(doc.get("negative_balance", 0)), 2)
            open_folios_count = doc.get("count", 0)

        return ServiceResult.success({
            "business_date": business_date,
            "revenue": {
                "total": round(total_revenue, 2),
                "total_with_tax": round(total_revenue + total_tax, 2),
                "by_category": revenue_by_category,
                "charges_count": total_charges_count,
            },
            "tax": {
                "total": round(total_tax, 2),
                "breakdown": tax_breakdown,
            },
            "payments": {
                "total": round(total_payments, 2),
                "by_method": payments_by_method,
                "payments_count": total_payments_count,
            },
            "open_folios": {
                "count": open_folios_count,
                "balance": open_balance,
            },
            "net_position": round(total_revenue + total_tax - total_payments, 2),
            "audit_status": audit_run.get("status") if audit_run else "not_run",
        })

    async def get_payment_reconciliation(
        self, ctx: OperationContext, business_date: str,
    ) -> ServiceResult:
        """Reconcile charges vs payments for a given date.

        Perf: charges + payments + high-balance folios paralel çekilir; seri
        await zinciri kaldırıldı. Bookings bulk-fetch yine tek round-trip ($in).
        """
        # Parallel fan-out: charges + payments + high-balance folios
        async def _to_list(cursor, n):
            return await cursor.to_list(n)

        charges, payments, high_balance_folios = await asyncio.gather(
            _to_list(self._db.folio_charges.find({
                "tenant_id": ctx.tenant_id,
                "date": business_date,
                "voided": {"$ne": True},
            }, {"_id": 0, "id": 1, "booking_id": 1, "charge_category": 1,
                "amount": 1, "tax_amount": 1, "total": 1, "description": 1}), 1000),
            _to_list(self._db.payments.find({
                "tenant_id": ctx.tenant_id,
                "status": {"$ne": "voided"},
                "$or": [{"date": business_date}, {"payment_date": business_date}],
            }, {"_id": 0, "id": 1, "booking_id": 1, "amount": 1,
                "payment_method": 1, "description": 1}), 1000),
            _to_list(self._db.folios.find({
                "tenant_id": ctx.tenant_id,
                "status": "open",
                "$or": [
                    {"balance": {"$gt": 500}},
                    {"balance": {"$lt": -100}},
                ],
            }, {"_id": 0, "id": 1, "folio_number": 1, "balance": 1, "booking_id": 1}), 200),
        )
        total_charges = sum(c.get("total", 0) for c in charges)
        total_payments_amount = sum(p.get("amount", 0) for p in payments)

        # Discrepancy detection
        discrepancies = []

        # Check for duplicate charges (same booking, category, amount, date)
        seen_charges = {}
        for c in charges:
            key = f"{c.get('booking_id')}_{c.get('charge_category')}_{c.get('amount')}"
            if key in seen_charges:
                discrepancies.append({
                    "type": "duplicate_charge",
                    "severity": "warning",
                    "message": f"Olasi tekrar masraf: {c.get('description', 'N/A')} - {c.get('amount', 0)} TL",
                    "entity_id": c.get("id"),
                    "booking_id": c.get("booking_id"),
                    "amount": c.get("amount", 0),
                })
            seen_charges[key] = c

        # Bulk-fetch all referenced bookings in ONE round-trip (was N+1).
        # Single $in over the union of charge.booking_id values; we read all
        # fields needed by both the orphan check and the rate-discrepancy
        # check so the second loop hits memory only.
        booking_ids = {c.get("booking_id") for c in charges if c.get("booking_id")}
        bookings_by_id: dict[str, dict] = {}
        if booking_ids:
            bookings_cursor = self._db.bookings.find(
                {"id": {"$in": list(booking_ids)}, "tenant_id": ctx.tenant_id},
                {"_id": 0, "id": 1, "status": 1, "room_rate": 1, "rate": 1},
            )
            async for b in bookings_cursor:
                bid = b.get("id")
                if bid:
                    bookings_by_id[bid] = b

        # Check for charges without matching bookings
        for bid in booking_ids:
            if bid not in bookings_by_id:
                discrepancies.append({
                    "type": "orphan_charge",
                    "severity": "error",
                    "message": f"Masraf sahipsiz: Rezervasyon bulunamadi ({bid[:8]}...)",
                    "booking_id": bid,
                })

        # Check for rate discrepancy (room charges vs booking rate)
        room_charges = [c for c in charges if c.get("charge_category") == "room"]
        for rc in room_charges:
            bid = rc.get("booking_id")
            if not bid:
                continue
            booking = bookings_by_id.get(bid)
            if booking:
                expected_rate = booking.get("room_rate") or booking.get("rate") or 0
                actual_rate = rc.get("amount", 0)
                if expected_rate > 0 and abs(actual_rate - expected_rate) > 0.01:
                    discrepancies.append({
                        "type": "rate_discrepancy",
                        "severity": "warning",
                        "message": f"Oran tutarsizligi: Beklenen {expected_rate} TL, Gercek {actual_rate} TL",
                        "booking_id": bid,
                        "expected": expected_rate,
                        "actual": actual_rate,
                    })

        # High-value unbalanced folios — already gathered above in parallel batch
        for f in high_balance_folios:
            if f.get("balance", 0) > 1000:
                discrepancies.append({
                    "type": "high_balance",
                    "severity": "error",
                    "message": f"Yuksek bakiyeli folio: {f.get('folio_number')} - {f.get('balance', 0):.2f} TL",
                    "entity_id": f.get("id"),
                    "amount": f.get("balance", 0),
                })

        variance = round(total_charges - total_payments_amount, 2)

        return ServiceResult.success({
            "business_date": business_date,
            "charges_total": round(total_charges, 2),
            "charges_count": len(charges),
            "payments_total": round(total_payments_amount, 2),
            "payments_count": len(payments),
            "variance": variance,
            "is_balanced": abs(variance) < 0.01,
            "discrepancies": discrepancies,
            "discrepancy_count": len(discrepancies),
            "high_balance_folios": high_balance_folios,
            "high_balance_count": len(high_balance_folios),
        })

    async def get_financial_report(
        self, ctx: OperationContext,
        start_date: str, end_date: str,
    ) -> ServiceResult:
        """Generate financial report for a date range."""
        # Revenue trend by date
        revenue_pipeline = [
            {"$match": {
                "tenant_id": ctx.tenant_id,
                "date": {"$gte": start_date, "$lte": end_date},
                "voided": {"$ne": True},
            }},
            {"$group": {
                "_id": {"date": "$date", "category": "$charge_category"},
                "amount": {"$sum": "$amount"},
                "tax": {"$sum": "$tax_amount"},
                "total": {"$sum": "$total"},
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id.date": 1}},
        ]

        daily_revenue = {}
        category_totals = {}
        grand_total_revenue = 0.0
        grand_total_tax = 0.0

        async for doc in self._db.folio_charges.aggregate(revenue_pipeline):
            date = doc["_id"]["date"]
            cat = doc["_id"]["category"] or "other"

            if date not in daily_revenue:
                daily_revenue[date] = {"date": date, "categories": {}, "total": 0.0, "tax": 0.0}
            daily_revenue[date]["categories"][cat] = {
                "amount": round(doc["amount"], 2),
                "tax": round(doc["tax"], 2),
                "count": doc["count"],
            }
            daily_revenue[date]["total"] = round(daily_revenue[date]["total"] + doc["amount"], 2)
            daily_revenue[date]["tax"] = round(daily_revenue[date]["tax"] + doc["tax"], 2)

            if cat not in category_totals:
                category_totals[cat] = {"amount": 0.0, "tax": 0.0, "count": 0}
            category_totals[cat]["amount"] = round(category_totals[cat]["amount"] + doc["amount"], 2)
            category_totals[cat]["tax"] = round(category_totals[cat]["tax"] + doc["tax"], 2)
            category_totals[cat]["count"] += doc["count"]

            grand_total_revenue += doc["amount"]
            grand_total_tax += doc["tax"]

        # Payment trend
        payment_pipeline = [
            {"$match": {
                "tenant_id": ctx.tenant_id,
                "status": {"$ne": "voided"},
                "$or": [
                    {"date": {"$gte": start_date, "$lte": end_date}},
                    {"payment_date": {"$gte": start_date, "$lte": end_date}},
                ],
            }},
            {"$group": {
                "_id": "$payment_method",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
            }},
        ]
        payment_method_totals = {}
        grand_total_payments = 0.0
        async for doc in self._db.payments.aggregate(payment_pipeline):
            method = doc["_id"] or "other"
            payment_method_totals[method] = {
                "amount": round(doc["total"], 2),
                "count": doc["count"],
            }
            grand_total_payments += doc["total"]

        # Audit runs in range
        audit_runs = await self._db.night_audit_runs.find(
            {
                "tenant_id": ctx.tenant_id,
                "business_date": {"$gte": start_date, "$lte": end_date},
            },
            {"_id": 0, "audit_id": 1, "business_date": 1, "status": 1,
             "total_room_revenue": 1, "total_tax_amount": 1,
             "rooms_processed": 1, "charges_posted": 1,
             "no_shows_processed": 1, "exceptions_count": 1,
             "duration_ms": 1},
        ).sort("business_date", 1).to_list(100)

        # Occupancy data for the range
        occupancy_pipeline = [
            {"$match": {
                "tenant_id": ctx.tenant_id,
                "status": {"$in": ["checked_in", "checked_out"]},
                "check_in": {"$lte": end_date},
                "check_out": {"$gte": start_date},
            }},
            {"$count": "total_bookings"},
        ]
        occ_result = await self._db.bookings.aggregate(occupancy_pipeline).to_list(1)
        total_bookings = occ_result[0]["total_bookings"] if occ_result else 0

        total_rooms = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id})

        return ServiceResult.success({
            "start_date": start_date,
            "end_date": end_date,
            "summary": {
                "total_revenue": round(grand_total_revenue, 2),
                "total_tax": round(grand_total_tax, 2),
                "total_with_tax": round(grand_total_revenue + grand_total_tax, 2),
                "total_payments": round(grand_total_payments, 2),
                "net_position": round(grand_total_revenue + grand_total_tax - grand_total_payments, 2),
                "total_bookings": total_bookings,
                "total_rooms": total_rooms,
            },
            "revenue_by_category": category_totals,
            "revenue_by_date": list(daily_revenue.values()),
            "payments_by_method": payment_method_totals,
            "audit_runs": audit_runs,
        })

    async def _enrich_with_guest_room(
        self, tenant_id: str, items: list[dict],
    ) -> list[dict]:
        """items[]'taki guest_id/room_id/booking_id'leri kullanarak
        guest_name + room_no doldur. Hepsi tenant-scoped."""
        if not items:
            return items
        booking_ids = {it.get("booking_id") for it in items if it.get("booking_id")}
        booking_map: dict = {}
        if booking_ids:
            async for b in self._db.bookings.find(
                {"tenant_id": tenant_id, "id": {"$in": list(booking_ids)}},
                {"_id": 0, "id": 1, "guest_id": 1, "guest_name": 1,
                 "room_id": 1, "room_no": 1, "confirmation_code": 1},
            ):
                booking_map[b["id"]] = b

        # guests/rooms koleksiyonlari OTORITE — bookings.guest_name eski sync
        # artigi olabilir ("V4 Refund"). Tum guest_id/room_id'leri lookup'a koy.
        guest_ids = set()
        room_ids = set()
        for it in items:
            b = booking_map.get(it.get("booking_id")) or {}
            gid = it.get("guest_id") or b.get("guest_id")
            rid = it.get("room_id") or b.get("room_id")
            if gid:
                guest_ids.add(gid)
            if rid:
                room_ids.add(rid)

        from core.guest_name_utils import is_placeholder_guest_name
        guest_map: dict = {}
        if guest_ids:
            async for g in self._db.guests.find(
                {"tenant_id": tenant_id, "id": {"$in": list(guest_ids)}},
                {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1},
            ):
                full = (g.get("name") or
                        " ".join(filter(None, [g.get("first_name"), g.get("last_name")])).strip())
                # Placeholder ("C4", "V4 Refund") guest_map'e KOYMA —
                # display_guest_name fallback'a düşsün.
                if full and not is_placeholder_guest_name(full):
                    guest_map[g["id"]] = full

        room_map: dict = {}
        if room_ids:
            async for r in self._db.rooms.find(
                {"tenant_id": tenant_id, "id": {"$in": list(room_ids)}},
                {"_id": 0, "id": 1, "room_number": 1, "room_no": 1},
            ):
                room_map[r["id"]] = r.get("room_number") or r.get("room_no")

        from core.guest_name_utils import display_guest_name, is_placeholder_guest_name
        for it in items:
            b = booking_map.get(it.get("booking_id")) or {}
            # Onceligi guests koleksiyonu kazanir; lookup basarisiz olursa
            # booking_map ve son olarak it'in mevcut degeri fallback olur.
            gid = it.get("guest_id") or b.get("guest_id")
            authoritative_name = guest_map.get(gid) if gid else None
            if authoritative_name:
                it["guest_name"] = authoritative_name
            else:
                # Booking'deki guest_name de placeholder olabilir — display_guest_name
                # fallback uygulayarak "Misafir <ID8>" göster.
                fallback_raw = it.get("guest_name") or b.get("guest_name")
                if is_placeholder_guest_name(fallback_raw) and gid:
                    it["guest_name"] = display_guest_name(fallback_raw, gid)
                elif not it.get("guest_name"):
                    it["guest_name"] = fallback_raw
            rid = it.get("room_id") or b.get("room_id")
            authoritative_room = room_map.get(rid) if rid else None
            if authoritative_room:
                it["room_no"] = authoritative_room
            elif not it.get("room_no"):
                it["room_no"] = b.get("room_no") or None
            if not it.get("booking_id") and b.get("id"):
                it["booking_id"] = b["id"]
            if not it.get("confirmation_code") and b.get("confirmation_code"):
                it["confirmation_code"] = b["confirmation_code"]
        return items

    async def get_integrity_check(
        self, ctx: OperationContext, business_date: str,
    ) -> ServiceResult:
        """Run financial integrity checks for a given business date.

        Perf: 6 bağımsız check paralel çalışır (asyncio.gather). Önceden seri
        await zinciri + her check sonrası ayrı `_enrich_with_guest_room` çağrısı
        4×3=12 ek round-trip yapıyordu; şimdi tek geçişte ortak enrichment.
        Check #4 (room rate) için DB-level $or filtresi ile sadece sıfır/eksik
        fiyatlı kayıtlar çekilir (full scan değil).
        """
        ITEM_LIMIT = 50
        tid = ctx.tenant_id

        async def _check1_bookings():
            bookings = await self._db.bookings.find(
                {"tenant_id": tid, "status": "checked_in"},
                {"_id": 0, "id": 1, "folio_id": 1, "guest_name": 1,
                 "room_no": 1, "guest_id": 1, "room_id": 1},
            ).to_list(500)
            # booking.folio_id dokumana HIC yazilmiyor (tek yonlu bag) →
            # "folyosu yok" tespitini booking.folio_id yerine folios
            # koleksiyonundaki acik guest folyo varligi uzerinden yap.
            # Aksi halde HER checked-in booking yanlislikla "folyosuz"
            # olarak isaretleniyordu (false-positive seli).
            open_folio_bids: set = set()
            bids = [b["id"] for b in bookings if b.get("id")]
            if bids:
                async for f in self._db.folios.find(
                    {"tenant_id": tid, "booking_id": {"$in": bids},
                     "folio_type": "guest", "status": "open"},
                    {"_id": 0, "booking_id": 1},
                ):
                    open_folio_bids.add(f["booking_id"])
            return bookings, open_folio_bids

        async def _check2_voided():
            q = {"tenant_id": tid, "date": business_date, "voided": True}
            return await asyncio.gather(
                self._db.folio_charges.count_documents(q),
                self._db.folio_charges.find(q, {
                    "_id": 0, "id": 1, "folio_id": 1, "booking_id": 1, "amount": 1,
                    "description": 1, "voided_reason": 1,
                }).limit(ITEM_LIMIT).to_list(ITEM_LIMIT),
            )

        async def _check3_negative():
            q = {"tenant_id": tid, "status": "open", "balance": {"$lt": -0.01}}
            return await asyncio.gather(
                self._db.folios.count_documents(q),
                self._db.folios.find(q, {
                    "_id": 0, "id": 1, "booking_id": 1, "balance": 1, "guest_name": 1,
                    "room_no": 1, "guest_id": 1, "room_id": 1,
                }).limit(ITEM_LIMIT).to_list(ITEM_LIMIT),
            )

        async def _check4_rate():
            # DB-level filter — Python truthy fallback semantiği:
            # effective = room_rate if truthy else (rate if truthy else 0)
            # issue iff effective <= 0. "Truthy" burada None/missing/0 değil.
            # Örn: room_rate=0, rate=120 → effective=120 → NO issue (eski mantık).
            q = {
                "tenant_id": tid,
                "status": "checked_in",
                "$expr": {
                    "$lte": [
                        {"$cond": [
                            # room_rate truthy mi?  (not null AND not 0)
                            {"$and": [
                                {"$ne": [{"$ifNull": ["$room_rate", None]}, None]},
                                {"$ne": ["$room_rate", 0]},
                            ]},
                            "$room_rate",
                            {"$cond": [
                                # rate truthy mi?
                                {"$and": [
                                    {"$ne": [{"$ifNull": ["$rate", None]}, None]},
                                    {"$ne": ["$rate", 0]},
                                ]},
                                "$rate",
                                0,
                            ]},
                        ]},
                        0,
                    ],
                },
            }
            return await asyncio.gather(
                self._db.bookings.count_documents(q),
                self._db.bookings.find(q, {
                    "_id": 0, "id": 1, "room_rate": 1, "rate": 1, "guest_name": 1,
                    "room_no": 1, "guest_id": 1, "room_id": 1,
                }).limit(ITEM_LIMIT).to_list(ITEM_LIMIT),
            )

        async def _check5_closed():
            closed_folios = await self._db.folios.find(
                {"tenant_id": tid, "status": "closed"},
                {"_id": 0, "id": 1},
            ).to_list(500)
            closed_ids = [f["id"] for f in closed_folios]
            if not closed_ids:
                return 0, []
            q = {"tenant_id": tid, "folio_id": {"$in": closed_ids},
                 "date": business_date, "voided": {"$ne": True}}
            return await asyncio.gather(
                self._db.folio_charges.count_documents(q),
                self._db.folio_charges.find(q, {
                    "_id": 0, "folio_id": 1, "booking_id": 1, "amount": 1, "description": 1,
                }).limit(ITEM_LIMIT).to_list(ITEM_LIMIT),
            )

        async def _check6_audit():
            audit_run = await self._db.night_audit_runs.find_one(
                {"tenant_id": tid, "business_date": business_date,
                 "status": {"$in": ["completed", "completed_with_exceptions"]}},
                {"_id": 0, "audit_id": 1, "charges_posted": 1},
            )
            if not audit_run:
                return None
            actual = await self._db.folio_charges.count_documents({
                "tenant_id": tid,
                "audit_id": audit_run["audit_id"],
                "voided": {"$ne": True},
            })
            return audit_run, actual

        r1, r2, r3, r4, r5, r6 = await asyncio.gather(
            _check1_bookings(), _check2_voided(), _check3_negative(),
            _check4_rate(), _check5_closed(), _check6_audit(),
            return_exceptions=True,
        )

        def _ok(result, default):
            if isinstance(result, BaseException):
                logger.warning("integrity_check subquery failed: %s", result)
                return default
            return result

        checked_in, open_folio_bids = _ok(r1, ([], set()))
        voided_count, voided_raw = _ok(r2, (0, []))
        neg_balance, neg_raw = _ok(r3, (0, []))
        rate_count, rate_raw = _ok(r4, (0, []))
        closed_folio_charges, closed_raw = _ok(r5, (0, []))
        audit_result = _ok(r6, None)

        # Gercekten acik folyosu olmayan checked-in booking'ler (folios
        # koleksiyonundan cozuldu; booking.folio_id'ye guvenilmez).
        missing_folios = [
            b for b in checked_in
            if not (b.get("folio_id") or b["id"] in open_folio_bids)
        ]
        mf_items = [{"booking_id": b["id"], "guest_name": b.get("guest_name"),
                     "room_no": b.get("room_no"), "guest_id": b.get("guest_id"),
                     "room_id": b.get("room_id"), "action": "open_booking"}
                    for b in missing_folios[:ITEM_LIMIT]]

        voided_items = [{
            "folio_id": ch.get("folio_id"), "booking_id": ch.get("booking_id"),
            "amount": ch.get("amount"), "description": ch.get("description"),
            "reason": ch.get("voided_reason"), "action": "open_folio",
        } for ch in voided_raw]

        neg_items = [{
            "folio_id": f.get("id"), "booking_id": f.get("booking_id"),
            "balance": round(f.get("balance", 0), 2),
            "overpayment": round(abs(f.get("balance", 0)), 2),
            "guest_name": f.get("guest_name"), "room_no": f.get("room_no"),
            "guest_id": f.get("guest_id"), "room_id": f.get("room_id"),
            "action": "open_folio",
        } for f in neg_raw]

        rate_items = [{
            "booking_id": b["id"],
            "rate": b.get("room_rate") or b.get("rate") or 0,
            "guest_name": b.get("guest_name"), "room_no": b.get("room_no"),
            "guest_id": b.get("guest_id"), "room_id": b.get("room_id"),
            "action": "open_booking",
        } for b in rate_raw]

        closed_charge_items = [{
            "folio_id": ch.get("folio_id"), "booking_id": ch.get("booking_id"),
            "amount": ch.get("amount"), "description": ch.get("description"),
            "action": "open_folio",
        } for ch in closed_raw]

        # Single shared enrichment pass — bookings/guests/rooms tek tek $in.
        all_items_to_enrich = mf_items + voided_items + neg_items + rate_items + closed_charge_items
        if all_items_to_enrich:
            await self._enrich_with_guest_room(tid, all_items_to_enrich)

        checks = [
            {
                "check": "bookings_with_folios",
                "label": "Rezervasyon-Folio Eslesmesi",
                "status": "pass" if not missing_folios else "fail",
                "detail": f"{len(checked_in)} aktif rezervasyondan {len(missing_folios)} tanesinin folyosu yok",
                "count": len(missing_folios),
                "items": mf_items,
            },
            {
                "check": "voided_charges",
                "label": "Iptal Edilen Masraflar",
                "status": "pass" if voided_count == 0 else "warning",
                "detail": f"Bugun {voided_count} masraf iptal edildi",
                "count": voided_count,
                "items": voided_items,
            },
            {
                "check": "negative_balance_folios",
                "label": "Negatif Bakiyeli Folyolar",
                "status": "pass" if neg_balance == 0 else "warning",
                "detail": f"{neg_balance} folyoda negatif bakiye (fazla odeme)",
                "count": neg_balance,
                "items": neg_items,
            },
            {
                "check": "room_rate_consistency",
                "label": "Oda Fiyat Tutarliligi",
                "status": "pass" if rate_count == 0 else "warning",
                "detail": f"{rate_count} aktif rezervasyonda sifir/eksik oda fiyati",
                "count": rate_count,
                "items": rate_items,
            },
            {
                "check": "closed_folio_charges",
                "label": "Kapali Folyoya Masraf",
                "status": "pass" if closed_folio_charges == 0 else "error",
                "detail": f"{closed_folio_charges} masraf kapali folyolara kaydedilmis",
                "count": closed_folio_charges,
                "items": closed_charge_items,
            },
        ]

        if audit_result is not None:
            audit_run, actual_posted = audit_result
            expected = audit_run.get("charges_posted", 0)
            match = actual_posted == expected
            checks.append({
                "check": "audit_charge_count",
                "label": "Denetim Masraf Sayisi",
                "status": "pass" if match else "error",
                "detail": f"Beklenen: {expected}, Gercek: {actual_posted}",
                "expected": expected,
                "actual": actual_posted,
            })

        # Overall
        fail_count = sum(1 for c in checks if c["status"] == "error")
        warn_count = sum(1 for c in checks if c["status"] == "warning")
        pass_count = sum(1 for c in checks if c["status"] == "pass")

        return ServiceResult.success({
            "business_date": business_date,
            "checks": checks,
            "summary": {
                "total": len(checks),
                "passed": pass_count,
                "warnings": warn_count,
                "failures": fail_count,
                "overall_status": "fail" if fail_count > 0 else ("warning" if warn_count > 0 else "pass"),
            },
        })


financial_service = FinancialService()
