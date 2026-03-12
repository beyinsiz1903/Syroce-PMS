"""
Transformation script: Extracts endpoint definitions from server.py
into legacy_routes.py and removes infrastructure/orchestration code.
"""
import re

with open('/app/backend/server.py', 'r') as f:
    lines = f.readlines()

total = len(lines)
print(f"Total lines in server.py: {total}")

# Find marker line numbers (0-indexed)
def find_line(pattern, start=0):
    for i in range(start, total):
        if pattern in lines[i]:
            return i
    return -1

# ── Sections to REMOVE ──────────────────────────────────────────────
# 1. Lines 0 to just before "# ============= CHANNEL MANAGER (PROD MVP) ="
cm_marker = find_line("# ============= CHANNEL MANAGER (PROD MVP) =============")
print(f"CM marker at line {cm_marker}")

# 2. CORS / Middleware setup block
cors_start = find_line("_cors_raw = os.environ.get('CORS_ORIGINS', '')")
logging_line = find_line("logging.basicConfig(level=logging.INFO", cors_start)
middleware_end = logging_line + 1 if logging_line >= 0 else -1
print(f"Middleware block: {cors_start} - {middleware_end}")

# 3. Startup/Shutdown events
startup_marker = find_line('@app.on_event("startup")')
# Find end of shutdown (client.close() line)
shutdown_end = find_line("client.close()", startup_marker)
if shutdown_end >= 0:
    shutdown_end += 1  # include the close line
print(f"Startup/Shutdown block: {startup_marker} - {shutdown_end}")

# 4. Router mounting section at the end
router_mount_start = find_line("# Include router at the very end after ALL endpoints are defined")
print(f"Router mount start: {router_mount_start}")

# 5. Final CM v2 router section (at very end)
# This is after the analytics endpoints and includes app.include_router calls
# We need to keep the analytics endpoints but remove the include_router calls

# Find all lines with app.include_router or app.mount to remove in the tail section
# Also find lines with @app.get/@app.post (non api_router) to remove

# Build removal set
skip = set()

# Section 1: Everything from start to CM marker (imports, config, app creation)
# This will be replaced by the new import header
for i in range(0, cm_marker):
    skip.add(i)

# Section 2: Middleware setup
if cors_start >= 0 and middleware_end >= 0:
    for i in range(cors_start, middleware_end):
        skip.add(i)

# Section 3: Startup/Shutdown
if startup_marker >= 0 and shutdown_end >= 0:
    for i in range(startup_marker, shutdown_end):
        skip.add(i)

# Section 4: Router mounting from marker to end of file
# But we need to keep endpoint definitions that are between router mounts
# Let's be more surgical - remove lines that contain app.include_router, 
# try/except blocks around router imports, and print statements about routers
if router_mount_start >= 0:
    # Remove from router_mount_start to end, but preserve @api_router endpoints
    i = router_mount_start
    in_try_block = False
    try_indent = 0
    while i < total:
        line = lines[i]
        stripped = line.strip()
        
        # Check if this is an @api_router endpoint definition
        if stripped.startswith('@api_router.'):
            # This is an endpoint, keep it and all following code until next section
            # Don't skip
            in_try_block = False
            i += 1
            continue
        
        # Check if this is a function def that's part of an endpoint
        if stripped.startswith('async def ') or stripped.startswith('def '):
            # Check previous non-empty line for decorator
            prev_i = i - 1
            while prev_i >= 0 and lines[prev_i].strip() == '':
                prev_i -= 1
            if prev_i >= 0 and '@api_router.' in lines[prev_i]:
                # This is part of an endpoint definition
                i += 1
                continue
        
        # Skip lines that are part of router mounting
        if ('app.include_router' in stripped or
            'app.mount' in stripped or
            'Include router' in stripped or
            stripped.startswith('# Include ') or
            stripped.startswith('# Mount ') or
            stripped.startswith('print("✅') or
            stripped.startswith('print(f"✅') or
            stripped.startswith('print(f"⚠️') or
            stripped.startswith('print("⚠️') or
            (stripped.startswith('from ') and 'import' in stripped and 'router' in stripped.lower() and i > router_mount_start) or
            (stripped.startswith('import ') and 'traceback' in stripped and i > router_mount_start)):
            skip.add(i)
            i += 1
            continue
            
        # Skip try/except blocks that wrap router imports
        if stripped == 'try:' and i > router_mount_start:
            # Look ahead to see if this is a router import try block
            lookahead = ''
            for j in range(i+1, min(i+5, total)):
                lookahead += lines[j].strip() + ' '
            if 'include_router' in lookahead or 'import' in lookahead and 'router' in lookahead.lower():
                # Skip this entire try/except block
                indent = len(line) - len(line.lstrip())
                j = i
                while j < total:
                    curr_line = lines[j]
                    curr_stripped = curr_line.strip()
                    curr_indent = len(curr_line) - len(curr_line.lstrip()) if curr_stripped else indent + 1
                    
                    if j > i and curr_indent <= indent and curr_stripped and not curr_stripped.startswith('except') and not curr_stripped.startswith('finally'):
                        break
                    skip.add(j)
                    j += 1
                i = j
                continue
        
        # Skip section headers/comments in the mounting area
        if stripped.startswith('# =====') and i > router_mount_start:
            skip.add(i)
            i += 1
            continue
        
        # Keep everything else (endpoint code, helper functions, etc.)
        i += 1

# Also remove @app.get/@app.post endpoints (health, download - they go to app.py)
# These are in the first section which is already removed

# Remove duplicate import of pydantic etc that appears after shutdown (line ~9519)
dup_import = find_line("from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator", shutdown_end if shutdown_end > 0 else 9500)
if dup_import >= 0 and dup_import < shutdown_end + 50:
    # These are inline model definitions - check if they're duplicates
    # They start at line ~9519 and define enums that already exist in models/
    # Let's find where the model definitions end
    j = dup_import
    while j < total:
        stripped = lines[j].strip()
        if stripped.startswith('@api_router.') or stripped.startswith('@app.'):
            break
        j += 1
    # Check if these are all enum/model definitions
    content_block = ''.join(lines[dup_import:j])
    if 'class AccountType' in content_block or 'class TransactionType' in content_block:
        print(f"Removing duplicate model definitions: {dup_import} - {j}")
        for i in range(dup_import, j):
            skip.add(i)

print(f"Total lines to skip: {len(skip)}")

# ── Build import header ─────────────────────────────────────────────
header = '''"""
Legacy Routes — All inline endpoint definitions extracted from the monolithic server.py.
Phase B will decompose these into domain-specific router modules.
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
import jwt as pyjwt
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
    "professional": {UserRole.ADMIN, UserRole.FRONT_DESK, UserRole.HOUSEKEEPING, UserRole.REVENUE_MANAGER, UserRole.FINANCE, UserRole.MAINTENANCE},
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

'''

# ── Write legacy_routes.py ──────────────────────────────────────────
with open('/app/backend/legacy_routes.py', 'w') as f:
    f.write(header)
    for i in range(total):
        if i not in skip:
            f.write(lines[i])

# Count remaining lines
remaining = total - len(skip)
print(f"legacy_routes.py created: ~{remaining + header.count(chr(10))} lines")
print(f"Removed {len(skip)} lines of infrastructure/orchestration code")
