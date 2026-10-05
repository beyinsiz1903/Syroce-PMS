import asyncio
import logging
import secrets
import string
import uuid
from decimal import Decimal

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.tenant_db import get_db_for_tenant
from domains.guest.qr_catalogue_service import _utc_now, fetch_catalogue_data, is_service_available, resolve_catalogue_mode, validate_input_value
from domains.guest.qr_constants import map_legacy_routing
from domains.guest.qr_request_description import compute_payload_fingerprint, generate_deterministic_description
from models.schemas.qr_catalogue_submission import StructuredRequestSubmit

logger = logging.getLogger(__name__)

# Existing unit tests replace this seam with an isolated fake database.
# Production requests always use the tenant-scoped database proxy.
raw_db = None


def _db_for_tenant(tenant_id: str):
    return raw_db if raw_db is not None else get_db_for_tenant(tenant_id)


def generate_public_reference(prefix="REQ"):
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(8))
    return f"{prefix}-{suffix}"


def _build_ledger_upsert_update(ledger_doc: dict, updated_at):
    """Keep MongoDB upsert operators path-disjoint.

    MongoDB rejects an update when the same field appears in both
    ``$setOnInsert`` and ``$set``. ``updated_at`` must refresh for both a new
    ledger and a concurrent retry, so it belongs exclusively to ``$set``.
    """
    insert_doc = {key: value for key, value in ledger_doc.items() if key != "updated_at"}
    return {"$setOnInsert": insert_doc, "$set": {"updated_at": updated_at}}


def _room_charge_for_item(catalogue_item: dict, validated_value: dict) -> dict | None:
    """Build an immutable, server-calculated room-charge snapshot.

    Browser values only select a catalogue item and (when permitted) a
    quantity.  Currency and price are never accepted from the guest.
    """
    if not catalogue_item.get("room_charge_enabled"):
        return None
    quantity = int(validated_value.get("quantity", 1))
    unit_minor = int(catalogue_item.get("unit_price_minor") or 0)
    currency = str(catalogue_item.get("currency") or "").upper()
    if quantity < 1 or unit_minor < 1 or not currency:
        raise HTTPException(status_code=503, detail="Oda servisi fiyatı şu anda kullanılamıyor")
    return {
        "unit_price_minor": unit_minor,
        "quantity": quantity,
        "total_minor": unit_minor * quantity,
        "currency": currency,
        "folio_category": catalogue_item.get("folio_category") or "room_service",
    }


async def _post_room_service_charges(tenant_id: str, tenant_db, booking_id: str, submission_group_id: str, prepared_items: list[dict]):
    """Post confirmed QR menu items once to the active guest folio.

    The folio service recognizes ``external_reference`` so an interrupted
    request/retry converges to the original financial line rather than
    duplicating it.
    """
    chargeable = [item for item in prepared_items if item.get("room_charge")]
    if not chargeable:
        return []

    folio = await tenant_db["folios"].find_one(
        {"tenant_id": tenant_id, "booking_id": booking_id, "status": "open"},
        {"_id": 0},
    )
    if not folio:
        raise HTTPException(status_code=409, detail="Açık oda folyosu bulunamadı; sipariş kaydedilmedi")

    from modules.pms_core.folio_hardening_service import FolioHardeningService

    posted = []
    for item in chargeable:
        room_charge = item["room_charge"]
        reference = f"qr-room-service:{submission_group_id}:{item['service_code']}"
        amount = Decimal(room_charge["unit_price_minor"]) / Decimal(100)
        result = await FolioHardeningService().post_charge(
            tenant_id=tenant_id,
            folio_id=folio["id"],
            booking_id=booking_id,
            charge_data={
                "category": room_charge["folio_category"],
                "description": f"[QR Oda Servisi] {item['title']}",
                "amount": float(amount),
                "quantity": room_charge["quantity"],
                "tax_rate": 0,
                "department": "room_service",
                "currency": room_charge["currency"],
                "external_reference": reference,
            },
            posted_by="guest-qr-room-service",
        )
        if not result.get("success"):
            raise HTTPException(status_code=409, detail="Oda hesabına yazılamadı; sipariş kaydedilmedi")
        charge_id = (result.get("charge") or {}).get("id")
        if not charge_id:
            raise HTTPException(status_code=503, detail="Oda hesabı kaydı doğrulanamadı")
        posted.append({"service_code": item["service_code"], "folio_charge_id": charge_id, **room_charge})

    await tenant_db["guest_service_submissions"].update_one(
        {"tenant_id": tenant_id, "property_id": prepared_items[0]["property_id"], "booking_id": booking_id, "submission_group_id": submission_group_id},
        {"$set": {"room_charge_status": "posted", "room_charge_lines": posted, "updated_at": _utc_now()}},
    )
    return posted


