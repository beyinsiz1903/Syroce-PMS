"""Append-only review of three fixed synthetic legacy accounting exceptions.

Never stamps a historical journal, changes a source, posts money or asserts
historical/fiscal certification. A current audit receipt attests the exact
observed source snapshots; changing any of them invalidates the review.
"""
from datetime import UTC, datetime

from fastapi import HTTPException

from core.audit_chain import append_audit_log, compute_record_hash
from core.booking_atomicity import with_resource_locks
from core.integrations.operational_gl_valuation import digest, minor
from modules.pms_core.demo_source_remediation import POLICY as SOURCE_POLICY
from modules.pms_core.demo_source_remediation import TENANT, fingerprint
from shared_kernel.audit_helper import build_audit_entry
from shared_kernel.gl_posting import GLPostingError, normalize_journal_lines, verify_journal_entry_hash

POLICY = "demo-legacy-accounting-review-20261026-v1"
NOTICE = "Bugünkü DEMO kaynak incelemesi; özgün tarihî mühür veya gerçek mali belge doğrulaması değildir."
RUN = "63499e9c-3d33-401e-9608-1f45fa555fef"
ORIGINAL = "3beb5ef1-e776-4b06-b77a-db168d32c838"
CORRECTION = "36e9c3f3-4eba-4d34-9687-c73e8e55444f"
PAYMENT = "c0ea0c02-2eb2-4d9a-a2c1-d79390cece2c"
LEGACY = {
    "7e1f453c-26d8-4081-8668-a702ce0f8ed4": ("2026-08-15", 100),
    "f9625778-5bb1-45f7-bd1e-cc5fcb317c78": ("2026-08-16", 1),
}


def require(condition, message):
    if not condition:
        raise HTTPException(409, message)


async def row(db, collection, tenant, query, session=None):
    return await db[collection].find_one({"tenant_id": tenant, **query}, {"_id": 0},
        **({"session": session} if session is not None else {}))


async def audit_receipt(db, tenant, receipt, session=None):
    if not receipt:
        return False
    audit = await row(db, "audit_logs", tenant, {"id": receipt.get("audit_id")}, session)
    if not audit:
        audit = await row(db, "audit_logs_archive", tenant, {"id": receipt.get("audit_id")}, session)
    return bool(audit and audit.get("seq") and audit.get("record_hash") == receipt.get("audit_hash")
        and compute_record_hash(audit, audit["seq"], audit.get("prev_hash", "")) == receipt["audit_hash"]
        and isinstance(audit.get("after_snapshot"), dict)
        and audit["after_snapshot"].get("plan_hash") == fingerprint(receipt.get("plan"))
        and audit["after_snapshot"].get("payload_hash") == receipt.get("payload_hash")
        and audit["after_snapshot"].get("result") == receipt.get("result"))


async def guard(db, tenant, session=None):
    if tenant != TENANT:
        raise HTTPException(404, "Demo inceleme kapsamı bulunamadı")
    kw = {"session": session} if session is not None else {}
    identity = await db.tenants.find_one({"id": tenant}, {"_id": 0}, **kw)
    settings = await row(db, "tenant_settings", tenant, {}, session)
    exely = await row(db, "exely_connections", tenant, {"is_active": True}, session)
    runner = await row(db, "hotelrunner_connections", tenant, {"is_active": True}, session)
    require(identity and str(identity.get("hotel_id")) == "100001" and identity.get("property_name") == "Syroce Demo Hotel", "Demo tesis kimliği değişti")
    require(settings and settings.get("business_date") in {"2026-10-24", "2026-10-25"}, "İncelenen Demo iş günü değişti")
    require(exely and str(exely.get("hotel_code")) == "501694" and exely.get("mode") == "sandbox"
        and not exely.get("ari_write_enabled") and not exely.get("auto_sync_reservations") and not runner, "Demo dış bağlantıları kapalı olmalı")


def balances(entry):
    values = {}
    for line in entry["lines"]:
        code = line["account_code"]
        values[code] = values.get(code, 0) + minor(line.get("debit")) - minor(line.get("credit"))
    return {k: v for k, v in values.items() if v}


