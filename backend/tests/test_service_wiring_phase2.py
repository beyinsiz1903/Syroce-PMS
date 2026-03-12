"""
Tests — Service Wiring Validation for Phase B completion
Validates all new services are importable, instantiable, and wired to routers.
"""
import pytest
import importlib

pytestmark = pytest.mark.asyncio


# ── Service Import Tests ──

def test_frontdesk_service_import():
    from domains.pms.frontdesk_service import frontdesk_service
    assert frontdesk_service is not None
    assert hasattr(frontdesk_service, "checkin")
    assert hasattr(frontdesk_service, "checkout")
    assert hasattr(frontdesk_service, "get_todays_arrivals")
    assert hasattr(frontdesk_service, "get_guest_alerts")
    assert hasattr(frontdesk_service, "issue_keycard")
    assert hasattr(frontdesk_service, "get_unified_arrivals")


def test_night_audit_service_import():
    from domains.pms.night_audit_service import night_audit_service
    assert night_audit_service is not None
    assert hasattr(night_audit_service, "get_audit_logs")
    assert hasattr(night_audit_service, "get_error_logs")
    assert hasattr(night_audit_service, "get_night_audit_logs")
    assert hasattr(night_audit_service, "get_ota_sync_logs")
    assert hasattr(night_audit_service, "get_rms_publish_logs")
    assert hasattr(night_audit_service, "get_maintenance_prediction_logs")


def test_pos_fnb_service_import():
    from domains.pms.pos_fnb.pos_fnb_service import pos_fnb_service
    assert pos_fnb_service is not None
    assert hasattr(pos_fnb_service, "get_kitchen_display")
    assert hasattr(pos_fnb_service, "get_fnb_dashboard")
    assert hasattr(pos_fnb_service, "adjust_stock")
    assert hasattr(pos_fnb_service, "get_active_orders")


def test_pricing_service_import():
    from domains.revenue.pricing.pricing_service import pricing_service
    assert pricing_service is not None
    assert hasattr(pricing_service, "update_room_rate")
    assert hasattr(pricing_service, "list_rate_plans")
    assert hasattr(pricing_service, "get_demand_forecast")
    assert hasattr(pricing_service, "get_revenue_dashboard")
    assert hasattr(pricing_service, "get_dynamic_pricing_suggestion")


def test_rms_service_import():
    from domains.revenue.rms.rms_service import rms_service
    assert rms_service is not None
    assert hasattr(rms_service, "create_group_booking")
    assert hasattr(rms_service, "create_corporate_contract")
    assert hasattr(rms_service, "create_ota_promotion")
    assert hasattr(rms_service, "create_inventory_item")
    assert hasattr(rms_service, "get_yield_analysis")


def test_messaging_service_import():
    from domains.guest.messaging.messaging_service import messaging_service
    assert messaging_service is not None
    assert hasattr(messaging_service, "send_message")
    assert hasattr(messaging_service, "get_guest_messages")
    assert hasattr(messaging_service, "send_internal_message")
    assert hasattr(messaging_service, "get_templates")


def test_mobile_ops_service_import():
    from domains.pms.mobile.mobile_ops_service import mobile_ops_service
    assert mobile_ops_service is not None
    assert hasattr(mobile_ops_service, "process_no_show")
    assert hasattr(mobile_ops_service, "change_room")
    assert hasattr(mobile_ops_service, "create_quick_task")
    assert hasattr(mobile_ops_service, "get_mobile_dashboard")


# ── Schema Import Tests ──

def test_pos_fnb_schemas_import():
    from domains.pms.pos_fnb.schemas import POSMenuItem, POSOrder, POSOrderItem, TableLayout, KitchenOrderItem, Alert
    assert POSMenuItem is not None
    assert POSOrder is not None


def test_mobile_schemas_import():
    from domains.pms.mobile.schemas import ProcessNoShowRequest, ChangeRoomRequest, QuickTaskRequest, QuickOrderRequest
    assert ProcessNoShowRequest is not None


def test_pricing_schemas_import():
    from domains.revenue.pricing.schemas import RatePlanFilter, RatePlanCreate, PackageCreate, CompetitorRate, RateOverrideRequest
    assert RatePlanFilter is not None


def test_rms_schemas_import():
    from domains.revenue.rms.schemas import GroupBookingCreate, CorporateContractCreate, OTAPromotionCreate, InventoryItemCreate
    assert GroupBookingCreate is not None


def test_messaging_schemas_import():
    from domains.guest.messaging.schemas import MessageType, SendMessageRequest, SentMessage, MessageTemplate, InternalMessage
    assert MessageType is not None
    assert SendMessageRequest is not None


# ── Router Wiring Tests ──

def test_frontdesk_router_uses_service():
    """Verify frontdesk router imports frontdesk_service."""
    mod = importlib.import_module("domains.pms.frontdesk_router")
    source = open(mod.__file__).read()
    assert "frontdesk_service" in source
    assert "OperationContext" in source


def test_night_audit_router_uses_service():
    """Verify night audit router imports night_audit_service."""
    mod = importlib.import_module("domains.pms.night_audit_router")
    source = open(mod.__file__).read()
    assert "night_audit_service" in source
    assert "OperationContext" in source


def test_pricing_router_uses_service():
    """Verify pricing router imports pricing_service."""
    mod = importlib.import_module("domains.revenue.pricing_router")
    source = open(mod.__file__).read()
    assert "pricing_service" in source
    assert "OperationContext" in source


def test_messaging_router_imports_service():
    """Verify messaging router imports messaging_service."""
    mod = importlib.import_module("domains.guest.messaging.router")
    source = open(mod.__file__).read()
    assert "messaging_service" in source
    assert "OperationContext" in source


# ── Common Contracts ──

def test_operation_context():
    from common.context import OperationContext
    ctx = OperationContext(tenant_id="t1", actor_id="a1", actor_email="a@b.com", actor_role="admin")
    assert ctx.tenant_id == "t1"
    assert ctx.actor_role == "admin"


def test_service_result():
    from common.result import ServiceResult
    ok = ServiceResult.success({"key": "value"})
    assert ok.ok is True
    assert ok.data["key"] == "value"

    fail = ServiceResult.fail("err msg", "ERR_CODE")
    assert fail.ok is False
    assert fail.error == "err msg"
    assert fail.code == "ERR_CODE"


def test_domain_errors():
    from common.errors import DomainError, NotFoundError, ValidationError, ForbiddenError, TenantViolationError
    assert issubclass(NotFoundError, DomainError)
    assert issubclass(ForbiddenError, DomainError)
    assert issubclass(TenantViolationError, DomainError)
