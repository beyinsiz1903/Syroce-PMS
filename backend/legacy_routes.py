"""
Legacy Routes — Compatibility Layer

Phase B: Domain Module Separation COMPLETE
==========================================
All 404 endpoint definitions have been extracted into domain-specific routers
under backend/domains/. This file now contains only:

1. Shared inline Pydantic model definitions (used by domain routers and server.py)
2. The api_router instance (empty, kept for backward compatibility)
3. Helper function imports re-exported for server.py

Migration Status:
- 0 endpoints remain (all moved to backend/domains/)
- 18 domain routers created
- 408 routes registered

Next Phase: Move remaining inline models to models/ package
"""
from fastapi import APIRouter, HTTPException, Depends, status, File, UploadFile, Form, Request, Header, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import ORJSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator, conint
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timezone, timedelta, date
from enum import Enum
from pathlib import Path
import os
import uuid
import logging
import io
import base64
import secrets
import hashlib
import random
import sys

sys.path.append(os.path.dirname(__file__))

# ── Core infrastructure (single source of truth) ────────────────────
from core.database import db, client
from core.security import (
    get_current_user, create_token, hash_password, verify_password,
    _is_super_admin, security, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS,
    pwd_context, generate_qr_code, generate_time_based_qr_token,
)
from core.helpers import (
    FEATURES_BY_PLAN, resolve_tenant_features, load_tenant_doc,
    create_audit_log, MODULE_DEFAULTS, get_tenant_modules,
    require_feature, require_super_admin_guard as require_super_admin,
    require_module, require_admin,
)

# ── Models ──────────────────────────────────────────────────────────
from models.enums import (
    UserRole, Permission, RoomStatus, BookingStatus, PaymentStatus,
    PaymentMethod, ChargeType, InvoiceStatus, LoyaltyTier, ChannelType,
    ChannelStatus, MappingStatus, PricingStrategy, ContractedRateType,
    RateType, MarketSegment, CancellationPolicyType, CompanyStatus,
    OTAChannel, OTAPaymentModel, ParityStatus, ChannelHealth,
    FolioType, FolioStatus, ChargeCategory, FolioOperationType,
    PaymentType, DepartmentType, RiskLevel, MaintenanceTaskStatus,
    MaintenancePriority, WarehouseLocation, MaintenanceType, OrderStatus,
    OutletType, MeasurementUnit, GuestRequestType, GuestRequestStatus,
    CheckInStatus, InspectionStatus, LostFoundStatus, RoomServiceStatus,
    ROLE_PERMISSIONS,
)
from models.schemas import (
    Tenant, User, TenantRegister, GuestRegister, UserLogin, TokenResponse,
    NotificationPreferences, RoomCreate, Room, HousekeepingTask,
    MaintenanceWorkOrder, SensorAlert, MaintenanceAsset,
    PreventiveMaintenancePlan, CompanyCreate, Company, BankAccount,
    CreditLimit, Expense, CashFlow, CityLedgerTransaction,
    SLAConfiguration, SparePart, SparePartUsage, TaskPhoto,
    AssetMaintenanceHistory, PlannedMaintenance, MaintenanceTaskExtended,
    Outlet, Ingredient, RecipeIngredient, Recipe, POSOrder,
    StockConsumption, GuestRequest, IDScanResult, MobileCheckIn,
    InspectionChecklistItem, RoomInspection, LostFoundItem,
    HKTaskAssignment, CleaningTimer, RateOverride, RevenueForecast,
    DemandData, GuestCreate, Guest, BookingCreate, Booking,
    BookingExtended, FolioCreate, Folio, ChargeCreate, FolioCharge,
    PaymentCreate, Payment, FolioOperationCreate, RatePlan, Package,
    FolioOperation, CityTaxRule, AuditLog, RateOverrideLog,
    RoomMoveHistory, ChannelConnection, ChannelConnectionCreate,
    RoomMapping, RoomMappingCreate, RateUpdate, OTAReservation,
    ExceptionQueue, RMSSuggestion, RoomServiceCreate, RoomService,
    InvoiceItem, InvoiceCreate, Invoice, LoyaltyProgramCreate,
    LoyaltyProgram, LoyaltyTransactionCreate, LoyaltyTransaction,
    Product, OrderCreate, Order, PriceAnalysis, SendWhatsAppRequest,
    SendEmailRequest, SendSMSRequest, CreateMessageTemplateRequest,
    AddCompetitorRequest, ScrapePricesRequest, AutoPricingRequest,
    DemandForecastRequest, ReportIssueRequest, UploadPhotoRequest,
    CreatePOSTransactionRequest, CreateGroupReservationRequest,
    AssignGroupRoomsRequest, CreateBlockReservationRequest,
    UseBlockRoomRequest, CreatePropertyRequest, TransferReservationRequest,
    CreateMarketplaceProductRequest, AdjustInventoryRequest,
    CreatePurchaseOrderRequest, ReceivePurchaseOrderRequest,
    CreateDeliveryRequest, CreateSupplierRequest,
    UpdateSupplierCreditRequest, ApprovePurchaseOrderRequest,
    RejectPurchaseOrderRequest, UpdateDeliveryStatusRequest,
    CreateWarehouseRequest, CreateCurrencyRateRequest,
    CreateMultiCurrencyInvoiceRequest, GenerateInvoiceFromFolioRequest,
    ConvertCurrencyRequest, CreateRateCodeRequest,
    GetCalendarTooltipRequest, CreateOutletRequest,
    CreateMenuItemRequest, CreatePOSTransactionWithMenuRequest,
    GenerateZReportRequest, CreateSurveyRequest,
    SubmitSurveyResponseRequest, ExternalReviewWebhookRequest,
    CreateDepartmentFeedbackRequest, CreateTaskRequest,
    UpdateTaskStatusRequest, AssignTaskRequest, CreateRoleRequest,
    AssignRoleRequest, UpdateUserRoleRequest, CreateBackupRequest,
    _ensure_hotel_context,
)

# ── Third-party ─────────────────────────────────────────────────────
import bcrypt
import jwt
import qrcode
from passlib.context import CryptContext
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# ── Optional imports ────────────────────────────────────────────────
try:
    from cache_manager import cached, cache, DashboardCache, RoomCache, BookingCache
    print("✅ Cache manager imported (legacy_routes)")
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator

try:
    from accounting_models import (
        AccountingInvoice, AccountingInvoiceItem, AdditionalTax,
        Supplier as AccSupplier, InventoryItem, StockMovement,
        AccountType as AccAccountType, TransactionType as AccTransactionType,
        ExpenseCategory as AccExpenseCategory, IncomeCategory as AccIncomeCategory,
        InvoiceType, VATRate, AdditionalTaxType, WithholdingRate
    )
except ImportError as e:
    print(f"⚠️ Accounting models not available in legacy_routes: {e}")

try:
    from room_block_models import RoomBlock, RoomBlockCreate, RoomBlockUpdate, BlockType, BlockStatus
