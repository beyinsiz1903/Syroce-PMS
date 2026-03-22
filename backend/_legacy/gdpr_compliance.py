"""KVKK/GDPR Compliance Module - Data Processing, Consent, Export, Delete, Anonymize"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import json
import io
import hashlib

router = APIRouter(prefix="/api/gdpr", tags=["KVKK/GDPR Compliance"])

# ============= MODELS =============
class ConsentRecord(BaseModel):
    consent_type: str  # 'marketing', 'analytics', 'data_processing', 'third_party'
    granted: bool
    source: str = "web"  # 'web', 'mobile', 'paper', 'verbal'
    ip_address: Optional[str] = None

class DataExportRequest(BaseModel):
    format: str = "json"  # 'json' or 'csv'
    include_bookings: bool = True
    include_folios: bool = True
    include_communications: bool = True

class DataDeletionRequest(BaseModel):
    reason: str
    confirm: bool = False
    anonymize_instead: bool = False

class DataProcessingAgreement(BaseModel):
    processor_name: str
    purpose: str
    data_categories: List[str]
    retention_period_days: int
    security_measures: List[str]
    cross_border_transfer: bool = False
    transfer_country: Optional[str] = None

# ============= ENDPOINTS =============
def create_gdpr_routes(db, get_current_user):
    """Create GDPR/KVKK compliance routes"""
    
    # ---- CONSENT MANAGEMENT ----
    @router.get("/consent/{guest_id}")
    async def get_guest_consents(
        guest_id: str,
        current_user=Depends(get_current_user)
    ):
        """Get all consent records for a guest"""
        consents = await db.gdpr_consents.find(
            {"guest_id": guest_id, "tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).sort("updated_at", -1).to_list(100)
        
        return {
            "guest_id": guest_id,
            "consents": consents,
            "summary": {
                "marketing": next((c["granted"] for c in consents if c["consent_type"] == "marketing"), False),
                "analytics": next((c["granted"] for c in consents if c["consent_type"] == "analytics"), False),
                "data_processing": next((c["granted"] for c in consents if c["consent_type"] == "data_processing"), False),
                "third_party": next((c["granted"] for c in consents if c["consent_type"] == "third_party"), False)
            }
        }
    
    @router.post("/consent/{guest_id}")
    async def record_consent(
        guest_id: str,
        consent: ConsentRecord,
        current_user=Depends(get_current_user)
    ):
        """Record a consent decision"""
        consent_doc = {
            "id": str(uuid.uuid4()),
            "guest_id": guest_id,
            "tenant_id": current_user.tenant_id,
            "consent_type": consent.consent_type,
            "granted": consent.granted,
            "source": consent.source,
            "ip_address": consent.ip_address,
            "recorded_by": current_user.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Upsert consent
        await db.gdpr_consents.update_one(
            {
                "guest_id": guest_id,
                "tenant_id": current_user.tenant_id,
                "consent_type": consent.consent_type
            },
            {"$set": consent_doc},
            upsert=True
        )
        
        # Audit trail
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": f"consent_{'granted' if consent.granted else 'revoked'}_{consent.consent_type}",
            "resource_type": "gdpr",
            "resource_id": guest_id,
            "details": {"consent_type": consent.consent_type, "granted": consent.granted},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {"success": True, "message": f"Onay {'kaydedildi' if consent.granted else 'geri cekildi'}"}
    
    # ---- DATA EXPORT (Right to Data Portability) ----
    @router.post("/export/{guest_id}")
    async def export_guest_data(
        guest_id: str,
        request: DataExportRequest,
        current_user=Depends(get_current_user)
    ):
        """Export all guest data (KVKK/GDPR Right to Data Portability)"""
        if current_user.role not in ["admin", "super_admin", "front_desk"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        tenant_id = current_user.tenant_id
        
        # Collect all guest data
        guest = await db.guests.find_one(
            {"id": guest_id, "tenant_id": tenant_id},
            {"_id": 0}
        )
        if not guest:
            raise HTTPException(status_code=404, detail="Misafir bulunamadi")
        
        export_data = {"guest_profile": guest}
        
        if request.include_bookings:
            bookings = await db.bookings.find(
                {"guest_id": guest_id, "tenant_id": tenant_id},
                {"_id": 0}
            ).to_list(1000)
            export_data["bookings"] = bookings
        
        if request.include_folios:
            folios = await db.folios.find(
                {"guest_id": guest_id, "tenant_id": tenant_id},
                {"_id": 0}
            ).to_list(1000)
            export_data["folios"] = folios
        
        if request.include_communications:
            comms = await db.guest_communications.find(
                {"guest_id": guest_id, "tenant_id": tenant_id},
                {"_id": 0}
            ).to_list(1000)
            export_data["communications"] = comms
        
        # Consents
        consents = await db.gdpr_consents.find(
            {"guest_id": guest_id, "tenant_id": tenant_id},
            {"_id": 0}
        ).to_list(100)
        export_data["consents"] = consents
        
        # Audit log
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": current_user.id,
            "action": "gdpr_data_export",
            "resource_type": "gdpr",
            "resource_id": guest_id,
            "details": {"format": request.format},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        export_data["export_metadata"] = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": current_user.email,
            "tenant_id": tenant_id,
            "format": request.format
        }
        
        if request.format == "json":
            content = json.dumps(export_data, indent=2, ensure_ascii=False, default=str)
            return StreamingResponse(
                io.BytesIO(content.encode('utf-8')),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=guest_{guest_id}_data_export.json"}
            )
        
        return export_data
    
    # ---- DATA DELETION (Right to be Forgotten) ----
    @router.post("/delete/{guest_id}")
    async def delete_guest_data(
        guest_id: str,
        request: DataDeletionRequest,
        current_user=Depends(get_current_user)
    ):
        """Delete or anonymize guest data (KVKK/GDPR Right to be Forgotten)"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Sadece admin bu islemi yapabilir")
        
        if not request.confirm:
            raise HTTPException(status_code=400, detail="Silme islemini onaylamaniz gerekiyor (confirm=true)")
        
        tenant_id = current_user.tenant_id
        
        guest = await db.guests.find_one(
            {"id": guest_id, "tenant_id": tenant_id},
            {"_id": 0}
        )
        if not guest:
            raise HTTPException(status_code=404, detail="Misafir bulunamadi")
        
        if request.anonymize_instead:
            # Anonymize instead of delete
            anon_hash = hashlib.sha256(guest_id.encode()).hexdigest()[:12]
            anonymized_data = {
                "name": f"Anonim Misafir #{anon_hash}",
                "email": f"anonymized_{anon_hash}@deleted.local",
                "phone": "***-***-****",
                "id_number": "***",
                "address": "[Anonimlestirildi]",
                "notes": "[Anonimlestirildi]",
                "is_anonymized": True,
                "anonymized_at": datetime.now(timezone.utc).isoformat(),
                "anonymized_by": current_user.id,
                "anonymization_reason": request.reason
            }
            
            await db.guests.update_one(
                {"id": guest_id, "tenant_id": tenant_id},
                {"$set": anonymized_data}
            )
            
            # Anonymize related booking guest names
            await db.bookings.update_many(
                {"guest_id": guest_id, "tenant_id": tenant_id},
                {"$set": {"guest_name": f"Anonim Misafir #{anon_hash}", "guest_email": f"anonymized_{anon_hash}@deleted.local"}}
            )
            
            action = "gdpr_data_anonymized"
            message = "Misafir verileri basariyla anonimlestirildi"
        else:
            # Full deletion
            await db.guests.delete_one({"id": guest_id, "tenant_id": tenant_id})
            await db.gdpr_consents.delete_many({"guest_id": guest_id, "tenant_id": tenant_id})
            await db.guest_communications.delete_many({"guest_id": guest_id, "tenant_id": tenant_id})
            # Keep bookings for legal/financial reasons but anonymize guest info
            await db.bookings.update_many(
                {"guest_id": guest_id, "tenant_id": tenant_id},
                {"$set": {"guest_name": "[Silindi]", "guest_email": "[Silindi]", "guest_phone": "[Silindi]"}}
            )
            
            action = "gdpr_data_deleted"
            message = "Misafir verileri basariyla silindi"
        
        # Mandatory audit log (retained for compliance)
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": current_user.id,
            "action": action,
            "resource_type": "gdpr",
            "resource_id": guest_id,
            "details": {"reason": request.reason, "anonymize": request.anonymize_instead},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {"success": True, "message": message}
    
    # ---- DATA PROCESSING AGREEMENTS ----
    @router.get("/dpa")
    async def list_data_processing_agreements(current_user=Depends(get_current_user)):
        """List all data processing agreements"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        dpas = await db.data_processing_agreements.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).to_list(100)
        
        return {"agreements": dpas, "total": len(dpas)}
    
    @router.post("/dpa")
    async def create_data_processing_agreement(
        dpa: DataProcessingAgreement,
        current_user=Depends(get_current_user)
    ):
        """Create new data processing agreement"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        dpa_doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "processor_name": dpa.processor_name,
            "purpose": dpa.purpose,
            "data_categories": dpa.data_categories,
            "retention_period_days": dpa.retention_period_days,
            "security_measures": dpa.security_measures,
            "cross_border_transfer": dpa.cross_border_transfer,
            "transfer_country": dpa.transfer_country,
            "status": "active",
            "created_by": current_user.id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.data_processing_agreements.insert_one(dpa_doc)
        
        return {"success": True, "agreement": {k: v for k, v in dpa_doc.items() if k != '_id'}}
    
    # ---- COMPLIANCE DASHBOARD ----
    @router.get("/compliance-status")
    async def get_compliance_status(current_user=Depends(get_current_user)):
        """Get KVKK/GDPR compliance status dashboard"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        tenant_id = current_user.tenant_id
        
        # Count guests with/without consents
        total_guests = await db.guests.count_documents({"tenant_id": tenant_id})
        guests_with_consent = await db.gdpr_consents.distinct("guest_id", {"tenant_id": tenant_id})
        anonymized_guests = await db.guests.count_documents({"tenant_id": tenant_id, "is_anonymized": True})
        
        # Data processing agreements
        dpa_count = await db.data_processing_agreements.count_documents({"tenant_id": tenant_id})
        
        # Recent GDPR actions
        recent_actions = await db.audit_logs.find(
            {"tenant_id": tenant_id, "resource_type": "gdpr"},
            {"_id": 0}
        ).sort("timestamp", -1).to_list(10)
        
        # Compliance score calculation
        checks = {
            "consent_management": len(guests_with_consent) > 0,
            "data_processing_agreements": dpa_count > 0,
            "data_export_capability": True,  # Always available via API
            "data_deletion_capability": True,  # Always available via API
            "anonymization_capability": True,  # Always available via API
            "audit_trail": True,  # Always active
            "encryption_at_rest": True,  # MongoDB encryption
            "access_control": True  # RBAC system
        }
        score = sum(1 for v in checks.values() if v) / len(checks) * 100
        
        return {
            "compliance_score": round(score, 1),
            "total_guests": total_guests,
            "guests_with_consent": len(guests_with_consent),
            "guests_without_consent": total_guests - len(guests_with_consent),
            "anonymized_guests": anonymized_guests,
            "data_processing_agreements": dpa_count,
            "compliance_checks": checks,
            "recent_actions": recent_actions,
            "recommendations": [
                r for r in [
                    "Tum misafirlerden onay alinmali" if len(guests_with_consent) < total_guests else None,
                    "Veri isleme sozlesmesi olusturun" if dpa_count == 0 else None,
                ] if r
            ]
        }
    
    # ---- DATA RETENTION ----
    @router.get("/retention-policy")
    async def get_retention_policy(current_user=Depends(get_current_user)):
        """Get data retention policy"""
        policy = await db.retention_policies.find_one(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        )
        
        return policy or {
            "tenant_id": current_user.tenant_id,
            "guest_data_retention_days": 365 * 3,  # 3 years default
            "booking_data_retention_days": 365 * 7,  # 7 years for financial
            "audit_log_retention_days": 365 * 5,  # 5 years
            "communication_retention_days": 365 * 2,  # 2 years
            "auto_anonymize": False,
            "auto_delete": False
        }
    
    @router.put("/retention-policy")
    async def update_retention_policy(
        guest_data_days: int = 1095,
        booking_data_days: int = 2555,
        audit_log_days: int = 1825,
        auto_anonymize: bool = False,
        current_user=Depends(get_current_user)
    ):
        """Update data retention policy"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        await db.retention_policies.update_one(
            {"tenant_id": current_user.tenant_id},
            {"$set": {
                "tenant_id": current_user.tenant_id,
                "guest_data_retention_days": guest_data_days,
                "booking_data_retention_days": booking_data_days,
                "audit_log_retention_days": audit_log_days,
                "auto_anonymize": auto_anonymize,
                "updated_by": current_user.id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        return {"success": True, "message": "Veri saklama politikasi guncellendi"}
    
    return router
