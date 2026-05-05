"""CapX inbound match.created / match.cancelled webhook unit tests.

Spec PMS_INCELEME_RAPORU.md §1-6 davranışlarının testi:
  - HMAC-SHA256 imza doğrulama (raw body üzerinden) — geçersiz imza 401
  - Idempotency: aynı X-CapX-Event-Id 200 + duplicate=True
  - direction=incoming → bookings koleksiyonuna confirmed rezervasyon
  - direction=outgoing → capx_outgoing_transfers koleksiyonuna log
  - match.cancelled (incoming) → mevcut booking cancelled
  - match.cancelled (outgoing) → outgoing transfer status=cancelled

Mock yaklaşımı: handler fonksiyonlarını AsyncMock'lı bir db ile çağırıp
saf birim test yapılır; gerçek MongoDB veya FastAPI client gerekli değil.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ── Helpers ──────────────────────────────────────────────────────

TENANT_ID = "5bad4a34-6ee3-4566-9053-741b7375a9cf"
SECRET = "test-secret-abc"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _match_payload(
    *, direction: str = "incoming", match_id: str | None = None,
    status: str = "active", cancelled: bool = False,
) -> dict:
    mid = match_id or str(uuid.uuid4())
    return {
        "event_type": "match.cancelled" if cancelled else "match.created",
        "occurred_at": "2026-05-05T09:18:42+00:00",
        "match": {
            "id": mid,
            "reference_code": f"SPC-2026-{mid[:5]}",
            "status": "cancelled" if cancelled else status,
            "direction": direction,
            "fee_amount": 0,
            "currency": "TRY",
            "accepted_at": "2026-05-05T09:18:41+00:00",
            "cancelled_at": "2026-05-05T09:19:55+00:00" if cancelled else None,
            "cancel_reason": "müşteri iptal etti" if cancelled else None,
            "counterparty_hotel": {
                "id": "h-other", "name": "GuestHotelXYZ",
                "region": "Sapanca", "micro_location": "Kırkpınar",
                "phone": "5559876543", "contact_person": "B Owner",
            },
            "listing": {
                "id": "l-1", "concept": "Çift Kişilik",
                "region": "Sapanca", "micro_location": "Sapanca Merkez",
                "date_start": "2026-05-15T00:00:00+00:00",
                "date_end": "2026-05-17T00:00:00+00:00",
                "nights": 2, "pax": 2, "capacity_label": "DBL",
                "price_min": 1000, "price_max": 2000,
                "pms_external_ref": None,
            },
        },
    }


# ── HMAC verify (lib-level) ──────────────────────────────────────

def test_verify_accepts_valid_signature():
    from routers.capx_webhook import _verify
    body = json.dumps({"x": 1}).encode()
    assert _verify(body, SECRET, _sign(body)) is True


def test_verify_rejects_wrong_signature():
    from routers.capx_webhook import _verify
    body = json.dumps({"x": 1}).encode()
    assert _verify(body, SECRET, "sha256=" + "0" * 64) is False


def test_verify_rejects_missing_signature():
    from routers.capx_webhook import _verify
    body = b'{}'
    assert _verify(body, SECRET, None) is False
    assert _verify(body, SECRET, "") is False


def test_verify_rejects_empty_secret():
    from routers.capx_webhook import _verify
    body = b'{}'
    assert _verify(body, "", _sign(body)) is False


def test_verify_signature_is_body_byte_sensitive():
    """Spec §3 uyarısı: re-serialize edip imza hesaplamak HMAC'i bozmalı."""
    from routers.capx_webhook import _verify
    body1 = b'{"a":1,"b":2}'
    body2 = b'{"b":2,"a":1}'  # aynı obje, farklı byte sırası
    sig1 = _sign(body1)
    assert _verify(body1, SECRET, sig1) is True
    assert _verify(body2, SECRET, sig1) is False


