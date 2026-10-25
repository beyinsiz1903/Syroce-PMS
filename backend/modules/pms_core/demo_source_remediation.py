"""One reviewed reconstruction of named, synthetic Demo Hotel legacy sources.

NOT a production migration, historical-rate lookup or audit-chain repair.
Amounts/identities never change. Before-images, explicit demo assumptions and
one sealed audit receipt commit with the missing-field patches. No provider,
gateway, day-close or automatic GL operation is performed here.
"""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from bson import json_util
from fastapi import HTTPException

from core.audit_chain import append_audit_log, compute_record_hash
from core.booking_atomicity import with_resource_locks
from core.integrations.operational_gl_valuation import digest, minor
from modules.pms_core.cari_receivable_reporting import CREDITS, DEBITS
from modules.pms_core.payment_cashier_snapshot import cashier_values
from modules.pms_core.reporting_financials import effective_collection
from shared_kernel.audit_helper import build_audit_entry
from shared_kernel.gl_posting import verify_journal_entry_hash

TENANT = "5bad4a34-6ee3-4566-9053-741b7375a9cf"
POLICY = "demo-legacy-source-reconstruction-20261025-v1"
NOTICE = "Demo yeniden kurma: örnek kur/vade/vergi; tarihî kaynak doğrulaması veya gerçek mali kabul değildir."
ACCOUNT = "b35c95fb-fe21-4cb1-ab12-101f7b608e44"
HOLDS = ("2faf1e5b-3d87-4d13-9af5-d49b42e1805e", "6c44c4fe-7cf5-476e-bb96-bedfff359149", "45126c58-f9ef-42e1-968d-4732dbe0614c")
EXTERNAL = ("20261015-501694-1200415970", "20261020-501694-1200415974")
FX_IDS = {
    "54fab736-770c-5866-a7b2-522a781afa4b": "USD", "37a814a0-a6f8-43d6-97c4-7fe2a71e1d5b": "USD", "aad99f2e-e17f-428e-93f8-eb0741c30894": "USD",
    "7018ccd6-2b86-54c7-89de-530e52d7e6b0": "EUR", "6abacca9-1cf5-426f-a72c-ebc91a9e0896": "EUR", "773129b3-0c01-453f-991d-659f60aa0f55": "EUR",
}
COMP_IDS = ("a949b3d6-6da3-4075-b71e-1e1f513802fe", "5c810fd6-a440-4228-9459-d24e58a6330b", "268f0407-748a-45ba-ad2f-15bef258207a", "1819232c-160c-481d-b1db-bcfa41f72d7b",
            "7c51bfea-78bb-4501-9db8-92045d730dd2", "8702780e-b49f-4a42-b230-35a9bd0cc0c1", "d03fd139-2452-46a8-81a1-4b99c730a210", "34a58583-2c73-4040-ba48-ea59a1172ade")
SEPTEMBER_IDS = ("7de9f821-ed68-4e1f-bb77-fe825e49b385", "37317a5f-8ab4-4ab2-b6bb-85a90abc3850", "dffcb58d-6cd8-4da8-926f-97c8c85632bb", "c0ea0c02-2eb2-4d9a-a2c1-d79390cece2c", "fcb31e12-cd9f-46a1-85b4-d32d6dec193f",
                 "5ec2c201-b57b-453e-adff-f4f059a73c29", "6f3a1137-0c12-4de8-8477-c0b4b5a032c6", "b03cddcd-2668-4651-bbcb-f6c9d5e64b09", "2f2903b3-b15e-41dc-bcf7-7a6f3c60dd12", "d9ee6c65-409e-4224-aa90-51bef91c89b4", "3bb915f8-b58d-4d3b-946c-9fbaf3e9d423", "0d5ee40a-7fb6-4058-b8ed-a9899aaa37f3", "7b83edec-0f52-46b1-8160-71129e143e92")
RECLASS_PAYMENT = "fcb31e12-cd9f-46a1-85b4-d32d6dec193f"
RECLASS_RUN = "d5726e44-8e22-48f6-a3bd-7d9bee36be4b"
RECLASS_ENTRY = "202d0921-ca22-4808-a898-3915df337e71"


def fingerprint(value):
    return digest(json_util.dumps(value, sort_keys=True))


def provenance(kind):
    return {"policy_id": POLICY, "basis": "demo_reconstruction", "kind": kind,
            "historical_source_verified": False, "notice": NOTICE}


