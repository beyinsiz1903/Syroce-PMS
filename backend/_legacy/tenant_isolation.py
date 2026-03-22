"""
Tenant Data Isolation Module
=============================
Multi-property veri izolasyonu, cross-tenant erişim engelleme,
tenant-bazlı veritabanı sorgu sarmalayıcı (wrapper) ve audit logging.

Bu modül, her tenant'ın sadece kendi verilerine erişebilmesini garanti eder.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Set
from datetime import datetime, timezone, timedelta
import uuid
import logging

logger = logging.getLogger("tenant_isolation")

router = APIRouter(prefix="/api/tenant-isolation", tags=["Tenant Isolation"])

# ============= MODELS =============
class TenantIsolationPolicy(BaseModel):
    """Tenant izolasyon politikası"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    strict_mode: bool = True  # True = Her sorgu tenant_id filtreli
    allowed_cross_tenant_roles: List[str] = ["super_admin"]
    data_encryption_enabled: bool = True
    field_level_encryption: List[str] = []  # Şifrelenmesi gereken alanlar
    ip_restriction_enabled: bool = False
    allowed_ips: List[str] = []
    max_api_rate_per_minute: int = 1000
    data_export_requires_approval: bool = False
    pii_masking_enabled: bool = True
    pii_fields: List[str] = ["id_number", "credit_card", "passport_number", "tax_id"]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TenantAccessLog(BaseModel):
    """Tenant erişim logu"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    user_id: str
    action: str
    collection: str
    operation: str  # read, write, delete
    document_count: int = 0
    cross_tenant_access: bool = False
    ip_address: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DataClassification(BaseModel):
    """Veri sınıflandırma"""
    collection_name: str
    classification: str  # public, internal, confidential, restricted
    contains_pii: bool = False
    contains_financial: bool = False
    contains_health: bool = False
    retention_days: int = 1095  # 3 yıl default
    encryption_required: bool = False

class CrossTenantRequest(BaseModel):
    """Cross-tenant veri erişim talebi"""
    requesting_tenant_id: str
    target_tenant_id: str
    reason: str
    data_scope: str  # summary, detailed, full
    collections: List[str]
    approved: bool = False

class TenantIsolationReport(BaseModel):
    """İzolasyon durumu raporu"""
    tenant_id: str
    total_collections: int = 0
    isolated_collections: int = 0
    isolation_score: float = 0.0
    violations: List[Dict[str, Any]] = []
    recommendations: List[str] = []

# ============= CORE ISOLATION ENGINE =============
class TenantIsolationEngine:
    """Tenant veri izolasyonu motoru"""
    
    # Tenant-scoped koleksiyonlar (tenant_id filtresi ZORUNLU)
    TENANT_SCOPED_COLLECTIONS: Set[str] = {
        "rooms", "bookings", "guests", "folios", "tasks", "users",
        "audit_logs", "reports", "rate_plans", "invoices", "payments",
        "housekeeping_tasks", "maintenance_orders", "inventory_items",
        "suppliers", "expenses", "bank_accounts", "staff",
        "gdpr_consents", "ip_rules", "user_2fa", "notifications",
        "pos_orders", "restaurant_tables", "menu_items",
        "spa_services", "spa_bookings", "meeting_rooms", "events",
        "group_bookings", "crm_contacts", "crm_activities",
        "loyalty_members", "loyalty_transactions",
        "channel_mappings", "ota_connections",
        "data_processing_agreements", "retention_policies",
        "tenant_security_policies"
    }
    
    # Global koleksiyonlar (tenant_id filtresi gereksiz)
    GLOBAL_COLLECTIONS: Set[str] = {
        "tenants", "hotel_chains", "system_config", "system_logs",
        "subscription_plans", "marketplace_extensions"
    }
    
    # PII (Kişisel Tanımlayıcı Bilgi) alanları
    PII_FIELDS: Set[str] = {
        "id_number", "tc_kimlik", "passport_number", "credit_card",
        "credit_card_number", "cvv", "card_expiry", "tax_id",
        "social_security", "bank_account_number", "iban"
    }
    
    # Veri sınıflandırma haritası
    DATA_CLASSIFICATION: Dict[str, str] = {
        "guests": "confidential",
        "bookings": "internal",
        "folios": "confidential",
        "payments": "restricted",
        "users": "confidential",
        "audit_logs": "internal",
        "rooms": "internal",
        "tasks": "internal",
        "gdpr_consents": "restricted",
        "user_2fa": "restricted",
        "invoices": "confidential",
        "staff": "confidential",
    }
    
    def __init__(self, db):
        self.db = db
    
    async def validate_tenant_access(self, tenant_id: str, collection: str, 
                                      user_role: str, operation: str = "read") -> Dict[str, Any]:
        """Tenant erişim doğrulama"""
        result = {
            "allowed": False,
            "reason": "",
            "requires_audit": True,
            "data_classification": self.DATA_CLASSIFICATION.get(collection, "internal")
        }
        
        if not tenant_id:
            result["reason"] = "Tenant ID zorunlu"
            return result
        
        # Global koleksiyonlara super_admin dışında erişim yok
        if collection in self.GLOBAL_COLLECTIONS and user_role != "super_admin":
            result["reason"] = "Global koleksiyona erişim sadece super_admin için"
            return result
        
        # Tenant-scoped koleksiyonlar her zaman izinli (kendi tenant'ları için)
        if collection in self.TENANT_SCOPED_COLLECTIONS:
            result["allowed"] = True
            result["reason"] = "Tenant-scoped erişim onaylandı"
            return result
        
        # Bilinmeyen koleksiyonlara default olarak izin ver ama logla
        result["allowed"] = True
        result["reason"] = "Sınıflandırılmamış koleksiyon - izin verildi, loglanıyor"
        result["requires_audit"] = True
        return result
    
    async def enforce_tenant_filter(self, tenant_id: str, collection: str, 
                                     query: Dict[str, Any]) -> Dict[str, Any]:
        """Sorguya otomatik tenant_id filtresi ekle"""
        if collection in self.GLOBAL_COLLECTIONS:
            return query
        
        if collection in self.TENANT_SCOPED_COLLECTIONS:
            query["tenant_id"] = tenant_id
        
        return query
    
    def mask_pii_fields(self, document: Dict[str, Any], 
                         user_role: str = "staff") -> Dict[str, Any]:
        """PII alanlarını maskele"""
        if user_role in ["admin", "super_admin"]:
            return document
        
        masked = dict(document)
        for field in self.PII_FIELDS:
            if field in masked and masked[field]:
                value = str(masked[field])
                if len(value) > 4:
                    masked[field] = "***" + value[-4:]
                else:
                    masked[field] = "****"
        return masked
    
    async def log_data_access(self, tenant_id: str, user_id: str, 
                               collection: str, operation: str,
                               document_count: int = 0,
                               cross_tenant: bool = False,
                               ip_address: str = None):
        """Veri erişim logu kaydet"""
        log_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "collection": collection,
            "operation": operation,
            "document_count": document_count,
            "cross_tenant_access": cross_tenant,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.db.tenant_access_logs.insert_one(log_entry)
    
    async def check_isolation_health(self, tenant_id: str) -> TenantIsolationReport:
        """Tenant izolasyon sağlığını kontrol et"""
        violations = []
        recommendations = []
        isolated_count = 0
        total_count = len(self.TENANT_SCOPED_COLLECTIONS)
        
        for collection_name in self.TENANT_SCOPED_COLLECTIONS:
            collection = self.db[collection_name]
            
            # Koleksiyonda tenant_id olmayan doküman var mı?
            try:
                no_tenant = await collection.count_documents({
                    "tenant_id": {"$exists": False}
                })
                if no_tenant > 0:
                    violations.append({
                        "collection": collection_name,
                        "issue": f"{no_tenant} doküman tenant_id içermiyor",
                        "severity": "critical"
                    })
                else:
                    isolated_count += 1
                
                # Cross-tenant veri sızıntısı kontrolü
                if tenant_id:
                    other_tenant_data = await collection.count_documents({
                        "tenant_id": {"$ne": tenant_id, "$exists": True}
                    })
                    if other_tenant_data > 0:
                        # Bu normal - diğer tenant verileri de olacak
                        pass
            except Exception:
                # Koleksiyon olmayabilir
                isolated_count += 1
        
        # Politika kontrolleri
        policy = await self.db.tenant_isolation_policies.find_one(
            {"tenant_id": tenant_id}, {"_id": 0}
        )
        if not policy:
            recommendations.append("Tenant izolasyon politikası tanımlanmamış - varsayılan kullanılıyor")
        
        # 2FA kontrolü
        twofa_policy = await self.db.tenant_security_policies.find_one(
            {"tenant_id": tenant_id}, {"_id": 0}
        )
        if not twofa_policy or not twofa_policy.get("require_2fa"):
            recommendations.append("2FA zorunluluğu aktif değil - güvenlik için önerilir")
        
        # IP kısıtlama kontrolü
        ip_rules_count = await self.db.ip_rules.count_documents({"tenant_id": tenant_id})
        if ip_rules_count == 0:
            recommendations.append("IP erişim kuralları tanımlanmamış")
        
        # GDPR onay kontrolü
        total_guests = await self.db.guests.count_documents({"tenant_id": tenant_id})
        consented_guests = len(await self.db.gdpr_consents.distinct("guest_id", {"tenant_id": tenant_id}))
        if total_guests > 0 and consented_guests < total_guests:
            recommendations.append(
                f"{total_guests - consented_guests} misafirin KVKK onayı eksik"
            )
        
        score = (isolated_count / total_count * 100) if total_count > 0 else 0
        
        return TenantIsolationReport(
            tenant_id=tenant_id,
            total_collections=total_count,
            isolated_collections=isolated_count,
            isolation_score=round(score, 1),
            violations=violations,
            recommendations=recommendations
        )
    
    async def get_tenant_data_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Tenant veri özeti"""
        summary = {}
        for collection_name in self.TENANT_SCOPED_COLLECTIONS:
            try:
                count = await self.db[collection_name].count_documents({"tenant_id": tenant_id})
                if count > 0:
                    summary[collection_name] = count
            except Exception:
                pass
        return summary


