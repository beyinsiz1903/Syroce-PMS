"""Tenant-admin migration workbench. Uploaded data never selects a tenant."""

from __future__ import annotations

import csv
import io
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from core.helpers import require_module
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.data_migration import api_source, attachments, cutover, service
from modules.data_migration.formats import MAX_BYTES, MigrationError, parse_file
from modules.data_migration.schema import ALIASES, FIELDS, REQUIRED
from modules.pms_core.role_permission_service import require_op


def require_migration_admin(response: Response, user: User = Depends(get_current_user)):
    from core.security import _is_super_admin

    if not _is_super_admin(user) and str(getattr(user.role, "value", user.role)) != "admin":
        raise HTTPException(403, "Veri taşıma merkezi yalnız tesis yöneticisi ve süperadmin içindir.")
    if not user.tenant_id:
        raise HTTPException(403, "Önce işlem yapılacak tesisi seçin.")
    from security.guest_data_visibility import user_guest_data_visibility

    policy, _ = user_guest_data_visibility(user)
    if any(mode != "full" for mode in policy.values()):
        raise HTTPException(403, "Kısıtlı misafir alanı erişimiyle toplu veri taşıma kullanılamaz.")
    response.headers["Cache-Control"] = "no-store"
    return user


router = APIRouter(prefix="/api/data-migration", tags=["Data Migration"], dependencies=[Depends(require_module("pms")), Depends(require_op("manage_users"))])


class BatchIn(BaseModel):
    source: str = Field(min_length=2, max_length=80)
    namespace: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    publish_guests: bool = False
    allow_archive_updates: bool = False

    @field_validator("source")
    @classmethod
    def clean_source(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Geçerli bir kaynak adı gerekli")
        return value.strip()


ShortText = Annotated[str, Field(min_length=1, max_length=160)]


class MappingIn(BaseModel):
    mapping: dict[ShortText, ShortText] = Field(max_length=80)
    date_format: Literal["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"] = "%Y-%m-%d"
    decimal_separator: Literal[".", ","] = "."
    value_mapping: dict[ShortText, dict[ShortText, ShortText]] = Field(default_factory=dict, max_length=3)
    expected_count: int | None = Field(default=None, ge=0, le=50000)
    expected_totals: dict[ShortText, Annotated[str, Field(max_length=40)]] | None = Field(default=None, max_length=100)
    guest_links: dict[ShortText, ShortText] = Field(default_factory=dict, max_length=10000)
    folio_transactions_complete: bool = False
    preserve_extra_fields: bool = False


class CommitIn(BaseModel):
    review_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_only_ack: Literal[True]
    warnings_ack: Literal[True]


class RollbackIn(BaseModel):
    confirmation: Literal["ARSIVI GERI AL"]


class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    batch_id: str = Field(max_length=80)
    dataset_id: str = Field(max_length=80)


class CutoverIn(BaseModel):
    cutover_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_frozen_at: str = Field(max_length=40)
    target_links: dict[ShortText, dict[ShortText, ShortText]] = Field(default_factory=dict, max_length=3)
    accounts: dict[ShortText, ShortText] = Field(default_factory=dict, max_length=4)
    exchange_rates: dict[ShortText, Annotated[str, Field(max_length=24)]] = Field(default_factory=dict, max_length=40)
    balances_exclude_folios: bool = False
    source_writes_stopped: Literal[True]

    @field_validator("target_links")
    @classmethod
    def target_kinds(cls, value):
        if set(value) - {"rooms", "companies", "agencies"} or any(len(v) > 2000 for v in value.values()):
            raise ValueError("Hedef eşleştirmesi geçersiz veya çok büyük")
        return value


class CutoverCommitIn(BaseModel):
    review_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation: Literal["CANLI DEVRI ONAYLIYORUM"]


class ApiSourceIn(BaseModel):
    source_id: str = Field(pattern=r"^[a-z0-9_-]{3,60}$")


async def call(operation):
    try:
        return await operation
    except MigrationError as exc:
        raise HTTPException(422, str(exc)) from exc


async def batch_for(user, batch_id):
    return await call(service.get_batch(get_system_db(), user.tenant_id, batch_id))


@router.get("/schema")
async def schema(user: User = Depends(require_migration_admin)):
    return {
        "entities": {entity: {"fields": sorted(fields), "required": sorted(REQUIRED[entity])} for entity, fields in FIELDS.items()},
        "aliases": ALIASES,
        "formats": ["csv", "tsv", "xlsx", "json", "xml"],
        "limits": {"file_bytes": MAX_BYTES, "file_rows": 10000, "batch_rows": 50000, "files": 20},
        "capabilities": {
            "archive": True,
            "publish_guests": True,
            "activate_reservations": True,
            "draft_opening_balances": True,
            "post_opening_balances": False,
            "versioned_archive_deltas": True,
            "configured_json_api": True,
            "vendor_api_connectors": False,
            "cutover_billing_scope": "direct_guest_pay_only",
        },
    }


@router.get("/batches")
async def list_batches(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), user: User = Depends(require_migration_admin)):
    db = get_system_db()
    query = {"tenant_id": user.tenant_id}
    batches = await db.migration_batches.find(query, {"plan": 0}).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)
    return {"items": [service.public_batch(b) for b in batches], "total": await db.migration_batches.count_documents(query), "offset": offset, "limit": limit}


