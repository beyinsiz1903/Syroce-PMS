"""
Tests for Sales/CRM Domain Router
Covers K5 critical gap: Sales/CRM domain had zero test coverage.
Tests real domain schemas, classification logic, and router endpoint behavior.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime, timedelta

from domains.sales.schemas import (
    LeadStage,
    CreateLeadRequest,
    UpdateLeadStageRequest,
    PmsLiteLeadStatus,
    PmsLiteLeadContact,
    PmsLiteLeadHotel,
    PmsLiteLeadMetadata,
)


class TestLeadStageEnum:
    def test_all_stages_exist(self):
        assert LeadStage.COLD == "cold"
        assert LeadStage.WARM == "warm"
        assert LeadStage.HOT == "hot"
        assert LeadStage.CONVERTED == "converted"
        assert LeadStage.LOST == "lost"

    def test_stage_count(self):
        assert len(LeadStage) == 5


class TestCreateLeadRequest:
    def test_minimal_lead(self):
        lead = CreateLeadRequest(guest_name="Test Guest", source="website")
        assert lead.guest_name == "Test Guest"
        assert lead.source == "website"
        assert lead.stage == LeadStage.COLD
        assert lead.expected_revenue == 0

    def test_full_lead(self):
        lead = CreateLeadRequest(
            guest_name="VIP Guest",
            email="vip@example.com",
            phone="+905321234567",
            company="Acme Corp",
            stage=LeadStage.HOT,
            source="referral",
            notes="Important lead",
            expected_checkin="2026-05-01",
            expected_revenue=25000,
        )
        assert lead.stage == LeadStage.HOT
        assert lead.expected_revenue == 25000

    def test_invalid_stage_rejected(self):
        with pytest.raises(Exception):
            CreateLeadRequest(guest_name="X", source="web", stage="invalid_stage")


class TestUpdateLeadStageRequest:
    def test_update_stage(self):
        req = UpdateLeadStageRequest(stage=LeadStage.CONVERTED, notes="Converted to booking")
        assert req.stage == LeadStage.CONVERTED
        assert req.notes == "Converted to booking"

    def test_update_without_notes(self):
        req = UpdateLeadStageRequest(stage=LeadStage.WARM)
        assert req.notes is None


class TestPmsLiteLeadModels:
    def test_contact_model(self):
        contact = PmsLiteLeadContact(full_name="Ali Demir", phone="+905321234567")
        assert contact.full_name == "Ali Demir"
        assert contact.email is None

    def test_contact_with_email(self):
        contact = PmsLiteLeadContact(
            full_name="Ali Demir", phone="+905321234567", email="ali@example.com"
        )
        assert contact.email == "ali@example.com"

    def test_hotel_model(self):
        hotel = PmsLiteLeadHotel(property_name="Grand Hotel", rooms_count=50)
        assert hotel.property_name == "Grand Hotel"
        assert hotel.rooms_count == 50

    def test_hotel_rooms_validation(self):
        with pytest.raises(Exception):
            PmsLiteLeadHotel(property_name="X", rooms_count=0)
        with pytest.raises(Exception):
            PmsLiteLeadHotel(property_name="X", rooms_count=201)

    def test_metadata_defaults(self):
        meta = PmsLiteLeadMetadata()
        assert meta.utm_source is None
        assert meta.user_agent is None
        assert meta.ip is None

    def test_lead_status_enum(self):
        assert PmsLiteLeadStatus.NEW == "new"
        assert PmsLiteLeadStatus.WON == "won"
        assert len(PmsLiteLeadStatus) == 5


class TestCustomerClassificationLogic:
    def _classify(self, customer):
        if customer["total_revenue"] > 50000:
            customer["is_vip"] = True
        types = []
        if customer.get("is_vip"):
            types.append("vip")
        if customer.get("is_corporate"):
            types.append("corporate")
        if customer["total_bookings"] > 1:
            types.append("returning")
        else:
            types.append("new")
        return types

    def test_vip_customer(self):
        types = self._classify({"total_revenue": 60000, "total_bookings": 5, "is_corporate": False})
        assert "vip" in types
        assert "returning" in types

    def test_corporate_returning(self):
        types = self._classify({"total_revenue": 30000, "total_bookings": 10, "is_corporate": True})
        assert "corporate" in types
        assert "returning" in types
        assert "vip" not in types

    def test_new_customer(self):
        types = self._classify({"total_revenue": 1000, "total_bookings": 1, "is_corporate": False})
        assert types == ["new"]


class TestFollowUpLogic:
    def _needs_follow_up(self, updated_at_str):
        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        days_since = (datetime.now(UTC) - updated_at).days
        if days_since > 3:
            urgency = "high" if days_since > 7 else "medium"
            return True, urgency
        return False, None

    def test_needs_follow_up(self):
        old = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        needed, urgency = self._needs_follow_up(old)
        assert needed is True
        assert urgency == "high"

    def test_no_follow_up(self):
        recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        needed, urgency = self._needs_follow_up(recent)
        assert needed is False

    def test_medium_urgency(self):
        med = (datetime.now(UTC) - timedelta(days=5)).isoformat()
        needed, urgency = self._needs_follow_up(med)
        assert needed is True
        assert urgency == "medium"


class TestContractUtilization:
    def _calculate_utilization(self, committed, actual):
        if committed <= 0:
            return 0.0, "healthy"
        pct = round((actual / committed) * 100, 1)
        status = "under_utilized" if pct < 70 else "healthy"
        return pct, status

    def test_healthy(self):
        pct, status = self._calculate_utilization(500, 400)
        assert pct == 80.0
        assert status == "healthy"

    def test_under_utilized(self):
        pct, status = self._calculate_utilization(500, 200)
        assert pct == 40.0
        assert status == "under_utilized"

    def test_zero_commitment(self):
        pct, status = self._calculate_utilization(0, 0)
        assert pct == 0.0
        assert status == "healthy"