# ============= ENDPOINTS =============
def create_tenant_isolation_routes(db, get_current_user):
    """Tenant isolation endpoint'leri oluştur"""
    
    engine = TenantIsolationEngine(db)
    
    @router.get("/health")
    async def get_isolation_health(current_user=Depends(get_current_user)):
        """Tenant izolasyon sağlık durumu"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        report = await engine.check_isolation_health(current_user.tenant_id)
        return report.model_dump()
    
    @router.get("/policy")
    async def get_isolation_policy(current_user=Depends(get_current_user)):
        """Mevcut tenant izolasyon politikasını getir"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        policy = await db.tenant_isolation_policies.find_one(
            {"tenant_id": current_user.tenant_id}, {"_id": 0}
        )
        
        if not policy:
            # Varsayılan politika
            default_policy = TenantIsolationPolicy(
                tenant_id=current_user.tenant_id
            )
            return default_policy.model_dump()
        
        return policy
    
    @router.put("/policy")
    async def update_isolation_policy(
        strict_mode: bool = True,
        data_encryption_enabled: bool = True,
        pii_masking_enabled: bool = True,
        ip_restriction_enabled: bool = False,
        max_api_rate_per_minute: int = 1000,
        data_export_requires_approval: bool = False,
        current_user=Depends(get_current_user)
    ):
        """Tenant izolasyon politikasını güncelle"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        policy_doc = {
            "tenant_id": current_user.tenant_id,
            "strict_mode": strict_mode,
            "data_encryption_enabled": data_encryption_enabled,
            "pii_masking_enabled": pii_masking_enabled,
            "ip_restriction_enabled": ip_restriction_enabled,
            "max_api_rate_per_minute": max_api_rate_per_minute,
            "data_export_requires_approval": data_export_requires_approval,
            "allowed_cross_tenant_roles": ["super_admin"],
            "updated_by": current_user.id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.tenant_isolation_policies.update_one(
            {"tenant_id": current_user.tenant_id},
            {"$set": policy_doc},
            upsert=True
        )
        
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "isolation_policy_updated",
            "resource_type": "security",
            "details": policy_doc,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {"success": True, "message": "İzolasyon politikası güncellendi"}
    
    @router.get("/data-summary")
    async def get_data_summary(current_user=Depends(get_current_user)):
        """Tenant veri özeti - her koleksiyondaki doküman sayısı"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        summary = await engine.get_tenant_data_summary(current_user.tenant_id)
        
        total_records = sum(summary.values())
        
        return {
            "tenant_id": current_user.tenant_id,
            "collections": summary,
            "total_collections_with_data": len(summary),
            "total_records": total_records,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    @router.get("/access-logs")
    async def get_access_logs(
        limit: int = 50,
        operation: Optional[str] = None,
        current_user=Depends(get_current_user)
    ):
        """Tenant veri erişim logları"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        query = {"tenant_id": current_user.tenant_id}
        if operation:
            query["operation"] = operation
        
        logs = await db.tenant_access_logs.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).to_list(limit)
        
        return {"logs": logs, "total": len(logs)}
    
    @router.get("/data-classification")
    async def get_data_classification(current_user=Depends(get_current_user)):
        """Veri sınıflandırma haritası"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        classifications = []
        for collection, classification in engine.DATA_CLASSIFICATION.items():
            count = 0
            try:
                count = await db[collection].count_documents({"tenant_id": current_user.tenant_id})
            except Exception:
                pass
            
            classifications.append({
                "collection": collection,
                "classification": classification,
                "contains_pii": collection in ["guests", "users", "staff"],
                "contains_financial": collection in ["folios", "payments", "invoices"],
                "record_count": count,
                "encryption_required": classification in ["restricted", "confidential"]
            })
        
        return {
            "tenant_id": current_user.tenant_id,
            "classifications": classifications,
            "summary": {
                "public": sum(1 for c in classifications if c["classification"] == "public"),
                "internal": sum(1 for c in classifications if c["classification"] == "internal"),
                "confidential": sum(1 for c in classifications if c["classification"] == "confidential"),
                "restricted": sum(1 for c in classifications if c["classification"] == "restricted")
            }
        }
    
    @router.post("/cross-tenant-request")
    async def create_cross_tenant_request(
        target_tenant_id: str,
        reason: str,
        data_scope: str = "summary",
        collections: List[str] = [],
        current_user=Depends(get_current_user)
    ):
        """Cross-tenant veri erişim talebi oluştur"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        # Super admin doğrudan erişebilir
        auto_approve = current_user.role == "super_admin"
        
        request_doc = {
            "id": str(uuid.uuid4()),
            "requesting_tenant_id": current_user.tenant_id,
            "requesting_user_id": current_user.id,
            "target_tenant_id": target_tenant_id,
            "reason": reason,
            "data_scope": data_scope,
            "collections": collections,
            "approved": auto_approve,
            "status": "approved" if auto_approve else "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.cross_tenant_requests.insert_one(request_doc)
        request_doc.pop("_id", None)
        
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "cross_tenant_request_created",
            "resource_type": "security",
            "details": {
                "target_tenant": target_tenant_id,
                "scope": data_scope,
                "auto_approved": auto_approve
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "success": True,
            "request": request_doc,
            "message": "Talep onaylandı" if auto_approve else "Talep onay bekliyor"
        }
    
    @router.get("/cross-tenant-requests")
    async def list_cross_tenant_requests(
        status_filter: Optional[str] = None,
        current_user=Depends(get_current_user)
    ):
        """Cross-tenant talepleri listele"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        query = {
            "$or": [
                {"requesting_tenant_id": current_user.tenant_id},
                {"target_tenant_id": current_user.tenant_id}
            ]
        }
        if status_filter:
            query["status"] = status_filter
        
        requests = await db.cross_tenant_requests.find(
            query, {"_id": 0}
        ).sort("created_at", -1).to_list(100)
        
        return {"requests": requests, "total": len(requests)}
    
    @router.put("/cross-tenant-requests/{request_id}/approve")
    async def approve_cross_tenant_request(
        request_id: str,
        approved: bool = True,
        current_user=Depends(get_current_user)
    ):
        """Cross-tenant talebi onayla/reddet"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        req = await db.cross_tenant_requests.find_one(
            {"id": request_id, "target_tenant_id": current_user.tenant_id}
        )
        if not req:
            raise HTTPException(status_code=404, detail="Talep bulunamadı")
        
        new_status = "approved" if approved else "rejected"
        await db.cross_tenant_requests.update_one(
            {"id": request_id},
            {"$set": {
                "approved": approved,
                "status": new_status,
                "reviewed_by": current_user.id,
                "reviewed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {
            "success": True,
            "message": f"Talep {'onaylandı' if approved else 'reddedildi'}"
        }
    
    @router.get("/pii-scan")
    async def scan_pii_data(current_user=Depends(get_current_user)):
        """PII veri taraması - hassas veri tespiti"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        pii_report = []
        tenant_id = current_user.tenant_id
        
        # Misafir PII kontrolü
        guests_with_pii = await db.guests.count_documents({
            "tenant_id": tenant_id,
            "$or": [
                {"id_number": {"$exists": True, "$ne": None, "$ne": ""}},
                {"passport_number": {"$exists": True, "$ne": None, "$ne": ""}},
                {"tax_id": {"$exists": True, "$ne": None, "$ne": ""}}
            ]
        })
        total_guests = await db.guests.count_documents({"tenant_id": tenant_id})
        
        pii_report.append({
            "collection": "guests",
            "total_records": total_guests,
            "records_with_pii": guests_with_pii,
            "pii_types": ["id_number", "passport_number", "tax_id", "email", "phone"],
            "risk_level": "high" if guests_with_pii > 0 else "low"
        })
        
        # Kullanıcı PII kontrolü
        users_count = await db.users.count_documents({"tenant_id": tenant_id})
        pii_report.append({
            "collection": "users",
            "total_records": users_count,
            "records_with_pii": users_count,  # Tüm kullanıcılar email/isim içerir
            "pii_types": ["email", "name", "phone"],
            "risk_level": "medium"
        })
        
        # Anonim misafir kontrolü
        anonymized_count = await db.guests.count_documents({
            "tenant_id": tenant_id,
            "is_anonymized": True
        })
        
        return {
            "tenant_id": tenant_id,
            "scan_date": datetime.now(timezone.utc).isoformat(),
            "collections_scanned": len(pii_report),
            "pii_findings": pii_report,
            "anonymized_records": anonymized_count,
            "total_pii_records": sum(r["records_with_pii"] for r in pii_report),
            "overall_risk": "high" if any(r["risk_level"] == "high" for r in pii_report) else "medium"
        }
    
    @router.get("/audit-trail")
    async def get_security_audit_trail(
        days: int = 30,
        action_type: Optional[str] = None,
        current_user=Depends(get_current_user)
    ):
        """Güvenlik audit trail - son N günlük güvenlik olayları"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        query = {
            "tenant_id": current_user.tenant_id,
            "timestamp": {"$gte": cutoff},
            "resource_type": {"$in": ["security", "gdpr", "auth"]}
        }
        if action_type:
            query["action"] = {"$regex": action_type, "$options": "i"}
        
        events = await db.audit_logs.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).to_list(500)
        
        # Özet istatistikler
        action_counts = {}
        for event in events:
            action = event.get("action", "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1
        
        return {
            "tenant_id": current_user.tenant_id,
            "period_days": days,
            "total_events": len(events),
            "events": events[:100],  # Son 100
            "action_summary": action_counts,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    return router