@router.get("/mapping-templates")
async def mapping_templates(user: User = Depends(require_migration_admin)):
    items = await get_system_db().migration_templates.find({"tenant_id": user.tenant_id}, {"_id": 0}).sort("name", 1).limit(200).to_list(200)
    return {"items": items}


@router.get("/api-sources")
async def api_sources(user: User = Depends(require_migration_admin)):
    try:
        return {"items": api_source.public_sources(user.tenant_id)}
    except MigrationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/archive/{record_id}/versions")
async def archive_versions(record_id: str, user: User = Depends(require_migration_admin)):
    documents = await get_system_db().migration_versions.find({"tenant_id": user.tenant_id, "record_id": record_id}).sort("archived_at", -1).limit(101).to_list(101)
    return {
        "items": [{"archived_at": d["archived_at"], "replaced_by_batch": d["replaced_by_batch"], "data": service.unseal(d["previous"]["payload"], user.tenant_id)} for d in documents[:100]],
        "truncated": len(documents) > 100,
    }


@router.get("/archive/{record_id}/attachments")
async def list_attachments(record_id: str, user: User = Depends(require_migration_admin)):
    items = (
        await get_system_db()
        .migration_attachments.find({"tenant_id": user.tenant_id, "record_id": record_id}, {"_id": 0, "id": 1, "size": 1, "content_type": 1, "created_at": 1})
        .limit(20)
        .to_list(20)
    )
    return {"items": items}


@router.post("/archive/{record_id}/attachments")
async def add_attachment(record_id: str, source_id: str = Form(..., min_length=1, max_length=160), file: UploadFile = File(...), user: User = Depends(require_migration_admin)):
    db = get_system_db()
    try:
        data = await file.read(MAX_BYTES + 1)

        async def run():
            return await attachments.upload(db, user.tenant_id, record_id, source_id, file.filename, data)

        return await call(service.namespace_guard(db, {"tenant_id": user.tenant_id}, run))
    finally:
        await file.close()


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(attachment_id: str, user: User = Depends(require_migration_admin)):
    data, mime, ext = await call(attachments.download(get_system_db(), user.tenant_id, attachment_id))
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="source-document{ext}"', "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )


@router.post("/batches/{batch_id}/api-import")
async def import_api_source(batch_id: str, body: ApiSourceIn, user: User = Depends(require_migration_admin)):
    db, batch = get_system_db(), await batch_for(user, batch_id)
    return await call(service.namespace_guard(db, batch, lambda: api_source.import_snapshot(db, batch, user.id, body.source_id)))


@router.post("/mapping-templates")
async def save_mapping_template(body: TemplateIn, user: User = Depends(require_migration_admin)):
    batch = await batch_for(user, body.batch_id)
    dataset = next((d for d in batch["datasets"] if d["id"] == body.dataset_id), None)
    if not dataset:
        raise HTTPException(404, "Dosya bulunamadı.")
    template_id = service.digest([user.tenant_id, body.name.strip(), dataset["entity"]])
    item = {
        "id": template_id,
        "tenant_id": user.tenant_id,
        "name": body.name.strip(),
        "entity": dataset["entity"],
        **{key: dataset[key] for key in ("mapping", "date_format", "decimal_separator", "value_mapping")},
        "preserve_extra_fields": dataset.get("preserve_extra_fields", False),
    }
    await get_system_db().migration_templates.update_one({"_id": template_id, "tenant_id": user.tenant_id}, {"$set": item}, upsert=True)
    return item


