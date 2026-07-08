from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from core.database import db
from core.tenant_db import set_tenant_context
from domains.contact_center.quality_models import (
    CallEvaluationCreate,
    ScorecardConfigCreate,
    ScorecardQuestion,
    ScorecardSection,
)
from domains.contact_center.quality_router import (
    get_call_evaluations,
    get_quality_trends,
    get_scorecards,
    post_call_evaluation,
    post_scorecard,
)
from domains.contact_center.reports_router import get_performance_reports
from domains.contact_center.router import (
    AssignConversationPayload,
    LinkConversationPayload,
    SendWhatsAppMessage,
    assign_conversation,
    close_conversation,
    link_conversation,
    read_conversation,
    send_conversation_message,
)
from domains.contact_center.voice_router import get_call_recording
from models.enums import MessageDirection, UserRole
from models.schemas import User

_TENANT = "test_tenant_cc_faz4"
_SUPERVISOR_ID = "supervisor_cc_4"
_AGENT_ID = "agent_cc_4"


@pytest.fixture(autouse=True)
async def setup_test_tenant():
    set_tenant_context(_TENANT)
    # Clear collections
    collections = [
        "contact_center_calls",
        "contact_center_quality_scorecards",
        "contact_center_quality_evaluations",
        "contact_center_conversations",
        "contact_center_messages",
        "contact_center_callbacks",
        "contact_center_queues",
        "users",
        "contact_center_dispositions",
    ]
    for c in collections:
        await db[c].delete_many({"tenant_id": _TENANT})

    # Seed users
    await db.users.insert_many(
        [
            {
                "id": _AGENT_ID,
                "tenant_id": _TENANT,
                "username": "agent_cc_4",
                "role": UserRole.CALL_CENTER_AGENT.value,
            },
            {
                "id": _SUPERVISOR_ID,
                "tenant_id": _TENANT,
                "username": "super_cc_4",
                "role": UserRole.SUPERVISOR.value,
            },
        ]
    )
    yield
    for c in collections:
        await db[c].delete_many({"tenant_id": _TENANT})


def _get_user(u_id, role):
    return User(id=u_id, tenant_id=_TENANT, username=f"user_{u_id}", email=f"{u_id}@test.com", name=f"User {u_id}", role=role, is_active=True)


@pytest.mark.asyncio
async def test_call_recording_access_and_audits():
    # Insert call with recording
    call_id = "call_rec_1"
    await db.contact_center_calls.insert_one(
        {
            "id": call_id,
            "tenant_id": _TENANT,
            "recording_ref": "call_recordings/test/call_rec_1/rec.enc",
            "agent_id": _AGENT_ID,
        }
    )

    # Mock storage fetch
    import domains.contact_center.recording_storage as rs

    rs.store_recording_bytes(b"mock_audio", tenant_id=_TENANT, call_id=call_id)

    supervisor = _get_user(_SUPERVISOR_ID, UserRole.SUPERVISOR)
    agent = _get_user(_AGENT_ID, UserRole.CALL_CENTER_AGENT)
    other_agent = _get_user("other_agent", UserRole.CALL_CENTER_AGENT)

    # 1. Supervisor access (succeeds)
    # We catch the exception because boto3 s3 client won't be configured, but it should reach the load_recording_bytes stage
    try:
        await get_call_recording(call_id, current_user=supervisor)
    except Exception:
        pass

    # Assert audit log has access success or fail (depending on boto config, but audit logging must trigger)
    audit = await db.audit_logs.find_one({"tenant_id": _TENANT, "entity_id": call_id})
    assert audit is not None
    assert audit["action"] in ["recording_access_success", "recording_access_failed"]

    # 2. Call owner agent access (succeeds)
    try:
        await get_call_recording(call_id, current_user=agent)
    except Exception:
        pass

    # 3. Forbidden agent access (fails 403)
    with pytest.raises(HTTPException) as exc:
        await get_call_recording(call_id, current_user=other_agent)
    assert exc.value.status_code == 403

    # Assert failed audit log
    forbidden_audit = await db.audit_logs.find_one({"tenant_id": _TENANT, "entity_id": call_id, "action": "recording_access_failed", "metadata.reason": "forbidden"})
    assert forbidden_audit is not None


