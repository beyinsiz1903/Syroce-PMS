import logging
import secrets
import string
import uuid

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.database import _raw_db as raw_db
from domains.guest.qr_catalogue_service import _utc_now, fetch_catalogue_data, is_service_available, resolve_catalogue_mode, validate_input_value
from domains.guest.qr_request_description import compute_payload_fingerprint, generate_deterministic_description
from models.schemas.qr_catalogue_submission import StructuredRequestSubmit
from routers.room_qr_requests import CATEGORY_MAP

logger = logging.getLogger(__name__)

def generate_public_reference(prefix="REQ"):
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"{prefix}-{suffix}"

def map_legacy_routing(service_code: str, department_code: str):
    if service_code in CATEGORY_MAP:
        return service_code, CATEGORY_MAP[service_code]["department"]

    legacy_depts = {c["department"] for c in CATEGORY_MAP.values()}
    if department_code in legacy_depts:
        return "other", department_code

    return "other", "other"

async def handle_structured_submission(tenant_id: str, property_id: str, room_id: str, booking_id: str, session_id: str, room_number: str, payload: StructuredRequestSubmit, guest_name: str | None, guest_phone: str | None):
    service_codes = [it.service_code for it in payload.items]
    if len(service_codes) != len(set(service_codes)):
        raise HTTPException(status_code=400, detail="Mükerrer hizmet kodu tespit edildi")

    fingerprint = compute_payload_fingerprint(payload.language, payload.items)

    ledger = await raw_db["guest_service_submissions"].find_one({
        "tenant_id": tenant_id,
        "property_id": property_id,
        "booking_id": booking_id,
        "idempotency_key": payload.idempotency_key
    })

    if ledger:
        if ledger.get("payload_fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Farklı bir talep aynı anahtarla gönderildi (Conflict)")
        prepared_items = ledger["prepared_items"]
        submission_group_id = ledger["submission_group_id"]
        submission_reference = ledger.get("submission_reference", generate_public_reference("GSR"))
    else:
        mode = await resolve_catalogue_mode(tenant_id, property_id)
        if mode == "disabled":
            raise HTTPException(status_code=403, detail="Hizmet şu anda kullanılamıyor")

        depts_data, services_data = await fetch_catalogue_data(tenant_id, property_id, mode)
        services_map = {s["service_code"]: s for s in services_data}

        prop = await raw_db["properties"].find_one({"id": property_id, "tenant_id": tenant_id}) or {}
        prop_tz = prop.get("timezone", "UTC")
        prop_lang = prop.get("default_language", "en")

        now_utc = _utc_now()
        submission_group_id = str(uuid.uuid4())
        submission_reference = generate_public_reference("GSR")

        prepared_items = []
        expected_codes = []
        pub_refs = []

        for it in payload.items:
            cat_item = services_map.get(it.service_code)
            if not cat_item or not cat_item.get("enabled", True):
                raise HTTPException(status_code=400, detail=f"Geçersiz veya kullanılamayan hizmet: {it.service_code}")

            if not is_service_available(cat_item.get("service_hours"), prop_tz):
                raise HTTPException(status_code=400, detail=f"Hizmet şu anda mesai dışı: {it.service_code}")

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
                    raise HTTPException(status_code=400, detail=f"Geçersiz veri alanı bulundu: {k}")

            try:
                validated_val = validate_input_value(input_type, cat_item.get("input_config", {}), val_obj, prop_tz)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"{it.service_code}: {str(e)}")

            cat, dept = map_legacy_routing(cat_item["service_code"], cat_item["department_code"])
            title_label = cat_item.get("labels", {}).get(payload.language) or cat_item.get("labels", {}).get("tr", cat_item["service_code"])

            desc = generate_deterministic_description(
                input_type,
                validated_val,
                it.note,
                cat_item.get("labels"),
                cat_item.get("input_config", {}),
                payload.language,
                prop_lang
            )

            req_ref = generate_public_reference("REQ")
            req_id = str(uuid.uuid4())

            # Use original submitted time info in snapshot if time-related
            snapshot_tz = prop_tz

            doc = {
                "_id": req_id,
                "tenant_id": tenant_id,
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
                    "timezone_snapshot": snapshot_tz
                }
            }
            if input_type in ("time", "datetime", "date") and "time_value" in val_obj:
                 doc["catalogue_snapshot"]["submitted_local_time"] = val_obj["time_value"]

            prepared_items.append(doc)
            expected_codes.append(it.service_code)
            pub_refs.append(req_ref)

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
            "public_request_references": pub_refs,
            "attempt_count": 0,
            "last_error_code": None,
            "created_at": now_utc,
            "updated_at": now_utc,
            "completed_at": None
        }

        try:
            res = await raw_db["guest_service_submissions"].find_one_and_update(
                {
                    "tenant_id": tenant_id,
                    "property_id": property_id,
                    "booking_id": booking_id,
                    "idempotency_key": payload.idempotency_key
                },
                {"$setOnInsert": ledger_doc},
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
            if res.get("payload_fingerprint") != fingerprint:
                raise HTTPException(status_code=409, detail="Farklı bir talep aynı anahtarla gönderildi (Conflict)")

            prepared_items = res["prepared_items"]
            submission_group_id = res["submission_group_id"]
            submission_reference = res["submission_reference"]
        except DuplicateKeyError:
            reread = None
            for _ in range(3):
                reread = await raw_db["guest_service_submissions"].find_one({
                    "tenant_id": tenant_id,
                    "property_id": property_id,
                    "booking_id": booking_id,
                    "idempotency_key": payload.idempotency_key
                })
                if reread:
                    break

            if not reread:
                logger.error(f"Failed to reread ledger after DuplicateKeyError for {payload.idempotency_key}")
                raise HTTPException(status_code=503, detail="Sistem hatası, lütfen tekrar deneyiniz")

            if reread.get("payload_fingerprint") != fingerprint:
                raise HTTPException(status_code=409, detail="Farklı bir talep aynı anahtarla gönderildi (Conflict)")

            prepared_items = reread["prepared_items"]
            submission_group_id = reread["submission_group_id"]
            submission_reference = reread["submission_reference"]

    await raw_db["guest_service_submissions"].update_one(
        {"submission_group_id": submission_group_id},
        {
            "$inc": {"attempt_count": 1},
            "$set": {"updated_at": _utc_now()}
        }
    )

    created_count = 0
    replayed_count = 0
    ref_list = []

    docs_to_emit = []

    for item_doc in prepared_items:
        try:
            upd = await raw_db["qr_requests"].update_one(
                {
                    "tenant_id": tenant_id,
                    "submission_group_id": submission_group_id,
                    "service_code": item_doc["service_code"]
                },
                {"$setOnInsert": item_doc},
                upsert=True
            )
            if upd.upserted_id:
                created_count += 1
                docs_to_emit.append(item_doc)
            else:
                replayed_count += 1

            ref_list.append({
                "service_code": item_doc["service_code"],
                "request_reference": item_doc["request_reference"]
            })
        except DuplicateKeyError:
            logger.error("Collision during qr_requests upsert")
            raise HTTPException(status_code=503, detail="Sistem hatası")

    count_expected = len(prepared_items)
    actual_count = await raw_db["qr_requests"].count_documents({
        "tenant_id": tenant_id,
        "submission_group_id": submission_group_id
    })

    if actual_count == count_expected:
        await raw_db["guest_service_submissions"].update_one(
            {"submission_group_id": submission_group_id},
            {"$set": {"status": "completed", "completed_at": _utc_now()}}
        )

    return {
        "success": True,
        "submission_reference": submission_reference,
        "request_references": ref_list,
        "stats": {
            "created": created_count,
            "replayed": replayed_count
        },
        "docs_to_emit": docs_to_emit
    }