# ── handle_match_created ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_match_created_incoming_creates_booking():
    from integrations.capx import inbound_match

    mock_db = MagicMock()
    mock_db.bookings.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=None)

    created_booking = {"id": "new-booking-uuid", "status": "confirmed"}
    mock_create = AsyncMock(return_value=created_booking)

    with patch.object(inbound_match, "db", mock_db), \
         patch.object(
             inbound_match.ReservationService, "create_reservation", mock_create
         ):
        payload = _match_payload(direction="incoming")
        result = await inbound_match.handle_match_created(
            tenant_id=TENANT_ID, payload=payload,
        )

    assert result["handled"] is True
    assert result["action"] == "booking_created"
    assert result["direction"] == "incoming"
    assert result["booking_id"] == "new-booking-uuid"

    # ReservationService doğru argümanlarla çağrıldı mı
    mock_create.assert_awaited_once()
    call_args = mock_create.call_args
    assert call_args.args[0] == TENANT_ID
    booking_data = call_args.args[1]
    assert booking_data["channel"] == "capx"
    assert booking_data["origin"] == "capx"
    assert booking_data["status"] == "confirmed"
    assert booking_data["adults"] == 2
    assert booking_data["nights"] == 2
    assert booking_data["capx_match_id"] == payload["match"]["id"]
    assert booking_data["capx_direction"] == "incoming"
    assert booking_data["room_type"] == "DBL"


@pytest.mark.asyncio
async def test_match_created_incoming_idempotent_when_booking_exists():
    from integrations.capx import inbound_match

    existing = {"id": "existing-uuid", "capx_match_id": "m1"}
    mock_db = MagicMock()
    mock_db.bookings.find_one = AsyncMock(return_value=existing)

    mock_create = AsyncMock()
    with patch.object(inbound_match, "db", mock_db), \
         patch.object(
             inbound_match.ReservationService, "create_reservation", mock_create
         ):
        payload = _match_payload(direction="incoming", match_id="m1")
        result = await inbound_match.handle_match_created(
            tenant_id=TENANT_ID, payload=payload,
        )

    assert result["action"] == "noop_existing_booking"
    assert result["booking_id"] == "existing-uuid"
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_match_created_outgoing_logs_transfer_only():
    from integrations.capx import inbound_match

    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.insert_one = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection

    mock_create = AsyncMock()
    with patch.object(inbound_match, "db", mock_db), \
         patch.object(
             inbound_match.ReservationService, "create_reservation", mock_create
         ):
        payload = _match_payload(direction="outgoing")
        result = await inbound_match.handle_match_created(
            tenant_id=TENANT_ID, payload=payload,
        )

    assert result["handled"] is True
    assert result["action"] == "outgoing_logged"
    assert result["direction"] == "outgoing"
    mock_create.assert_not_awaited()
    mock_collection.insert_one.assert_awaited_once()
    inserted = mock_collection.insert_one.await_args.args[0]
    assert inserted["tenant_id"] == TENANT_ID
    assert inserted["status"] == "active"
    assert inserted["capx_match_id"] == payload["match"]["id"]


@pytest.mark.asyncio
async def test_match_created_invalid_direction_raises():
    from integrations.capx import inbound_match

    payload = _match_payload(direction="incoming")
    payload["match"]["direction"] = "sideways"
    with pytest.raises(ValueError, match="invalid direction"):
        await inbound_match.handle_match_created(
            tenant_id=TENANT_ID, payload=payload,
        )


@pytest.mark.asyncio
async def test_match_created_missing_match_raises():
    from integrations.capx import inbound_match
    with pytest.raises(ValueError, match="payload.match"):
        await inbound_match.handle_match_created(
            tenant_id=TENANT_ID, payload={"event_type": "match.created"},
        )


# ── handle_match_cancelled ───────────────────────────────────────

@pytest.mark.asyncio
async def test_match_cancelled_incoming_cancels_booking():
    from integrations.capx import inbound_match

    existing = {"id": "bk-1", "status": "confirmed", "capx_match_id": "m-cancel"}
    mock_db = MagicMock()
    mock_db.bookings.find_one = AsyncMock(return_value=existing)

    mock_cancel = AsyncMock(return_value=True)
    with patch.object(inbound_match, "db", mock_db), \
         patch.object(
             inbound_match.ReservationService, "cancel_reservation", mock_cancel
         ):
        payload = _match_payload(
            direction="incoming", match_id="m-cancel", cancelled=True,
        )
        result = await inbound_match.handle_match_cancelled(
            tenant_id=TENANT_ID, payload=payload,
        )

    assert result["action"] == "booking_cancelled"
    assert result["booking_id"] == "bk-1"
    mock_cancel.assert_awaited_once()
    args = mock_cancel.call_args
    assert args.args[0] == TENANT_ID
    assert args.args[1] == "bk-1"
    assert "müşteri iptal etti" in args.kwargs.get("reason", "")