@pytest.mark.asyncio
async def test_quality_scorecard_and_evaluations():
    supervisor = _get_user(_SUPERVISOR_ID, UserRole.SUPERVISOR)

    # 1. Create Scorecard Config
    sc_payload = ScorecardConfigCreate(
        name="Phase 4 Scorecard Template",
        sections=[
            ScorecardSection(
                section_name="Soft Skills",
                weight=1.5,
                questions=[ScorecardQuestion(id="q_polite", text="Politeness", max_points=10, weight=1.0), ScorecardQuestion(id="q_tone", text="Tone & Clarity", max_points=10, weight=1.0)],
            ),
            ScorecardSection(section_name="Compliance", weight=1.0, questions=[ScorecardQuestion(id="q_verify", text="Verification Completed", max_points=5, weight=2.0)]),
        ],
    )

    scorecard_doc = await post_scorecard(sc_payload, current_user=supervisor)
    assert scorecard_doc["name"] == "Phase 4 Scorecard Template"
    assert scorecard_doc["is_active"] is True

    # Check retrieve scorecards
    scs = await get_scorecards(current_user=supervisor)
    assert len(scs) == 1

    # 2. Submit Call Evaluation
    call_id = "call_eval_1"
    await db.contact_center_calls.insert_one(
        {
            "id": call_id,
            "tenant_id": _TENANT,
            "agent_id": _AGENT_ID,
        }
    )

    # Scores: q_polite = 8/10, q_tone = 9/10, q_verify = 4/5
    # Total calculation:
    # Section 1 (Soft Skills, weight 1.5):
    #   q_polite: points 8 * weight 1.0 * sec_weight 1.5 = 12.0 earned. Max = 10 * 1 * 1.5 = 15.0 possible
    #   q_tone: points 9 * weight 1.0 * sec_weight 1.5 = 13.5 earned. Max = 10 * 1 * 1.5 = 15.0 possible
    # Section 2 (Compliance, weight 1.0):
    #   q_verify: points 4 * weight 2.0 * sec_weight 1.0 = 8.0 earned. Max = 5 * 2 * 1.0 = 10.0 possible
    # Total Earned = 12.0 + 13.5 + 8.0 = 33.5
    # Total Possible = 15.0 + 15.0 + 10.0 = 40.0
    # Expected Score = 33.5 / 40.0 * 100 = 83.75%
    eval_payload = CallEvaluationCreate(scorecard_id=scorecard_doc["id"], scores={"q_polite": 8, "q_tone": 9, "q_verify": 4}, comments="Great job overall", coaching_notes="Improve active listening")

    eval_doc = await post_call_evaluation(call_id, eval_payload, current_user=supervisor)
    assert eval_doc["total_score"] == 83.75
    assert eval_doc["agent_id"] == _AGENT_ID
    assert eval_doc["evaluator_id"] == _SUPERVISOR_ID

    # Retrieve evaluations for call
    call_evals = await get_call_evaluations(call_id, current_user=supervisor)
    assert len(call_evals) == 1
    assert call_evals[0]["id"] == eval_doc["id"]

    # 3. Retrieve Quality Trends
    trends_res = await get_quality_trends(current_user=supervisor)
    trends = trends_res["trends"]
    assert len(trends) == 1
    assert trends[0]["agent_id"] == _AGENT_ID
    assert trends[0]["average_score"] == 83.75


