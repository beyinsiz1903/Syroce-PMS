"""Explicit, audited repair of a derived account balance, never of ledger rows.

The operator must review/accept source authority. No payment, write-off or GL
entry is invented to hide a difference. A changed preview requires re-review.
"""
import hashlib
import logging
from datetime import UTC, datetime

from bson import json_util
from fastapi import HTTPException

from core.audit_chain import append_audit_log
from core.booking_atomicity import with_resource_locks
from core.report_cache import invalidate_receivable_report_caches
from modules.pms_core.cari_receivable_reporting import CREDITS, DEBITS
from modules.pms_core.report_money import currency_code, money, rounded
from shared_kernel.audit_helper import build_audit_entry

SOURCES = {"cari_accounts": ("cari_transactions", "cari_account_id"),
           "city_ledger_accounts": ("city_ledger_transactions", "account_id")}
logger = logging.getLogger(__name__)


def _digest(value):
    return hashlib.sha256(json_util.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def projection_preview(account, rows, *, source, fallback_currency):
    native = currency_code(account.get("currency"), fallback_currency)
    reasons, identities = set(), set()
    total = money(0)
    target = None
    count = 0
    try:
        total = money(account.get("opening_balance"))
        for row in rows:
            if row.get("voided") or row.get("deleted") or row.get("status") in {"voided", "cancelled", "canceled", "failed"}:
                continue
            if row.get("status") not in {None, "completed", "posted"}:
                reasons.add("uncommitted_source")
                continue
            key = str(row.get("id") or row.get("_id") or "")
            if not key or key in identities:
                reasons.add("missing_or_duplicate_source_identity")
            identities.add(key)
            kind, amount = row.get("transaction_type"), money(row.get("amount"))
            if kind not in DEBITS | CREDITS or amount <= 0:
                reasons.add("invalid_source_amount_or_type")
                continue
            if currency_code(row.get("currency") or native) != native:
                reasons.add("mixed_currency_sources")
                continue
            total += amount if kind in DEBITS else -amount
            count += 1
        if not count and "opening_balance" not in account:
            reasons.add("source_history_missing")
        old = {key: rounded(account[key]) for key in ("balance", "current_balance") if key in account}
        if not old:
            reasons.add("projection_missing")
        if not reasons:
            target = rounded(total)
    except (ValueError, TypeError, ArithmeticError):
        reasons.add("invalid_account_source")
        old = {}
    return {
        "source": source, "account_id": str(account["id"]), "currency": native,
        "account_name": str(account.get("name") or account.get("account_name") or account.get("company_name") or account["id"]),
        "cached_balances": old, "source_balance": target, "source_transaction_count": count,
        "repairable": not reasons, "blocked_reasons": sorted(reasons),
        "needs_repair": target is not None and any(value != target for value in old.values()),
        "source_fingerprint": _digest({"source": source, "account": account, "rows": sorted(rows, key=_digest)}),
        "scope": "derived_account_balance_only_no_ledger_payment_or_gl_changes",
        "source_authority_requires_operator_review": True,
    }


async def load_projection_preview(database, tenant_id, source, account_id, *, fallback_currency, session=None):
    if source not in SOURCES:
        raise HTTPException(422, "Geçersiz cari kaynak türü")
    kwargs = {"session": session} if session is not None else {}
    accounts = await database[source].find({"tenant_id": tenant_id, "id": account_id}, **kwargs).to_list(2)
    if not accounts:
        raise HTTPException(404, "Cari hesap bulunamadı")
    if len(accounts) != 1:
        raise HTTPException(409, "Cari hesap kimliği birden fazla kayıtta var")
    account = accounts[0]
    other = "city_ledger_accounts" if source == "cari_accounts" else "cari_accounts"
    if await database[other].find_one({"tenant_id": tenant_id, "id": account_id}, **kwargs):
        raise HTTPException(409, "Cari hesap kimliği birden fazla kaynakta var")
    collection, field = SOURCES[source]
    aliases = [str(account[key]) for key in ("id", "account_id", "legacy_id", "_id") if account.get(key) is not None]
    rows = await database[collection].find({"tenant_id": tenant_id, field: {"$in": aliases}}, **kwargs).to_list(None)
    return account, projection_preview(account, rows, source=source, fallback_currency=fallback_currency)


async def repair_projection(database, client, user, source, account_id, data, *, fallback_currency):
    request = data.model_dump(mode="json")
    payload_hash = _digest(request)
    receipt_id = _digest([user.tenant_id, source, account_id, str(data.request_id)])

    async def commit(session):
        receipt = await database.account_projection_repairs.find_one({"_id": receipt_id, "tenant_id": user.tenant_id}, session=session)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise HTTPException(409, "İstek kimliği farklı içerikle kullanıldı")
            return {**receipt["result"], "replayed": True}
        account, preview = await load_projection_preview(database, user.tenant_id, source, account_id,
            fallback_currency=fallback_currency, session=session)
        if preview["source_fingerprint"] != data.source_fingerprint:
            raise HTTPException(409, "Cari kaynaklar değişti; önizlemeyi tekrar kontrol edin")
        if not preview["repairable"]:
            raise HTTPException(409, {"message": "Kaynaklar otomatik bakiye düzeltmesine uygun değil", "reasons": preview["blocked_reasons"]})
        if not preview["needs_repair"]:
            raise HTTPException(409, "Cari bakiyesi zaten kaynaklarla eşleşiyor")
        now = datetime.now(UTC).isoformat()
        values = {"current_balance": preview["source_balance"], "projection_repaired_at": now}
        if source == "cari_accounts" or "balance" in account:
            values["balance"] = preview["source_balance"]
        # Match exactly what was reviewed; no stale preview may overwrite a
        # changed account. Concurrent normal writers touching it conflict.
        query = {"_id": account["_id"], "tenant_id": user.tenant_id}
        query.update({key: account[key] if key in account else {"$exists": False} for key in ("balance", "current_balance")})
        updated = await database[source].update_one(query, {"$set": values}, session=session)
        if updated.modified_count != 1:
            raise HTTPException(409, "Cari bakiyesi değişti; önizlemeyi yenileyin")
        result = {"success": True, "replayed": False, **preview, "new_balance": preview["source_balance"], "request_id": str(data.request_id)}
        entry = build_audit_entry(actor_id=user.id, tenant_id=user.tenant_id, property_id=user.tenant_id,
            entity_type="cari_account", entity_id=account_id, action="account_projection_rebuilt",
            metadata={**preview, "actor_name": user.name, "reason": data.reason.strip(),
                      "source_review_reference": data.source_review_reference.strip(), "request_id": str(data.request_id)})
        # Metadata alone is not part of the chain's canonical content. Seal
        # the financial before/after proof AND the operator's explanation.
        entry["before_snapshot"] = {"cached_balances": preview["cached_balances"], "source_fingerprint": preview["source_fingerprint"]}
        entry["after_snapshot"] = {"new_balance": preview["source_balance"], "currency": preview["currency"],
            "source": source, "source_transaction_count": preview["source_transaction_count"],
            "reason": data.reason.strip(), "source_review_reference": data.source_review_reference.strip(), "request_id": str(data.request_id)}
        await append_audit_log(database, entry, session=session, require_chain=True)
        await database.account_projection_repairs.insert_one({"_id": receipt_id, "tenant_id": user.tenant_id,
            "payload_hash": payload_hash, "result": result, "created_at": now}, session=session)
        return result

    result = await with_resource_locks(client=client, db=database, tenant_id=user.tenant_id,
        locks_collection="reservation_financial_locks", resources=[("cari_account", account_id)], callback=commit)
    try:
        invalidate_receivable_report_caches(user.tenant_id)
    except Exception:
        # A cache problem must never turn an already committed repair into
        # an ambiguous HTTP500. The UI refresh also requests nocache=1.
        logger.warning("Receivable cache refresh failed after committed account projection repair", exc_info=True)
    return result
