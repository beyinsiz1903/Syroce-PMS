"""IP-Based Access Control Module - Whitelist/Blacklist IP Management"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid
import ipaddress
import re

router = APIRouter(prefix="/api/security/ip", tags=["IP Access Control"])

# ============= MODELS =============
class IPRule(BaseModel):
    ip_address: str  # Can be single IP, CIDR range, or wildcard
    rule_type: str = "whitelist"  # whitelist or blacklist
    description: Optional[str] = None
    expires_at: Optional[str] = None

class IPRuleResponse(BaseModel):
    id: str
    tenant_id: str
    ip_address: str
    rule_type: str
    description: Optional[str] = None
    created_by: str
    created_at: str
    expires_at: Optional[str] = None
    is_active: bool = True
    hit_count: int = 0

# ============= HELPER FUNCTIONS =============
def is_valid_ip_or_cidr(ip_str: str) -> bool:
    """Validate IP address or CIDR notation"""
    try:
        if '/' in ip_str:
            ipaddress.ip_network(ip_str, strict=False)
        else:
            ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        # Check for wildcard patterns like 192.168.*.*
        pattern = r'^(\d{1,3}|\*)(\.(\d{1,3}|\*)){3}$'
        return bool(re.match(pattern, ip_str))

def ip_matches_rule(client_ip: str, rule_ip: str) -> bool:
    """Check if client IP matches a rule"""
    try:
        if '/' in rule_ip:
            network = ipaddress.ip_network(rule_ip, strict=False)
            return ipaddress.ip_address(client_ip) in network
        elif '*' in rule_ip:
            parts = rule_ip.split('.')
            client_parts = client_ip.split('.')
            if len(parts) != 4 or len(client_parts) != 4:
                return False
            return all(p == '*' or p == c for p, c in zip(parts, client_parts))
        else:
            return client_ip == rule_ip
    except (ValueError, TypeError):
        return False

# ============= ENDPOINTS =============
def create_ip_access_routes(db, get_current_user):
    """Create IP access control routes"""
    
    @router.get("/rules")
    async def list_ip_rules(current_user=Depends(get_current_user)):
        """List all IP rules for tenant"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        rules = await db.ip_rules.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).sort("created_at", -1).to_list(500)
        
        return {
            "rules": rules,
            "total": len(rules),
            "whitelist_count": sum(1 for r in rules if r.get("rule_type") == "whitelist"),
            "blacklist_count": sum(1 for r in rules if r.get("rule_type") == "blacklist")
        }
    
    @router.post("/rules")
    async def create_ip_rule(
        rule: IPRule,
        current_user=Depends(get_current_user)
    ):
        """Create new IP rule"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        if not is_valid_ip_or_cidr(rule.ip_address):
            raise HTTPException(status_code=400, detail="Gecersiz IP adresi veya CIDR")
        
        if rule.rule_type not in ["whitelist", "blacklist"]:
            raise HTTPException(status_code=400, detail="Kural tipi whitelist veya blacklist olmali")
        
        # Check for duplicate
        existing = await db.ip_rules.find_one({
            "tenant_id": current_user.tenant_id,
            "ip_address": rule.ip_address,
            "rule_type": rule.rule_type
        })
        if existing:
            raise HTTPException(status_code=409, detail="Bu IP kurali zaten mevcut")
        
        rule_doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "ip_address": rule.ip_address,
            "rule_type": rule.rule_type,
            "description": rule.description,
            "expires_at": rule.expires_at,
            "created_by": current_user.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True,
            "hit_count": 0
        }
        
        await db.ip_rules.insert_one(rule_doc)
        rule_doc.pop("_id", None)
        
        # Audit log
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": f"ip_rule_created_{rule.rule_type}",
            "resource_type": "security",
            "details": {"ip": rule.ip_address, "type": rule.rule_type},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {"success": True, "rule": rule_doc}
    
    @router.delete("/rules/{rule_id}")
    async def delete_ip_rule(rule_id: str, current_user=Depends(get_current_user)):
        """Delete IP rule"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        result = await db.ip_rules.delete_one({
            "id": rule_id,
            "tenant_id": current_user.tenant_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Kural bulunamadi")
        
        return {"success": True, "message": "IP kurali silindi"}
    
    @router.put("/rules/{rule_id}/toggle")
    async def toggle_ip_rule(rule_id: str, current_user=Depends(get_current_user)):
        """Toggle IP rule active/inactive"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        rule = await db.ip_rules.find_one({
            "id": rule_id,
            "tenant_id": current_user.tenant_id
        })
        
        if not rule:
            raise HTTPException(status_code=404, detail="Kural bulunamadi")
        
        new_status = not rule.get("is_active", True)
        await db.ip_rules.update_one(
            {"id": rule_id},
            {"$set": {"is_active": new_status}}
        )
        
        return {"success": True, "is_active": new_status}
    
    @router.post("/check")
    async def check_ip(
        request: Request,
        current_user=Depends(get_current_user)
    ):
        """Check if current IP is allowed"""
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        
        # Get active rules
        rules = await db.ip_rules.find({
            "tenant_id": current_user.tenant_id,
            "is_active": True
        }).to_list(1000)
        
        blacklisted = False
        whitelisted = False
        has_whitelist = any(r["rule_type"] == "whitelist" for r in rules)
        
        for rule in rules:
            if ip_matches_rule(client_ip, rule["ip_address"]):
                if rule["rule_type"] == "blacklist":
                    blacklisted = True
                elif rule["rule_type"] == "whitelist":
                    whitelisted = True
                # Increment hit count
                await db.ip_rules.update_one(
                    {"id": rule["id"]},
                    {"$inc": {"hit_count": 1}}
                )
        
        allowed = True
        reason = "Erisim izni verildi"
        
        if blacklisted:
            allowed = False
            reason = "IP adresi kara listede"
        elif has_whitelist and not whitelisted:
            allowed = False
            reason = "IP adresi beyaz listede degil"
        
        return {
            "client_ip": client_ip,
            "allowed": allowed,
            "reason": reason,
            "blacklisted": blacklisted,
            "whitelisted": whitelisted
        }
    
    @router.get("/access-log")
    async def get_access_log(
        limit: int = 50,
        current_user=Depends(get_current_user)
    ):
        """Get IP access log"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        logs = await db.ip_access_log.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0}
        ).sort("timestamp", -1).to_list(limit)
        
        return {"logs": logs, "total": len(logs)}
    
    return router