async def plan(db, tenant, session=None):
    if tenant != TENANT:
        raise HTTPException(404, "Demo inceleme kapsamı bulunamadı")
    snapshots = []
    for bid, (day, value) in LEGACY.items():
        entry = await row(db, "gl_journal_entries", tenant, {"id": bid}, session)
        require(entry and entry.get("date") == day and entry.get("status") == "posted" and entry.get("source") == "manual"
            and not entry.get("entry_hash") and not entry.get("posting_sequence"), "İncelenen eski mühürsüz fiş değişti")
        try:
            _, debit, credit = normalize_journal_lines(entry.get("lines"))
        except GLPostingError as exc:
            raise HTTPException(409, "Eski Demo fiş satırları doğrulanamadı") from exc
        require(minor(debit) == minor(credit) == value
            and balances(entry) == {"100": value, "600": -value}, "Eski Demo fiş tutarı/hesapları değişti")
        snapshots.append({"collection": "gl_journal_entries", "id": bid, "value": entry})
        if entry.get("reversal_status"):
            reverse = await row(db, "gl_journal_entries", tenant, {"id": entry.get("reversed_by_entry_id")}, session)
            require(reverse and reverse.get("reverses_entry_id") == bid and verify_journal_entry_hash(reverse)
                and balances(reverse) == {"100": -value, "600": value}, "Eski fişin mevcut ters kaydı doğrulanamadı")
            snapshots.append({"collection": "gl_journal_entries", "id": reverse["id"], "value": reverse})
    original = await row(db, "gl_journal_entries", tenant, {"id": ORIGINAL}, session)
    correction = await row(db, "gl_journal_entries", tenant, {"id": CORRECTION}, session)
    for entry, source, expected in ((original, "night_audit", {"100": 800000, "120": -800000}),
                                    (correction, "night_audit_correction", {"100": -800000, "120": 800000})):
        require(entry and entry.get("date") == "2026-10-15" and entry.get("source") == source and entry.get("source_ref") == RUN
            and entry.get("status") == "posted" and not entry.get("reversal_status") and verify_journal_entry_hash(entry)
            and balances(entry) == expected, "15 Ekim kayıt çifti değişti")
        require(not await row(db, "gl_journal_entries", tenant, {"reverses_entry_id": entry["id"]}, session), "Kayıt çifti sonradan ters çevrilmiş")
        snapshots.append({"collection": "gl_journal_entries", "id": entry["id"], "value": entry})
    manifest = correction.get("source_manifest") or {}
    require(manifest.get("sources") == [] and manifest.get("source_hash") == digest({k: v for k, v in manifest.items() if k != "source_hash"}), "Mevcut boş kaynak özeti değişti")
    run = await row(db, "night_audit_runs", tenant, {"id": RUN}, session)
    require(run and run.get("status") == "completed" and run.get("gl_journal_entry_id") == ORIGINAL and run.get("gl_valued_entry_id") == CORRECTION, "15 Ekim gün sonu bağı değişti")
    # Only fixed link fields, not incidental diagnostic/clock metadata.
    snapshots.append({"collection": "night_audit_runs", "id": RUN, "value": {k: run.get(k) for k in
        ("id", "tenant_id", "business_date", "status", "gl_journal_entry_id", "gl_valued_entry_id")}})
    source = await row(db, "payments", tenant, {"id": PAYMENT}, session)
    prior = await row(db, "demo_source_remediations", tenant, {"id": SOURCE_POLICY}, session)
    require(prior is not None, "Önceki kaynak yeniden-kurma kanıtı yok")
    previous_audit = await row(db, "audit_logs", tenant, {"id": prior.get("audit_id")}, session)
    if not previous_audit:
        previous_audit = await row(db, "audit_logs_archive", tenant, {"id": prior.get("audit_id")}, session)
    require(previous_audit and previous_audit.get("seq") and previous_audit.get("record_hash") == prior.get("audit_hash")
        and compute_record_hash(previous_audit, previous_audit["seq"], previous_audit.get("prev_hash", "")) == prior["audit_hash"], "Önceki kaynak kararının mührü değişti")
    prior_plan = prior.get("plan") or {}
    require(isinstance(prior_plan, dict) and isinstance(prior_plan.get("documents"), list)
        and all(isinstance(d, dict) and d.get("after_hash") for d in prior_plan["documents"])
        and isinstance(previous_audit.get("before_snapshot"), dict)
        and isinstance(previous_audit.get("after_snapshot"), dict), "Önceki kaynak kararının planı eksik")
    prior_hash = fingerprint({k: v for k, v in prior_plan.items() if k != "source_fingerprint"})
    require(prior_plan.get("source_fingerprint") == prior_hash
        and previous_audit.get("before_snapshot", {}).get("source_fingerprint") == prior_hash
        and previous_audit.get("after_snapshot", {}).get("document_after_hashes") == [d["after_hash"] for d in prior_plan["documents"]], "Önceki karar planı audit kanıtıyla eşleşmiyor")
    reviewed = next((d for d in prior_plan["documents"] if d.get("collection") == "payments" and d.get("id") == PAYMENT), None)
    require(source and reviewed and fingerprint(source) == reviewed["after_hash"] and minor(source["amount"]) == 800000
        and source.get("currency") == "TRY" and source.get("business_date") == "2026-09-05"
        and source.get("method") == "cash" and not source.get("voided") and str(source.get("processed_at", "")).startswith("2026-10-15"), "8.000 TRY'nin özgün/güncel kaynak dayanağı değişti")
    september = await row(db, "night_audit_runs", tenant, {"business_date": "2026-09-05", "status": "completed", "dry_run": {"$ne": True}}, session)
    valued = await row(db, "gl_journal_entries", tenant, {"id": (september or {}).get("gl_valued_entry_id")}, session)
    require(valued and verify_journal_entry_hash(valued), "5 Eylül değerleme fişi doğrulanamadı")
    represented = [s for s in valued.get("source_manifest", {}).get("sources", []) if s.get("kind") == "payment" and s.get("id") == PAYMENT]
    require(len(represented) == 1 and represented[0].get("amount_minor") == 800000 and represented[0].get("currency") == "TRY", "5 Eylül kaynağı tek kez temsil etmeli")
    snapshots.extend([{"collection": "payments", "id": PAYMENT, "value": source},
        {"collection": "gl_journal_entries", "id": valued["id"], "value": valued}])
    return {"policy_id": POLICY, "notice": NOTICE, "historical_source_verified": False, "original_seals_created": 0,
        "new_journals": 0, "source_run_id": RUN, "source_accounting_day": "2026-09-05", "duplicate_posting_day": "2026-10-15",
        "amount_minor": 800000, "legacy_ids": sorted(LEGACY), "prior_source_audit_hash": prior["audit_hash"],
        "snapshots": sorted(snapshots, key=lambda r: (r["collection"], r["id"]))}