except ImportError:
    class BlockType:
        OUT_OF_ORDER = "out_of_order"
        OUT_OF_SERVICE = "out_of_service"
        MAINTENANCE = "maintenance"
    class BlockStatus:
        ACTIVE = "active"
        CANCELLED = "cancelled"
        EXPIRED = "expired"

try:
    from crm_models import (
        GuestProfile, GuestPreferences, GuestBehavior,
        UpsellOffer as CRMUpsellOffer, MessageTemplate, Message,
        LoyaltyStatus, UpsellType, MessageChannel, MessageStatus
    )
except Exception:
    pass

try:
    from night_audit_module import (
        NightAuditRecord, AuditStatus, AutomaticPosting,
        CityLedgerAccount, CityLedgerTransaction as NACityLedgerTransaction,
        SplitPayment, QueueRoom, AuditTrailEntry
    )
except ImportError:
    pass

try:
    from websocket_server import broadcast_kitchen_orders
except ImportError:
    async def broadcast_kitchen_orders(*a, **kw): pass

# ── APM store (for system monitoring endpoints) ─────────────────────
try:
    from apm_middleware import APMMiddleware, EnhancedRateLimitMiddleware, apm_store, get_rate_limit_stats
except Exception:
    from collections import deque
    class _FallbackStore:
        requests = deque(maxlen=100)
        rate_limit_hits = 0
        started_at = datetime.now(timezone.utc)
        def get_summary(self, minutes=10): return {"total_requests": 0, "error_rate_percent": 0}
        def get_recent_errors(self, limit=50): return []
        def record_request(self, **kw): pass
        def record_rate_limit_hit(self, p): pass
    apm_store = _FallbackStore()
    def get_rate_limit_stats(): return {}

# ── Constants ───────────────────────────────────────────────────────
DEFAULT_PUSH_CHANNELS = [
    "general", "arrivals", "housekeeping", "maintenance", "finance", "executive"
]

CM_PARTNER_WEBHOOK_URL = os.environ.get(
    "CM_PARTNER_WEBHOOK_URL", "https://agency.syroce.com/webhooks/cm"
)

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/app/backend/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── RBAC tier matrix ────────────────────────────────────────────────
TIER_ROLE_MATRIX = {
    "basic": {UserRole.ADMIN, UserRole.FRONT_DESK, UserRole.HOUSEKEEPING},
    "professional": {UserRole.ADMIN, UserRole.FRONT_DESK, UserRole.HOUSEKEEPING, UserRole.FINANCE, UserRole.SALES},
    "enterprise": set(UserRole),
}

def has_permission(user_role, permission) -> bool:
    return permission.value in ROLE_PERMISSIONS.get(user_role, set())

def is_role_allowed_for_tier(role: str, tier: str) -> bool:
    try:
        r = UserRole(role)
    except ValueError:
        return False
    allowed = TIER_ROLE_MATRIX.get(tier, TIER_ROLE_MATRIX.get("enterprise", set()))
    return r in allowed

# ── API Router ──────────────────────────────────────────────────────
api_router = APIRouter(prefix="/api")

# ============= CHANNEL MANAGER — MOVED to domains/channel_manager/router.py =============
# Backward compat: cm_push_event is imported by server.py
from domains.channel_manager.router import cm_push_event  # noqa: F401
from domains.channel_manager.router import get_cm_actor  # noqa: F401
from domains.channel_manager.router import require_cm_api_key  # noqa: F401


def has_permission(user_role: UserRole, permission: Permission) -> bool:
    """Check if a role has a specific permission"""
    return permission.value in ROLE_PERMISSIONS.get(user_role, [])


# ─── Tier-based RBAC: which roles are allowed per subscription tier ───
ROLES_BY_TIER: Dict[str, List[str]] = {
    "basic": ["admin"],
    "professional": ["admin", "supervisor", "front_desk", "housekeeping", "finance"],
    "enterprise": [
        "admin", "supervisor", "front_desk", "housekeeping",
        "finance", "sales", "revenue", "maintenance", "fnb",
        "spa", "concierge", "night_auditor", "staff"
    ],
}


def is_role_allowed_for_tier(role: str, tier: str) -> bool:
    """Check if a role is allowed for the given subscription tier"""
    tier_lower = (tier or "basic").lower()
    if tier_lower == "pro":
        tier_lower = "professional"
    if tier_lower == "ultra":
        tier_lower = "enterprise"
    allowed = ROLES_BY_TIER.get(tier_lower, ROLES_BY_TIER["basic"])
    return role in allowed

async def create_audit_log(
    tenant_id: str,
    user,  # User model instance
    action: str,
    entity_type: str,
    entity_id: str,
    changes: Optional[dict] = None,
    ip_address: Optional[str] = None
):
    """Create an audit log entry"""
    audit = AuditLog(
        tenant_id=tenant_id,
        user_id=user.id,
        user_name=user.name,
        user_role=user.role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        ip_address=ip_address
    )
    
    audit_dict = audit.model_dump()
    audit_dict['timestamp'] = audit_dict['timestamp'].isoformat()
    await db.audit_logs.insert_one(audit_dict)


# ================== PLAN & FEATURES ==================

FEATURES_BY_PLAN: Dict[str, Dict[str, bool]] = {
    "core_small_hotel": {
        # CORE
        "core_dashboard": True,
        "core_pms": True,
        "core_rooms": True,
        "core_rates_availability": True,
        "core_bookings_frontdesk": True,
        "core_calendar": True,
        "core_guests_basic": True,
        "core_housekeeping_basic": True,
        "core_channel_basic": True,
        "core_reports_basic": True,
        "core_users_roles": True,

        # HIDDEN (enterprise modüller)
        "hidden_invoices_accounting": False,
        "hidden_rms": False,
        "hidden_ai": False,
        "hidden_marketplace": False,
        "hidden_monitoring_admin": False,
        "hidden_multiproperty": False,
        "hidden_graphql": False,

        # FUTURE (şimdilik kapalı)
        "future_crm": False,
        "future_maintenance": False,
        "future_pos": False,
        "future_automation_rules": False,
        "future_guest_portal": False,
        "future_mobile_app": False,
    },
}

# PMS Lite: bungalov segmenti için sadece core ekranlar
FEATURES_BY_PLAN["pms_lite"] = {
    # Menü/route whitelist için net, küçük bir set:
    "dashboard": True,

    # PMS çekirdeği (Rooms/Bookings/Guests)
    "pms": True,
    "rooms": True,
    "bookings": True,
    "guests": True,

    # Takvim
    "reservation_calendar": True,

    # Lite raporlar (full reports değil)
    "reports_lite": True,

    # Lite settings (otel bilgisi + kullanıcılar gibi)
    "settings_lite": True,
}


