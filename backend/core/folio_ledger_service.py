"""
Immutable Folio Ledger Service
===============================
Append-only ledger for all folio financial entries.
Entries are NEVER updated — voids, adjustments, and transfers create new entries.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from core.database import db

logger = logging.getLogger(__name__)

VALID_ENTRY_TYPES = {
    "charge", "payment", "void", "adjustment",
    "transfer_out", "transfer_in", "refund", "tax",
}

VALID_CHARGE_CODES = {
    "ROOM", "FB", "SPA", "MINIBAR", "PARKING",
    "TELEPHONE", "LAUNDRY", "TAX", "MISC", "NOSHOW",
}

VALID_PAYMENT_METHODS = {
    "cash", "card", "bank_transfer", "online", "city_ledger",
}


async def ensure_folio_ledger_indexes():
    """Create all required indexes for the folio_ledger collection."""
    coll = db.folio_ledger
    await coll.create_index(
        [("tenant_id", 1), ("folio_id", 1), ("sequence_number", 1)],
        unique=True,
        name="idx_ledger_folio_seq",
    )
    await coll.create_index(
        [("tenant_id", 1), ("folio_id", 1), ("entry_type", 1)],
        name="idx_ledger_folio_type",
    )
    await coll.create_index(
        [("tenant_id", 1), ("booking_id", 1)],
        name="idx_ledger_booking",
    )
    await coll.create_index(
        [("tenant_id", 1), ("business_date", 1)],
        name="idx_ledger_business_date",
    )
    await coll.create_index(
        [("idempotency_key", 1)],
        unique=True,
        sparse=True,
        name="idx_ledger_idempotency",
    )
    await coll.create_index(
        [("tenant_id", 1), ("posted_at", -1)],
        name="idx_ledger_audit",
    )
    # Reconciliation reports
    await db.folio_reconciliation_reports.create_index(
        [("tenant_id", 1), ("business_date", 1)],
        name="idx_recon_tenant_date",
    )
    logger.info("Folio ledger indexes ensured")


class FolioLedgerService:
    """Immutable append-only folio ledger."""

    def __init__(self):
        self.coll = db.folio_ledger

    async def _next_sequence(self, tenant_id: str, folio_id: str) -> int:
        last = await self.coll.find_one(
            {"tenant_id": tenant_id, "folio_id": folio_id},
            {"sequence_number": 1, "_id": 0},
            sort=[("sequence_number", -1)],
        )
        return (last["sequence_number"] + 1) if last else 1

    async def _insert_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        try:
            await self.coll.insert_one(entry)
            entry.pop("_id", None)
            return entry
        except DuplicateKeyError:
            existing = await self.coll.find_one(
                {"idempotency_key": entry.get("idempotency_key")},
                {"_id": 0},
            )
            if existing:
                return existing
            raise

    async def post_charge(
        self,
        tenant_id: str,
        folio_id: str,
        booking_id: str,
        amount: float,
        description: str,
        charge_code: str = "ROOM",
        currency: str = "TRY",
        tax_amount: float = 0.0,
        tax_breakdown: Optional[List[Dict]] = None,
        idempotency_key: Optional[str] = None,
        posted_by: str = "system",
        business_date: Optional[str] = None,
        night_audit_run_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        seq = await self._next_sequence(tenant_id, folio_id)
        entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": booking_id,
            "sequence_number": seq,
            "entry_type": "charge",
            "amount": round(amount, 2),
            "currency": currency,
            "description": description,
            "charge_code": charge_code,
            "tax_amount": round(tax_amount, 2),
            "tax_breakdown": tax_breakdown or [],
            "payment_method": None,
            "reference_id": None,
            "is_voided": False,
            "voided_by_entry_id": None,
            "voided_at": None,
            "voided_reason": None,
            "correlation_id": str(uuid.uuid4()),
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
            "posted_by": posted_by,
            "posted_at": now,
            "business_date": business_date or now[:10],
            "night_audit_run_id": night_audit_run_id,
            "metadata": metadata or {},
        }
        result = await self._insert_entry(entry)
        return {"entry_id": result["id"], "new_balance": await self.compute_balance(tenant_id, folio_id)}

    async def post_payment(
        self,
        tenant_id: str,
        folio_id: str,
        booking_id: str,
        amount: float,
        payment_method: str = "cash",
        reference: str = "",
        currency: str = "TRY",
        idempotency_key: Optional[str] = None,
        posted_by: str = "system",
        business_date: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        seq = await self._next_sequence(tenant_id, folio_id)
        entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": booking_id,
            "sequence_number": seq,
            "entry_type": "payment",
            "amount": -round(amount, 2),
            "currency": currency,
            "description": f"Payment ({payment_method})" + (f" - {reference}" if reference else ""),
            "charge_code": None,
            "tax_amount": 0.0,
            "tax_breakdown": [],
            "payment_method": payment_method,
            "reference_id": reference or None,
            "is_voided": False,
            "voided_by_entry_id": None,
            "voided_at": None,
            "voided_reason": None,
            "correlation_id": str(uuid.uuid4()),
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
            "posted_by": posted_by,
            "posted_at": now,
            "business_date": business_date or now[:10],
            "night_audit_run_id": None,
            "metadata": metadata or {},
        }
        result = await self._insert_entry(entry)
        return {"entry_id": result["id"], "new_balance": await self.compute_balance(tenant_id, folio_id)}

    async def void_entry(
        self,
        tenant_id: str,
        folio_id: str,
        entry_id: str,
        reason: str,
        posted_by: str = "system",
    ) -> Dict[str, Any]:
        original = await self.coll.find_one(
            {"id": entry_id, "tenant_id": tenant_id, "folio_id": folio_id},
            {"_id": 0},
        )
        if not original:
            raise ValueError(f"Entry {entry_id} not found")
        if original.get("is_voided"):
            raise ValueError(f"Entry {entry_id} already voided")
        if original["entry_type"] == "void":
            raise ValueError("Cannot void a void entry")

        now = datetime.now(timezone.utc).isoformat()
        seq = await self._next_sequence(tenant_id, folio_id)
        void_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": original["booking_id"],
            "sequence_number": seq,
            "entry_type": "void",
            "amount": -original["amount"],
            "currency": original["currency"],
            "description": f"VOID: {original['description']} - {reason}",
            "charge_code": original.get("charge_code"),
            "tax_amount": -original.get("tax_amount", 0),
            "tax_breakdown": [],
            "payment_method": original.get("payment_method"),
            "reference_id": entry_id,
            "is_voided": False,
            "voided_by_entry_id": None,
            "voided_at": None,
            "voided_reason": None,
            "correlation_id": str(uuid.uuid4()),
            "idempotency_key": f"void:{entry_id}",
            "posted_by": posted_by,
            "posted_at": now,
            "business_date": original.get("business_date", now[:10]),
            "night_audit_run_id": None,
            "metadata": {"voided_entry_id": entry_id, "void_reason": reason},
        }
        result = await self._insert_entry(void_entry)

        # Mark original as voided (only allowed field update)
        await self.coll.update_one(
            {"id": entry_id, "tenant_id": tenant_id},
            {"$set": {"is_voided": True, "voided_by_entry_id": result["id"], "voided_at": now, "voided_reason": reason}},
        )
        return {
            "void_entry_id": result["id"],
            "new_balance": await self.compute_balance(tenant_id, folio_id),
        }

    async def transfer(
        self,
        tenant_id: str,
        from_folio_id: str,
        to_folio_id: str,
        amount: float,
        description: str = "Transfer",
        booking_id: str = "",
        idempotency_key: Optional[str] = None,
        posted_by: str = "system",
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        corr_id = str(uuid.uuid4())
        idem_key = idempotency_key or str(uuid.uuid4())

        seq_out = await self._next_sequence(tenant_id, from_folio_id)
        out_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "folio_id": from_folio_id,
            "booking_id": booking_id,
            "sequence_number": seq_out,
            "entry_type": "transfer_out",
            "amount": -round(amount, 2),
            "currency": "TRY",
            "description": f"Transfer Out: {description}",
            "charge_code": None,
            "tax_amount": 0,
            "tax_breakdown": [],
            "payment_method": None,
            "reference_id": to_folio_id,
            "is_voided": False,
            "voided_by_entry_id": None,
            "voided_at": None,
            "voided_reason": None,
            "correlation_id": corr_id,
            "idempotency_key": f"{idem_key}:out",
            "posted_by": posted_by,
            "posted_at": now,
            "business_date": now[:10],
            "night_audit_run_id": None,
            "metadata": {"transfer_to": to_folio_id},
        }

        seq_in = await self._next_sequence(tenant_id, to_folio_id)
        in_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "folio_id": to_folio_id,
            "booking_id": booking_id,
            "sequence_number": seq_in,
            "entry_type": "transfer_in",
            "amount": round(amount, 2),
            "currency": "TRY",
            "description": f"Transfer In: {description}",
            "charge_code": None,
            "tax_amount": 0,
            "tax_breakdown": [],
            "payment_method": None,
            "reference_id": from_folio_id,
            "is_voided": False,
            "voided_by_entry_id": None,
            "voided_at": None,
            "voided_reason": None,
            "correlation_id": corr_id,
            "idempotency_key": f"{idem_key}:in",
            "posted_by": posted_by,
            "posted_at": now,
            "business_date": now[:10],
            "night_audit_run_id": None,
            "metadata": {"transfer_from": from_folio_id},
        }

        out_result = await self._insert_entry(out_entry)
        in_result = await self._insert_entry(in_entry)

        return {
            "transfer_out_id": out_result["id"],
            "transfer_in_id": in_result["id"],
        }

    async def compute_balance(self, tenant_id: str, folio_id: str) -> float:
        """
        Balance = SUM(charges + adjustments + transfer_in + tax)
               - SUM(payments + refunds + transfer_out)
               (void entries carry negative amounts that naturally cancel)
        """
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "folio_id": folio_id}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        result = await self.coll.aggregate(pipeline).to_list(1)
        return round(result[0]["total"], 2) if result else 0.0

    async def get_ledger(
        self, tenant_id: str, folio_id: str
    ) -> Dict[str, Any]:
        entries = await self.coll.find(
            {"tenant_id": tenant_id, "folio_id": folio_id},
            {"_id": 0},
        ).sort("sequence_number", 1).to_list(10000)
        balance = await self.compute_balance(tenant_id, folio_id)
        return {"entries": entries, "balance": balance, "entry_count": len(entries)}

    async def reconcile_folio(self, tenant_id: str, folio_id: str) -> Dict[str, Any]:
        """Compare ledger balance vs stored folio balance."""
        ledger_balance = await self.compute_balance(tenant_id, folio_id)
        folio = await db.folios.find_one(
            {"id": folio_id, "tenant_id": tenant_id},
            {"_id": 0, "balance": 1},
        )
        folio_balance = folio.get("balance", 0.0) if folio else 0.0
        difference = round(ledger_balance - folio_balance, 2)
        return {
            "folio_id": folio_id,
            "ledger_balance": ledger_balance,
            "folio_balance": folio_balance,
            "balanced": abs(difference) < 0.01,
            "difference": difference,
        }


class ReconciliationEngine:
    """Nightly reconciliation for all open folios."""

    def __init__(self):
        self.ledger = FolioLedgerService()

    async def run_reconciliation(self, tenant_id: str, business_date: str) -> Dict[str, Any]:
        report_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        open_folios = await db.folios.find(
            {"tenant_id": tenant_id, "status": "open"},
            {"_id": 0, "id": 1, "booking_id": 1, "balance": 1},
        ).to_list(10000)

        mismatches = []
        balanced_count = 0
        error_count = 0

        for folio in open_folios:
            try:
                result = await self.ledger.reconcile_folio(tenant_id, folio["id"])
                if result["balanced"]:
                    balanced_count += 1
                else:
                    mismatches.append({
                        "folio_id": folio["id"],
                        "booking_id": folio.get("booking_id", ""),
                        "ledger_balance": result["ledger_balance"],
                        "folio_balance": result["folio_balance"],
                        "difference": result["difference"],
                        "probable_cause": "ledger_folio_drift",
                    })
            except Exception as e:
                error_count += 1
                logger.error(f"Reconciliation error for folio {folio['id']}: {e}")

        status = "balanced" if not mismatches and not error_count else ("mismatch" if mismatches else "error")

        report = {
            "id": report_id,
            "tenant_id": tenant_id,
            "business_date": business_date,
            "run_at": now,
            "status": status,
            "summary": {
                "total_folios_checked": len(open_folios),
                "balanced": balanced_count,
                "mismatched": len(mismatches),
                "errors": error_count,
            },
            "mismatches": mismatches,
        }

        await db.folio_reconciliation_reports.insert_one(report)
        report.pop("_id", None)

        if mismatches:
            logger.warning(
                "Reconciliation found %d mismatches for tenant %s on %s",
                len(mismatches), tenant_id, business_date,
            )

        return {"report_id": report_id, "summary": report["summary"], "mismatches": mismatches}
