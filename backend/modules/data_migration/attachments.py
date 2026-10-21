"""Encrypted, download-only source documents; never reused as identity consent."""

import base64

from fastapi import HTTPException

from .formats import MAX_BYTES, MigrationError
from .schema import digest, private_fingerprint
from .service import now, seal, unseal


async def upload(db, tenant, record, source_id, filename, data):
    from security.upload_validator import validate_document_bytes

    if not data or len(data) > MAX_BYTES:
        raise MigrationError("Ek belge 1 bayt–5 MB arasında olmalı.")
    if not await db.migration_archive.find_one({"tenant_id": tenant, "id": record}):
        raise MigrationError("Ek belgenin bağlı olduğu arşiv kaydı bulunamadı.")
    try:
        mime = validate_document_bytes(data)
    except HTTPException as exc:
        raise MigrationError("Ek belge geçerli PDF veya görsel olmalı.") from exc
    if mime not in {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise MigrationError("Arşiv ekleri yalnız PDF ve görsel kabul eder; çalıştırılabilir/Office/ZIP alınmaz.")
    ext = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}[mime]
    fingerprint = private_fingerprint(base64.b64encode(data).decode("ascii"))
    key = private_fingerprint([tenant, record, source_id])
    prior = await db.migration_attachments.find_one({"_id": key, "tenant_id": tenant})
    if prior:
        if prior["content_hash"] != fingerprint:
            raise MigrationError("Aynı kaynak ek belge kimliği değişmiş içerikle geldi; farklı sürüm kimliği kullanın.")
        return {"id": key, "size": prior["size"], "content_type": prior["content_type"]}
    if await db.migration_attachments.count_documents({"tenant_id": tenant, "record_id": record}) >= 20:
        raise MigrationError("Bir arşiv kaydı en fazla 20 ek belge içerebilir.")
    # Filename and source attachment identifier may contain personal data.
    payload = {"source_id": source_id, "filename": str(filename or "belge")[:160], "base64": base64.b64encode(data).decode("ascii")}
    await db.migration_attachments.update_one(
        {"_id": key, "tenant_id": tenant},
        {
            "$setOnInsert": {
                "id": key,
                "tenant_id": tenant,
                "record_id": record,
                "content_hash": fingerprint,
                "payload": seal(payload, tenant),
                "size": len(data),
                "content_type": mime,
                "extension": ext,
                "created_at": now(),
            }
        },
        upsert=True,
    )
    await db.audit_logs.update_one(
        {"_id": digest([tenant, key, "migration_attachment_added"]), "tenant_id": tenant},
        {"$setOnInsert": {"tenant_id": tenant, "action": "migration_attachment_added", "target_id": record, "created_at": now()}},
        upsert=True,
    )
    return {"id": key, "size": len(data), "content_type": mime}


async def download(db, tenant, key):
    document = await db.migration_attachments.find_one({"_id": key, "tenant_id": tenant})
    if not document:
        raise MigrationError("Ek belge bulunamadı.")
    return base64.b64decode(unseal(document["payload"], tenant)["base64"], validate=True), document["content_type"], document["extension"]
