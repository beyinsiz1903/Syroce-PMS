"""Explicit, reviewed live cutover. Archive import itself has no live effects.

No historical payments, invoices, KBS jobs, channel jobs or messages are replayed.
Money first enters an ordinary draft voucher (separate accounting approval).
Each booking is created by the existing room-night locking kernel. A multi-row
cutover is resumable, NOT advertised as an all-or-nothing database transaction.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pymongo import ReturnDocument

from .formats import MigrationError
from .schema import digest, private_fingerprint
from .service import audit, now, seal, unseal

LIMIT = 2000
ACTIVE = {"confirmed", "checked_in", "pending"}


def live_id(key, kind):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"migration-live:{kind}:{key}"))


async def get_job(db, batch):
    job = await db.migration_cutovers.find_one({"_id": batch["id"], "tenant_id": batch["tenant_id"]})
    if not job:
        return None
    result = {k: v for k, v in job.items() if k not in {"_id", "config_payload", "plan_payload", "lease_until"}}
    result["config"] = unseal(job["config_payload"], batch["tenant_id"])
    return result


async def configure(db, batch, actor, config):
    if batch["state"] != "complete":
        raise MigrationError("Önce arşiv aktarımını tamamlayın.")
    prior = await get_job(db, batch)
    if prior and prior["state"] not in {"draft", "reviewed"}:
        raise MigrationError("Başlatılmış canlı devir değiştirilemez; mevcut işin durumunu inceleyin.")
    await db.migration_cutovers.update_one(
        {"_id": batch["id"], "tenant_id": batch["tenant_id"], "state": {"$in": ["draft", "reviewed"]}} if prior else {"_id": batch["id"], "tenant_id": batch["tenant_id"]},
        {
            "$set": {"state": "draft", "config_payload": seal(config, batch["tenant_id"]), "report": None, "review_token": None, "updated_at": now(), "updated_by": actor},
            "$setOnInsert": {"cursor": 0, "created_at": now()},
            "$inc": {"revision": 1},
        },
        upsert=not bool(prior),
    )
    await audit(db, batch, actor, "migration_cutover_configured")
    return await get_job(db, batch)


async def _business_date(db, tenant):
    settings = await db.tenant_settings.find_one({"tenant_id": tenant}, {"business_date": 1})
    return str((settings or {}).get("business_date") or "")[:10]


async def _target(db, tenant, config, entity, source_id):
    target = config.get("target_links", {}).get(entity, {}).get(source_id)
    if not target:
        raise MigrationError(f"Canlı hedef eşleştirmesi eksik: {entity}")
    value = await db[entity].find_one({"tenant_id": tenant, "id": target, "archived": {"$ne": True}, "status": {"$nin": ["deleted", "inactive"]}})
    if not value:
        raise MigrationError(f"Hedef kayıt bu tesiste kullanılamıyor: {entity}")
    return value


async def build_plan(db, batch, config):
    tenant, cutoff = batch["tenant_id"], config["cutover_date"]
    try:
        date.fromisoformat(cutoff)
        frozen = datetime.fromisoformat(config["source_frozen_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise MigrationError("Kesim tarihi ve saat dilimli kaynak kesim anı geçersiz.") from None
    if await _business_date(db, tenant) != cutoff:
        raise MigrationError("Kesim tarihi otelin açık iş günüyle aynı olmalı; iş gününü ayrıca doğrulayın.")
    hotel = await db.hotel_settings.find_one({"tenant_id": tenant}, {"timezone": 1}) or {}
    try:
        zone = ZoneInfo(hotel.get("timezone") or "Europe/Istanbul")
    except (ValueError, ZoneInfoNotFoundError):
        raise MigrationError("Tesis saat dilimini doğrulayın.") from None
    if frozen.tzinfo is None or frozen > now() + timedelta(minutes=1) or frozen.astimezone(zone).date().isoformat() != cutoff:
        raise MigrationError("Kaynak kesim anı saat dilimli ve kesim gününde olmalı; gelecek an kullanılamaz.")
    documents = await db.migration_archive.find({"tenant_id": tenant, "namespace": batch["namespace"]}).sort("id", 1).limit(50001).to_list(50001)
    if len(documents) > 50000:
        raise MigrationError("Canlı devir kapsamı 50.000 arşiv kaydını aşıyor; kapsamı bölün.")
    origins = {d["owner_batch_id"] for d in documents}
    batches = await db.migration_batches.find({"tenant_id": tenant, "id": {"$in": list(origins)}}).to_list(len(origins))
    if len(batches) != len(origins) or any(b["state"] != "complete" or not b.get("report", {}).get("all_source_reconciled") for b in batches):
        raise MigrationError("Kaynağın tüm arşiv parçaları tamamlanmış ve bağımsız sayım/tutarlarıyla mutabık olmalı.")
    rows = {d["id"]: {**{k: d.get(k) for k in ("id", "entity", "content_hash", "refs", "guest_id")}, "data": unseal(d["payload"], tenant)} for d in documents}
    selected = [r for r in rows.values() if r["entity"] == "reservations" and r["data"]["status"] in ACTIVE]
    if len(selected) > LIMIT:
        raise MigrationError("Tek canlı devir en fazla 2.000 aktif rezervasyon içerebilir.")
    errors, bookings, monetary, totals = [], [], [], defaultdict(Decimal)
    occupied = set()
    linked = await db.migration_live_links.find({"tenant_id": tenant, "namespace": batch["namespace"]}).to_list(100001)
    live_links = {d["record_id"]: d for d in linked}
    rates_by_booking, folios_by_booking = defaultdict(list), defaultdict(list)
    for row in rows.values():
        if row["entity"] in {"daily_rates", "folios"}:
            (rates_by_booking if row["entity"] == "daily_rates" else folios_by_booking)[row["refs"].get("reservation_source_id")].append(row)
    for source in selected:
        data, key = source["data"], source["id"]
        try:
            if source["refs"].get("company_source_id") or source["refs"].get("agency_source_id"):
                # Linking a commercial party is not enough to establish the
                # payor, commission, transferred debt and prior settlements.
                # Do not let ordinary agency reports invent those from the
                # target's current default commission after migration.
                raise MigrationError("Şirket/acente aktif rezervasyonu için ödeyen, komisyon ve alt defter devir uyarlaması gerekli; yalnız ID eşleştirmesiyle canlıya alınmaz. Arşiv kaydı korunur.")
            if key in live_links:
                raise MigrationError("Kaynak rezervasyon başka canlı devirde kullanıldı; tekrar yayınlanmaz.")
            if data["status"] == "pending":
                raise MigrationError("Bekleyen rezervasyonu kaynakta kesinleştirin veya iptal edin; otomatik kesinleştirme yapılmaz.")
            if data["check_out"] <= cutoff:
                raise MigrationError("Kaynakta süresi geçmiş aktif konaklama var; çıkış/durum kaydını düzeltin.")
            if data["status"] == "confirmed" and data["check_in"] < cutoff or data["status"] == "checked_in" and data["check_in"] > cutoff:
                raise MigrationError("Kesim gününe göre rezervasyon durumu/tarihleri uyuşmuyor.")
            guest = rows[source["refs"]["guest_source_id"]]
            guest_id = guest.get("guest_id")
            if not guest_id or not await db.guests.find_one({"tenant_id": tenant, "id": guest_id, "archived": {"$ne": True}}):
                raise MigrationError("Misafiri önce yayınlayın veya mevcut misafirle açıkça bağlayın.")
            room_key = source["refs"].get("room_source_id")
            if room_key not in rows:
                raise MigrationError("Aktif rezervasyon için kaynak oda zorunlu.")
            room = await _target(db, tenant, config, "rooms", rows[room_key]["data"]["source_id"])
            if room.get("is_active") is False or room.get("status") in {"out_of_order", "out_of_service", "maintenance", "blocked"}:
                raise MigrationError("Hedef oda satışa kapalı.")
            adults, children = int(data.get("adults") or 1), int(data.get("children") or 0)
            if adults + children > int(room.get("capacity") or 100) or adults > 50 or children > 50:
                raise MigrationError("Misafir sayısı hedef oda kapasitesini aşıyor.")
            booking_id = live_id(key, "booking")
            from core.atomic_booking import _find_overlapping_active_booking, _night_dates

            nights = _night_dates(data["check_in"], data["check_out"])
            if len(nights) > 366:
                raise MigrationError("Aktif konaklama en fazla 366 gece olabilir.")
            if await _find_overlapping_active_booking(tenant_id=tenant, room_id=room["id"], check_in=data["check_in"], check_out=data["check_out"], exclude_booking_id=booking_id):
                raise MigrationError("Hedef odada canlı rezervasyon çakışması var.")
            if await db.room_night_locks.find_one({"tenant_id": tenant, "room_id": room["id"], "night_date": {"$in": nights}}):
                raise MigrationError("Hedef odada kilit/blokaj var.")
            if any((room["id"], night) in occupied for night in nights):
                raise MigrationError("Kaynak rezervasyonlar aynı hedef oda/gecede çakışıyor.")
            rates = rates_by_booking[key]
            rate_days = [r["data"]["rate_date"] for r in rates]
            if len(set(rate_days)) != len(rate_days) or set(rate_days) != set(nights) or any(r["data"]["currency"] != data["currency"] or Decimal(r["data"]["amount"]) < 0 for r in rates):
                raise MigrationError("Her gece için tek, aynı dövizde brüt günlük fiyat gerekli.")
            if sum((Decimal(r["data"]["amount"]) for r in rates), Decimal(0)) != Decimal(data["total_amount"]):
                raise MigrationError("Günlük brüt fiyatların toplamı rezervasyon bedeliyle uyuşmuyor.")
            if any(Decimal(r["data"]["amount"]).quantize(Decimal("0.01")) != Decimal(r["data"]["amount"]) for r in rates):
                raise MigrationError("Canlı gecelik ücret iki ondalık destekliyor; bu döviz için özel uyarlama gerekli.")
            folios = folios_by_booking[key]
            if not folios or len(folios) > 8:
                raise MigrationError("Aktif rezervasyonun 1–8 açık folyo kesim bakiyesi gerekli (sıfır dahil).")
            for folio in folios:
                f = folio["data"]
                if f["currency"] != data["currency"] or not {"charged_amount", "paid_amount"} <= f.keys():
                    raise MigrationError("Folyo kesim borç/ödeme toplamları ve aynı döviz gerekli.")
                if Decimal(f["charged_amount"]) < 0 or Decimal(f["paid_amount"]) < 0 or Decimal(f["charged_amount"]) - Decimal(f["paid_amount"]) != Decimal(f["balance"]):
                    raise MigrationError("Folyo kesim borç − ödeme toplamı bakiye ile uyuşmuyor.")
                monetary.append((folio, "receivable" if Decimal(f["balance"]) >= 0 else "deposit", abs(Decimal(f["balance"]))))
            accrued_room = sum((Decimal(r["data"]["amount"]) for r in rates if r["data"]["rate_date"] < cutoff), Decimal(0))
            source_charged = sum((Decimal(f["data"]["charged_amount"]) for f in folios), Decimal(0))
            if source_charged < accrued_room:
                raise MigrationError("Kesim borcu geçmiş brüt oda gecelerinden düşük; indirim/komp/erken çıkış için özel mutabakat gerekli.")
            parties = {}
            for entity, field in (("companies", "company_source_id"), ("agencies", "agency_source_id")):
                if source["refs"].get(field):
                    party = await _target(db, tenant, config, entity, rows[source["refs"][field]]["data"]["source_id"])
                    parties["company_id" if entity == "companies" else "agency_id"] = party["id"]
            occupied.update((room["id"], night) for night in nights)
            bookings.append(
                {
                    "record_id": key,
                    "content_hash": source["content_hash"],
                    "data": data,
                    "guest_id": guest_id,
                    "guest_name": guest["data"]["name"],
                    "room": {k: room.get(k) for k in ("id", "room_number", "room_type")},
                    "parties": parties,
                    "folios": folios,
                    "rates": rates,
                    "booking_id": booking_id,
                    "source_accommodation": str(accrued_room),
                    "source_charged": str(source_charged),
                    "source_paid": str(sum((Decimal(f["data"]["paid_amount"]) for f in folios), Decimal(0))),
                }
            )
        except MigrationError as exc:
            errors.append({"record_id": key, "message": str(exc)})
    balances = [r for r in rows.values() if r["entity"] == "balances"]
    if balances and monetary and not config.get("balances_exclude_folios"):
        errors.append({"message": "Bağımsız cari bakiyelerin aktif folyoları içermediği kaynakta doğrulanmalı; çift devir engellendi."})
    for r in balances:
        if r["id"] in live_links or r["data"]["balance_date"] != cutoff:
            errors.append({"record_id": r["id"], "message": "Cari bakiye daha önce devredildi veya kesim günüyle uyuşmuyor."})
        monetary.append((r, r["data"]["kind"], Decimal(r["data"]["amount"])))
    if len(monetary) > 250:
        errors.append({"message": "Bir açılış fişi en fazla 250 kaynak bakiye içerebilir; kaynak kapsamını bölün."})
    lines = []
    for row, kind, amount in monetary:
        try:
            if not amount:
                continue
            currency = row["data"]["currency"]
            if amount.quantize(Decimal("0.01")) != amount:
                raise MigrationError("GL iki ondalık destekliyor; daha hassas döviz için özel muhasebe uyarlaması gerekli.")
            rate = Decimal(str(config.get("exchange_rates", {}).get(currency, "1" if currency == "TRY" else "0")))
            if not rate.is_finite() or rate <= 0 or rate > 1000000 or currency == "TRY" and rate != 1:
                raise MigrationError("Kesim anı döviz kuru açıkça girilmeli (TRY = 1).")
            base = (abs(amount) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if base <= 0:
                raise MigrationError("TL karşılığı sıfıra yuvarlanan bakiye otomatik devredilemez.")
            account = config.get("accounts", {}).get(kind)
            offset = config.get("accounts", {}).get("clearing")
            if not account or not offset or account == offset:
                raise MigrationError("Alacak/borç/depozito ve farklı açılış karşı hesabı eşleştirilmeli.")
            debit = (kind == "receivable") == (amount > 0)
            extra = {"currency": currency, "foreign_amount": str(abs(amount)), "exchange_rate": str(rate)} if currency != "TRY" else {}
            lines.extend(
                [
                    {"account_code": account, "debit": str(base if debit else 0), "credit": str(0 if debit else base), "memo": "PMS devir " + row["id"][:16], **extra},
                    {"account_code": offset, "debit": str(0 if debit else base), "credit": str(base if debit else 0), "memo": "PMS açılış karşılığı", **extra},
                ]
            )
            totals[f"{kind}:{currency}"] += amount
        except (ValueError, ArithmeticError) as exc:
            errors.append({"record_id": row["id"], "message": str(exc) if isinstance(exc, MigrationError) else "Devir tutarı/kur geçersiz."})
    if lines:
        profile = await db.gl_setup_profiles.find_one({"tenant_id": tenant})
        if not profile or profile.get("currency", "TRY") != "TRY":
            errors.append({"message": "Önce TRY bazlı yasal muhasebe kurulumunu tamamlayın; farklı baz döviz için özel uyarlama gerekli."})
        codes = {line["account_code"] for line in lines}
        accounts = await db.gl_accounts.find({"tenant_id": tenant, "code": {"$in": list(codes)}, "active": True}).to_list(len(codes))
        if {a["code"] for a in accounts} != codes or any(a.get("type", a.get("account_type")) not in {"asset", "liability", "equity"} for a in accounts):
            errors.append({"message": "Açılış hesaplarının tümü aktif bilanço hesabı olmalı; gelir/gider hesabına devir yapılmaz."})
        from shared_kernel.gl_periods import GLPeriodError, assert_gl_period_open
        from shared_kernel.gl_posting import GLPostingError, normalize_journal_lines

        try:
            normalize_journal_lines(lines)
            await assert_gl_period_open(db, tenant, cutoff)
        except (GLPeriodError, GLPostingError) as exc:
            errors.append({"message": str(exc)})
    if not selected and not balances:
        errors.append({"message": "Kesim anında devredilecek aktif rezervasyon veya cari bakiye yok."})
    report = {
        "bookings": len(bookings),
        "folios": sum(len(b["folios"]) for b in bookings),
        "balances": len(balances),
        "totals": {k: str(v) for k, v in totals.items()},
        "errors": errors[:200],
        "error_count": len(errors),
        "voucher_required": bool(lines),
        "accounting_action": "draft_then_separate_approval_and_posting",
        "partial_progress_possible": True,
    }
    plan = {"bookings": bookings, "lines": lines, "monetary_keys": [r["id"] for r, _, _ in monetary], "source_hashes": {d["id"]: d["content_hash"] for d in documents}, "cutover_date": cutoff}
    return plan, report


async def review(db, batch, actor):
    job = await get_job(db, batch)
    if not job or job["state"] not in {"draft", "reviewed"}:
        raise MigrationError("Önce canlı devir ayarlarını kaydedin.")
    plan, report = await build_plan(db, batch, job["config"])
    token = private_fingerprint([job["revision"], job["config"], plan, report])
    # Keep single-document frozen plans below Mongo's limit. No unbounded BSON.
    import json

    payload = seal(plan, batch["tenant_id"])
    if len(json.dumps(payload)) > 8 * 1024 * 1024:
        raise MigrationError("Canlı devir planı çok büyük; kaynak kapsamını bölün.")
    result = await db.migration_cutovers.update_one(
        {"_id": batch["id"], "tenant_id": batch["tenant_id"], "revision": job["revision"], "state": job["state"]},
        {"$set": {"state": "reviewed", "plan_payload": payload, "report": report, "review_token": token}},
    )
    if not result.matched_count:
        raise MigrationError("Canlı devir ayarları değişti; yeniden inceleyin.")
    await audit(db, batch, actor, "migration_cutover_reviewed")
    return await get_job(db, batch)


async def activation_plan(db, batch, token):
    job = await db.migration_cutovers.find_one({"_id": batch["id"], "tenant_id": batch["tenant_id"]})
    if not job or token != job.get("review_token") or job.get("report", {}).get("error_count") or job["state"] not in {"reviewed", "awaiting_finance", "activating", "failed", "complete"}:
        raise MigrationError("Hatasız güncel canlı devir incelemesini onaylayın.")
    plan = unseal(job["plan_payload"], batch["tenant_id"])
    if job["state"] == "complete":
        return job, plan
    if await _business_date(db, batch["tenant_id"]) != plan["cutover_date"]:
        raise MigrationError("Otelin iş günü değişti; devir durduruldu. Destek mutabakatı gerekli.")
    async for row in db.migration_archive.find({"tenant_id": batch["tenant_id"], "namespace": batch["namespace"]}, {"id": 1, "content_hash": 1}):
        if plan["source_hashes"].get(row["id"]) != row["content_hash"]:
            raise MigrationError("Kesimden sonra kaynak arşiv değişti; tekrar mutabakat gerekli.")
    if await db.migration_archive.count_documents({"tenant_id": batch["tenant_id"], "namespace": batch["namespace"]}) != len(plan["source_hashes"]):
        raise MigrationError("Kaynak arşivden kayıt eksilmiş; devir durduruldu.")
    return job, plan


async def claim_source(db, batch):
    """Permanent cutover ownership, not an expiring worker lease.

    A posted opening voucher cannot be silently reused by a second batch.
    Recovery of a different cutover requires explicit finance reconciliation.
    """
    key = digest([batch["tenant_id"], batch["namespace"]])
    await db.migration_cutover_sources.update_one(
        {"_id": key, "tenant_id": batch["tenant_id"]}, {"$setOnInsert": {"tenant_id": batch["tenant_id"], "namespace": batch["namespace"], "batch_id": batch["id"]}}, upsert=True
    )
    claim = await db.migration_cutover_sources.find_one({"_id": key, "tenant_id": batch["tenant_id"]})
    if claim["batch_id"] != batch["id"]:
        raise MigrationError("Bu kaynak başka canlı devir işine bağlı; ikinci açılış/aktivasyon engellendi.")


async def record_voucher(db, batch, token, voucher):
    await db.migration_cutovers.update_one(
        {"_id": batch["id"], "tenant_id": batch["tenant_id"], "review_token": token, "state": {"$in": ["reviewed", "awaiting_finance"]}},
        {"$set": {"voucher_id": voucher["id"], "state": "awaiting_finance"}},
    )
    return await get_job(db, batch)


async def activate(db, batch, actor, token):
    job, plan = await activation_plan(db, batch, token)
    if job["state"] == "complete":
        return await get_job(db, batch)
    await claim_source(db, batch)
    if plan["lines"]:
        from shared_kernel.gl_posting import normalize_journal_lines

        voucher = await db.gl_vouchers.find_one({"tenant_id": batch["tenant_id"], "id": job.get("voucher_id"), "status": "posted"})
        expected_lines = normalize_journal_lines(plan["lines"])[0]
        # The accounting post enriches account names; compare the immutable
        # commercial fields, not presentation-only enrichment.
        keys = ("account_code", "debit_minor", "credit_minor", "currency", "foreign_amount_minor", "exchange_rate")
        actual_lines = (voucher or {}).get("lines", [])
        if not voucher or [{k: l.get(k) for k in keys} for l in actual_lines] != [{k: l.get(k) for k in keys} for l in expected_lines] or voucher.get("date") != plan["cutover_date"]:
            raise MigrationError("Açılış fişi aynı tarih/satırlarla muhasebede ayrıca onaylanıp kaydedilmeli.")
    lock = await db.migration_cutovers.find_one_and_update(
        {"_id": batch["id"], "tenant_id": batch["tenant_id"], "review_token": token, "state": job["state"], "$or": [{"lease_until": None}, {"lease_until": {"$lt": now()}}]},
        {"$set": {"state": "activating", "lease_until": now() + timedelta(minutes=5)}},
        return_document=ReturnDocument.AFTER,
    )
    if not lock:
        raise MigrationError("Canlı devir başka işlemde sürüyor.")
    try:
        from core.atomic_booking import create_booking_atomic, ensure_booking_indexes

        await ensure_booking_indexes()
        index_info = await db.room_night_locks.index_information()
        index = index_info.get("ux_room_night", {})
        if not index.get("unique") or list(index.get("key", [])) != [("tenant_id", 1), ("room_id", 1), ("night_date", 1)]:
            raise MigrationError("Benzersiz oda/gece kilidi doğrulanamadı; canlı devir güvenli biçimde durduruldu.")
        for booking in plan["bookings"][lock["cursor"] : lock["cursor"] + 10]:
            tenant, booking_id = batch["tenant_id"], booking["booking_id"]
            if not await db.guests.find_one({"tenant_id": tenant, "id": booking["guest_id"], "archived": {"$ne": True}, "status": {"$ne": "deleted"}}):
                raise MigrationError("İncelemeden sonra hedef misafir kullanılamaz oldu.")
            room = await db.rooms.find_one(
                {"tenant_id": tenant, "id": booking["room"]["id"], "is_active": {"$ne": False}, "status": {"$nin": ["deleted", "out_of_order", "out_of_service", "maintenance", "blocked"]}}
            )
            if not room:
                raise MigrationError("İncelemeden sonra hedef oda kullanılamaz oldu.")
            if booking["data"]["status"] == "checked_in" and room.get("current_booking_id") not in {None, "", booking_id}:
                raise MigrationError("Hedef odada farklı konaklayan misafir var; devir durduruldu.")
            provenance = {"migration_batch_id": batch["id"], "migration_record_id": booking["record_id"], "migration_cutover_date": plan["cutover_date"]}
            # A deterministic _id is the crash/retry barrier even if old live
            # collections lack a unique tenant/id index.
            for number, folio in enumerate(booking["folios"], 1):
                f = folio["data"]
                folio_id = live_id(folio["id"], "folio")
                await db.folios.update_one(
                    {"_id": folio_id, "tenant_id": tenant},
                    {
                        "$setOnInsert": {
                            "id": folio_id,
                            "tenant_id": tenant,
                            "booking_id": booking_id,
                            "guest_id": booking["guest_id"],
                            "folio_type": "guest",
                            "status": "open",
                            "folio_number": "MIG-" + folio_id,
                            "window_number": number,
                            "currency": f["currency"],
                            "balance": float(f["balance"]),
                            "opening_balance": float(f["balance"]),
                            "opening_balance_date": plan["cutover_date"],
                            "opening_voucher_id": job.get("voucher_id"),
                            "source_paid_amount": float(f["paid_amount"]),
                            "created_at": now().isoformat(),
                            **provenance,
                        }
                    },
                    upsert=True,
                )
            for rate in booking["rates"]:
                rate_id = live_id(rate["id"], "rate")
                await db.daily_rates.update_one(
                    {"_id": rate_id, "tenant_id": tenant},
                    {
                        "$setOnInsert": {
                            "id": rate_id,
                            "tenant_id": tenant,
                            "booking_id": booking_id,
                            "date": rate["data"]["rate_date"],
                            "rate": float(rate["data"]["amount"]),
                            "currency": rate["data"]["currency"],
                            **provenance,
                        }
                    },
                    upsert=True,
                )
            existing = await db.bookings.find_one({"tenant_id": tenant, "id": booking_id})
            if existing and (existing.get("migration_record_id") != booking["record_id"] or existing.get("migration_batch_id") != batch["id"]):
                raise MigrationError("Canlı kayıt kimliği başka kayda ait; devir durduruldu.")
            if not existing:
                from models.schemas.bookings import Booking

                data = booking["data"]
                document = Booking(
                    id=booking_id,
                    tenant_id=tenant,
                    guest_id=booking["guest_id"],
                    guest_name=booking["guest_name"],
                    room_id=booking["room"]["id"],
                    room_number=booking["room"].get("room_number"),
                    check_in=datetime.fromisoformat(data["check_in"]).replace(tzinfo=UTC),
                    check_out=datetime.fromisoformat(data["check_out"]).replace(tzinfo=UTC),
                    status=data["status"],
                    total_amount=float(data["total_amount"]),
                    currency=data["currency"],
                    adults=int(data.get("adults") or 1),
                    children=int(data.get("children") or 0),
                    paid_amount=float(booking["source_paid"]),
                    origin="import",
                    **booking["parties"],
                ).model_dump(mode="json")
                document.update(
                    {
                        "_id": booking_id,
                        "folio_id": live_id(booking["folios"][0]["id"], "folio"),
                        "pricing_tax_inclusive": True,
                        "agency_id": booking["parties"].get("agency_id"),
                        "kbs_migration_review_required": data["status"] == "checked_in",
                        **provenance,
                    }
                )
                document["migration_financial_snapshot"] = {"charged": booking["source_charged"], "paid": booking["source_paid"], "accommodation": booking["source_accommodation"]}
                await create_booking_atomic(tenant_id=tenant, booking_doc=document, suppress_messaging=True)
            if booking["data"]["status"] == "checked_in" and (not existing or existing.get("status") == "checked_in"):
                # Keep the legacy room projection consistent, without changing
                # cleanliness or undoing an operator checkout on resume.
                await db.rooms.update_one(
                    {"tenant_id": tenant, "id": room["id"], "current_booking_id": {"$in": [None, "", booking_id]}}, {"$set": {"status": "occupied", "current_booking_id": booking_id}}
                )
            # Subsequent operator edits are NEVER overwritten by resume.
            for key in [booking["record_id"], *[f["id"] for f in booking["folios"]], *[r["id"] for r in booking["rates"]]]:
                await db.migration_live_links.update_one(
                    {"_id": digest([tenant, key]), "tenant_id": tenant},
                    {"$setOnInsert": {"tenant_id": tenant, "namespace": batch["namespace"], "record_id": key, "batch_id": batch["id"], "booking_id": booking_id}},
                    upsert=True,
                )
            lock["cursor"] += 1
            await db.migration_cutovers.update_one({"_id": batch["id"], "tenant_id": tenant}, {"$set": {"cursor": lock["cursor"]}})
        done = lock["cursor"] == len(plan["bookings"])
        if done:
            for key in plan["monetary_keys"]:
                await db.migration_live_links.update_one(
                    {"_id": digest([batch["tenant_id"], key]), "tenant_id": batch["tenant_id"]},
                    {"$setOnInsert": {"tenant_id": batch["tenant_id"], "namespace": batch["namespace"], "record_id": key, "batch_id": batch["id"], "voucher_id": job.get("voucher_id")}},
                    upsert=True,
                )
        await audit(db, {**batch, "cursor": lock["cursor"]}, actor, "migration_cutover_completed" if done else "migration_cutover_chunk")
        await db.migration_cutovers.update_one(
            {"_id": batch["id"], "tenant_id": batch["tenant_id"]}, {"$set": {"state": "complete" if done else "activating", "lease_until": None, "last_error": None}}
        )
    except BaseException:
        await db.migration_cutovers.update_one(
            {"_id": batch["id"], "tenant_id": batch["tenant_id"]},
            {"$set": {"state": "failed", "lease_until": None, "last_error": "Kısmi canlı devir durdu; aynı planla devam edin. Otomatik silme yapılmaz."}},
        )
        raise
    return await get_job(db, batch)