def resolve_tenant_features(tenant_doc: Dict[str, Any]) -> Dict[str, bool]:
    """Plan + overrides ile efektif feature set üretir."""
    tenant_doc = tenant_doc or {}

    # Plan alanını normalize et: subscription_plan > plan > subscription_tier > core_small_hotel
    plan = (
        tenant_doc.get("subscription_plan")
        or tenant_doc.get("plan")
        or tenant_doc.get("subscription_tier")
        or "core_small_hotel"
    )

    # 1) Sistemde tanımlı bütün feature key’lerini topla
    all_keys: set[str] = set()
    for _plan, feats in FEATURES_BY_PLAN.items():
        for k in (feats or {}).keys():
            all_keys.add(k)

    # 2) Default: hepsi kapalı
    resolved: Dict[str, bool] = {k: False for k in all_keys}

    # 3) Plan bazlı açık olanları uygula
    plan_feats = FEATURES_BY_PLAN.get(plan) or FEATURES_BY_PLAN.get("core_small_hotel") or {}
    for k, v in plan_feats.items():
        resolved[k] = bool(v)

    # 4) Tenant bazlı override (varsa) — ancak PMS Lite için whitelist dışına çıkılmasına izin verme
    tenant_overrides = tenant_doc.get("features") or {}
    if isinstance(tenant_overrides, dict):
        if plan == "pms_lite":
            # Sadece planın kendisinde tanımlı anahtarlar override edilebilir
            for k in plan_feats.keys():
                if k in tenant_overrides:
                    resolved[k] = bool(tenant_overrides[k])
        else:
            # Diğer planlarda esnek override davranışını koru
            for k in resolved.keys():
                if k in tenant_overrides:
                    resolved[k] = bool(tenant_overrides[k])

    # 5) Plan bilgisi zaten tenant.plan alanında mevcut, features'a eklemeye gerek yok
    # resolved["plan"] = plan  # REMOVED: This was causing Pydantic validation error

    return resolved


RejectReasonCode = Literal[
    "NO_AVAILABILITY",
    "PRICE_MISMATCH",
    "OVERBOOK",
    "POLICY",
    "OTHER",
]


class RejectRequest(BaseModel):
    reason_code: RejectReasonCode
    reason_note: Optional[str] = Field(default=None, max_length=500)
async def _collect_push_devices(
    tenant_id: str,
    user_ids: Optional[List[str]] = None,
    departments: Optional[List[str]] = None
):
    query: Dict[str, Any] = {'tenant_id': tenant_id}
    if user_ids:
        query['user_id'] = {'$in': user_ids}
    if departments:
        query['departments'] = {'$in': departments}
    return await db.push_device_tokens.find(query, {'_id': 0}).to_list(1000)


async def _simulate_push_delivery(devices: List[dict], payload: dict) -> List[dict]:
    deliveries = []
    for device in devices:
        deliveries.append({
            'device_id': device.get('device_id'),
            'platform': device.get('platform', 'unknown'),
            'user_id': device.get('user_id'),
            'status': 'queued',
            'delivered_at': datetime.now(timezone.utc).isoformat()
        })
    if deliveries:
        print(f"📱 Mock push deliver: {len(deliveries)} devices → {payload.get('title')}")
    return deliveries


async def _record_push_log(tenant_id: str, payload: dict, deliveries: List[dict], created_by: str):
    log_entry = {
        'id': str(uuid.uuid4()),
        'tenant_id': tenant_id,
        'title': payload.get('title'),
        'body': payload.get('body'),
        'channels': payload.get('channels', ['in_app']),
        'target_user_ids': payload.get('user_ids'),
        'target_departments': payload.get('departments'),
        'delivery_count': len(deliveries),
        'deliveries': deliveries[:50],
        'created_by': created_by,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.push_delivery_logs.insert_one(log_entry)
    return log_entry
class LogoConnector:
    """Mock Logo/Netsis connector for ERP sync"""
    def __init__(self):
        self.base_url = os.environ.get('LOGO_API_URL', 'https://logo.example/api')
    
    async def send_invoice(self, invoice):
        await asyncio.sleep(0.1)
        return {
            'external_id': f"LOGO-{invoice['id'][:8]}",
            'status': 'synced',
            'message': 'Invoice pushed to Logo'
        }
    
    async def send_payment(self, payment):
        await asyncio.sleep(0.1)
        return {
            'external_id': f"LOGO-PAY-{payment['id'][:8]}",
            'status': 'synced',
            'message': 'Payment pushed to Logo'
        }


class NetsisConnector:
    """Mock Netsis connector"""
    def __init__(self):
        self.base_url = os.environ.get('NETSIS_API_URL', 'https://netsis.example/api')
    
    async def send_invoice(self, invoice):
        await asyncio.sleep(0.1)
        return {
            'external_id': f"NETSIS-{invoice['id'][:8]}",
            'status': 'synced',
            'message': 'Invoice pushed to Netsis'
        }


async def _gather_invoices(tenant_id: str, since: Optional[str] = None):
    query = {'tenant_id': tenant_id}
    if since:
        query['created_at'] = {'$gte': since}
    invoices = await db.finance_invoices.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)
    return invoices


async def _gather_payments(tenant_id: str, since: Optional[str] = None):
    query = {'tenant_id': tenant_id}
    if since:
        query['created_at'] = {'$gte': since}
    payments = await db.finance_payments.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)
    return payments


async def _log_accounting_sync(tenant_id: str, payload: dict):
    record = {
        'id': str(uuid.uuid4()),
        'tenant_id': tenant_id,
        **payload,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.accounting_sync_logs.insert_one(record)
    return record
async def generate_folio_number(tenant_id: str) -> str:
    """Generate unique folio number"""
    year = datetime.now(timezone.utc).year
    count = await db.folios.count_documents({'tenant_id': tenant_id}) + 1
    return f"F-{year}-{count:05d}"

async def calculate_folio_balance(folio_id: str, tenant_id: str) -> float:
    """Calculate folio balance (charges - payments) with proper 2-decimal rounding"""
    try:
        charges = await db.folio_charges.find({
            'folio_id': folio_id,
            'tenant_id': tenant_id,
            'voided': False
        }).to_list(1000)
        
        payments = await db.payments.find({
            'folio_id': folio_id,
            'tenant_id': tenant_id,
            'voided': False
        }).to_list(1000)
        
        total_charges = sum(float(c.get('total', 0)) for c in charges)
        total_payments = sum(float(p.get('amount', 0)) for p in payments)
        
        balance = total_charges - total_payments
        # Round to 2 decimal places for currency precision
        return round(balance, 2)
    except Exception as e:
        print(f"Error calculating folio balance: {str(e)}")
        return 0.0
class RatePlanFilter(BaseModel):
    channel: Optional[ChannelType] = None
    company_id: Optional[str] = None
    date: Optional[date] = None
class RatePlanCreate(BaseModel):
    name: str
    code: str
    type: RateType = RateType.BAR
    currency: str = "EUR"
    base_price: float
    room_type: str = "Standard"  # Default room type
    market_segment: Optional[MarketSegment] = None
    channel_restrictions: List[ChannelType] = []
    company_ids: List[str] = []
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    days_of_week: List[int] = []
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    cancellation_policy: Optional[CancellationPolicyType] = None
class PackageCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    included_services: List[str] = []
    price_type: str = "per_room"
    additional_amount: float = 0.0
    linked_rate_plan_ids: List[str] = []
async def create_rate_override(
    booking_id: str,
    new_rate: float,
    override_reason: str,
    current_user: User = Depends(get_current_user)
):
    """Create a rate override log for an existing booking."""
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    base_rate = booking.get('base_rate') or booking.get('total_amount')
    
    override_log = RateOverrideLog(
        tenant_id=current_user.tenant_id,
        booking_id=booking_id,
        user_id=current_user.id,
        user_name=current_user.name,
        base_rate=base_rate,
        new_rate=new_rate,
        override_reason=override_reason
    )
    
    override_dict = override_log.model_dump()
    override_dict['timestamp'] = override_dict['timestamp'].isoformat()
    await db.rate_override_logs.insert_one(override_dict)
    
    # Update booking with new rate
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'total_amount': new_rate}}
    )
    
    return {"message": "Rate override logged successfully", "log": override_log}