@pytest.mark.asyncio
async def test_match_cancelled_incoming_noop_when_no_booking():
    from integrations.capx import inbound_match

    mock_db = MagicMock()
    mock_db.bookings.find_one = AsyncMock(return_value=None)

    mock_cancel = AsyncMock()
    with patch.object(inbound_match, "db", mock_db), \
         patch.object(
             inbound_match.ReservationService, "cancel_reservation", mock_cancel
         ):
        payload = _match_payload(
            direction="incoming", match_id="m-missing", cancelled=True,
        )
        result = await inbound_match.handle_match_cancelled(
            tenant_id=TENANT_ID, payload=payload,
        )

    assert result["action"] == "noop_no_booking"
    mock_cancel.assert_not_awaited()


@pytest.mark.asyncio
async def test_match_cancelled_incoming_noop_on_terminal_status():
    """Booking zaten checked_out/cancelled ise tekrar iptal yok."""
    from integrations.capx import inbound_match

    existing = {"id": "bk-done", "status": "checked_out", "capx_match_id": "m-x"}
    mock_db = MagicMock()
    mock_db.bookings.find_one = AsyncMock(return_value=existing)

    mock_cancel = AsyncMock()
    with patch.object(inbound_match, "db", mock_db), \
         patch.object(
             inbound_match.ReservationService, "cancel_reservation", mock_cancel
         ):
        payload = _match_payload(
            direction="incoming", match_id="m-x", cancelled=True,
        )
        result = await inbound_match.handle_match_cancelled(
            tenant_id=TENANT_ID, payload=payload,
        )

    assert result["action"] == "noop_terminal_status"
    assert result["current_status"] == "checked_out"
    mock_cancel.assert_not_awaited()


@pytest.mark.asyncio
async def test_match_cancelled_outgoing_marks_transfer_cancelled():
    from integrations.capx import inbound_match

    update_result = MagicMock(modified_count=1)
    mock_collection = MagicMock()
    mock_collection.update_one = AsyncMock(return_value=update_result)
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_collection

    with patch.object(inbound_match, "db", mock_db):
        payload = _match_payload(
            direction="outgoing", match_id="m-out", cancelled=True,
        )
        result = await inbound_match.handle_match_cancelled(
            tenant_id=TENANT_ID, payload=payload,
        )

    assert result["action"] == "outgoing_cancelled"
    mock_collection.update_one.assert_awaited_once()
    filt = mock_collection.update_one.await_args.args[0]
    upd = mock_collection.update_one.await_args.args[1]["$set"]
    assert filt == {"tenant_id": TENANT_ID, "capx_match_id": "m-out"}
    assert upd["status"] == "cancelled"
    assert upd["cancel_reason"] == "müşteri iptal etti"


# ── Booking payload mapping ──────────────────────────────────────

def test_booking_payload_uses_price_max_when_present():
    from integrations.capx.inbound_match import _booking_payload_from_match
    match = _match_payload()["match"]
    bd = _booking_payload_from_match(match)
    assert bd["total_amount"] == 2000
    assert bd["base_rate"] == 1000


def test_booking_payload_falls_back_to_price_min_when_no_max():
    from integrations.capx.inbound_match import _booking_payload_from_match
    match = _match_payload()["match"]
    match["listing"]["price_max"] = None
    bd = _booking_payload_from_match(match)
    assert bd["total_amount"] == 1000


def test_booking_payload_uses_contact_person_or_name_for_guest():
    from integrations.capx.inbound_match import _booking_payload_from_match
    match = _match_payload()["match"]
    assert _booking_payload_from_match(match)["guest_name"] == "B Owner"
    match["counterparty_hotel"]["contact_person"] = None
    assert _booking_payload_from_match(match)["guest_name"] == "GuestHotelXYZ"
    match["counterparty_hotel"]["name"] = None
    assert _booking_payload_from_match(match)["guest_name"] == "CapX Misafir"


# ── Callback URL builder ─────────────────────────────────────────

def test_build_callback_url_uses_public_base_url(monkeypatch):
    from routers.capx_integration import _build_callback_url
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://pms.example.com")
    monkeypatch.delenv("REPLIT_DEV_DOMAIN", raising=False)
    assert _build_callback_url(TENANT_ID) == (
        f"https://pms.example.com/api/webhooks/capx/by-tenant/{TENANT_ID}"
    )


def test_build_callback_url_fallback_to_replit_dev_domain(monkeypatch):
    from routers.capx_integration import _build_callback_url
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("REPLIT_DEV_DOMAIN", "abc-123.replit.dev")
    assert _build_callback_url(TENANT_ID) == (
        f"https://abc-123.replit.dev/api/webhooks/capx/by-tenant/{TENANT_ID}"
    )