async def verified(db, tenant):
    if tenant != TENANT:
        return None
    receipt = await row(db, "demo_source_remediations", tenant, {"id": POLICY})
    if not receipt:
        return None
    require(await audit_receipt(db, tenant, receipt), "Demo inceleme kararı/audit mührü doğrulanamadı")
    current = await plan(db, tenant)
    require(current == receipt["plan"], "İncelenen kaynak/fiş sonradan değişti; yeniden inceleme gerekli")
    return {"policy_id": POLICY, "review_valid": True, "historical_source_verified": False,
        "original_seals_created": 0, "legacy_reviewed_count": len(LEGACY), "audit_hash": receipt["audit_hash"], "notice": NOTICE}


async def preview(db, tenant):
    await guard(db, tenant)
    result = await verified(db, tenant)
    current = await plan(db, tenant)
    return {"applied": bool(result), "review": result, "policy_id": POLICY, "notice": NOTICE,
        "source_fingerprint": fingerprint(current), "legacy_ids": current["legacy_ids"], "amount_minor": current["amount_minor"],
        "original_seals_created": 0, "new_journals": 0, "historical_source_verified": False}


async def apply(db, client, user, data):
    payload_hash = fingerprint(data.model_dump(mode="json"))

    async def commit(session):
        require(session is not None, "İnceleme kararı transaction gerektirir")
        await guard(db, user.tenant_id, session)
        old = await row(db, "demo_source_remediations", user.tenant_id, {"id": POLICY}, session)
        if old:
            require(old["payload_hash"] == payload_hash and await audit_receipt(db, user.tenant_id, old, session), "İnceleme farklı içerikle kaydedilmiş veya mührü değişmiş")
            require(await plan(db, user.tenant_id, session) == old["plan"], "İnceleme kaynakları sonradan değişmiş")
            return {**old["result"], "replayed": True}
        current = await plan(db, user.tenant_id, session)
        require(fingerprint(current) == data.source_fingerprint, "Kaynak özeti değişti; önizlemeyi yeniden inceleyin")
        result = {"policy_id": POLICY, "applied": True, "replayed": False, "request_id": str(data.request_id),
            "reviewed_by": user.id, "reviewed_at": datetime.now(UTC).isoformat(), "reason": data.reason,
            "notice": NOTICE, "historical_source_verified": False, "original_seals_created": 0, "new_journals": 0, "legacy_reviewed_count": 2}
        audit = build_audit_entry(actor_id=user.id, tenant_id=user.tenant_id, property_id=user.tenant_id,
            entity_type="demo_accounting_review", entity_id=POLICY, action="demo_legacy_accounting_reviewed")
        audit["after_snapshot"] = {"plan_hash": fingerprint(current), "payload_hash": payload_hash, "result": result}
        await append_audit_log(db, audit, session=session, require_chain=True)
        await db.demo_source_remediations.insert_one({"tenant_id": user.tenant_id, "id": POLICY,
            "payload_hash": payload_hash, "plan": current, "result": result, "audit_id": audit["id"], "audit_hash": audit["record_hash"]}, session=session)
        return result

    await guard(db, user.tenant_id)
    return await with_resource_locks(client=client, db=db, tenant_id=user.tenant_id,
        locks_collection="reservation_financial_locks", resources=[("demo_accounting_review", POLICY)], callback=commit)