async def get_daily_flash_report_data(current_user: User):
    """
    Helper function to get flash report data (reusable for PDF and email)
    """
    today = datetime.now(timezone.utc).date()
    
    # Occupancy
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}).to_list(1000)
    total_rooms = len(rooms)
    occupied_rooms = len([r for r in rooms if r.get('current_status') == 'occupied'])
    occupancy_percentage = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
    
    # Revenue
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'date': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        },
        'voided': False
    }).to_list(10000)
    
    room_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'room')
    total_revenue = sum(c.get('total', 0) for c in charges)
    
    # Movements
    arrivals = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': today.isoformat(),
        'status': {'$in': ['confirmed', 'checked_in']}
    }).to_list(1000)
    
    departures = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_out': today.isoformat(),
        'status': {'$in': ['checked_in', 'checked_out']}
    }).to_list(1000)
    
    return {
        'occupancy': {
            'occupied': occupied_rooms,
            'total': total_rooms,
            'percentage': occupancy_percentage
        },
        'revenue': {
            'room_revenue': room_revenue,
            'total_revenue': total_revenue
        },
        'movements': {
            'arrivals': len(arrivals),
            'departures': len(departures)
        }
    }
class PermissionCheckRequest(BaseModel):
    permission: str
class ChannelMixRequest(BaseModel):
    start_date: str = Field(..., description="Inclusive period start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Inclusive period end date (YYYY-MM-DD)")
