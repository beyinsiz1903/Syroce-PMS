"""Two explicitly authorized synthetic classifications, never historical tax proof.

Only missing original-concession metadata is added. Posted money, dates, source
identities, sealed GL entries and external systems are untouched. Complete before
images and the new test assumption are sealed in the same transaction.
"""
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException

from core.audit_chain import append_audit_log, compute_record_hash
from core.booking_atomicity import with_resource_locks
from core.report_cache import invalidate_financial_report_caches
from modules.pms_core.demo_source_remediation import fingerprint
from shared_kernel.audit_helper import build_audit_entry

TENANT = "5bad4a34-6ee3-4566-9053-741b7375a9cf"
POLICY = "demo-comp-tax-reconstruction-20261128-v1"
NOTICE = "Yeni sentetik test tanımı: %20 KDV dahil. Özgün tarihî net/vergi doğrulanmış değildir. Önceki kaynak sürümleri korunur."
SOURCES = (("folio_charges", "cacc4ae5-bd21-55cf-bddb-d975d9ff6ba3", 25),
           ("extra_charges", "fd2a768f-fc39-495b-ae63-716281a43116", 60))


async def _guard(database, tenant_id, session=None):
    if tenant_id != TENANT:
        raise HTTPException(404, "Bu test düzeltmesinin kapsamı bulunamadı")
    kw = {"session": session} if session is not None else {}
    tenant = await database.tenants.find_one({"id": tenant_id}, {"_id": 0}, **kw)
    link = await database.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0}, **kw)
    if (not tenant or str(tenant.get("hotel_id")) != "100001" or tenant.get("property_name") != "Syroce Demo Hotel"
        or not link or str(link.get("hotel_code")) != "501694" or link.get("mode") not in {"sandbox", "test"}):
        raise HTTPException(409, "TEST501694 tesis kimliği doğrulanamadı")


async def _receipt(database, tenant_id, session=None):
    kw = {"session": session} if session is not None else {}
    receipt = await database.demo_comp_reconstructions.find_one({"tenant_id": tenant_id, "id": POLICY}, {"_id": 0}, **kw)
    if not receipt:
        return None
    audit = await database.audit_logs.find_one({"tenant_id": tenant_id, "id": receipt["audit_id"]}, {"_id": 0}, **kw)
    if (not audit or audit.get("record_hash") != receipt["audit_hash"]
        or compute_record_hash(audit, audit["seq"], audit["prev_hash"]) != receipt["audit_hash"]
        or audit.get("before_snapshot") != {"hash": fingerprint(receipt["before"])}
        or audit.get("after_snapshot") != {"hash": fingerprint(receipt["result"]), "after_hashes": receipt["after_hashes"]}):
        raise HTTPException(409, "Test düzeltmesinin geçmiş/mühür kanıtı değişti")
    for collection, source_id, _ in SOURCES:
        row = await database[collection].find_one({"tenant_id": tenant_id, "id": source_id}, {"_id": 0}, **kw)
        if fingerprint(row) != receipt["after_hashes"][source_id]:
            raise HTTPException(409, "Düzeltilmiş test kaynağı değişti")
    return receipt


