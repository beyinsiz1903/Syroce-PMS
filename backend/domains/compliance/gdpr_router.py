"""Tenant-scoped KVKK/GDPR policy and data-processor agreement workflows."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.audit import log_audit_event
from core.database import db
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op

from .retention_service import anonymization_runtime_enabled, enforce_guest_retention

router = APIRouter(prefix="/api/gdpr", tags=["GDPR / KVKK"])


class RetentionPolicyUpdate(BaseModel):
    guest_data_retention_days: int = Field(default=730, ge=30, le=3650)
    booking_data_retention_days: int = Field(default=1825, ge=365, le=3650)
    audit_log_retention_days: int = Field(default=3650, ge=365, le=3650)
    marketing_consent_retention_days: int = Field(default=365, ge=30, le=3650)
    auto_anonymize: bool = False


class DPACreate(BaseModel):
    processor_name: str = Field(min_length=2, max_length=160)
    purpose: str = Field(min_length=3, max_length=1000)
    retention_period_days: int = Field(ge=1, le=3650)
    status: Literal["draft", "active", "expired", "terminated"] = "draft"
    effective_from: date | None = None
    expires_at: date | None = None
    contact_email: str | None = Field(default=None, max_length=254)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("processor_name", "purpose")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Alan boş olamaz")
        return value


class DPAUpdate(BaseModel):
    processor_name: str | None = Field(default=None, min_length=2, max_length=160)
    purpose: str | None = Field(default=None, min_length=3, max_length=1000)
    retention_period_days: int | None = Field(default=None, ge=1, le=3650)
    status: Literal["draft", "active", "expired", "terminated"] | None = None
    effective_from: date | None = None
    expires_at: date | None = None
    contact_email: str | None = Field(default=None, max_length=254)
    notes: str | None = Field(default=None, max_length=2000)


class RetentionRunRequest(BaseModel):
    dry_run: bool = True
    limit: int = Field(default=500, ge=1, le=2000)
    confirmation: str | None = Field(default=None, max_length=80)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _actor_id(current_user) -> str:
    return str(getattr(current_user, "id", None) or getattr(current_user, "email", None) or "unknown")


def _default_policy(tenant_id: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "guest_data_retention_days": 730,
        "booking_data_retention_days": 1825,
        "audit_log_retention_days": 3650,
        "marketing_consent_retention_days": 365,
        "auto_anonymize": False,
        "configured": False,
    }


def _public_policy(policy: dict) -> dict:
    result = {key: value for key, value in policy.items() if key not in {"_id", "tenant_id"}}
    result["policies"] = [
        {
            "data_type": "guest_pii",
            "retention_days": result["guest_data_retention_days"],
            "auto_anonymize": result["auto_anonymize"],
        },
        {
            "data_type": "booking_history",
            "retention_days": result["booking_data_retention_days"],
            "auto_anonymize": False,
        },
        {
            "data_type": "audit_logs",
            "retention_days": result["audit_log_retention_days"],
            "auto_anonymize": False,
        },
        {
            "data_type": "marketing_consents",
            "retention_days": result["marketing_consent_retention_days"],
            "auto_anonymize": result["auto_anonymize"],
        },
    ]
    return result


@router.get("/retention-policy")
async def get_retention_policy(current_user=Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    stored = await db.gdpr_retention_policies.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return _public_policy(stored or _default_policy(tenant_id))


@router.put("/retention-policy")
async def update_retention_policy(
    body: RetentionPolicyUpdate,
    current_user=Depends(get_current_user),
    _permission=Depends(require_op("manage_secrets")),
):
    tenant_id = current_user.tenant_id
    before = await db.gdpr_retention_policies.find_one({"tenant_id": tenant_id}, {"_id": 0})
    now = _now()
    payload = {
        **body.model_dump(),
        "tenant_id": tenant_id,
        "configured": True,
        "updated_at": now,
        "updated_by": _actor_id(current_user),
    }
    await db.gdpr_retention_policies.update_one(
        {"tenant_id": tenant_id},
        {"$set": payload, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gdpr.retention_policy.updated",
        entity_type="gdpr_retention_policy",
        entity_id=tenant_id,
        details="KVKK/GDPR veri saklama politikası güncellendi",
        before_value=before,
        after_value=payload,
        db=db,
    )
    return _public_policy(payload)


@router.post("/retention/run")
async def run_retention_policy(
    body: RetentionRunRequest,
    current_user=Depends(get_current_user),
    _permission=Depends(require_op("manage_secrets")),
):
    tenant_id = current_user.tenant_id
    policy = await db.gdpr_retention_policies.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not policy or not policy.get("configured"):
        raise HTTPException(409, "Önce veri saklama politikasını kaydedin")
    if not body.dry_run:
        if not policy.get("auto_anonymize"):
            raise HTTPException(409, "Otomatik anonimleştirme politika üzerinde etkin değil")
        if body.confirmation != "ANONYMIZE_EXPIRED_GUESTS":
            raise HTTPException(422, "Kalıcı işlem için onay metni geçersiz")
        if not anonymization_runtime_enabled():
            raise HTTPException(503, "Anonimleştirme dağıtım düzeyinde etkin değil")
    result = await enforce_guest_retention(
        db,
        tenant_id=tenant_id,
        retention_days=int(policy["guest_data_retention_days"]),
        dry_run=body.dry_run,
        limit=body.limit,
        actor_id=_actor_id(current_user),
    )
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gdpr.retention.previewed" if body.dry_run else "gdpr.retention.executed",
        entity_type="gdpr_retention_run",
        entity_id=str(uuid.uuid4()),
        details=(
            f"Retention {'önizlemesi' if body.dry_run else 'anonimleştirmesi'}: "
            f"{result['eligible_count']} uygun, {result['anonymized_count']} anonimleştirildi"
        ),
        after_value=result,
        db=db,
        severity="warning" if not body.dry_run else "info",
    )
    return result


@router.get("/dpa")
async def list_dpas(current_user=Depends(get_current_user)):
    items = await db.dpa_records.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(500)
    return {"agreements": items, "total": len(items)}


@router.post("/dpa", status_code=201)
async def create_dpa(
    body: DPACreate,
    current_user=Depends(get_current_user),
    _permission=Depends(require_op("manage_secrets")),
):
    if body.effective_from and body.expires_at and body.expires_at <= body.effective_from:
        raise HTTPException(status_code=422, detail="Bitiş tarihi başlangıç tarihinden sonra olmalıdır")
    now = _now()
    record = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(mode="json"),
        "created_at": now,
        "created_by": _actor_id(current_user),
        "updated_at": now,
        "updated_by": _actor_id(current_user),
    }
    await db.dpa_records.insert_one(record.copy())
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=_actor_id(current_user),
        action="gdpr.dpa.created",
        entity_type="data_processing_agreement",
        entity_id=record["id"],
        details=f"Veri işleyen sözleşmesi oluşturuldu: {record['processor_name']}",
        after_value=record,
        db=db,
    )
    return {key: value for key, value in record.items() if key not in {"_id", "tenant_id"}}


@router.patch("/dpa/{agreement_id}")
async def update_dpa(
    agreement_id: str,
    body: DPAUpdate,
    current_user=Depends(get_current_user),
    _permission=Depends(require_op("manage_secrets")),
):
    query = {"id": agreement_id, "tenant_id": current_user.tenant_id}
    before = await db.dpa_records.find_one(query, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Veri işleme sözleşmesi bulunamadı")
    changes = body.model_dump(exclude_unset=True, mode="json")
    effective_from = changes.get("effective_from", before.get("effective_from"))
    expires_at = changes.get("expires_at", before.get("expires_at"))
    if effective_from and expires_at and expires_at <= effective_from:
        raise HTTPException(status_code=422, detail="Bitiş tarihi başlangıç tarihinden sonra olmalıdır")
    changes.update({"updated_at": _now(), "updated_by": _actor_id(current_user)})
    await db.dpa_records.update_one(query, {"$set": changes})
    after = {**before, **changes}
    await log_audit_event(
        tenant_id=current_user.tenant_id,
        user_id=_actor_id(current_user),
        action="gdpr.dpa.updated",
        entity_type="data_processing_agreement",
        entity_id=agreement_id,
        details=f"Veri işleyen sözleşmesi güncellendi: {after.get('processor_name', agreement_id)}",
        before_value=before,
        after_value=after,
        db=db,
    )
    return {key: value for key, value in after.items() if key not in {"_id", "tenant_id"}}


@router.get("/compliance-status")
async def get_compliance_status(current_user=Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    total_guests = await db.guests.count_documents({"tenant_id": tenant_id})
    guests_with_consent = await db.kvkk_consents.count_documents({"tenant_id": tenant_id})
    anonymized_guests = await db.guests.count_documents(
        {"tenant_id": tenant_id, "$or": [{"anonymized": True}, {"is_anonymized": True}]}
    )
    erasure_requests = await db.kvkk_erasure_requests.count_documents({"tenant_id": tenant_id})
    open_erasure_requests = await db.kvkk_erasure_requests.count_documents(
        {"tenant_id": tenant_id, "status": {"$nin": ["completed", "rejected", "cancelled"]}}
    )
    active_dpas = await db.dpa_records.count_documents({"tenant_id": tenant_id, "status": "active"})
    retention = await db.gdpr_retention_policies.find_one({"tenant_id": tenant_id}, {"_id": 0})
    consent_coverage = total_guests == 0 or guests_with_consent >= total_guests
    checks = {
        "misafir_onaylari_tamam": consent_coverage,
        "saklama_politikasi_tanimli": bool(retention and retention.get("configured")),
        "acik_silme_talebi_yok": open_erasure_requests == 0,
        "aktif_veri_isleyen_sozlesmesi_var": active_dpas > 0,
    }
    score = round((sum(1 for passed in checks.values() if passed) / len(checks)) * 100)
    recommendations = []
    if not consent_coverage:
        recommendations.append("Eksik misafir açık rıza/onay kayıtlarını tamamlayın.")
    if not checks["saklama_politikasi_tanimli"]:
        recommendations.append("Tesise özel veri saklama politikasını onaylayıp kaydedin.")
    if open_erasure_requests:
        recommendations.append(f"Bekleyen {open_erasure_requests} veri silme talebini sonuçlandırın.")
    if not active_dpas:
        recommendations.append("Aktif veri işleyen sağlayıcılar için DPA kaydı oluşturun.")

    recent_actions = await db.audit_logs.find(
        {"tenant_id": tenant_id, "operation_name": {"$regex": "^gdpr\\."}},
        {"_id": 0, "id": 1, "operation_name": 1, "details": 1, "timestamp": 1},
    ).sort("timestamp", -1).to_list(20)
    recent_actions = [
        {
            "id": item.get("id"),
            "action": item.get("details") or item.get("operation_name"),
            "timestamp": item.get("timestamp"),
        }
        for item in recent_actions
    ]
    return {
        "compliance_score": score,
        "total_guests": total_guests,
        "guests_with_consent": guests_with_consent,
        "consented_guests": guests_with_consent,
        "anonymized_guests": anonymized_guests,
        "erasure_requests": erasure_requests,
        "open_erasure_requests": open_erasure_requests,
        "data_processing_agreements": active_dpas,
        "compliance_checks": checks,
        "recommendations": recommendations,
        "recent_actions": recent_actions,
        "last_audit": recent_actions[0]["timestamp"] if recent_actions else None,
        "status": "action_required" if recommendations else "compliant",
    }