async def log_ai_activity(
    activity_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Log AI activity for tracking and analytics"""
    activity = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': current_user.id,
        'type': activity_data.get('type'),  # upsell_prediction, message_generation, demand_forecast
        'title': activity_data.get('title'),
        'description': activity_data.get('description'),
        'model': activity_data.get('model'),
        'status': activity_data.get('status', 'success'),
        'result': activity_data.get('result'),
        'execution_time': activity_data.get('execution_time'),  # in milliseconds
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metadata': activity_data.get('metadata', {})
    }
    
    await db.ai_activity_log.insert_one(activity)
    return {'message': 'Activity logged successfully', 'activity_id': activity['id']}

# Import and include AI endpoints (optional - fallback if dependencies missing)
try:
    from ai_endpoints import api_router as ai_ai_router
    api_router.include_router(ai_ai_router, tags=["AI Intelligence"])
    print("✅ AI endpoints loaded successfully")
except Exception as e:
    # Log but don't break main app; some AI features may be disabled
    print(f"⚠️ AI endpoints not loaded: {e}")
class PassportScanData(BaseModel):
    """Passport scan data from OCR"""
    passport_number: Optional[str] = None
    name: Optional[str] = None
    surname: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[str] = None
    expiry_date: Optional[str] = None
    sex: Optional[str] = None
    mrz_line1: Optional[str] = None
    mrz_line2: Optional[str] = None

class PassportScanRequest(BaseModel):
    """Request for passport scanning"""
    image_base64: str  # Base64 encoded image
    booking_id: Optional[str] = None

class WalkInBookingRequest(BaseModel):
    """Quick walk-in booking request"""
    guest_name: str
    guest_email: Optional[str] = None
    guest_phone: str
    guest_id_number: Optional[str] = None
    nationality: Optional[str] = None
    room_id: str
    nights: int = 1
    adults: int = 1
    children: int = 0
    rate_per_night: Optional[float] = None  # If not provided, use room base price
    special_requests: Optional[str] = None

class GuestAlert(BaseModel):
    """Guest alert model"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    alert_type: str  # vip, birthday, anniversary, special_request, complaint, preference
    priority: str = "normal"  # low, normal, high, urgent
    title: str
    description: str
    is_active: bool = True
    show_on_checkin: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
class LinenInventoryItem(BaseModel):
    """Linen inventory tracking"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_type: str  # sheet, pillowcase, towel, bathrobe, etc
    size: Optional[str] = None  # single, double, king, etc
    quantity_in_stock: int = 0
    quantity_in_use: int = 0
    quantity_in_laundry: int = 0
    quantity_damaged: int = 0
    reorder_level: int = 50
    unit_cost: float = 0.0
    last_restocked: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class GuestStayHistory(BaseModel):
    """Guest stay history entry"""
    booking_id: str
    check_in: str
    check_out: str
    room_number: str
    nights: int
    total_spent: float
    rating: Optional[float] = None

class GuestPreference(BaseModel):
    """Guest preferences"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    pillow_type: Optional[str] = None  # soft, firm, memory_foam
    room_temperature: Optional[int] = None  # Celsius
    smoking: bool = False
    floor_preference: Optional[str] = None  # high, low, middle
    room_view: Optional[str] = None  # sea, mountain, city
    newspaper: Optional[str] = None
    extra_requests: List[str] = []
    dietary_restrictions: List[str] = []
    allergies: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GuestTag(BaseModel):
    """Guest tags for categorization"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    tag: str  # VIP, Honeymoon, Complainer, Corporate, Long-Stay, Repeat, Birthday
    color: str = "blue"
    added_by: str
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
def calculate_profile_completion(guest, preferences, tags):
    """Calculate profile completion percentage"""
    total_fields = 15
    completed = 0
    
    if guest.get('phone'): completed += 1
    if guest.get('email'): completed += 1
    if guest.get('id_number'): completed += 1
    if guest.get('nationality'): completed += 1
    if guest.get('address'): completed += 1
    if guest.get('date_of_birth'): completed += 1
    
    if preferences:
        if preferences.get('pillow_type'): completed += 1
        if preferences.get('room_temperature'): completed += 1
        if preferences.get('floor_preference'): completed += 1
        if preferences.get('room_view'): completed += 1
        if preferences.get('newspaper'): completed += 1
        if preferences.get('extra_requests'): completed += 1
        if preferences.get('dietary_restrictions'): completed += 1
        if preferences.get('allergies'): completed += 1
    
    if tags: completed += 1
    
    return round((completed / total_fields) * 100, 1)
def get_cancellation_policy_details(policy: str):
    """Get cancellation policy details"""
    policies = {
        'same_day': {
            'description': 'Free cancellation until 18:00 on check-in day',
            'penalty_before_deadline': 0,
            'penalty_after_deadline': 100
        },
        'h24': {
            'description': 'Free cancellation until 24 hours before check-in',
            'penalty_before_deadline': 0,
            'penalty_after_deadline': 100
        },
        'h48': {
            'description': 'Free cancellation until 48 hours before check-in',
            'penalty_before_deadline': 0,
            'penalty_after_deadline': 100
        },
        'h72': {
            'description': 'Free cancellation until 72 hours before check-in',
            'penalty_before_deadline': 0,
            'penalty_after_deadline': 100
        },
        'd7': {
            'description': 'Free cancellation until 7 days before check-in',
            'penalty_before_deadline': 0,
            'penalty_after_deadline': 100
        },
        'd14': {
            'description': 'Free cancellation until 14 days before check-in',
            'penalty_before_deadline': 0,
            'penalty_after_deadline': 100
        },
        'non_refundable': {
            'description': 'Non-refundable booking',
            'penalty_before_deadline': 100,
            'penalty_after_deadline': 100
        },
        'flexible': {
            'description': 'Flexible cancellation (free until check-in)',
            'penalty_before_deadline': 0,
            'penalty_after_deadline': 50
        }
    }
    
    return policies.get(policy, policies['h24'])
class DynamicRestrictionsRequest(BaseModel):
    date: str
    room_type: str
    min_los: Optional[int] = None  # Minimum Length of Stay
    cta: bool = False  # Closed to Arrival
    ctd: bool = False  # Closed to Departure
    stop_sell: bool = False
class RedeemPointsRequest(BaseModel):
    points_to_redeem: int
    reward_type: str  # free_night, upgrade, fnb_credit, spa_credit
class MinimumStockAlertRequest(BaseModel):
    item_id: str
    min_stock_level: int
    alert_recipients: List[str] = []
class DemandForecast(BaseModel):
    """Demand forecast model"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: str
    room_type: Optional[str] = None
    forecasted_occupancy: float
    confidence: float
    factors: Dict[str, Any] = {}  # events, seasonality, historical
    model_version: str = "ml-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CompetitorRate(BaseModel):
    """Competitor rate scraping"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    competitor_name: str
    date: str
    room_type: str
    rate: float
    source: str  # google_hotels, booking_com, expedia
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class PermissionSet(BaseModel):
    """Enhanced permission set for RBAC 2.0"""
    view: bool = False
    create: bool = False
    edit: bool = False
    delete: bool = False
    export: bool = False
    approve: bool = False

class ResourcePermissions(BaseModel):
    """Permissions for a specific resource"""
    resource: str
    permissions: PermissionSet

# Enhanced role definitions
RBAC_V2_PERMISSIONS = {
    UserRole.ADMIN: {
        'reservations': PermissionSet(view=True, create=True, edit=True, delete=True, export=True, approve=True),
        'pricing': PermissionSet(view=True, create=True, edit=True, delete=False, export=True, approve=False),
        'housekeeping': PermissionSet(view=True, create=True, edit=True, delete=True, export=True, approve=True),
        'accounting': PermissionSet(view=True, create=True, edit=True, delete=False, export=True, approve=True),
        'reports': PermissionSet(view=True, create=True, edit=True, delete=True, export=True, approve=True),
        'settings': PermissionSet(view=True, create=True, edit=True, delete=False, export=True, approve=False)
    },
    UserRole.SUPERVISOR: {
        'reservations': PermissionSet(view=True, create=True, edit=True, delete=False, export=True, approve=True),
        'pricing': PermissionSet(view=True, create=False, edit=False, delete=False, export=False, approve=False),
        'housekeeping': PermissionSet(view=True, create=True, edit=True, delete=False, export=True, approve=True),
        'accounting': PermissionSet(view=True, create=False, edit=False, delete=False, export=True, approve=False),
        'reports': PermissionSet(view=True, create=True, edit=True, delete=False, export=True, approve=False),
        'settings': PermissionSet(view=True, create=False, edit=False, delete=False, export=False, approve=False)
    },
    UserRole.FRONT_DESK: {
        'reservations': PermissionSet(view=True, create=True, edit=True, delete=False, export=False, approve=False),
        'pricing': PermissionSet(view=False, create=False, edit=False, delete=False, export=False, approve=False),  # CANNOT SEE PRICING
        'housekeeping': PermissionSet(view=True, create=False, edit=False, delete=False, export=False, approve=False),
        'accounting': PermissionSet(view=True, create=True, edit=False, delete=False, export=False, approve=False),
        'reports': PermissionSet(view=True, create=False, edit=False, delete=False, export=False, approve=False),
        'settings': PermissionSet(view=False, create=False, edit=False, delete=False, export=False, approve=False)
    },
    UserRole.HOUSEKEEPING: {
        'reservations': PermissionSet(view=False, create=False, edit=False, delete=False, export=False, approve=False),  # CANNOT SEE RESERVATIONS
        'pricing': PermissionSet(view=False, create=False, edit=False, delete=False, export=False, approve=False),
        'housekeeping': PermissionSet(view=True, create=True, edit=True, delete=False, export=False, approve=False),
        'accounting': PermissionSet(view=False, create=False, edit=False, delete=False, export=False, approve=False),
        'reports': PermissionSet(view=True, create=False, edit=False, delete=False, export=False, approve=False),
        'settings': PermissionSet(view=False, create=False, edit=False, delete=False, export=False, approve=False)
    },
    UserRole.FINANCE: {
        'reservations': PermissionSet(view=True, create=False, edit=False, delete=False, export=True, approve=False),  # CANNOT ACCESS ROOM PLAN
        'pricing': PermissionSet(view=True, create=False, edit=False, delete=False, export=True, approve=False),
        'housekeeping': PermissionSet(view=False, create=False, edit=False, delete=False, export=False, approve=False),
        'accounting': PermissionSet(view=True, create=True, edit=True, delete=True, export=True, approve=True),
        'reports': PermissionSet(view=True, create=True, edit=True, delete=False, export=True, approve=False),
        'settings': PermissionSet(view=False, create=False, edit=False, delete=False, export=False, approve=False)
    }
}
async def night_audit_post_room_charges(tenant_id: str, date: str):
    """Post room charges for all occupied rooms"""
    posted_count = 0
    total_amount = 0
    
    # Get all checked-in bookings
    async for booking in db.bookings.find({
        'tenant_id': tenant_id,
        'status': 'checked_in',
        'check_in': {'$lte': date},
        'check_out': {'$gte': date}
    }):
        # Get guest folio
        folio = await db.folios.find_one({
            'booking_id': booking.get('id'),
            'folio_type': 'guest',
            'status': 'open'
        })
        
        if folio:
            # Calculate room rate (from booking)
            nights = (datetime.fromisoformat(booking.get('check_out')) - datetime.fromisoformat(booking.get('check_in'))).days
            room_rate = booking.get('total_amount', 0) / nights if nights > 0 else 0
            
            # Post room charge (would call existing charge posting endpoint)
            posted_count += 1
            total_amount += room_rate
    
    return {
        'charges_posted': posted_count,
        'total_amount': round(total_amount, 2)
    }


async def night_audit_calculate_revenue(tenant_id: str, date: str):
    """Calculate daily revenue breakdown"""
    # Get all charges for the date
    revenue = {
        'room_revenue': 0,
        'fnb_revenue': 0,
        'other_revenue': 0,
        'total_revenue': 0
    }
    
    async for charge in db.folio_charges.find({
        'tenant_id': tenant_id,
        'date': {'$gte': date, '$lt': (datetime.fromisoformat(date) + timedelta(days=1)).isoformat()}
    }):
        category = charge.get('charge_category')
        amount = charge.get('total', 0)
        
        if category == 'room':
            revenue['room_revenue'] += amount
        elif category in ['food', 'beverage']:
            revenue['fnb_revenue'] += amount
        else:
            revenue['other_revenue'] += amount
        
        revenue['total_revenue'] += amount
    
    return {k: round(v, 2) for k, v in revenue.items()}


async def night_audit_recalculate_ar(tenant_id: str):
    """Recalculate accounts receivable"""
    total_ar = 0
    open_folios = 0
    
    async for folio in db.folios.find({
        'tenant_id': tenant_id,
        'status': 'open',
        'folio_type': {'$in': ['company', 'agency']}
    }):
        balance = folio.get('balance', 0)
        total_ar += balance
        open_folios += 1
    
    return {
        'total_ar': round(total_ar, 2),
        'open_folios': open_folios
    }


async def night_audit_housekeeping_rollup(tenant_id: str, date: str):
    """Housekeeping summary for the day"""
    tasks_completed = await db.housekeeping_tasks.count_documents({
        'tenant_id': tenant_id,
        'status': 'completed',
        'completed_at': {'$gte': date, '$lt': (datetime.fromisoformat(date) + timedelta(days=1)).isoformat()}
    })
    
    return {
        'tasks_completed': tasks_completed,
        'date': date
    }


async def night_audit_ota_reconciliation(tenant_id: str, date: str):
    """OTA bookings reconciliation"""
    ota_bookings = 0
    ota_revenue = 0
    
    async for booking in db.bookings.find({
        'tenant_id': tenant_id,
        'check_in': date,
        'ota_channel': {'$ne': None}
    }):
        ota_bookings += 1
        ota_revenue += booking.get('total_amount', 0)
    
    return {
        'ota_bookings': ota_bookings,
        'ota_revenue': round(ota_revenue, 2)
    }


# ============= INBOX & ALERT CENTER =============

class Alert(BaseModel):
    """Universal alert model"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    alert_type: str  # housekeeping, maintenance, ota, overbooking, rms, ar, marketplace, review
    priority: str  # low, normal, high, urgent
    title: str
    description: str
    source_module: str
    source_id: Optional[str] = None
    assigned_to: Optional[str] = None
    status: str = "unread"  # unread, read, acknowledged, resolved
    action_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    read_at: Optional[datetime] = None
class TableLayout(BaseModel):
    """Table layout for restaurant floor plan"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    outlet_id: str
    table_number: str
    seats: int
    position_x: float  # X coordinate on floor plan
    position_y: float  # Y coordinate on floor plan
    shape: str = "rectangle"  # rectangle, circle, square
    width: float = 100
    height: float = 100
    status: str = "available"  # available, occupied, reserved, dirty
    current_transaction_id: Optional[str] = None
    server_assigned: Optional[str] = None

class KitchenOrderItem(BaseModel):
    """Kitchen order item for KDS"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_id: str
    table_number: str
    item_name: str
    quantity: int
    special_instructions: Optional[str] = None
    station: str  # hot_kitchen, cold_kitchen, bar, pastry
    status: str = "pending"  # pending, preparing, ready, served
    priority: str = "normal"  # urgent, high, normal
    ordered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ready_at: Optional[datetime] = None
    served_at: Optional[datetime] = None
def create_default_table_layout(tenant_id: str, outlet_id: str):
    """Create default table layout (4x4 grid)"""
    tables = []
    table_num = 1
    for row in range(4):
        for col in range(4):
            tables.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'outlet_id': outlet_id,
                'table_number': str(table_num),
                'seats': 4,
                'position_x': col * 150 + 50,
                'position_y': row * 150 + 50,
                'shape': 'rectangle',
                'width': 100,
                'height': 100,
                'status': 'available'
            })
            table_num += 1
    return tables