@router.post("/batches", status_code=201)
async def create_batch(body: BatchIn, user: User = Depends(require_migration_admin)):
    return await call(service.create_batch(get_system_db(), user.tenant_id, user.id, **body.model_dump()))


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, user: User = Depends(require_migration_admin)):
    return service.public_batch(await batch_for(user, batch_id))


@router.post("/batches/{batch_id}/files")
async def upload(
    batch_id: str,
    entity: str = Form(...),
    encoding: Literal["utf-8-sig", "cp1254"] = Form("utf-8-sig"),
    sheet: str | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(require_migration_admin),
):
    batch = await batch_for(user, batch_id)
    if entity not in FIELDS:
        raise HTTPException(422, "Geçersiz veri türü.")
    try:
        content = await file.read(MAX_BYTES + 1)
        headers, rows = parse_file(file.filename, content, encoding=encoding, sheet=sheet or None)
    except MigrationError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()
    return await call(service.add_dataset(get_system_db(), batch, user.id, entity=entity, headers=headers, rows=rows))


@router.put("/batches/{batch_id}/datasets/{dataset_id}")
async def update_mapping(batch_id: str, dataset_id: str, body: MappingIn, user: User = Depends(require_migration_admin)):
    batch = await batch_for(user, batch_id)
    dataset = next((d for d in batch["datasets"] if d["id"] == dataset_id), None)
    if not dataset:
        raise HTTPException(404, "Dosya bulunamadı.")
    if set(body.mapping) - FIELDS[dataset["entity"]] or set(body.mapping.values()) - set(dataset["headers"]) or len(set(body.mapping.values())) != len(body.mapping):
        raise HTTPException(422, "Sütun eşleştirmesi geçersiz.")
    if set(body.value_mapping) - {"status", "kind", "currency"} or any(len(m) > 100 for m in body.value_mapping.values()):
        raise HTTPException(422, "Kod eşleştirmesi geçersiz veya çok büyük.")
    datasets = [{**d, **body.model_dump()} if d["id"] == dataset_id else d for d in batch["datasets"]]
    return await call(service.change_batch(get_system_db(), batch, user.id, {"datasets": datasets}))


@router.delete("/batches/{batch_id}/datasets/{dataset_id}")
async def remove_dataset(batch_id: str, dataset_id: str, user: User = Depends(require_migration_admin)):
    batch = await batch_for(user, batch_id)
    if not any(d["id"] == dataset_id for d in batch["datasets"]):
        raise HTTPException(404, "Dosya bulunamadı.")
    result = await call(service.change_batch(get_system_db(), batch, user.id, {"datasets": [d for d in batch["datasets"] if d["id"] != dataset_id]}))
    await get_system_db().migration_staging.delete_many({"tenant_id": user.tenant_id, "batch_id": batch_id, "dataset_id": dataset_id})
    return result


@router.post("/batches/{batch_id}/review")
async def review_batch(batch_id: str, user: User = Depends(require_migration_admin)):
    return await call(service.review(get_system_db(), await batch_for(user, batch_id), user.id))


@router.post("/batches/{batch_id}/commit")
async def commit(batch_id: str, body: CommitIn, user: User = Depends(require_migration_admin)):
    db = get_system_db()
    batch = await batch_for(user, batch_id)

    async def run():
        return await service.commit_chunk(db, await service.get_batch(db, user.tenant_id, batch_id), user.id, body.review_token)

    return await call(service.namespace_guard(db, batch, run))


@router.post("/batches/{batch_id}/rollback")
async def rollback(batch_id: str, body: RollbackIn, user: User = Depends(require_migration_admin)):
    db = get_system_db()
    batch = await batch_for(user, batch_id)

    async def run():
        return await service.rollback(db, await service.get_batch(db, user.tenant_id, batch_id), user.id)

    return await call(service.namespace_guard(db, batch, run))


