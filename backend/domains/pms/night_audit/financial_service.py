"""
Night Audit — Financial Service (Production-Grade)
Provides financial reporting, revenue reconciliation, and payment integrity checks.
"""
import logging

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)

DEFAULT_VAT_RATE = 0.10
ACCOMMODATION_TAX_RATE = 0.02


class FinancialService:
    """Financial reporting and reconciliation for night audit."""

    def __init__(self):
        from core.database import db
        self._db = db

    async def get_daily_financial_summary(
        self, ctx: OperationContext, business_date: str,
    ) -> ServiceResult:
        """Generate comprehensive daily financial summary."""
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
        revenue_by_category = {}
        total_revenue = 0.0
        total_tax = 0.0
        total_charges_count = 0
        async for doc in self._db.folio_charges.aggregate(charge_pipeline):
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
        payments_by_method = {}
        total_payments = 0.0
        total_payments_count = 0
        async for doc in self._db.payments.aggregate(payment_pipeline):
            method = doc["_id"] or "other"
            payments_by_method[method] = {
                "amount": round(doc["total_amount"], 2),
                "count": doc["count"],
            }
            total_payments += doc["total_amount"]
            total_payments_count += doc["count"]

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
        async for doc in self._db.folios.aggregate(folio_payment_pipeline):
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
        tax_breakdown = {"vat": 0.0, "accommodation_tax": 0.0}
        async for doc in self._db.folio_charges.aggregate(tax_pipeline):
            tax_breakdown["vat"] = round(doc.get("total_vat", 0), 2)
            tax_breakdown["accommodation_tax"] = round(doc.get("total_accommodation_tax", 0), 2)

        # Open folios summary
        open_folios_count = await self._db.folios.count_documents({
            "tenant_id": ctx.tenant_id,
            "status": "open",
        })
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
            }},
        ]
        open_balance = {"total": 0.0, "receivable": 0.0, "overpayment": 0.0}
        async for doc in self._db.folios.aggregate(open_balance_pipeline):
            open_balance["total"] = round(doc.get("total_balance", 0), 2)
            open_balance["receivable"] = round(doc.get("positive_balance", 0), 2)
            open_balance["overpayment"] = round(abs(doc.get("negative_balance", 0)), 2)

        # Night audit run for this date
        audit_run = await self._db.night_audit_runs.find_one(
            {"tenant_id": ctx.tenant_id, "business_date": business_date},
            {"_id": 0},
        )

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
        """Reconcile charges vs payments for a given date."""
        # Total charges
        charges_cursor = self._db.folio_charges.find({
            "tenant_id": ctx.tenant_id,
            "date": business_date,
            "voided": {"$ne": True},
        }, {"_id": 0, "id": 1, "booking_id": 1, "charge_category": 1,
            "amount": 1, "tax_amount": 1, "total": 1, "description": 1})
        charges = await charges_cursor.to_list(1000)
        total_charges = sum(c.get("total", 0) for c in charges)

        # Total payments
        payments_cursor = self._db.payments.find({
            "tenant_id": ctx.tenant_id,
            "status": {"$ne": "voided"},
            "$or": [{"date": business_date}, {"payment_date": business_date}],
        }, {"_id": 0, "id": 1, "booking_id": 1, "amount": 1,
            "payment_method": 1, "description": 1})
        payments = await payments_cursor.to_list(1000)
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

        # Check for charges without matching bookings
        booking_ids = set(c.get("booking_id") for c in charges if c.get("booking_id"))
        for bid in booking_ids:
            booking = await self._db.bookings.find_one(
                {"id": bid, "tenant_id": ctx.tenant_id},
                {"_id": 0, "id": 1, "status": 1},
            )
            if not booking:
                discrepancies.append({
                    "type": "orphan_charge",
                    "severity": "error",
                    "message": f"Masraf sahipsiz: Rezervasyon bulunamadi ({bid[:8]}...)",
                    "booking_id": bid,
                })

        # Check for rate discrepancy (room charges vs booking rate)
        room_charges = [c for c in charges if c.get("charge_category") == "room"]
        for rc in room_charges:
            if rc.get("booking_id"):
                booking = await self._db.bookings.find_one(
                    {"id": rc["booking_id"], "tenant_id": ctx.tenant_id},
                    {"_id": 0, "room_rate": 1, "rate": 1},
                )
                if booking:
                    expected_rate = booking.get("room_rate") or booking.get("rate") or 0
                    actual_rate = rc.get("amount", 0)
                    if expected_rate > 0 and abs(actual_rate - expected_rate) > 0.01:
                        discrepancies.append({
                            "type": "rate_discrepancy",
                            "severity": "warning",
                            "message": f"Oran tutarsizligi: Beklenen {expected_rate} TL, Gercek {actual_rate} TL",
                            "booking_id": rc.get("booking_id"),
                            "expected": expected_rate,
                            "actual": actual_rate,
                        })

        # Check high-value unbalanced folios
        high_balance_folios = []
        hb_cursor = self._db.folios.find({
            "tenant_id": ctx.tenant_id,
            "status": "open",
            "$or": [
                {"balance": {"$gt": 500}},
                {"balance": {"$lt": -100}},
            ],
        }, {"_id": 0, "id": 1, "folio_number": 1, "balance": 1, "booking_id": 1})
        async for f in hb_cursor:
            high_balance_folios.append(f)
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

    async def get_integrity_check(
        self, ctx: OperationContext, business_date: str,
    ) -> ServiceResult:
        """Run financial integrity checks for a given business date."""
        checks = []

        # 1. Verify all checked-in bookings have folios
        checked_in = await self._db.bookings.find(
            {"tenant_id": ctx.tenant_id, "status": "checked_in"},
            {"_id": 0, "id": 1, "folio_id": 1, "guest_name": 1},
        ).to_list(500)
        missing_folios = [b for b in checked_in if not b.get("folio_id")]
        checks.append({
            "check": "bookings_with_folios",
            "label": "Rezervasyon-Folio Eslesmesi",
            "status": "pass" if not missing_folios else "fail",
            "detail": f"{len(checked_in)} aktif rezervasyondan {len(missing_folios)} tanesinin folyosu yok",
            "count": len(missing_folios),
            "items": [{"booking_id": b["id"], "guest": b.get("guest_name", "?")} for b in missing_folios[:10]],
        })

        # 2. Check for voided charges today
        voided_count = await self._db.folio_charges.count_documents({
            "tenant_id": ctx.tenant_id,
            "date": business_date,
            "voided": True,
        })
        checks.append({
            "check": "voided_charges",
            "label": "Iptal Edilen Masraflar",
            "status": "pass" if voided_count == 0 else "warning",
            "detail": f"Bugun {voided_count} masraf iptal edildi",
            "count": voided_count,
        })

        # 3. Negative balance folios
        neg_balance = await self._db.folios.count_documents({
            "tenant_id": ctx.tenant_id,
            "status": "open",
            "balance": {"$lt": -0.01},
        })
        checks.append({
            "check": "negative_balance_folios",
            "label": "Negatif Bakiyeli Folyolar",
            "status": "pass" if neg_balance == 0 else "warning",
            "detail": f"{neg_balance} folyoda negatif bakiye (fazla odeme)",
            "count": neg_balance,
        })

        # 4. Room rate consistency
        rate_issues = 0
        async for booking in self._db.bookings.find(
            {"tenant_id": ctx.tenant_id, "status": "checked_in"},
            {"_id": 0, "id": 1, "room_rate": 1, "rate": 1},
        ):
            rate = booking.get("room_rate") or booking.get("rate") or 0
            if rate <= 0:
                rate_issues += 1
        checks.append({
            "check": "room_rate_consistency",
            "label": "Oda Fiyat Tutarliligi",
            "status": "pass" if rate_issues == 0 else "warning",
            "detail": f"{rate_issues} aktif rezervasyonda sifir/eksik oda fiyati",
            "count": rate_issues,
        })

        # 5. Check for charges posted after close
        closed_folio_charges = 0
        closed_folios = await self._db.folios.find(
            {"tenant_id": ctx.tenant_id, "status": "closed"},
            {"_id": 0, "id": 1},
        ).to_list(500)
        closed_ids = [f["id"] for f in closed_folios]
        if closed_ids:
            closed_folio_charges = await self._db.folio_charges.count_documents({
                "tenant_id": ctx.tenant_id,
                "folio_id": {"$in": closed_ids},
                "date": business_date,
                "voided": {"$ne": True},
            })
        checks.append({
            "check": "closed_folio_charges",
            "label": "Kapali Folyoya Masraf",
            "status": "pass" if closed_folio_charges == 0 else "error",
            "detail": f"{closed_folio_charges} masraf kapali folyolara kaydedilmis",
            "count": closed_folio_charges,
        })

        # 6. Unposted night audit charges
        audit_run = await self._db.night_audit_runs.find_one(
            {"tenant_id": ctx.tenant_id, "business_date": business_date, "status": {"$in": ["completed", "completed_with_exceptions"]}},
            {"_id": 0, "audit_id": 1, "charges_posted": 1},
        )
        if audit_run:
            actual_posted = await self._db.folio_charges.count_documents({
                "tenant_id": ctx.tenant_id,
                "audit_id": audit_run["audit_id"],
                "voided": {"$ne": True},
            })
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