def calculate_table_duration(table):
    """Calculate how long table has been occupied"""
    # Would track from transaction start time
    return 45  # Simulated
class InternalMessage(BaseModel):
    """Internal messaging between departments"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    from_user_id: str
    from_user_name: str
    from_department: str
    to_user_id: Optional[str] = None  # None = broadcast to department
    to_user_name: Optional[str] = None
    to_department: Optional[str] = None  # None = all departments
    message: str
    priority: str = "normal"  # low, normal, high, urgent
    message_type: str = "text"  # text, task, alert, announcement
    attachments: List[str] = []
    read: bool = False
    read_at: Optional[datetime] = None
    replied_to: Optional[str] = None  # Original message ID if this is a reply
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
def calculate_time_ago(timestamp_str):
    """Calculate time ago from timestamp"""
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        delta = datetime.now(timezone.utc) - timestamp
        
        if delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds >= 3600:
            return f"{delta.seconds // 3600}h ago"
        elif delta.seconds >= 60:
            return f"{delta.seconds // 60}m ago"
        else:
            return "Just now"
    except:
        return "Unknown"
class GuestPersona(BaseModel):
    """AI-generated guest persona"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    persona_type: str  # price_sensitive, experience_seeker, complainer, upsell_candidate, high_ltv, ota_to_direct_candidate
    confidence_score: float  # 0.0 - 1.0
    indicators: List[str] = []  # Why this persona was assigned
    recommendations: List[str] = []  # Action items
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
def generate_campaign_suggestions(personas_by_type):
    """Generate marketing campaign suggestions"""
    campaigns = []
    
    if 'price_sensitive' in personas_by_type:
        campaigns.append({
            'target': 'Price Sensitive',
            'count': len(personas_by_type['price_sensitive']),
            'campaign': 'Early Bird Discount - 20% off bookings 60+ days in advance'
        })
    
    if 'ota_to_direct_candidate' in personas_by_type:
        campaigns.append({
            'target': 'OTA → Direct',
            'count': len(personas_by_type['ota_to_direct_candidate']),
            'campaign': 'Direct Booking Bonus - 15% off + 500 loyalty points'
        })
    
    if 'high_ltv' in personas_by_type:
        campaigns.append({
            'target': 'High LTV',
            'count': len(personas_by_type['high_ltv']),
            'campaign': 'VIP Exclusive Event - Private wine tasting invitation'
        })
    
    return campaigns