async def handle_structured_submission(
    tenant_id: str, property_id: str, room_id: str, booking_id: str, session_id: str, room_number: str, payload: StructuredRequestSubmit, guest_name: str | None, guest_phone: str | None
):
    tenant_db = _db_for_tenant(tenant_id)
    seen_codes = set()
    for it in payload.items:
        if it.service_code in seen_codes:
            raise HTTPException(status_code=422, detail="Geçersiz girdi")
        seen_codes.add(it.service_code)

    fingerprint = compute_payload_fingerprint(payload.language, payload.items, payload.confirm_room_charge)

    # 1. Lookup existing ledger
    ledger = await tenant_db["guest_service_submissions"].find_one({"tenant_id": tenant_id, "property_id": property_id, "booking_id": booking_id, "idempotency_key": payload.idempotency_key})

    if ledger:
        if ledger.get("payload_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Talep işleme alınamadı")
        prepared_items = ledger["prepared_items"]
        submission_group_id = ledger["submission_group_id"]
        submission_reference = ledger.get("submission_reference")
        if not submission_reference:
            raise HTTPException(status_code=503, detail="Sistem hatası")
    else:
        # 2. Resolve & Validate against catalogue
        mode = await resolve_catalogue_mode(tenant_id, property_id)
        if mode == "disabled":
            raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

        depts_data, services_data = await fetch_catalogue_data(tenant_id, property_id, mode)
        services_map = {s["service_code"]: s for s in services_data}

        prop = await tenant_db["properties"].find_one({"id": property_id, "tenant_id": tenant_id}) or {}
        prop_tz = prop.get("timezone", "UTC")
        prop_lang = prop.get("default_language", "en")

        now_utc = _utc_now()
        submission_group_id = str(uuid.uuid4())
        submission_reference = generate_public_reference("GSR")

        prepared_items = []
        expected_codes = []

        for it in payload.items:
            cat_item = services_map.get(it.service_code)
            if not cat_item or not cat_item.get("enabled", True):
                raise HTTPException(status_code=400, detail="Talep işleme alınamadı")

            if not is_service_available(cat_item.get("service_hours"), prop_tz):
                raise HTTPException(status_code=400, detail="Talep işleme alınamadı")

            val_obj = it.value.model_dump(exclude_none=True) if it.value else {}
            input_type = cat_item.get("input_type")
            allowed_keys = []
            if input_type == "one_tap":
                allowed_keys = []
            elif input_type == "quantity":
                allowed_keys = ["quantity"]
            elif input_type in ("single_choice", "multi_choice"):
                allowed_keys = ["selected_options"]
            elif input_type == "date":
                allowed_keys = ["date_value"]
            elif input_type == "time":
                allowed_keys = ["time_value"]
            elif input_type == "datetime":
                allowed_keys = ["datetime_value"]

            for k in val_obj.keys():
                if k not in allowed_keys:
                    raise HTTPException(status_code=400, detail="Geçersiz veri alanı bulundu")

            try:
                validated_val = validate_input_value(input_type, cat_item.get("input_config", {}), val_obj, prop_tz)
            except ValueError:
                # Mask schema error
                raise HTTPException(status_code=422, detail="Geçersiz girdi")

            room_charge = _room_charge_for_item(cat_item, validated_val)
            if room_charge and not payload.confirm_room_charge:
                raise HTTPException(status_code=422, detail="Oda hesabına yazma onayı gerekli")

            cat, dept = map_legacy_routing(cat_item["service_code"], cat_item["department_code"])
            title_label = cat_item.get("labels", {}).get(payload.language) or cat_item.get("labels", {}).get("tr", cat_item["service_code"])

            desc = generate_deterministic_description(input_type, validated_val, it.note, cat_item.get("labels"), cat_item.get("input_config", {}), payload.language, prop_lang)

            req_ref = generate_public_reference("REQ")
            req_id = str(uuid.uuid4())

            doc = {
                "_id": req_id,
                "tenant_id": tenant_id,
                "property_id": property_id,
                "room_id": room_id,
                "room_number": room_number,
                "category": cat,
                "department": dept,
                "title": f"{title_label} — Oda {room_number}",
                "description": desc,
                "priority": cat_item.get("auto_priority", "normal"),
                "status": "new",
                "language": payload.language,
                "guest_name": guest_name,
                "guest_phone": guest_phone,
                "booking_id": booking_id,
                "guest_session_id": session_id,
                "assigned_to": None,
                "created_at": now_utc,
                "updated_at": now_utc,
                "completed_at": None,
                "source": "qr",
                "status_history": [{"status": "new", "by": "guest", "at": now_utc, "note": "QR üzerinden gönderildi (Structured)"}],
                "submission_group_id": submission_group_id,
                "service_code": it.service_code,
                "request_reference": req_ref,
                "catalogue_snapshot": {
                    "service_code": cat_item["service_code"],
                    "department_code": cat_item["department_code"],
                    "labels": cat_item.get("labels", {}),
                    "department_labels": cat_item.get("department_labels", {}),
                    "input_type": input_type,
                    "validated_value": validated_val,
                    "guest_note": it.note,
                    "input_config_snapshot": cat_item.get("input_config", {}),
                    "auto_priority_snapshot": cat_item.get("auto_priority", "normal"),
                    "estimated_minutes_snapshot": cat_item.get("estimated_minutes", 0),
                    "is_chargeable_snapshot": cat_item.get("is_chargeable", False),
                    "charge_warning_snapshot": cat_item.get("charge_warning"),
                    "catalogue_version": cat_item.get("version", 1),
                    "catalogue_mode": mode,
                    "timezone_snapshot": prop_tz,
                },
            }
            if room_charge:
                doc["room_charge"] = room_charge
                doc["catalogue_snapshot"]["room_charge_snapshot"] = room_charge

            if input_type in ("time", "datetime", "date") and "time_value" in val_obj:
                doc["catalogue_snapshot"]["submitted_local_time"] = val_obj["time_value"]
            if input_type in ("time", "datetime"):
                if "submitted_local_time" in validated_val:
                    doc["catalogue_snapshot"]["submitted_local_time"] = validated_val["submitted_local_time"]
                if "submitted_local_datetime" in validated_val:
                    doc["catalogue_snapshot"]["submitted_local_datetime"] = validated_val["submitted_local_datetime"]
                if "resolved_local_datetime" in validated_val:
                    doc["catalogue_snapshot"]["resolved_local_datetime"] = validated_val["resolved_local_datetime"]
                if "resolved_utc_datetime" in validated_val:
                    doc["catalogue_snapshot"]["resolved_utc_datetime"] = validated_val["resolved_utc_datetime"]

            prepared_items.append(doc)
            expected_codes.append(it.service_code)

        ledger_doc = {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "booking_id": booking_id,
            "idempotency_key": payload.idempotency_key,
            "payload_fingerprint": fingerprint,
            "submission_group_id": submission_group_id,
            "submission_reference": submission_reference,
            "status": "pending",
            "expected_service_codes": expected_codes,
            "prepared_items": prepared_items,
            "attempt_count": 0,
            "last_error_code": None,
            "created_at": now_utc,
            "updated_at": now_utc,
            "completed_at": None,
            "room_charge_consent": payload.confirm_room_charge,
            "room_charge_status": "not_required",
        }

        # 3. Write Ledger
        try:
            res = await tenant_db["guest_service_submissions"].find_one_and_update(
                {"tenant_id": tenant_id, "property_id": property_id, "booking_id": booking_id, "idempotency_key": payload.idempotency_key},
                _build_ledger_upsert_update(ledger_doc, _utc_now()),
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            if res.get("payload_fingerprint") != fingerprint:
                raise HTTPException(status_code=409, detail="Talep işleme alınamadı")

            prepared_items = res["prepared_items"]
            submission_group_id = res["submission_group_id"]
            submission_reference = res.get("submission_reference")
            if not submission_reference:
                raise HTTPException(status_code=503, detail="Sistem hatası")
        except DuplicateKeyError:
            for _ in range(5):
                res = await tenant_db["guest_service_submissions"].find_one({"tenant_id": tenant_id, "property_id": property_id, "booking_id": booking_id, "idempotency_key": payload.idempotency_key})
                if res:
                    break
                await asyncio.sleep(0.05)
            else:
                raise HTTPException(status_code=503, detail="Sistem hatası")

            if res.get("payload_fingerprint") != fingerprint:
                raise HTTPException(status_code=409, detail="Talep işleme alınamadı")

            prepared_items = res["prepared_items"]
            submission_group_id = res["submission_group_id"]
            submission_reference = res.get("submission_reference")
            if not submission_reference:
                raise HTTPException(status_code=503, detail="Sistem hatası")

    upd_res = await tenant_db["guest_service_submissions"].update_one(
        {"tenant_id": tenant_id, "property_id": property_id, "booking_id": booking_id, "submission_group_id": submission_group_id}, {"$inc": {"attempt_count": 1}, "$set": {"updated_at": _utc_now()}}
    )
    if upd_res.matched_count != 1:
        raise HTTPException(status_code=503, detail="Sistem hatası")

    docs_to_emit = []
    created_count = 0
    replayed_count = 0

    # 4. Idempotent Insert Loop
    for item_doc in prepared_items:
        for attempt in range(3):
            try:
                await tenant_db["qr_requests"].insert_one(item_doc)
                docs_to_emit.append(item_doc)
                created_count += 1
                break
            except DuplicateKeyError as e:
                details = getattr(e, "details", None) or {}
                key_pattern = details.get("keyPattern", {})

                if "request_reference" in key_pattern:
                    new_ref = generate_public_reference("REQ")
                    item_doc["request_reference"] = new_ref

                    # Update ledger so we know the new ref
                    upd_res = await tenant_db["guest_service_submissions"].update_one(
                        {
                            "tenant_id": tenant_id,
                            "property_id": property_id,
                            "booking_id": booking_id,
                            "submission_group_id": submission_group_id,
                            "prepared_items.service_code": item_doc["service_code"],
                        },
                        {"$set": {"prepared_items.$.request_reference": new_ref, "updated_at": _utc_now()}},
                    )
                    if upd_res.matched_count != 1:
                        raise HTTPException(status_code=503, detail="Sistem hatası")
                    reread = await tenant_db["guest_service_submissions"].find_one(
                        {"tenant_id": tenant_id, "property_id": property_id, "booking_id": booking_id, "submission_group_id": submission_group_id}
                    )
                    if not reread:
                        raise HTTPException(status_code=503, detail="Sistem hatası")
                    found = False
                    for pi in reread.get("prepared_items", []):
                        if pi["service_code"] == item_doc["service_code"]:
                            item_doc = pi
                            found = True
                            break
                    if not found:
                        raise HTTPException(status_code=503, detail="Sistem hatası")
                    continue

                # If duplicate on submission_group_id + service_code, it's a replay
                if "submission_group_id" in key_pattern and "service_code" in key_pattern:
                    replayed_count += 1
                    break

                logger.error("Collision during qr_requests upsert: group=req_collision_unknown")
                raise HTTPException(status_code=503, detail="Sistem hatası")
        else:
            raise HTTPException(status_code=503, detail="Sistem hatası")

    # 5. Convergence check
    expected_set = {it["service_code"] for it in prepared_items}
    expected_pairs = {(it["service_code"], it.get("request_reference")) for it in prepared_items}
    actual_docs = await tenant_db["qr_requests"].find({"tenant_id": tenant_id, "submission_group_id": submission_group_id}).to_list(None)
    actual_set = {d["service_code"] for d in actual_docs}
    actual_pairs = {(d["service_code"], d.get("request_reference")) for d in actual_docs}

    if expected_set == actual_set and len(actual_docs) == len(prepared_items) and len(actual_docs) == len(actual_set) and expected_pairs == actual_pairs:
        try:
            posted_room_charges = await _post_room_service_charges(
                tenant_id, tenant_db, booking_id, submission_group_id, prepared_items
            )
        except HTTPException:
            raise
        upd_res = await tenant_db["guest_service_submissions"].update_one(
            {"tenant_id": tenant_id, "property_id": property_id, "booking_id": booking_id, "submission_group_id": submission_group_id},
            {"$set": {"status": "completed", "completed_at": _utc_now(), "updated_at": _utc_now()}},
        )

        if upd_res.matched_count == 1:
            reread = await tenant_db["guest_service_submissions"].find_one({"tenant_id": tenant_id, "property_id": property_id, "booking_id": booking_id, "submission_group_id": submission_group_id})
            if reread and reread.get("status") == "completed" and reread.get("completed_at"):
                # Always derive public refs from winning ledger
                final_refs = []
                for itm in reread.get("prepared_items", []):
                    final_refs.append({"service_code": itm["service_code"], "request_reference": itm["request_reference"]})

                return {
                    "success": True,
                    "submission_reference": submission_reference,
                    "request_references": final_refs,
                    "stats": {"created": created_count, "replayed": replayed_count},
                    "room_charge_lines": posted_room_charges,
                    "docs_to_emit": docs_to_emit,
                }

        logger.error("Ledger completion update failed: group=ledger_completion_failure")
        raise HTTPException(status_code=503, detail="Talep işleme alınamadı, eksik kayıtlar var.")
    else:
        # Items are missing. Leave as pending, update last_error_code
        await tenant_db["guest_service_submissions"].update_one(
            {"tenant_id": tenant_id, "property_id": property_id, "booking_id": booking_id, "submission_group_id": submission_group_id},
            {"$set": {"status": "pending", "last_error_code": "CONVERGENCE_MISS", "updated_at": _utc_now()}},
        )
        logger.error("Ledger convergence failed: group=ledger_convergence_miss")
        raise HTTPException(status_code=503, detail="Talep işleme alınamadı, eksik kayıtlar var.")
