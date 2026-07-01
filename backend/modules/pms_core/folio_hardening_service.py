"""
Folio & Billing Hardening Service - Charge posting, payment, refund, split, void/reversal, tax breakdown.
"""

import uuid
from datetime import UTC, datetime

from core.database import db


class FolioHardeningService:
    """Production-grade folio operations with audit trail and business rules."""

    # ── CHARGE POSTING ──

    async def post_charge(self, tenant_id: str, folio_id: str, booking_id: str, charge_data: dict, posted_by: str) -> dict:
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
        now = datetime.now(UTC)

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

        await self._log_audit(tenant_id, "folio_charge", charge_id, "charge_posted", posted_by, {"folio_id": folio_id, "amount": total, "category": charge_data.get("category")})

        # v95.1 — revenue raporu cache'ini geçersiz kıl (yeni charge)
        try:
            from cache_manager import cache as _cache

            if _cache:
                _cache.invalidate_tenant_cache(tenant_id, "folio_revenue_by_category")
        except ImportError:
            pass

        charge_doc.pop("_id", None)
        return {"success": True, "charge": charge_doc}

    # ── PAYMENT POSTING ──

    async def post_payment(self, tenant_id: str, folio_id: str, booking_id: str, payment_data: dict, processed_by: str) -> dict:
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
        now = datetime.now(UTC)

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

        await self._log_audit(tenant_id, "payment", payment_id, "payment_posted", processed_by, {"folio_id": folio_id, "amount": amount, "method": payment_data.get("method")})

        payment_doc.pop("_id", None)
        return {"success": True, "payment": payment_doc}

    # ── REFUND ──

    async def post_refund(self, tenant_id: str, folio_id: str, booking_id: str, amount: float, reason: str, method: str, processed_by: str) -> dict:
        """Post a refund to a folio."""
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not folio:
            return {"success": False, "error": "Folio not found"}
        if folio.get("status") != "open":
            return {"success": False, "error": f"Folio is {folio.get('status')}, cannot post refunds"}

        if amount <= 0:
            return {"success": False, "error": "Refund amount must be positive"}

        refund_id = str(uuid.uuid4())
        now = datetime.now(UTC)

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

        await self._log_audit(tenant_id, "refund", refund_id, "refund_posted", processed_by, {"folio_id": folio_id, "amount": amount, "reason": reason})

        refund_doc.pop("_id", None)
        return {"success": True, "refund": refund_doc}

    # ── VOID CHARGE ──

    async def void_charge(self, tenant_id: str, charge_id: str, reason: str, voided_by: str) -> dict:
        """Void a charge (soft delete with reason tracking)."""
        charge = await db.folio_charges.find_one({"id": charge_id, "tenant_id": tenant_id}, {"_id": 0})
        if not charge:
            return {"success": False, "error": "Charge not found"}
        if charge.get("voided"):
            return {"success": False, "error": "Charge already voided"}

        if not reason:
            return {"success": False, "error": "Void reason is required"}

        folio = await db.folios.find_one({"id": charge["folio_id"], "tenant_id": tenant_id}, {"_id": 0, "status": 1})
        if folio and folio.get("status") != "open":
            return {"success": False, "error": f"Folio is {folio.get('status')}, cannot void charge"}

        now = datetime.now(UTC)
        await db.folio_charges.update_one({"id": charge_id, "tenant_id": tenant_id}, {"$set": {"voided": True, "void_reason": reason, "voided_by": voided_by, "voided_at": now.isoformat()}})

        await self._recalculate_folio_balance(tenant_id, charge["folio_id"])

        await self._log_audit(tenant_id, "folio_charge", charge_id, "charge_voided", voided_by, {"folio_id": charge["folio_id"], "amount": charge.get("total"), "reason": reason})

        # v95.1 — revenue raporu cache'ini geçersiz kıl (charge void)
        try:
            from cache_manager import cache as _cache

            if _cache:
                _cache.invalidate_tenant_cache(tenant_id, "folio_revenue_by_category")
        except ImportError:
            pass

        return {"success": True, "charge_id": charge_id, "voided_amount": charge.get("total")}

    # ── VOID PAYMENT ──

    async def void_payment(self, tenant_id: str, payment_id: str, reason: str, voided_by: str) -> dict:
        """Void a payment."""
        payment = await db.payments.find_one({"id": payment_id, "tenant_id": tenant_id}, {"_id": 0})
        if not payment:
            return {"success": False, "error": "Payment not found"}
        if payment.get("voided"):
            return {"success": False, "error": "Payment already voided"}
        if not reason:
            return {"success": False, "error": "Void reason is required"}

        folio = await db.folios.find_one({"id": payment["folio_id"], "tenant_id": tenant_id}, {"_id": 0, "status": 1})
        if folio and folio.get("status") != "open":
            return {"success": False, "error": f"Folio is {folio.get('status')}, cannot void payment"}

        now = datetime.now(UTC)
        await db.payments.update_one({"id": payment_id, "tenant_id": tenant_id}, {"$set": {"voided": True, "void_reason": reason, "voided_by": voided_by, "voided_at": now.isoformat()}})

        await self._recalculate_folio_balance(tenant_id, payment["folio_id"])

        await self._log_audit(tenant_id, "payment", payment_id, "payment_voided", voided_by, {"folio_id": payment["folio_id"], "amount": payment.get("amount"), "reason": reason})

        return {"success": True, "payment_id": payment_id, "voided_amount": payment.get("amount")}

    # ── SPLIT FOLIO ──

    @staticmethod
    def _extra_charge_to_folio_charge(ec: dict, tenant_id: str, folio_id: str, performed_by: str, now: datetime) -> dict:
        """Normalize a booking-scoped `extra_charges` row into a `folio_charges` doc.

        `extra_charges` belgeleri tek tip değildir: erken giriş/geç çıkış kalemleri
        yalnızca `charge_name`/`charge_amount` taşır; ek hizmet kalemleri ayrıca
        `description`/`amount`/`quantity`/`total` taşıyabilir. Bölme sırasında hedef
        folioya standart bir folio kalemi olarak yazabilmek için alanları normalize
        eder (eksik tutar alanları charge_amount/amount'tan türetilir).
        """
        total = ec.get("total")
        if total is None:
            total = ec.get("charge_amount", ec.get("amount", 0))
        total = round(float(total or 0), 2)

        amount = ec.get("amount")
        if amount is None:
            amount = total
        amount = round(float(amount or 0), 2)

        return {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "folio_id": folio_id,
            "booking_id": ec.get("booking_id"),
            "charge_category": ec.get("charge_category") or ec.get("category") or "extra",
            "description": ec.get("description") or ec.get("charge_name") or "Ekstra masraf",
            "unit_price": ec.get("unit_price", amount),
            "quantity": ec.get("quantity", 1.0),
            "amount": amount,
            "tax_rate": ec.get("tax_rate", 0),
            "tax_amount": round(float(ec.get("tax_amount", 0) or 0), 2),
            "total": total,
            "department": ec.get("department"),
            "posted_by": performed_by,
            "date": now.isoformat(),
            "voided": False,
            "split_from_extra_charge_id": ec.get("id"),
        }

    async def split_folio(self, tenant_id: str, source_folio_id: str, charge_ids: list[str], target_folio_type: str, reason: str, performed_by: str) -> dict:
        """Split charges from one folio to a new folio.

        Bölünebilir kalemler iki kaynaktan gelir:
          - `folio_charges`: kaynak folioya bağlı kalemler — folio_id hedefe taşınır.
          - `extra_charges`: booking kapsamlı, folio'ya bağlı OLMAYAN ekstra
            masraflar (erken giriş/geç çıkış/ek hizmet). Seçilen ekstra masraf,
            hedef folioya normalize edilmiş bir `folio_charges` kalemi olarak yazılır
            ve `extra_charges`'tan silinir; böylece bakiye/vergi/fatura akışları tek
            tip folio kalemi üzerinden tutarlı çalışır. Kaynak folio bakiyesi
            etkilenmez (ekstra masraf zaten folio bakiyesine dâhil değildi); booking
            seviyesi özet çift saymadan korunur.
        """
        source_folio = await db.folios.find_one({"id": source_folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not source_folio:
            return {"success": False, "error": "Source folio not found"}

        if not charge_ids:
            return {"success": False, "error": "No charges selected for split"}

        # Verify charges belong to source folio
        charges = await db.folio_charges.find({"id": {"$in": charge_ids}, "folio_id": source_folio_id, "tenant_id": tenant_id, "voided": False}, {"_id": 0}).to_list(100)

        # Ekstra masraflar booking kapsamlıdır (folio_id taşımaz); kaynak folionun
        # booking'ine ait olan seçili ekstra masrafları da bölünebilir kalem say.
        extra_charges: list[dict] = []
        source_booking_id = source_folio.get("booking_id")
        if source_booking_id:
            extra_charges = await db.extra_charges.find({"id": {"$in": charge_ids}, "booking_id": source_booking_id, "tenant_id": tenant_id, "voided": {"$ne": True}}, {"_id": 0}).to_list(100)

        found_ids = {c["id"] for c in charges} | {e["id"] for e in extra_charges}
        if found_ids != set(charge_ids):
            return {"success": False, "error": "Some charges not found or already voided"}

        # Create new folio
        from core.utils import generate_folio_number

        new_folio_id = str(uuid.uuid4())
        now = datetime.now(UTC)

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

        # Move folio charges to new folio
        transferred_total = 0
        for charge in charges:
            await db.folio_charges.update_one({"id": charge["id"], "tenant_id": tenant_id}, {"$set": {"folio_id": new_folio_id}})
            transferred_total += charge.get("total", 0)

        # Move extra charges → normalize into a folio charge on the new folio,
        # then remove the original extra_charges row (it's now a folio line).
        for ec in extra_charges:
            normalized = self._extra_charge_to_folio_charge(ec, tenant_id, new_folio_id, performed_by, now)
            await db.folio_charges.insert_one(normalized)
            await db.extra_charges.delete_one({"id": ec["id"], "tenant_id": tenant_id})
            transferred_total += normalized["total"]

        moved_count = len(charges) + len(extra_charges)

        # Recalculate both folios
        await self._recalculate_folio_balance(tenant_id, source_folio_id)
        await self._recalculate_folio_balance(tenant_id, new_folio_id)

        # Log operation
        await db.folio_operations.insert_one(
            {
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
            }
        )

        await self._log_audit(tenant_id, "folio", source_folio_id, "folio_split", performed_by, {"new_folio_id": new_folio_id, "charge_count": moved_count, "amount": transferred_total})

        new_folio.pop("_id", None)
        return {"success": True, "new_folio": new_folio, "transferred_charges": moved_count, "transferred_amount": round(transferred_total, 2)}

    # ── SPLIT FOLIO BY AMOUNT (even / custom) ──

    async def _read_booking_extra_charges(self, tenant_id: str, booking_id: str | None) -> list[dict]:
        """Read a booking's voided-olmayan ekstra masraf satırlarını (read-only)."""
        if not booking_id:
            return []
        return await db.extra_charges.find({"booking_id": booking_id, "tenant_id": tenant_id, "voided": {"$ne": True}}, {"_id": 0}).to_list(None)

    async def _absorb_extra_charges(self, tenant_id: str, source_folio_id: str, extras: list[dict], performed_by: str, now: datetime) -> float:
        """Normalize given `extra_charges` onto the source folio.

        Tutar tabanlı bölme (eşit/özel) `folio.balance` üzerinden çalışır;
        `extra_charges` ise booking kapsamlıdır ve `calculate_folio_balance`'a
        dâhil DEĞİLDİR (Task #426). Bölünebilir bakiye ekstra masrafları da
        kapsasın diye, kaynak booking'in voided olmayan ekstra masrafları —
        by_item akışındaki normalizasyonun aynısıyla — kaynak folioya birer
        `folio_charges` kalemi olarak yazılır ve `extra_charges`'tan silinir.

        Çift sayım olmaz: ekstra masraf artık folio bakiyesine (folio_charges)
        dâhildir; booking özetinde `total_extra` 0'a düşer, aynı tutar
        `total_charges`'a geçer → booking seviyesi net bakiye değişmez.

        Yalnızca bölme kabul edildikten SONRA çağrılır; reddedilen bölme DB'yi
        değiştirmez. Döndürülen değer: absorbe edilen ekstra masraf toplam tutarı.
        """
        absorbed_total = 0.0
        for ec in extras:
            normalized = self._extra_charge_to_folio_charge(ec, tenant_id, source_folio_id, performed_by, now)
            await db.folio_charges.insert_one(normalized)
            await db.extra_charges.delete_one({"id": ec["id"], "tenant_id": tenant_id})
            absorbed_total += normalized["total"]
        return round(absorbed_total, 2)

    async def split_folio_by_amounts(self, tenant_id: str, source_folio_id: str, splits: list[dict], reason: str, performed_by: str) -> dict:
        """Split a folio by transferring monetary amounts (not specific charges).

        For each item in `splits` ({amount, target_folio_type}) a new folio is
        created with a single positive 'Folio bölme aktarımı' adjustment charge.
        A single negative adjustment charge is posted on the source folio for
        the total transferred amount, so balances reconcile via the standard
        recalculation pipeline.

        Bölmeden önce kaynak booking'in ekstra masrafları kaynak folioya
        absorbe edilir (Task #426) — böylece tutar tabanlı bölme, ekstra masraf
        toplamını da kapsayan bir bölünebilir bakiye üzerinden çalışır ve çift
        sayım oluşmaz (bkz. `_absorb_booking_extra_charges`).
        """
        from core.utils import generate_folio_number

        source_folio = await db.folios.find_one({"id": source_folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not source_folio:
            return {"success": False, "error": "Source folio not found"}
        if source_folio.get("status") != "open":
            return {"success": False, "error": f"Folio is {source_folio.get('status')}, cannot split"}

        if not splits:
            return {"success": False, "error": "En az bir hedef folio gerekli"}

        # Ekstra masrafları (booking kapsamlı, folio.balance'a dâhil DEĞİL) önce
        # read-only oku; bölünebilir bakiye = folio.balance + ekstra masraf toplamı
        # (Task #426). Absorbe (DB mutasyonu) yalnızca bölme KABUL edildikten sonra
        # yapılır; reddedilen bölme DB'yi değiştirmez.
        now = datetime.now(UTC)
        extras = await self._read_booking_extra_charges(tenant_id, source_folio.get("booking_id"))
        extra_total = round(
            sum(self._extra_charge_to_folio_charge(ec, tenant_id, source_folio_id, performed_by, now)["total"] for ec in extras),
            2,
        )

        # Validate amounts
        cleaned: list[dict] = []
        for s in splits:
            amt = round(float(s.get("amount", 0) or 0), 2)
            if amt <= 0:
                return {"success": False, "error": "Her bölme tutarı 0'dan büyük olmalı"}
            cleaned.append({"amount": amt, "target_folio_type": s.get("target_folio_type") or "guest"})

        total_transfer = round(sum(s["amount"] for s in cleaned), 2)
        folio_balance = round(float(source_folio.get("balance", 0) or 0), 2)
        source_balance = round(folio_balance + extra_total, 2)

        if source_balance <= 0:
            return {"success": False, "error": "Kaynak folio bakiyesi 0 veya negatif, bölünemez"}
        if total_transfer >= source_balance:
            return {
                "success": False,
                "error": (f"Aktarılacak toplam (${total_transfer:.2f}) kaynak folio bakiyesinden (${source_balance:.2f}) küçük olmalı — orijinalde en az bir miktar kalmalı"),
            }

        # Bölme kabul edildi → ekstra masrafları kaynak folioya absorbe et +
        # bakiyeyi yeniden hesapla, böylece negatif düzeltme ekstrayı da kapsar.
        absorbed_extra_total = 0.0
        if extras:
            absorbed_extra_total = await self._absorb_extra_charges(tenant_id, source_folio_id, extras, performed_by, now)
            if absorbed_extra_total > 0:
                await self._recalculate_folio_balance(tenant_id, source_folio_id)
                source_folio = await db.folios.find_one({"id": source_folio_id, "tenant_id": tenant_id}, {"_id": 0})

        new_folios: list[dict] = []

        # 1) Create target folios + positive adjustment charges
        for idx, s in enumerate(cleaned, start=1):
            new_folio_id = str(uuid.uuid4())
            new_folio = {
                "id": new_folio_id,
                "tenant_id": tenant_id,
                "booking_id": source_folio.get("booking_id"),
                "folio_number": await generate_folio_number(tenant_id),
                "folio_type": s["target_folio_type"],
                "status": "open",
                "guest_id": source_folio.get("guest_id"),
                "company_id": source_folio.get("company_id"),
                "balance": 0.0,
                "notes": f"Split from {source_folio.get('folio_number')} (#{idx}/{len(cleaned)}): {reason}",
                "created_at": now.isoformat(),
            }
            await db.folios.insert_one(new_folio)

            charge_doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "folio_id": new_folio_id,
                "booking_id": source_folio.get("booking_id"),
                "charge_category": "split_adjustment",
                "description": f"Folio bölme aktarımı — kaynak {source_folio.get('folio_number')}",
                "unit_price": s["amount"],
                "quantity": 1.0,
                "amount": s["amount"],
                "tax_rate": 0,
                "tax_amount": 0,
                "total": s["amount"],
                "department": "folio_ops",
                "posted_by": performed_by,
                "date": now.isoformat(),
                "voided": False,
            }
            await db.folio_charges.insert_one(charge_doc)

            await self._recalculate_folio_balance(tenant_id, new_folio_id)
            new_folio.pop("_id", None)
            new_folios.append({**new_folio, "transferred_amount": s["amount"]})

        # 2) Single negative adjustment on source folio
        source_adjust = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "folio_id": source_folio_id,
            "booking_id": source_folio.get("booking_id"),
            "charge_category": "split_adjustment",
            "description": f"Folio bölme: {len(cleaned)} hedefe aktarım",
            "unit_price": -total_transfer,
            "quantity": 1.0,
            "amount": -total_transfer,
            "tax_rate": 0,
            "tax_amount": 0,
            "total": -total_transfer,
            "department": "folio_ops",
            "posted_by": performed_by,
            "date": now.isoformat(),
            "voided": False,
        }
        await db.folio_charges.insert_one(source_adjust)
        await self._recalculate_folio_balance(tenant_id, source_folio_id)

        # 3) Operation log + audit
        await db.folio_operations.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "operation_type": "split_by_amount",
                "from_folio_id": source_folio_id,
                "to_folio_ids": [f["id"] for f in new_folios],
                "amount": total_transfer,
                "absorbed_extra_total": absorbed_extra_total,
                "reason": reason,
                "performed_by": performed_by,
                "performed_at": now.isoformat(),
            }
        )
        await self._log_audit(
            tenant_id,
            "folio",
            source_folio_id,
            "folio_split_by_amount",
            performed_by,
            {"target_count": len(new_folios), "total_transferred": total_transfer, "absorbed_extra_total": absorbed_extra_total},
        )

        return {
            "success": True,
            "new_folios": new_folios,
            "transferred_amount": total_transfer,
            "target_count": len(new_folios),
            "absorbed_extra_total": absorbed_extra_total,
        }

    # ── TAX BREAKDOWN ──

    async def get_tax_breakdown(self, tenant_id: str, folio_id: str) -> dict:
        """Get detailed tax breakdown for a folio."""
        # Tax breakdown — limit kaldırıldı (500 → cursor iteration, batch=500)
        cursor = db.folio_charges.find({"folio_id": folio_id, "tenant_id": tenant_id, "voided": False}, {"_id": 0}).batch_size(500)
        charges = [c async for c in cursor]

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

    async def transfer_to_city_ledger(self, tenant_id: str, folio_id: str, account_id: str, reason: str, performed_by: str) -> dict:
        """Transfer folio balance to city ledger account."""
        folio = await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})
        if not folio:
            return {"success": False, "error": "Folio not found"}

        # Calculate balance (server-side aggregation, limit yok)
        from core.utils import calculate_folio_balance

        balance = await calculate_folio_balance(folio_id, tenant_id)

        if balance <= 0:
            return {"success": False, "error": "No outstanding balance to transfer"}

        now = datetime.now(UTC)

        # Create city ledger transaction
        await db.city_ledger_transactions.insert_one(
            {
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
            }
        )

        # Close the folio
        await db.folios.update_one({"id": folio_id, "tenant_id": tenant_id}, {"$set": {"status": "closed", "closed_at": now.isoformat(), "city_ledger_account_id": account_id}})

        await self._log_audit(tenant_id, "folio", folio_id, "city_ledger_transfer", performed_by, {"account_id": account_id, "amount": balance})

        return {"success": True, "transferred_amount": balance, "account_id": account_id}

    # ── TRANSACTION AUDIT TRAIL ──

    async def get_folio_audit_trail(self, tenant_id: str, folio_id: str) -> list[dict]:
        """Get complete audit trail for a folio."""
        trail = await db.pms_audit_trail.find({"tenant_id": tenant_id, "entity_id": folio_id}, {"_id": 0}).sort("timestamp", -1).to_list(200)
        return trail

    # ── INTERNAL HELPERS ──

    async def _recalculate_folio_balance(self, tenant_id: str, folio_id: str):
        from core.utils import calculate_folio_balance

        balance = await calculate_folio_balance(folio_id, tenant_id)
        await db.folios.update_one({"id": folio_id, "tenant_id": tenant_id}, {"$set": {"balance": balance}})

    async def _log_audit(self, tenant_id: str, entity_type: str, entity_id: str, action: str, user_id: str, metadata: dict = None):
        await db.pms_audit_trail.insert_one(
            {
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "performed_by": user_id,
                "metadata": metadata or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
