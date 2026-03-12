"""
Folio Detail Service - Timeline view, running balance, split folio visibility,
tax breakdown per line, city ledger history, invoice association, audit trail,
supervisor override and void reason visibility.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from core.database import db


class FolioDetailService:
    """Comprehensive folio detail operations for the Folio Detail View."""

    async def get_folio_detail(self, tenant_id: str, folio_id: str) -> Dict:
        """Get complete folio detail with timeline, running balance, split view, tax breakdown."""
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not folio:
            return {"success": False, "error": "Folio not found"}

        # Get all charges (including voided for visibility)
        charges = await db.folio_charges.find(
            {"folio_id": folio_id, "tenant_id": tenant_id}, {"_id": 0}
        ).sort("date", 1).to_list(1000)

        # Get all payments (including voided)
        payments = await db.payments.find(
            {"folio_id": folio_id, "tenant_id": tenant_id}, {"_id": 0}
        ).sort("processed_at", 1).to_list(1000)

        # Build timeline with running balance
        timeline = self._build_timeline(charges, payments)

        # Split folio info
        split_info = await self._get_split_folio_info(tenant_id, folio_id)

        # Tax breakdown per line
        tax_breakdown = self._calculate_line_tax_breakdown(charges)

        # City ledger transfer history
        city_ledger_history = await self._get_city_ledger_history(tenant_id, folio_id)

        # Invoice association
        invoices = await self._get_associated_invoices(tenant_id, folio_id, folio.get("booking_id"))

        # Audit trail
        audit_trail = await db.pms_audit_trail.find(
            {"tenant_id": tenant_id, "entity_id": folio_id}, {"_id": 0}
        ).sort("timestamp", -1).to_list(100)

        # Supervisor overrides and void details
        void_details = self._extract_void_details(charges, payments)

        # Summary
        active_charges = [c for c in charges if not c.get("voided")]
        active_payments = [p for p in payments if not p.get("voided")]
        total_charges = round(sum(c.get("total", c.get("amount", 0)) for c in active_charges), 2)
        total_payments = round(sum(p.get("amount", 0) for p in active_payments), 2)
        balance = round(total_charges - total_payments, 2)

        return {
            "success": True,
            "folio": folio,
            "summary": {
                "total_charges": total_charges,
                "total_payments": total_payments,
                "balance": balance,
                "charge_count": len(active_charges),
                "payment_count": len(active_payments),
                "voided_charges": len([c for c in charges if c.get("voided")]),
                "voided_payments": len([p for p in payments if p.get("voided")]),
            },
            "timeline": timeline,
            "charges": charges,
            "payments": payments,
            "tax_breakdown": tax_breakdown,
            "split_folio_info": split_info,
            "city_ledger_history": city_ledger_history,
            "invoices": invoices,
            "audit_trail": audit_trail,
            "void_details": void_details,
        }

    def _build_timeline(self, charges: List[Dict], payments: List[Dict]) -> List[Dict]:
        """Build a chronological timeline of all folio events with running balance."""
        events = []

        for c in charges:
            ts = c.get("date") or c.get("posted_at") or ""
            amount = c.get("total", c.get("amount", 0))
            events.append({
                "id": c.get("id"),
                "type": "charge",
                "timestamp": ts,
                "description": c.get("description", ""),
                "category": c.get("charge_category", "other"),
                "amount": amount,
                "tax_amount": c.get("tax_amount", 0),
                "voided": c.get("voided", False),
                "void_reason": c.get("void_reason"),
                "voided_by": c.get("voided_by"),
                "department": c.get("department"),
            })

        for p in payments:
            ts = p.get("processed_at") or ""
            events.append({
                "id": p.get("id"),
                "type": "refund" if p.get("payment_type") == "refund" else "payment",
                "timestamp": ts,
                "description": f"{p.get('method', 'cash').upper()} - {p.get('notes', '')}".strip(" -"),
                "category": p.get("method", "cash"),
                "amount": p.get("amount", 0),
                "voided": p.get("voided", False),
                "void_reason": p.get("void_reason"),
                "voided_by": p.get("voided_by"),
                "reference": p.get("reference"),
            })

        # Sort by timestamp
        events.sort(key=lambda e: e.get("timestamp", ""))

        # Calculate running balance
        running = 0.0
        for e in events:
            if e.get("voided"):
                e["running_balance"] = running
                continue
            if e["type"] == "charge":
                running += e["amount"]
            elif e["type"] == "payment":
                running -= e["amount"]
            elif e["type"] == "refund":
                running -= abs(e["amount"])
            e["running_balance"] = round(running, 2)

        return events

    async def _get_split_folio_info(self, tenant_id: str, folio_id: str) -> Dict:
        """Get split folio operations related to this folio."""
        # Folios split FROM this folio
        split_from = await db.folio_operations.find(
            {"tenant_id": tenant_id, "from_folio_id": folio_id, "operation_type": "split"}, {"_id": 0}
        ).to_list(50)

        # Folios split TO this folio
        split_to = await db.folio_operations.find(
            {"tenant_id": tenant_id, "to_folio_id": folio_id, "operation_type": "split"}, {"_id": 0}
        ).to_list(50)

        # Related folios
        related_folio_ids = set()
        for op in split_from:
            related_folio_ids.add(op.get("to_folio_id"))
        for op in split_to:
            related_folio_ids.add(op.get("from_folio_id"))

        related_folios = []
        for fid in related_folio_ids:
            f = await db.folios.find_one({"id": fid, "tenant_id": tenant_id}, {"_id": 0, "id": 1, "folio_number": 1, "folio_type": 1, "status": 1, "balance": 1})
            if f:
                related_folios.append(f)

        return {
            "has_splits": len(split_from) > 0 or len(split_to) > 0,
            "split_from_operations": split_from,
            "split_to_operations": split_to,
            "related_folios": related_folios,
        }

    def _calculate_line_tax_breakdown(self, charges: List[Dict]) -> Dict:
        """Calculate line-level tax breakdown."""
        lines = []
        by_rate = {}
        total_net = 0
        total_tax = 0
        total_gross = 0

        for c in charges:
            if c.get("voided"):
                continue
            net = c.get("amount", 0)
            tax = c.get("tax_amount", 0)
            gross = c.get("total", net + tax)
            rate = c.get("tax_rate", 0)

            lines.append({
                "charge_id": c.get("id"),
                "description": c.get("description"),
                "category": c.get("charge_category"),
                "net_amount": round(net, 2),
                "tax_rate": rate,
                "tax_amount": round(tax, 2),
                "gross_amount": round(gross, 2),
            })

            rate_key = f"{rate}%"
            if rate_key not in by_rate:
                by_rate[rate_key] = {"rate": rate, "net": 0, "tax": 0, "gross": 0, "count": 0}
            by_rate[rate_key]["net"] += net
            by_rate[rate_key]["tax"] += tax
            by_rate[rate_key]["gross"] += gross
            by_rate[rate_key]["count"] += 1

            total_net += net
            total_tax += tax
            total_gross += gross

        # Round summaries
        for k in by_rate:
            for field in ["net", "tax", "gross"]:
                by_rate[k][field] = round(by_rate[k][field], 2)

        return {
            "lines": lines,
            "by_tax_rate": by_rate,
            "totals": {
                "net": round(total_net, 2),
                "tax": round(total_tax, 2),
                "gross": round(total_gross, 2),
            },
        }

    async def _get_city_ledger_history(self, tenant_id: str, folio_id: str) -> List[Dict]:
        """Get city ledger transfer history for this folio."""
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not folio:
            return []

        booking_id = folio.get("booking_id")
        transfers = await db.city_ledger_transactions.find(
            {"tenant_id": tenant_id, "booking_id": booking_id}, {"_id": 0}
        ).sort("transaction_date", -1).to_list(50)
        return transfers

    async def _get_associated_invoices(self, tenant_id: str, folio_id: str, booking_id: str = None) -> List[Dict]:
        """Get invoices associated with this folio or booking."""
        query = {"tenant_id": tenant_id, "$or": [{"folio_id": folio_id}]}
        if booking_id:
            query["$or"].append({"booking_id": booking_id})

        invoices = await db.invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)
        return invoices

    def _extract_void_details(self, charges: List[Dict], payments: List[Dict]) -> List[Dict]:
        """Extract all void/reversal details with supervisor override visibility."""
        voids = []

        for c in charges:
            if c.get("voided"):
                voids.append({
                    "type": "charge_void",
                    "item_id": c.get("id"),
                    "description": c.get("description"),
                    "original_amount": c.get("total", c.get("amount", 0)),
                    "void_reason": c.get("void_reason", ""),
                    "voided_by": c.get("voided_by"),
                    "voided_at": c.get("voided_at"),
                    "is_supervisor_override": bool(c.get("supervisor_override")),
                })

        for p in payments:
            if p.get("voided"):
                voids.append({
                    "type": "payment_void",
                    "item_id": p.get("id"),
                    "description": f"{p.get('method', '')} payment",
                    "original_amount": p.get("amount", 0),
                    "void_reason": p.get("void_reason", ""),
                    "voided_by": p.get("voided_by"),
                    "voided_at": p.get("voided_at"),
                    "is_supervisor_override": bool(p.get("supervisor_override")),
                })

        voids.sort(key=lambda v: v.get("voided_at") or "", reverse=True)
        return voids