@router.get("/batches/{batch_id}/cutover")
async def get_cutover(batch_id: str, user: User = Depends(require_migration_admin)):
    return await call(cutover.get_job(get_system_db(), await batch_for(user, batch_id)))


@router.put("/batches/{batch_id}/cutover")
async def configure_cutover(batch_id: str, body: CutoverIn, user: User = Depends(require_migration_admin)):
    db, batch = get_system_db(), await batch_for(user, batch_id)

    async def run():
        return await cutover.configure(db, batch, user.id, body.model_dump())

    return await call(service.namespace_guard(db, batch, run))


@router.post("/batches/{batch_id}/cutover/review")
async def review_cutover(batch_id: str, user: User = Depends(require_migration_admin)):
    db, batch = get_system_db(), await batch_for(user, batch_id)
    return await call(cutover.review(db, batch, user.id))


@router.post("/batches/{batch_id}/cutover/voucher")
async def draft_cutover_voucher(batch_id: str, body: CutoverCommitIn, user: User = Depends(require_migration_admin), _module=Depends(require_module("finance"))):
    db, batch = get_system_db(), await batch_for(user, batch_id)

    async def run():
        job, plan = await cutover.activation_plan(db, batch, body.review_token)
        if not plan["lines"]:
            raise MigrationError("Sıfır açılış için muhasebe fişi oluşturulmaz.")
        if job["state"] not in {"reviewed", "awaiting_finance"}:
            raise MigrationError("Açılış fişi bu durumda oluşturulamaz.")
        await cutover.claim_source(db, batch)
        from domains.accounting.gl_router import AccountingSetupOpeningBalanceIn, create_accounting_setup_opening_balance

        result = await create_accounting_setup_opening_balance(
            AccountingSetupOpeningBalanceIn(date=plan["cutover_date"], lines=plan["lines"], memo="PMS veri devir açılışı " + batch["id"], idempotency_key="migration:" + batch["id"]), current_user=user
        )
        return await cutover.record_voucher(db, batch, body.review_token, result["voucher"])

    return await call(service.namespace_guard(db, batch, run))


@router.post("/batches/{batch_id}/cutover/activate")
async def activate_cutover(batch_id: str, body: CutoverCommitIn, user: User = Depends(require_migration_admin)):
    db, batch = get_system_db(), await batch_for(user, batch_id)
    return await call(service.namespace_guard(db, batch, lambda: cutover.activate(db, batch, user.id, body.review_token)))


@router.get("/batches/{batch_id}/errors.csv")
async def errors_csv(batch_id: str, user: User = Depends(require_migration_admin)):
    batch = await batch_for(user, batch_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["dataset_id", "row", "message"])
    for error in (batch.get("report") or {}).get("errors", []):
        # No input values / names in this diagnostic export; formula-safe as well.
        writer.writerow([re.sub(r"^[=+@-]", "'", str(error.get(k, ""))) for k in ("dataset_id", "row", "message")])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="migration-errors.csv"', "Cache-Control": "no-store"})


@router.get("/archive")
async def archive(
    namespace: str | None = Query(None, max_length=80),
    entity: str | None = None,
    guest_id: str | None = None,
    record_id: str | None = Query(None, pattern=r"^[0-9a-f]{64}$"),
    parent_id: str | None = Query(None, pattern=r"^[0-9a-f]{64}$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_migration_admin),
):
    if entity and entity not in FIELDS:
        raise HTTPException(422, "Geçersiz veri türü.")
    return await call(
        service.archive_rows(get_system_db(), user.tenant_id, namespace=namespace, entity=entity, guest_id=guest_id, record_key=record_id, parent_key=parent_id, offset=offset, limit=limit)
    )


@router.get("/templates/{entity}.csv")
async def template(entity: str, user: User = Depends(require_migration_admin)):
    if entity not in FIELDS:
        raise HTTPException(404, "Şablon bulunamadı.")
    output = io.StringIO()
    csv.writer(output).writerow(sorted(REQUIRED[entity]) + sorted(FIELDS[entity] - REQUIRED[entity]))
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{entity}-template.csv"', "Cache-Control": "no-store"})