async def preview(database, tenant_id, session=None):
    await _guard(database, tenant_id, session)
    existing = await _receipt(database, tenant_id, session)
    if existing:
        return {**existing["result"], "already_applied": True}
    kw = {"session": session} if session is not None else {}
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0}, **kw)
    try:
        day = date.fromisoformat(str((settings or {}).get("business_date") or ""))
    except ValueError as exc:
        raise HTTPException(409, "Düzeltme öncesi açık iş günü doğrulanmalıdır") from exc
    if not date(2026, 11, 12) <= day <= date(2026, 11, 30):
        raise HTTPException(409, "Bu test düzeltmesinin Kasım iş günü kapsamı değişti")
    documents = []
    for collection, source_id, gross in SOURCES:
        row = await database[collection].find_one({"tenant_id": tenant_id, "id": source_id}, {"_id": 0}, **kw)
        source_day = str((row or {}).get("business_date") or (row or {}).get("date") or (row or {}).get("charge_date") or "")[:10]
        if (not row or row.get("voided") or not row.get("is_complimentary") or row.get("currency") != "TRY"
            or row.get("total") != 0 or row.get("complimentary_original_amount") != gross
            or row.get("complimentary_original_tax_snapshot") is not None or row.get("demo_reconstruction")
            or source_day != "2026-11-12"):
            raise HTTPException(409, "İncelenen sıfır bedelli test kaynağı değişti: " + source_id)
        net = (Decimal(gross) / Decimal("1.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        snapshot = {"net_amount": float(net), "vat_amount": float(Decimal(gross) - net), "tax_amount": 0.0,
                    "vat_rate": 20, "currency": "TRY", "basis": "explicit_new_synthetic_test_definition",
                    "historical_source_verified": False, "policy_id": POLICY}
        documents.append({"collection": collection, "id": source_id, "original_gross": gross,
                          "snapshot": snapshot, "before": row, "before_hash": fingerprint(row)})
    plan = {"policy_id": POLICY, "notice": NOTICE, "historical_source_verified": False,
            "vat_rate": 20, "tax_inclusive": True, "currency": "TRY", "business_date": day.isoformat(), "documents": documents}
    plan["source_fingerprint"] = fingerprint(plan)
    return plan


def public_plan(plan):
    if plan.get("already_applied"):
        return plan
    return {**plan, "documents": [{k: v for k, v in row.items() if k != "before"} for row in plan["documents"]]}


async def apply(database, client, user, data):
    await _guard(database, user.tenant_id)
    payload_hash = fingerprint({"request_id": str(data.request_id), "source_fingerprint": data.source_fingerprint, "reason": data.reason})
    await database.demo_comp_reconstructions.create_index([("tenant_id", 1), ("id", 1)], unique=True)

    async def commit(session):
        if session is None:
            raise HTTPException(503, "Test düzeltmesi transaction desteği gerektirir")
        await _guard(database, user.tenant_id, session)
        existing = await _receipt(database, user.tenant_id, session)
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise HTTPException(409, "Bu test düzeltmesi farklı içerikle zaten uygulandı")
            return {**existing["result"], "replayed": True}
        plan = await preview(database, user.tenant_id, session)
        if plan["source_fingerprint"] != data.source_fingerprint:
            raise HTTPException(409, "Kaynaklar değişti; önizlemeyi yeniden inceleyin")
        now = datetime.now(UTC).isoformat()
        after_hashes = {}
        for document in plan["documents"]:
            meta = {"policy_id": POLICY, "basis": "demo_reconstruction", "historical_source_verified": False,
                    "notice": NOTICE, "before_hash": document["before_hash"], "reason": data.reason,
                    "applied_at": now, "applied_by": user.id, "definition_business_date": plan["business_date"]}
            values = {"complimentary_original_tax_snapshot": document["snapshot"], "demo_reconstruction": meta}
            after_hashes[document["id"]] = fingerprint({**document["before"], **values})
            changed = await database[document["collection"]].update_one(
                {"tenant_id": user.tenant_id, "id": document["id"], "complimentary_original_tax_snapshot": None},
                {"$set": values}, session=session)
            if changed.modified_count != 1:
                raise HTTPException(409, "Test kaynağı eşzamanlı değişti")
        result = {"policy_id": POLICY, "applied": True, "replayed": False, "notice": NOTICE,
                  "historical_source_verified": False, "business_date": plan["business_date"],
                  "source_fingerprint": plan["source_fingerprint"], "documents": public_plan(plan)["documents"],
                  "reason": data.reason, "applied_at": now, "applied_by": user.id, "provider_writes": 0,
                  "posted_amount_change": 0, "automatic_GL_posting": False}
        before = [row["before"] for row in plan["documents"]]
        audit = build_audit_entry(actor_id=user.id, tenant_id=user.tenant_id, property_id=user.tenant_id,
                                 entity_type="demo_comp_reconstruction", entity_id=POLICY, action="synthetic_comp_definition_applied",
                                 metadata={"actor_name": user.name})
        audit["before_snapshot"] = {"hash": fingerprint(before)}
        audit["after_snapshot"] = {"hash": fingerprint(result), "after_hashes": after_hashes}
        await append_audit_log(database, audit, session=session, require_chain=True)
        await database.demo_comp_reconstructions.insert_one({"tenant_id": user.tenant_id, "id": POLICY,
            "payload_hash": payload_hash, "before": before, "result": result, "after_hashes": after_hashes,
            "audit_id": audit["id"], "audit_hash": audit["record_hash"]}, session=session)
        return result

    result = await with_resource_locks(client=client, db=database, tenant_id=user.tenant_id,
        locks_collection="reservation_financial_locks", resources=[("demo_comp_reconstruction", POLICY)], callback=commit)
    invalidate_financial_report_caches(user.tenant_id)
    return result