# ============= PREDICTIVE MAINTENANCE =============

class MaintenanceAlert(BaseModel):
    """Predictive maintenance alert"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    equipment_type: str  # hvac, plumbing, electrical, elevator
    alert_type: str = "predictive"  # predictive, reactive
    severity: str  # low, medium, high, critical
    prediction: str
    indicators: List[str] = []
    recommended_action: str
    estimated_failure_days: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_to: Optional[str] = None
    status: str = "pending"  # pending, scheduled, completed
async def create_predictive_maintenance_task(tenant_id, room_id, room_number, description, priority, alert_id):
    """Auto-create maintenance task from prediction"""
    task = {
        'id': str(uuid.uuid4()),
        'tenant_id': tenant_id,
        'room_id': room_id,
        'task_type': 'preventive',
        'description': description,
        'priority': priority,
        'status': 'pending',
        'source': 'predictive_ai',
        'alert_id': alert_id,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.maintenance_tasks.insert_one(task)
def distribute_tasks(room_ids, staff, task_type):
    """Distribute tasks evenly among staff"""
    assignments = []
    estimated_time = 45 if task_type == 'checkout' else 20
    priority = 'high' if task_type == 'checkout' else 'normal'
    
    for idx, room_id in enumerate(room_ids):
        staff_idx = idx % len(staff)
        staff_member = staff[staff_idx]
        
        assignments.append({
            'staff_id': staff_member.get('id'),
            'staff_name': staff_member.get('name'),
            'task': {
                'room_id': room_id,
                'type': task_type,
                'priority': priority,
                'estimated_minutes': estimated_time
            },
            'estimated_minutes': estimated_time
        })
    
    return assignments


def generate_scheduling_recommendations(capacity_pct, staff_count, total_rooms):
    """Generate staffing recommendations"""
    recommendations = []
    
    if capacity_pct > 110:
        extra_staff = ((capacity_pct - 100) / 100) * staff_count
        recommendations.append(f'🚨 Consider hiring {int(extra_staff)} additional staff members')
        recommendations.append('⚠️ Current staff will be overworked')
    elif capacity_pct > 90:
        recommendations.append('⚠️ Staff at near maximum capacity')
        recommendations.append('Consider part-time support for peak days')
    else:
        recommendations.append('✅ Staffing levels are adequate')
    
    if total_rooms > 50:
        recommendations.append('💡 Consider team-based cleaning for efficiency')
    
    return recommendations
def get_tier_benefits(tier):
    """Get benefits for loyalty tier"""
    benefits = {
        'silver': ['Late checkout (12pm)', 'Free breakfast', 'Free Wi-Fi'],
        'gold': ['Late checkout (1pm)', 'Free breakfast', 'Priority upgrade', 'Welcome amenity', 'Free Wi-Fi'],
        'platinum': ['Late checkout (2pm)', 'Free breakfast', 'Priority upgrade', 'Welcome amenity', 'Free Wi-Fi', 'Room upgrade guarantee', 'VIP lounge access']
    }
    return benefits.get(tier, [])
class TenantModulesUpdate(BaseModel):
    modules: Dict[str, bool]
class SubscriptionUpdateRequest(BaseModel):
    """Subscription duration/date update request

    Backward compatible:
    - If only subscription_days is provided → start=now, end=now+days (or unlimited)
    - If subscription_start_date or subscription_end_date provided → backend prefers these values

    Dates can be provided as:
    - YYYY-MM-DD
    - ISO8601 datetime (e.g. 2025-12-17T00:00:00Z)
    """

    subscription_days: Optional[int] = None  # None = unlimited
    subscription_start_date: Optional[str] = None
    subscription_end_date: Optional[str] = None

from subscription_models import (
    SubscriptionTier, SubscriptionPlan, SUBSCRIPTION_PLANS,
    has_feature_access, get_feature_comparison, FeatureFlag,
    PLAN_MODULE_DEFAULTS, get_plan_default_modules, get_all_module_keys
)
class ChangePlanRequest(BaseModel):
    new_tier: str  # basic, professional, enterprise
    billing_cycle: str = "monthly"  # monthly, yearly
class UpdateHotelInfoRequest(BaseModel):
    property_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    total_rooms: Optional[int] = None
class CreateTeamMemberRequest(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    role: str = "front_desk"
    password: str

class UpdateTeamMemberRoleRequest(BaseModel):
    role: str
async def get_guest_name(guest_id: str, tenant_id: str) -> str:
    """Helper to get guest name"""
    guest = await db.guests.find_one({'id': guest_id, 'tenant_id': tenant_id})
    return guest.get('name', 'Unknown') if guest else 'Unknown'
class GuestTagEnum(str, Enum):
    VIP = "vip"
    BLACKLIST = "blacklist"
    HONEYMOON = "honeymoon"
    ANNIVERSARY = "anniversary"
    BUSINESS_TRAVELER = "business_traveler"
    FREQUENT_GUEST = "frequent_guest"
    COMPLAINER = "complainer"
    HIGH_SPENDER = "high_spender"
def get_pricing_reason(occupancy_pct: float) -> str:
    """Get human-readable pricing recommendation reason"""
    if occupancy_pct < 30:
        return "Low occupancy - recommend discount to attract bookings"
    elif occupancy_pct < 60:
        return "Medium occupancy - standard pricing strategy"
    elif occupancy_pct < 80:
        return "Good occupancy - increase prices to maximize revenue"
    else:
        return "High occupancy - premium pricing for limited availability"
class MessageType(str, Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"

class AutoMessageTrigger(str, Enum):
    PRE_ARRIVAL = "pre_arrival"  # 1 day before check-in
    CHECK_IN_REMINDER = "check_in_reminder"  # Morning of check-in
    POST_CHECKOUT = "post_checkout"  # After checkout
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"

class MessageTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    template_name: str
    message_type: MessageType
    trigger: AutoMessageTrigger
    message_content: str
    active: bool = True
    variables: List[str] = []  # e.g., ['{guest_name}', '{room_number}', '{check_in_date}']

class SentMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    booking_id: Optional[str] = None
    message_type: MessageType
    recipient: str  # phone or email
    message_content: str
    status: str = "sent"  # sent, delivered, failed
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SendMessageRequest(BaseModel):
    guest_id: str
    message_type: MessageType
    recipient: str
    message_content: str
    booking_id: Optional[str] = None
    
    @field_validator('message_type', mode='before')
    @classmethod
    def lowercase_message_type(cls, v):
        """Convert message type to lowercase for case-insensitive validation"""
        if isinstance(v, str):
            return v.lower()
        return v
class POSCategory(str, Enum):
    FOOD = "food"
    BEVERAGE = "beverage"
    ALCOHOL = "alcohol"
    DESSERT = "dessert"
    APPETIZER = "appetizer"

class POSMenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_name: str
    category: POSCategory
    unit_price: float
    available: bool = True

class POSOrderItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_id: str
    item_name: str
    category: POSCategory
    quantity: int
    unit_price: float
    total_price: float

class POSOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: Optional[str] = None
    guest_id: Optional[str] = None
    folio_id: Optional[str] = None
    order_items: List[POSOrderItem]
    subtotal: float
    tax_amount: float
    total_amount: float
    status: str = "pending"  # pending, completed, cancelled
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class POSOrderItemRequest(BaseModel):
    item_id: str
    quantity: int = 1

class POSOrderCreateRequest(BaseModel):
    booking_id: Optional[str] = None
    folio_id: Optional[str] = None
    order_items: List[POSOrderItemRequest]
async def recalculate_folio_balance(folio_id: str, tenant_id: str):
    """Helper to recalculate folio balance"""
    # Get all non-voided charges
    total_charges = 0.0
    async for charge in db.folio_charges.find({
        'folio_id': folio_id,
        'tenant_id': tenant_id,
        'voided': False
    }):
        total_charges += charge.get('total', charge.get('amount', 0))
    
    # Get all payments
    total_payments = 0.0
    async for payment in db.payments.find({
        'folio_id': folio_id,
        'tenant_id': tenant_id
    }):
        total_payments += payment.get('amount', 0)
    
    # Update folio balance
    balance = total_charges - total_payments
    await db.folios.update_one(
        {'id': folio_id, 'tenant_id': tenant_id},
        {'$set': {'balance': balance}}
    )
class UpdateOrderStatusRequest(BaseModel):
    status: str  # pending, preparing, ready, served
    notes: Optional[str] = None

class StockAdjustRequest(BaseModel):
    product_id: str
    adjustment_type: str  # in, out, adjustment
    quantity: int
    reason: str
    notes: Optional[str] = None
class ApprovalType(str, Enum):
    DISCOUNT = "discount"
    PRICE_OVERRIDE = "price_override"
    BUDGET_EXPENSE = "budget_expense"
    RATE_CHANGE = "rate_change"
    REFUND = "refund"
    COMP_ROOM = "comp_room"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

class CreateApprovalRequest(BaseModel):
    approval_type: ApprovalType
    reference_id: Optional[str] = None  # booking_id, folio_id, etc.
    amount: float
    original_value: Optional[float] = None
    new_value: Optional[float] = None
    reason: str
    notes: Optional[str] = None
    priority: str = "normal"  # low, normal, high, urgent

class ApprovalActionRequest(BaseModel):
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
class BudgetMonth(BaseModel):
    month: int
    occ_target: float = 0
    adr_target: float = 0
    rev_target: float = 0


class BudgetConfig(BaseModel):
    year: int
    currency: str = "TRY"
    months: List[BudgetMonth]
class NotificationPreferenceRequest(BaseModel):
    notification_type: str
    enabled: bool
    channels: List[str] = ['in_app']  # in_app, email, sms, push

class SystemAlertRequest(BaseModel):
    type: str
    title: str
    message: str
    priority: str = "normal"
    target_roles: Optional[List[str]] = None
class LeadStage(str, Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    CONVERTED = "converted"
    LOST = "lost"

class CreateLeadRequest(BaseModel):
    guest_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    stage: LeadStage = LeadStage.COLD
    source: str  # website, phone, walk-in, referral, ota
    notes: Optional[str] = None
    expected_checkin: Optional[str] = None
    expected_revenue: float = 0

class UpdateLeadStageRequest(BaseModel):
    stage: LeadStage
    notes: Optional[str] = None
class PmsLiteLeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    LOST = "lost"
    WON = "won"


class PmsLiteLeadContact(BaseModel):
    full_name: str
    phone: str
    email: Optional[EmailStr] = None


class PmsLiteLeadHotel(BaseModel):
    property_name: str
    location: Optional[str] = None
    rooms_count: conint(ge=1, le=200)


class PmsLiteLeadMetadata(BaseModel):
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None


class PmsLiteLeadCreateRequest(BaseModel):
    contact: PmsLiteLeadContact
    hotel: PmsLiteLeadHotel
    metadata: Optional[PmsLiteLeadMetadata] = None


class PmsLiteLeadAdminUpdateRequest(BaseModel):
    status: Optional[PmsLiteLeadStatus] = None
    note: Optional[str] = None
def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


    return {"leads": leads, "count": total}
class RateOverrideRequest(BaseModel):
    room_type: str
    date: str
    new_rate: float
    reason: str
    requires_approval: bool = True


# NEW FRONTEND ENHANCEMENTS - REQUEST MODELS
class KeycardIssueRequest(BaseModel):
    booking_id: str
    card_type: str = "physical"  # physical, mobile, qr
    validity_hours: int = 48
class CleaningRequestCreate(BaseModel):
    booking_id: Optional[str] = None
    room_number: Optional[str] = None
    type: str = "regular"  # regular, urgent, turndown, do_not_disturb
    notes: Optional[str] = ""
class CleaningRequestStatusUpdate(BaseModel):
    status: str  # in_progress, completed, cancelled
    assigned_to: Optional[str] = None
    completed_by: Optional[str] = None
    notes: Optional[str] = None
class SLAConfig(BaseModel):
    category: str  # maintenance, housekeeping, guest_request
    response_time_minutes: int
    resolution_time_minutes: int
    priority: str = "normal"  # low, normal, high, urgent
class PingTestRequest(BaseModel):
    target: str = "8.8.8.8"  # Google DNS
    count: int = 4
class DemoRequest(BaseModel):
    name: str
    email: str
    phone: str
    hotel_name: str = Field(..., alias='hotelName')
    room_count: str = Field(..., alias='roomCount')
async def log_audit_trail(
    tenant_id: str,
    user_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    old_value: str = None,
    new_value: str = None
):
    """Helper function to log all system changes"""
    entry = AuditTrailEntry(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value
    )
    
    await db.audit_trail.insert_one(entry.model_dump())
async def log_audit_trail(
    tenant_id: str,
    user_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    old_value: str = None,
    new_value: str = None
):
    """Helper function to log all system changes"""
    entry = AuditTrailEntry(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value
    )
    
    await db.audit_trail.insert_one(entry.model_dump())
def get_menu_recommendation(category):
    """Get recommendation based on menu classification"""
    recommendations = {
        'Stars': 'Maintain quality, increase price slightly',
        'Plowhorses': 'Promote more, reduce cost',
        'Puzzles': 'Increase marketing, adjust pricing',
        'Dogs': 'Remove from menu or redesign'
    }
    return recommendations.get(category, 'Review item performance')