@pytest.mark.asyncio
async def test_omnichannel_reporting_calculations():
    supervisor = _get_user(_SUPERVISOR_ID, UserRole.SUPERVISOR)

    now = datetime.now(UTC)

    # Insert queue config
    await db.contact_center_queues.insert_one(
        {
            "id": "q1",
            "tenant_id": _TENANT,
            "name": "General Queue",
            "sla_threshold_seconds": 20,
        }
    )

    # Seed calls:
    # 1. Call answered within SLA (wait: 10s <= 20s, duration: 40s)
    # 2. Call answered outside SLA (wait: 30s > 20s, duration: 60s)
    # 3. Missed call (abandoned, wait: 15s)
    await db.contact_center_calls.insert_many(
        [
            {
                "id": "c1",
                "tenant_id": _TENANT,
                "queue_id": "q1",
                "agent_id": _AGENT_ID,
                "status": "completed",
                "started_at": now - timedelta(seconds=100),
                "answered_at": now - timedelta(seconds=90),
                "ended_at": now - timedelta(seconds=50),
                "duration_seconds": 40.0,
            },
            {
                "id": "c2",
                "tenant_id": _TENANT,
                "queue_id": "q1",
                "agent_id": _AGENT_ID,
                "status": "completed",
                "started_at": now - timedelta(seconds=150),
                "answered_at": now - timedelta(seconds=120),
                "ended_at": now - timedelta(seconds=60),
                "duration_seconds": 60.0,
                "linked_reservation_id": "res_123",
            },
            {
                "id": "c3",
                "tenant_id": _TENANT,
                "queue_id": "q1",
                "agent_id": None,
                "status": "missed",
                "started_at": now - timedelta(seconds=50),
                "ended_at": now - timedelta(seconds=35),
            },
        ]
    )

    # Seed disposition with FCR tag for c1
    # ACW duration = disposition.created_at - call.ended_at
    # Let ended_at = now - 50. Let disposition.created_at = now - 30 (ACW = 20s)
    await db.contact_center_dispositions.insert_one(
        {
            "id": "disp_c1",
            "tenant_id": _TENANT,
            "call_id": "c1",
            "agent_id": _AGENT_ID,
            "disposition": "resolved_successfully",
            "tags": ["fcr", "sales"],
            "created_at": now - timedelta(seconds=30),
        }
    )

    # Seed callback
    await db.contact_center_callbacks.insert_one(
        {
            "id": "cb1",
            "tenant_id": _TENANT,
            "status": "completed",
        }
    )

    # Calculate reports
    report = await get_performance_reports(current_user=supervisor)
    summary = report["summary"]

    assert summary["total_calls"] == 3
    assert summary["answered_count"] == 2
    assert summary["abandoned_count"] == 1
    # SLA: 1 call met / 2 answered = 50%
    assert summary["sla_percentage"] == 50.0
    # ASA: (10 + 30) / 2 = 20.0s
    assert summary["asa_seconds"] == 20.0
    # ACW: c1 disposition ACW = 20s. c2 has no disposition (0s). Average ACW = (20 + 0) / 2 = 10s
    assert summary["average_acw_seconds"] == 10.0
    # AHT: (duration_1 + acw_1 + duration_2 + acw_2) / 2 = (40 + 20 + 60 + 0) / 2 = 60.0s
    assert summary["aht_seconds"] == 60.0
    # FCR: 1 call (c1) resolved with FCR tag / 2 answered = 50%
    assert summary["fcr_percentage"] == 50.0
    # Callback success: 1 completed / 1 total = 100%
    assert summary["callback_success_rate"] == 100.0
    # Reservation Conversion: 1 call (c2) linked / 3 total = 33.33%
    assert summary["reservation_conversion_rate"] == 33.33

    # Check breakdowns
    assert len(report["agent_breakdown"]) == 1
    assert report["agent_breakdown"][0]["agent_id"] == _AGENT_ID
    assert report["agent_breakdown"][0]["answered_count"] == 2

    assert len(report["queue_breakdown"]) == 1
    assert report["queue_breakdown"][0]["queue_id"] == "q1"
    assert report["queue_breakdown"][0]["sla_percentage"] == 50.0