def is_demo_reconstructed(row):
    meta = row.get("demo_reconstruction") or {}
    return row.get("tenant_id") == TENANT and meta.get("policy_id") == POLICY and meta.get("basis") == "demo_reconstruction"


def is_archived_demo(row):
    named_source = row.get("id") in HOLDS or row.get("external_id") in EXTERNAL
    return named_source and is_demo_reconstructed(row) and (row.get("status") == "archived_demo" or row.get("pms_status") == "archived_demo")


async def guard(database, tenant_id, session=None):
    if tenant_id != TENANT:
        raise HTTPException(404, "Demo onarım kapsamı bulunamadı")
    kw = {"session": session} if session is not None else {}
    tenant = await database.tenants.find_one({"id": tenant_id}, {"_id": 0}, **kw)
    if not tenant or str(tenant.get("hotel_id")) != "100001" or tenant.get("property_name") != "Syroce Demo Hotel":
        raise HTTPException(409, "Demo tesis kimliği doğrulanamadı")
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, **kw)
    exely = await database.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, **kw)
    runner = await database.hotelrunner_connections.find_one({"tenant_id": tenant_id, "is_active": True}, **kw)
    if (settings or {}).get("business_date") != "2026-10-24" or not exely or str(exely.get("hotel_code")) != "501694" or exely.get("mode") != "sandbox":
        raise HTTPException(409, "Demo iş günü / TEST bağlantısı değişti")
    if exely.get("ari_write_enabled") or exely.get("auto_sync_reservations") or runner:
        raise HTTPException(409, "Demo dış bağlantıları kapalı olmalı")


async def _rows(database, collection, tenant_id, query, session):
    return await database[collection].find({"tenant_id": tenant_id, **query}, {"_id": 0}, **({"session": session} if session is not None else {})).to_list(None)


def _patch(plan, collection, row, values, kind):
    for key, value in values.items():
        if row.get(key) is not None and row[key] != value and key not in {"status", "pms_status"}:
            raise HTTPException(409, "Mevcut kaynak alanı farklı; otomatik üzerine yazılamaz: " + collection + ":" + row["id"] + ":" + key)
    after = {**row, **values, "demo_reconstruction": provenance(kind)}
    plan["documents"].append({"collection": collection, "id": row["id"], "before": row,
                              "before_hash": fingerprint(row), "set": {**values, "demo_reconstruction": provenance(kind)},
                              "after_hash": fingerprint(after)})


def allocated_demo_rows(rows):
    """Explicitly NEW demo FIFO instruction, not a claim about old settlements."""
    rows = deepcopy(rows)
    if len(rows) != 11 or sum((minor(r["amount"]) * (1 if r["transaction_type"] in DEBITS else -1) for r in rows), 0) != 450300:
        raise HTTPException(409, "İncelenen 4.503 TRY cari kaynakları değişti")
    remaining = {r["id"]: minor(r["amount"]) for r in rows if r["transaction_type"] in DEBITS}
    ordered = sorted((r for r in rows if r["transaction_type"] in DEBITS), key=lambda r: (r["created_at"], r["id"]))
    for row in sorted(rows, key=lambda r: (r["created_at"], r["id"])):
        if row.get("currency") not in {None, "TRY"} or row.get("allocations") or row.get("due_date"):
            raise HTTPException(409, "Cari vade / mahsup kaynağı değişti; yeniden inceleyin")
        row["currency"] = "TRY"
        if row["transaction_type"] in DEBITS:
            row["due_date"] = (date.fromisoformat(str(row["created_at"])[:10]) + timedelta(days=30)).isoformat()
        elif row["transaction_type"] in CREDITS:
            left, allocations = minor(row["amount"]), []
            for charge in ordered:
                if charge["created_at"] > row["created_at"]:
                    continue
                used = min(left, remaining[charge["id"]])
                if used:
                    allocations.append({"transaction_id": charge["id"], "amount": used / 100})
                    remaining[charge["id"]] -= used
                    left -= used
            if left:
                raise HTTPException(409, "Demo mahsup tutarı önceki borçlarla bağlanamıyor")
            row["allocations"] = allocations
        else:
            raise HTTPException(409, "Bilinmeyen cari kaynak türü")
    return rows


