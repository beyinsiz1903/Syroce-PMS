"""
Folio & Billing Hardening Service - Charge posting, payment, refund, split, void/reversal, tax breakdown.
"""
from datetime import datetime, timezone
from typing import Dict, List
import uuid

from core.database import db


class FolioHardeningService:
    """Production-grade folio operations with audit trail and business rules."""

    # ── CHARGE POSTING ──

    async def post_charge(self, tenant_id: str, folio_id: str, booking_id: str, charge_data: Dict, posted_by: str) -> Dict:
        """Post a charge to a folio with validation."""
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not folio:
            return {"success": False, "error": "Folio not found"}
        if folio.get("status") != "open":
            return {"success": False, "error": f"Folio is {folio.get('status')}, cannot post charges"}

        amount = charge_data.get("amount", 0)
        quantity = charge_data.get("quantity", 1.0)
        tax_rate = charge_data.get("tax_rate", 0)
        line_amount = round(amount * quantity, 2)
        tax_amount = round(line_amount * tax_rate / 100, 2)
        total = round(line_amount + tax_amount, 2)

        charge_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        charge_doc = {
            "id": charge_id,
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": booking_id,
            "charge_category": charge_data.get("category", "other"),
            "description": charge_data.get("description", ""),
            "unit_price": amount,
            "quantity": quantity,
            "amount": line_amount,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total": total,
            "department": charge_data.get("department"),
            "posted_by": posted_by,
            "date": now.isoformat(),
            "voided": False,
        }

        await db.folio_charges.insert_one(charge_doc)

        # Update folio balance
        await self._recalculate_folio_balance(tenant_id, folio_id)

        await self._log_audit(tenant_id, "folio_charge", charge_id, "charge_posted", posted_by,
                              {"folio_id": folio_id, "amount": total, "category": charge_data.get("category")})

        charge_doc.pop("_id", None)
        return {"success": True, "charge": charge_doc}

    # ── PAYMENT POSTING ──

    async def post_payment(self, tenant_id: str, folio_id: str, booking_id: str, payment_data: Dict, processed_by: str) -> Dict:
        """Post a payment to a folio."""
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not folio:
            return {"success": False, "error": "Folio not found"}
        if folio.get("status") != "open":
            return {"success": False, "error": f"Folio is {folio.get('status')}, cannot post payments"}

        amount = payment_data.get("amount", 0)
        if amount <= 0:
            return {"success": False, "error": "Payment amount must be positive"}

        payment_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        payment_doc = {
            "id": payment_id,
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": booking_id,
            "amount": amount,
            "method": payment_data.get("method", "cash"),
            "payment_type": payment_data.get("payment_type", "final"),
            "status": "paid",
            "reference": payment_data.get("reference"),
            "notes": payment_data.get("notes"),
            "processed_by": processed_by,
            "processed_at": now.isoformat(),
            "voided": False,
        }

        await db.payments.insert_one(payment_doc)
        await self._recalculate_folio_balance(tenant_id, folio_id)

        await self._log_audit(tenant_id, "payment", payment_id, "payment_posted", processed_by,
                              {"folio_id": folio_id, "amount": amount, "method": payment_data.get("method")})

        payment_doc.pop("_id", None)
        return {"success": True, "payment": payment_doc}

    # ── REFUND ──

    async def post_refund(self, tenant_id: str, folio_id: str, booking_id: str, amount: float, reason: str, method: str, processed_by: str) -> Dict:
        """Post a refund to a folio."""
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not folio:
            return {"success": False, "error": "Folio not found"}

        if amount <= 0:
            return {"success": False, "error": "Refund amount must be positive"}

        refund_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        refund_doc = {
            "id": refund_id,
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": booking_id,
            "amount": -amount,  # negative for refund
            "method": method,
            "payment_type": "refund",
            "status": "refunded",
            "reference": f"REFUND-{refund_id[:8]}",
            "notes": reason,
            "processed_by": processed_by,
            "processed_at": now.isoformat(),
            "voided": False,
        }

        await db.payments.insert_one(refund_doc)
        await self._recalculate_folio_balance(tenant_id, folio_id)

        await self._log_audit(tenant_id, "refund", refund_id, "refund_posted", processed_by,
                              {"folio_id": folio_id, "amount": amount, "reason": reason})

        refund_doc.pop("_id", None)
        return {"success": True, "refund": refund_doc}

    # ── VOID CHARGE ──

    async def void_charge(self, tenant_id: str, charge_id: str, reason: str, voided_by: str) -> Dict:
        """Void a charge (soft delete with reason tracking)."""
        charge = await db.folio_charges.find_one({"id": charge_id, "tenant_id": tenant_id}, {"_id": 0})
        if not charge:
            return {"success": False, "error": "Charge not found"}
        if charge.get("voided"):
            return {"success": False, "error": "Charge already voided"}

        if not reason:
            return {"success": False, "error": "Void reason is required"}

        now = datetime.now(timezone.utc)
        await db.folio_charges.update_one(
            {"id": charge_id, "tenant_id": tenant_id},
            {"$set": {"voided": True, "void_reason": reason, "voided_by": voided_by, "voided_at": now.isoformat()}}
        )

        await self._recalculate_folio_balance(tenant_id, charge["folio_id"])

        await self._log_audit(tenant_id, "folio_charge", charge_id, "charge_voided", voided_by,
                              {"folio_id": charge["folio_id"], "amount": charge.get("total"), "reason": reason})

        return {"success": True, "charge_id": charge_id, "voided_amount": charge.get("total")}

    # ── VOID PAYMENT ──

    async def void_payment(self, tenant_id: str, payment_id: str, reason: str, voided_by: str) -> Dict:
        """Void a payment."""
        payment = await db.payments.find_one({"id": payment_id, "tenant_id": tenant_id}, {"_id": 0})
        if not payment:
            return {"success": False, "error": "Payment not found"}
        if payment.get("voided"):
            return {"success": False, "error": "Payment already voided"}
        if not reason:
            return {"success": False, "error": "Void reason is required"}

        now = datetime.now(timezone.utc)
        await db.payments.update_one(
            {"id": payment_id, "tenant_id": tenant_id},
            {"$set": {"voided": True, "void_reason": reason, "voided_by": voided_by, "voided_at": now.isoformat()}}
        )

        await self._recalculate_folio_balance(tenant_id, payment["folio_id"])

        await self._log_audit(tenant_id, "payment", payment_id, "payment_voided", voided_by,
                              {"folio_id": payment["folio_id"], "amount": payment.get("amount"), "reason": reason})

        return {"success": True, "payment_id": payment_id, "voided_amount": payment.get("amount")}

    # ── SPLIT FOLIO ──

    async def split_folio(self, tenant_id: str, source_folio_id: str, charge_ids: List[str], target_folio_type: str, reason: str, performed_by: str) -> Dict:
        """Split charges from one folio to a new folio."""
        source_folio = await db.folios.find_one({"id": source_folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not source_folio:
            return {"success": False, "error": "Source folio not found"}

        if not charge_ids:
            return {"success": False, "error": "No charges selected for split"}

        # Verify charges belong to source folio
        charges = await db.folio_charges.find(
            {"id": {"$in": charge_ids}, "folio_id": source_folio_id, "tenant_id": tenant_id, "voided": False},
            {"_id": 0}
        ).to_list(100)

        if len(charges) != len(charge_ids):
            return {"success": False, "error": "Some charges not found or already voided"}

        # Create new folio
        from core.utils import generate_folio_number
        new_folio_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        new_folio = {
            "id": new_folio_id,
            "tenant_id": tenant_id,
            "booking_id": source_folio.get("booking_id"),
            "folio_number": await generate_folio_number(tenant_id),
            "folio_type": target_folio_type,
            "status": "open",
            "guest_id": source_folio.get("guest_id"),
            "company_id": source_folio.get("company_id"),
            "balance": 0.0,
            "notes": f"Split from {source_folio.get('folio_number')}: {reason}",
            "created_at": now.isoformat(),
        }
        await db.folios.insert_one(new_folio)

        # Move charges to new folio
        transferred_total = 0
        for charge in charges:
            await db.folio_charges.update_one(
                {"id": charge["id"], "tenant_id": tenant_id},
                {"$set": {"folio_id": new_folio_id}}
            )
            transferred_total += charge.get("total", 0)

        # Recalculate both folios
        await self._recalculate_folio_balance(tenant_id, source_folio_id)
        await self._recalculate_folio_balance(tenant_id, new_folio_id)

        # Log operation
        await db.folio_operations.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "operation_type": "split",
            "from_folio_id": source_folio_id,
            "to_folio_id": new_folio_id,
            "charge_ids": charge_ids,
            "amount": transferred_total,
            "reason": reason,
            "performed_by": performed_by,
            "performed_at": now.isoformat(),
        })

        await self._log_audit(tenant_id, "folio", source_folio_id, "folio_split", performed_by,
                              {"new_folio_id": new_folio_id, "charge_count": len(charges), "amount": transferred_total})

        new_folio.pop("_id", None)
        return {"success": True, "new_folio": new_folio, "transferred_charges": len(charges), "transferred_amount": round(transferred_total, 2)}

    # ── TAX BREAKDOWN ──

    async def get_tax_breakdown(self, tenant_id: str, folio_id: str) -> Dict:
        """Get detailed tax breakdown for a folio."""
        charges = await db.folio_charges.find(
            {"folio_id": folio_id, "tenant_id": tenant_id, "voided": False}, {"_id": 0}
        ).to_list(500)

        by_category = {}
        total_net = 0
        total_tax = 0
        total_gross = 0

        for charge in charges:
            cat = charge.get("charge_category", "other")
            if cat not in by_category:
                by_category[cat] = {"net": 0, "tax": 0, "gross": 0, "count": 0}
            amount = charge.get("amount", 0)
            tax = charge.get("tax_amount", 0)
            by_category[cat]["net"] += amount
            by_category[cat]["tax"] += tax
            by_category[cat]["gross"] += charge.get("total", amount + tax)
            by_category[cat]["count"] += 1
            total_net += amount
            total_tax += tax
            total_gross += charge.get("total", amount + tax)

        # Round
        for cat in by_category:
            for k in ["net", "tax", "gross"]:
                by_category[cat][k] = round(by_category[cat][k], 2)

        return {
            "folio_id": folio_id,
            "by_category": by_category,
            "total_net": round(total_net, 2),
            "total_tax": round(total_tax, 2),
            "total_gross": round(total_gross, 2),
        }

    # ── CITY LEDGER ──

    async def transfer_to_city_ledger(self, tenant_id: str, folio_id: str, account_id: str, reason: str, performed_by: str) -> Dict:
        """Transfer folio balance to city ledger account."""
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not folio:
            return {"success": False, "error": "Folio not found"}

        # Calculate balance
        charges = await db.folio_charges.find({"folio_id": folio_id, "tenant_id": tenant_id, "voided": False}, {"_id": 0}).to_list(500)
        payments = await db.payments.find({"folio_id": folio_id, "tenant_id": tenant_id, "voided": False}, {"_id": 0}).to_list(500)
        total_charges = sum(c.get("total", 0) for c in charges)
        total_payments = sum(p.get("amount", 0) for p in payments)
        balance = round(total_charges - total_payments, 2)

        if balance <= 0:
            return {"success": False, "error": "No outstanding balance to transfer"}

        now = datetime.now(timezone.utc)

        # Create city ledger transaction
        await db.city_ledger_transactions.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "account_id": account_id,
            "booking_id": folio.get("booking_id"),
            "transaction_type": "charge",
            "amount": balance,
            "description": f"Transfer from folio {folio.get('folio_number')}: {reason}",
            "posted_by": performed_by,
            "transaction_date": now.isoformat(),
            "created_at": now.isoformat(),
        })

        # Close the folio
        await db.folios.update_one(
            {"id": folio_id, "tenant_id": tenant_id},
            {"$set": {"status": "closed", "closed_at": now.isoformat(), "city_ledger_account_id": account_id}}
        )

        await self._log_audit(tenant_id, "folio", folio_id, "city_ledger_transfer", performed_by,
                              {"account_id": account_id, "amount": balance})

        return {"success": True, "transferred_amount": balance, "account_id": account_id}

    # ── TRANSACTION AUDIT TRAIL ──

    async def get_folio_audit_trail(self, tenant_id: str, folio_id: str) -> List[Dict]:
        """Get complete audit trail for a folio."""
        trail = await db.pms_audit_trail.find(
            {"tenant_id": tenant_id, "entity_id": folio_id},
            {"_id": 0}
        ).sort("timestamp", -1).to_list(200)
        return trail

    # ── INTERNAL HELPERS ──

    async def _recalculate_folio_balance(self, tenant_id: str, folio_id: str):
        charges = await db.folio_charges.find({"folio_id": folio_id, "tenant_id": tenant_id, "voided": False}, {"_id": 0}).to_list(500)
        payments = await db.payments.find({"folio_id": folio_id, "tenant_id": tenant_id, "voided": False}, {"_id": 0}).to_list(500)
        total_charges = sum(c.get("total", c.get("amount", 0)) for c in charges)
        total_payments = sum(p.get("amount", 0) for p in payments)
        balance = round(total_charges - total_payments, 2)
        await db.folios.update_one({"id": folio_id, "tenant_id": tenant_id}, {"$set": {"balance": balance}})

    async def _log_audit(self, tenant_id: str, entity_type: str, entity_id: str, action: str, user_id: str, metadata: Dict = None):
        await db.pms_audit_trail.insert_one({
            "tenant_id": tenant_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "performed_by": user_id,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