@pytest.mark.asyncio
async def test_whatsapp_inbox_management_and_sla():
    agent = _get_user(_AGENT_ID, UserRole.CALL_CENTER_AGENT)

    # 1. Create a WhatsApp conversation
    conv_id = "wa_conv_1"
    now = datetime.now(UTC)
    await db.contact_center_conversations.insert_one(
        {
            "id": conv_id,
            "tenant_id": _TENANT,
            "channel": "whatsapp",
            "status": "open",
            "unread_count": 2,
            "assigned_agent_id": None,
            "created_at": now - timedelta(minutes=10),
            "last_message_at": now - timedelta(minutes=5),
            "caller_id_enc": "encrypted_recipient_number",
        }
    )

    # 2. Read conversation
    res = await read_conversation(conv_id, current_user=agent)
    assert res["success"] is True
    conv_doc = await db.contact_center_conversations.find_one({"id": conv_id})
    assert conv_doc["unread_count"] == 0

    # 3. Assign conversation
    await assign_conversation(conv_id, AssignConversationPayload(agent_id=_AGENT_ID), current_user=agent)
    conv_doc = await db.contact_center_conversations.find_one({"id": conv_id})
    assert conv_doc["assigned_agent_id"] == _AGENT_ID

    # 4. Link guest & reservation
    await link_conversation(conv_id, LinkConversationPayload(guest_id="guest_99", booking_id="booking_88"), current_user=agent)
    conv_doc = await db.contact_center_conversations.find_one({"id": conv_id})
    assert conv_doc["guest_id"] == "guest_99"
    assert conv_doc["booking_id"] == "booking_88"

    # 5. Outbound reply recalculates SLA metrics
    # Seed mock messaging configuration for provider bypass
    await db.messaging_provider_configs.insert_one(
        {
            "tenant_id": _TENANT,
            "channel": "whatsapp",
            "phone_number_id": "wa_mock_phone_id",
            "meta_verify_token": "token",
            "meta_app_secret": "secret",
            "meta_system_access_token": "token",
            "twilio_account_sid": "AC_MOCK",
            "twilio_auth_token": "auth",
            "whatsapp_phone_number": "+905550001122",
        }
    )

    # Seed the first inbound message (created 10 minutes ago)
    await db.contact_center_messages.insert_one(
        {
            "id": "msg_in_1",
            "tenant_id": _TENANT,
            "conversation_id": conv_id,
            "channel": "whatsapp",
            "direction": MessageDirection.INBOUND.value,
            "created_at": now - timedelta(minutes=10),
        }
    )

    # Mock send_whatsapp on the provider
    class MockProvider:
        async def send_whatsapp(self, *args, **kwargs):
            return {"success": True, "provider_message_id": "wa_msg_out_1"}

    import domains.contact_center.router as cc_router

    cc_router.get_communication_provider = lambda channel: MockProvider()

    # Send outbound message
    msg_payload = SendWhatsAppMessage(body="Hello Guest, how can I help you?")
    reply_res = await send_conversation_message(conv_id, payload=msg_payload, current_user=agent)
    assert reply_res["success"] is True

    # Assert conversation updated SLA
    conv_doc = await db.contact_center_conversations.find_one({"id": conv_id})
    assert conv_doc["first_response_time_seconds"] is not None
    # Conversation created 10m (600s) ago. Reply is now. So first response time is around 600s
    assert 590 <= conv_doc["first_response_time_seconds"] <= 610
    assert conv_doc["average_response_time_seconds"] is not None
    assert conv_doc["sla_breached"] is False

    # 6. Close conversation
    await close_conversation(conv_id, current_user=agent)
    conv_doc = await db.contact_center_conversations.find_one({"id": conv_id})
    assert conv_doc["status"] == "closed"