def historical_metadata_incident(rows):
    findings = []
    for row in rows:
        if row.get("record_hash") == compute_record_hash(row, row["seq"], row.get("prev_hash", "")):
            continue
        restored = {**row, "ip_address": None, "user_agent": None}
        if row.get("record_hash") != compute_record_hash(restored, row["seq"], row.get("prev_hash", "")):
            raise HTTPException(409, "Açıklanamayan audit değişikliği; demo onarımı durduruldu")
        findings.append({"id": row["id"], "seq": row["seq"], "sealed_hash": row["record_hash"],
                         "observed_content_hash": compute_record_hash(row, row["seq"], row.get("prev_hash", "")),
                         "original_seal_reproduced_without_late_attribution": True})
    if len(findings) != 69:
        raise HTTPException(409, "İncelenen 69 tarihî audit bulgusu değişti")
    return {"resolution": "documented_historical_attribution_drift", "original_chain_valid": False,
            "original_records_rewritten": False, "findings": sorted(findings, key=lambda r: r["seq"])}


async def preview(database, tenant_id, session=None):
    await guard(database, tenant_id, session)
    receipt = await database.demo_source_remediations.find_one({"tenant_id": tenant_id, "id": POLICY}, **({"session": session} if session is not None else {}))
    if receipt:
        return {"already_applied": True, **receipt["result"]}
    plan = {"policy_id": POLICY, "notice": NOTICE, "rates_to_try": {"USD": "50", "EUR": "55"},
            "demo_terms_days": 30, "demo_comp_tax_policy": "zero_billed_gross_zero_booked_tax_not_fiscal_certification", "documents": []}
    holds = await _rows(database, "bookings", tenant_id, {"id": {"$in": list(HOLDS)}}, session)
    inbox = await _rows(database, "exely_reservations", tenant_id, {"external_id": {"$in": list(EXTERNAL)}}, session)
    if len(holds) != 3 or len(inbox) != 2:
        raise HTTPException(409, "Eski Exely kaynak sayısı değişti")
    for row in holds:
        if (row.get("status") != "pending_mapping" or row.get("room_id") or row.get("external_reservation_id") not in EXTERNAL
            or any(row.get(k) for k in ("checked_in_at", "checked_out_at", "actual_check_in", "actual_check_out"))):
            raise HTTPException(409, "Eski Exely kaydı artık boş bir eşleştirme beklemesi değil")
        locks = await _rows(database, "room_night_locks", tenant_id, {"booking_id": row["id"]}, session)
        sentinel = "ota-unmatched::exely::" + row["external_reservation_id"]
        if any(lock.get("room_id") != sentinel or lock.get("lock_type") != "ota_unmatched_hold" for lock in locks):
            raise HTTPException(409, "Fiziksel oda kilidi olan bekleme arşivlenemez")
        for coll in ("folios", "payments", "folio_charges", "extra_charges", "deposits", "security_funds"):
            if await _rows(database, coll, tenant_id, {"booking_id": row["id"]}, session):
                raise HTTPException(409, "Finansal kaydı olan bekleme arşivlenemez")
        _patch(plan, "bookings", row, {"status": "archived_demo"}, "unaccepted_test_hold_archived_not_a_stay_or_noshow")
    for row in inbox:
        if row.get("pms_status") != "pending_mapping" or row.get("delivery_confirmed"):
            raise HTTPException(409, "Kanal teslimat durumu değişti")
        _patch(plan, "exely_reservations", row, {"pms_status": "archived_demo"}, "local_test_archive_no_provider_cancellation_or_ack")
    payments = await _rows(database, "payments", tenant_id, {"id": {"$in": list(FX_IDS)}}, session)
    if len(payments) != 6:
        raise HTTPException(409, "Altı döviz hareketi bulunamadı")
    totals = {"USD": 0, "EUR": 0}
    cashier_rows = []
    for row in payments:
        code = FX_IDS[row["id"]]
        if row.get("currency") != code or row.get("method") not in {"card", "bank_transfer"} or row.get("business_date") != "2026-10-24" or not effective_collection(row):
            raise HTTPException(409, "İncelenen döviz kaynağı değişti")
        totals[code] += minor(effective_collection(row))
        values = {"received_to_try_rate": float(plan["rates_to_try"][code]), "reporting_currency": "TRY",
                  "reporting_amount": abs(minor(row["amount"])) / 100 * float(plan["rates_to_try"][code]), "exchange_rate_date": row["business_date"]}
        _patch(plan, "payments", row, values, "synthetic_receipt_value_not_historical_fx_evidence")
        valued = {**row, **values, "demo_reconstruction": provenance("synthetic_receipt_value_not_historical_fx_evidence")}
        cash = cashier_values(valued)
        cashier_rows.append({"id": str(uuid5(NAMESPACE_URL, POLICY + ":" + row["id"])), "ref_type": "payment", "ref_id": row["id"],
            "idempotency_key": "payment:" + row["id"], "amount": cash["amount"], "currency": cash["currency"],
            "original_amount": cash["original_amount"], "fx_rate": cash["fx_rate"], **cash["extra"],
            "method": row["method"], "direction": "out" if row["amount"] < 0 else "in", "type": "refund" if row["amount"] < 0 else "folio_payment",
            "business_date": row["business_date"], "description": NOTICE, "demo_reconstruction": provenance("cashier_source_reconstruction")})
    if any(totals.values()) or sum(minor(r["amount"]) * (1 if r["direction"] == "in" else -1) for r in cashier_rows):
        raise HTTPException(409, "Eski iade kaynakları native/TRY net sıfır değil")
    for code in totals:
        group = [r for r in payments if r["currency"] == code]
        if len({r.get("booking_id") for r in group}) != 1 or sorted(minor(r["amount"]) for r in group) != [-6000, -4000, 10000]:
            raise HTTPException(409, "İncelenen 100/40/60 demo ön ödeme grubu değişti")
    shifts = await _rows(database, "cashier_shifts", tenant_id, {"status": "open"}, session)
    if len(shifts) != 1 or shifts[0].get("business_date") != "2026-10-24":
        raise HTTPException(409, "24 Ekim açık demo kasa vardiyası gerekli")
    if await _rows(database, "cashier_shifts", tenant_id, {"transactions.ref_id": {"$in": list(FX_IDS)}}, session):
        raise HTTPException(409, "Döviz kaynakları kasada zaten temsil ediliyor; otomatik çoğaltılamaz")
    plan["cashier"] = {"id": shifts[0]["id"], "before_hash": fingerprint(shifts[0]), "append": sorted(cashier_rows, key=lambda r: r["ref_id"])}
    comp = await _rows(database, "extra_charges", tenant_id, {"id": {"$in": list(COMP_IDS)}}, session)
    if len(comp) != 8:
        raise HTTPException(409, "Sekiz full-comp kaynak bulunamadı")
    for row in comp:
        if not row.get("is_complimentary") or row.get("complimentary_scope") != "full" or minor(row.get("total")) or not row.get("complimentary_original_amount"):
            raise HTTPException(409, "Full-comp kaynak tutarı değişti")
        _patch(plan, "extra_charges", row, {"tax_amount": 0.0, "vat_amount": 0.0, "tax_breakdown": {"vat": 0.0, "accommodation_tax": 0.0}}, "demo_booked_zero_tax_not_tax_exemption_evidence")
    account = await _rows(database, "cari_accounts", tenant_id, {"id": ACCOUNT}, session)
    rows = await _rows(database, "cari_transactions", tenant_id, {"cari_account_id": ACCOUNT}, session)
    if len(account) != 1 or minor(account[0].get("balance")) != 450300:
        raise HTTPException(409, "İncelenen cari hesabın bakiyesi değişti")
    for before, after in zip(sorted(rows, key=lambda r: r["id"]), sorted(allocated_demo_rows(rows), key=lambda r: r["id"]), strict=True):
        _patch(plan, "cari_transactions", before, {k: after[k] for k in ("currency", "due_date", "allocations") if k in after}, "new_demo_terms_and_explicit_allocation_not_historical_contract")
    day5 = await _rows(database, "payments", tenant_id, {"id": {"$in": list(SEPTEMBER_IDS)}}, session)
    if len(day5) != 13 or sum(minor(effective_collection(r)) for r in day5) != 1462100:
        raise HTTPException(409, "5 Eylül kaynak kümesi değişti")
    for row in day5:
        if row.get("business_date") != "2026-09-05" or row.get("currency") not in {None, "TRY"} or row.get("method") != "cash":
            raise HTTPException(409, "5 Eylül ödeme kaynağı değişti")
        _patch(plan, "payments", row, {"currency": "TRY", "reporting_currency": "TRY", "reporting_amount": abs(row["amount"]), "exchange_rate_date": "2026-09-05"}, "demo_legacy_currency_resolution_not_original_currency_evidence")
    original = await _rows(database, "gl_journal_entries", tenant_id, {"id": RECLASS_ENTRY}, session)
    source = next(row for row in day5 if row["id"] == RECLASS_PAYMENT)
    if len(original) != 1 or not verify_journal_entry_hash(original[0]) or original[0].get("source_ref") != RECLASS_RUN or minor(source["amount"]) != 120000 or not str(source.get("processed_at", "")).startswith("2026-09-27"):
        raise HTTPException(409, "27 Eylül yeniden sınıflama kanıtı değişti")
    expected = {"100": 120000, "120": -120000}
    actual = {}
    for line in original[0]["lines"]:
        actual[line["account_code"]] = actual.get(line["account_code"], 0) + minor(line.get("debit")) - minor(line.get("credit"))
    if {k: v for k, v in actual.items() if v} != expected:
        raise HTTPException(409, "27 Eylül özgün yevmiye hesapları değişti")
    plan["reclassification"] = {"run_id": RECLASS_RUN, "original_entry_id": RECLASS_ENTRY, "original_entry_hash": original[0]["entry_hash"],
        "source_payment_id": source["id"], "source_payment_after_hash": next(r["after_hash"] for r in plan["documents"] if r["collection"] == "payments" and r["id"] == source["id"]),
        "amount_minor": 120000, "old_day": "2026-09-27", "accounting_day": "2026-09-05", "basis": "approved_demo_reclassification_not_verified_original_journal_lineage"}
    audit = await _rows(database, "audit_logs", tenant_id, {"record_hash": {"$exists": True}}, session)
    audit += await _rows(database, "audit_logs_archive", tenant_id, {"record_hash": {"$exists": True}}, session)
    plan["audit_incident"] = historical_metadata_incident(audit)
    plan["documents"].sort(key=lambda r: (r["collection"], r["id"]))
    plan["source_fingerprint"] = fingerprint(plan)
    return plan


def public_plan(plan):
    if plan.get("already_applied"):
        return plan
    return {k: v for k, v in plan.items() if k not in {"documents", "cashier", "audit_incident"}} | {
        "documents": [{k: row[k] for k in ("collection", "id", "before_hash", "set")} for row in plan["documents"]],
        "cashier_append_count": len(plan["cashier"]["append"]), "audit_incident_count": len(plan["audit_incident"]["findings"]),
        "audit_chain_will_remain_fail_visible": True, "requires_separate_gl_preview_post": True}


async def apply(database, client, user, data):
    request = data.model_dump(mode="json")
    payload_hash = fingerprint(request)

    async def commit(session):
        if session is None:
            raise HTTPException(503, "Demo onarımı transaction desteği gerektirir")
        await guard(database, user.tenant_id, session)
        existing = await database.demo_source_remediations.find_one({"tenant_id": user.tenant_id, "id": POLICY}, session=session)
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise HTTPException(409, "Bu demo onarımı farklı içerikle zaten uygulandı")
            return {**existing["result"], "replayed": True}
        plan = await preview(database, user.tenant_id, session)
        if plan["source_fingerprint"] != data.source_fingerprint:
            raise HTTPException(409, "Demo kaynakları değişti; önizlemeyi yeniden inceleyin")
        now = datetime.now(UTC).isoformat()
        for row in plan["documents"]:
            current = await database[row["collection"]].find_one({"tenant_id": user.tenant_id, "id": row["id"]}, {"_id": 0}, session=session)
            if fingerprint(current) != row["before_hash"]:
                raise HTTPException(409, "Kaynak işlem sırasında değişti")
            await database.demo_source_preimages.insert_one({"tenant_id": user.tenant_id, "policy_id": POLICY,
                "collection": row["collection"], "source_id": row["id"], "before": row["before"],
                "before_hash": row["before_hash"], "after_hash": row["after_hash"], "created_at": now}, session=session)
            result = await database[row["collection"]].update_one({"tenant_id": user.tenant_id, "id": row["id"]}, {"$set": row["set"]}, session=session)
            if result.modified_count != 1:
                raise HTTPException(409, "Demo kaynak güncellemesi uygulanamadı")
        shift = plan["cashier"]
        txns = [{**r, "created_at": now, "timestamp": now, "created_by": user.id, "created_by_name": user.name} for r in shift["append"]]
        changed = await database.cashier_shifts.update_one({"tenant_id": user.tenant_id, "id": shift["id"], "status": "open",
            "transactions.ref_id": {"$nin": list(FX_IDS)}}, {"$push": {"transactions": {"$each": txns}}}, session=session)
        if changed.modified_count != 1:
            raise HTTPException(409, "Kasa kaynakları eşzamanlı değişti")
        result = {"policy_id": POLICY, "applied": True, "replayed": False, "notice": NOTICE,
            "request_id": str(data.request_id),
            "source_fingerprint": plan["source_fingerprint"], "document_count": len(plan["documents"]),
            "cashier_appended": len(txns), "historical_audit_findings_documented": 69, "audit_chain_valid": False,
            "historical_source_verified": False, "business_date_unchanged": "2026-10-24", "provider_writes": 0,
            "reason": data.reason, "applied_at": now, "applied_by": user.id}
        entry = build_audit_entry(actor_id=user.id, tenant_id=user.tenant_id, property_id=user.tenant_id,
            entity_type="demo_source_remediation", entity_id=POLICY, action="demo_sources_reconstructed",
            metadata={"actor_name": user.name})
        entry["before_snapshot"] = {"source_fingerprint": plan["source_fingerprint"], "before_hashes": [r["before_hash"] for r in plan["documents"]], "cashier_before_hash": shift["before_hash"]}
        entry["after_snapshot"] = {"result": result, "document_after_hashes": [r["after_hash"] for r in plan["documents"]],
            "audit_incident": plan["audit_incident"], "reclassification": plan["reclassification"]}
        await append_audit_log(database, entry, session=session, require_chain=True)
        await database.demo_source_remediations.insert_one({"tenant_id": user.tenant_id, "id": POLICY,
            "payload_hash": payload_hash, "result": result, "plan": plan,
            "audit_id": entry["id"], "audit_hash": entry["record_hash"]}, session=session)
        return result

    await guard(database, user.tenant_id)
    target_payments = await _rows(database, "payments", user.tenant_id, {"id": {"$in": [*FX_IDS, *SEPTEMBER_IDS]}}, None)
    target_comp = await _rows(database, "extra_charges", user.tenant_id, {"id": {"$in": list(COMP_IDS)}}, None)
    booking_ids = set(HOLDS) | {r["booking_id"] for r in [*target_payments, *target_comp] if r.get("booking_id")}
    resources = sorted([("demo_source_remediation", POLICY), ("cari_account", ACCOUNT), *[("booking", bid) for bid in booking_ids]])
    result = await with_resource_locks(client=client, db=database, tenant_id=user.tenant_id,
        locks_collection="reservation_financial_locks", resources=resources, callback=commit)
    try:
        from modules.pms_core.deposit_operations import refresh_reports
        await refresh_reports(user.tenant_id)
    except Exception:
        # The durable receipt must be recoverable even if optional caches fail.
        import logging
        logging.getLogger(__name__).warning("Demo reconstruction committed; report cache refresh unavailable")
    return result


async def reclassification_proof(database, tenant_id, run_id, original):
    """Narrow demo-only exception backed by a sealed reconstruction receipt.

    Missing sources alone never authorize a contra; production and all other
    dates continue to fail closed. This attests a DEMO decision, not historical
    journal lineage that was never stored.
    """
    if tenant_id != TENANT or run_id != RECLASS_RUN or not original:
        return None
    receipt = await database.demo_source_remediations.find_one({"tenant_id": tenant_id, "id": POLICY}, {"_id": 0})
    if not receipt:
        return None
    audit = await database.audit_logs.find_one({"tenant_id": tenant_id, "id": receipt["audit_id"]}, {"_id": 0})
    proof = receipt["plan"]["reclassification"]
    if (not audit or audit.get("record_hash") != receipt["audit_hash"]
        or compute_record_hash(audit, audit["seq"], audit["prev_hash"]) != receipt["audit_hash"]
        or audit["after_snapshot"]["reclassification"] != proof
        or original.get("id") != proof["original_entry_id"] or original.get("entry_hash") != proof["original_entry_hash"]
        or not verify_journal_entry_hash(original)):
        raise HTTPException(409, "Demo yeniden sınıflama mühür/fiş kanıtı değişti")
    source = await database.payments.find_one({"tenant_id": tenant_id, "id": proof["source_payment_id"]}, {"_id": 0})
    if fingerprint(source) != proof["source_payment_after_hash"]:
        raise HTTPException(409, "Demo yeniden sınıflama ödeme kaynağı değişti")
    return {"kind": "demo_reclassified_payment", "id": POLICY + ":" + proof["source_payment_id"],
            "currency": "TRY", "proof": proof, "audit_hash": receipt["audit_hash"], "historical_source_verified": False}
