from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.platform_scaling import multi_property_platform as service_module
from routers import platform_scaling as router_module


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _length):
        return self.rows


def _collection(*, find_one=None, find_rows=None, count=0, modified_count=1):
    return SimpleNamespace(
        find_one=AsyncMock(return_value=find_one),
        find=lambda *_args, **_kwargs: _Cursor(find_rows or []),
        count_documents=AsyncMock(return_value=count),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=modified_count)),
        insert_one=AsyncMock(),
        delete_one=AsyncMock(),
        delete_many=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_chain_transfer_creates_target_booking_then_closes_source(monkeypatch):
    source_booking = {
        "id": "source-booking",
        "tenant_id": "denizli",
        "room_id": "room-101",
        "room_type": "Standard",
        "guest_name": "Test Guest",
        "check_in": "2026-10-10T14:00:00+00:00",
        "check_out": "2026-10-12T11:00:00+00:00",
        "status": "confirmed",
        "currency": "TRY",
        "total_amount": 4000,
    }
    bookings = _collection(find_one=source_booking)
    rooms = _collection(find_rows=[{"id": "room-204", "room_number": "204", "room_type": "Standard", "is_active": True}])
    fake_db = SimpleNamespace(
        bookings=bookings,
        rooms=rooms,
        folios=_collection(find_rows=[]),
        payments=_collection(),
        folio_charges=_collection(),
        extra_charges=_collection(),
        room_night_locks=_collection(),
        reservation_transfers=_collection(),
        chain_transfer_settlements=_collection(),
        reservation_activity_log=_collection(),
        notifications=_collection(),
    )
    monkeypatch.setattr(service_module, "db", fake_db)
    monkeypatch.setattr(service_module, "decrypt_booking_doc", lambda value: value)
    monkeypatch.setattr(
        service_module,
        "_properties_for_transfer_user",
        AsyncMock(return_value=("denizli", [
            {"tenant_id": "denizli", "chain_id": "chain-1", "property_name": "Denizli Oteli"},
            {"tenant_id": "fethiye", "chain_id": "chain-1", "property_name": "Fethiye Oteli"},
        ])),
    )
    atomic_create = AsyncMock(side_effect=lambda tenant_id, booking_doc: booking_doc)
    monkeypatch.setattr(service_module, "create_booking_atomic", atomic_create)

    result = await service_module.CentralReservationService().transfer_reservation(
        SimpleNamespace(id="user-1", tenant_id="denizli"),
        "source-booking",
        "fethiye",
        "Misafir talebi",
        "Standard",
    )

    assert result["success"] is True, result
    assert result["target_property_name"] == "Fethiye Oteli"
    target_payload = atomic_create.await_args.kwargs["booking_doc"]
    assert target_payload["tenant_id"] == "fethiye"
    assert target_payload["room_id"] == "room-204"
    assert target_payload["source_booking_id"] == "source-booking"
    assert target_payload["transfer_reference"].startswith("TRF-")
    source_update = bookings.update_one.await_args.args[1]["$set"]
    assert source_update["status"] == "cancelled"
    assert source_update["transferred_to_tenant_id"] == "fethiye"
    fake_db.room_night_locks.delete_many.assert_awaited_once_with({
        "booking_id": "source-booking",
        "tenant_id": "denizli",
    })
    fake_db.reservation_transfers.insert_one.assert_awaited_once()
    fake_db.chain_transfer_settlements.insert_one.assert_not_awaited()
    target_notification = fake_db.notifications.insert_one.await_args.args[0]
    assert target_notification["tenant_id"] == "fethiye"
    assert target_notification["related_id"] == result["target_booking_id"]
    assert target_payload["source_property_name"] == "Denizli Oteli"
    assert target_notification["metadata"]["transfer_reference"] == result["transfer_reference"]


@pytest.mark.asyncio
async def test_chain_transfer_rejects_booking_with_financial_activity(monkeypatch):
    fake_db = SimpleNamespace(
        bookings=_collection(find_one={
            "id": "source-booking", "tenant_id": "denizli", "status": "confirmed",
            "room_type": "Standard", "check_in": "2026-10-10", "check_out": "2026-10-12",
        }),
        folios=_collection(find_rows=[{"id": "folio-1"}]),
        payments=_collection(count=1),
        folio_charges=_collection(),
        extra_charges=_collection(),
        rooms=_collection(find_rows=[{"id": "room-204", "room_type": "Standard"}]),
    )
    monkeypatch.setattr(service_module, "db", fake_db)
    monkeypatch.setattr(service_module, "decrypt_booking_doc", lambda value: value)
    monkeypatch.setattr(
        service_module,
        "_properties_for_transfer_user",
        AsyncMock(return_value=("denizli", [
            {"tenant_id": "denizli", "chain_id": "chain-1"},
            {"tenant_id": "fethiye", "chain_id": "chain-1"},
        ])),
    )
    atomic_create = AsyncMock()
    monkeypatch.setattr(service_module, "create_booking_atomic", atomic_create)

    result = await service_module.CentralReservationService().transfer_reservation(
        SimpleNamespace(id="user-1", tenant_id="denizli"),
        "source-booking",
        "fethiye",
        "Misafir talebi",
        "Standard",
    )

    assert result["success"] is False
    assert result["error_code"] == "financial_handling_required"
    atomic_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_chain_transfer_retains_prepayment_and_creates_two_sided_settlement(monkeypatch):
    source_booking = {
        "id": "source-booking",
        "tenant_id": "denizli",
        "room_type": "Standard",
        "guest_name": "Ön Ödemeli Misafir",
        "check_in": "2026-10-10",
        "check_out": "2026-10-12",
        "status": "confirmed",
        "currency": "TRY",
    }
    fake_db = SimpleNamespace(
        bookings=_collection(find_one=source_booking),
        rooms=_collection(find_rows=[{"id": "room-204", "room_number": "204", "room_type": "Standard"}]),
        folios=_collection(find_rows=[{"id": "folio-1"}]),
        payments=_collection(
            count=1,
            find_rows=[{"id": "payment-1", "amount": 1000, "currency": "TRY", "method": "bank_transfer"}],
        ),
        folio_charges=_collection(),
        extra_charges=_collection(),
        room_night_locks=_collection(),
        reservation_transfers=_collection(),
        chain_transfer_settlements=_collection(),
        reservation_activity_log=_collection(),
        notifications=_collection(),
    )
    monkeypatch.setattr(service_module, "db", fake_db)
    monkeypatch.setattr(service_module, "decrypt_booking_doc", lambda value: value)
    monkeypatch.setattr(
        service_module,
        "_properties_for_transfer_user",
        AsyncMock(return_value=("denizli", [
            {"tenant_id": "denizli", "chain_id": "chain-1", "property_name": "Denizli Oteli"},
            {"tenant_id": "fethiye", "chain_id": "chain-1", "property_name": "Fethiye Oteli"},
        ])),
    )
    atomic_create = AsyncMock(side_effect=lambda tenant_id, booking_doc: booking_doc)
    monkeypatch.setattr(service_module, "create_booking_atomic", atomic_create)

    blocked = await service_module.CentralReservationService().transfer_reservation(
        SimpleNamespace(id="user-1", name="Merkez", tenant_id="denizli"),
        "source-booking",
        "fethiye",
        "Misafir talebi",
        "Standard",
    )
    assert blocked["error_code"] == "financial_handling_required"
    assert blocked["payment_totals"] == {"TRY": 1000.0}
    atomic_create.assert_not_awaited()

    result = await service_module.CentralReservationService().transfer_reservation(
        SimpleNamespace(id="user-1", name="Merkez", tenant_id="denizli"),
        "source-booking",
        "fethiye",
        "Misafir talebi",
        "Standard",
        "retain_and_settle",
    )

    assert result["success"] is True, result
    assert result["settlement_status"] == "open"
    settlement = fake_db.chain_transfer_settlements.insert_one.await_args.args[0]
    assert settlement["collection_property_id"] == "denizli"
    assert settlement["service_property_id"] == "fethiye"
    assert settlement["transfer_reference"] == result["transfer_reference"]
    assert settlement["currency_lines"] == [{
        "currency": "TRY",
        "amount": 1000.0,
        "source_position": "payable",
        "target_position": "receivable",
    }]
    target_payload = atomic_create.await_args.kwargs["booking_doc"]
    assert target_payload["transferred_prepayments"] == [{"currency": "TRY", "amount": 1000.0}]
    assert target_payload["transfer_reference"] == result["transfer_reference"]
    assert fake_db.notifications.insert_one.await_count == 3


@pytest.mark.asyncio
async def test_reconciliation_notifies_both_properties_with_transfer_reference(monkeypatch):
    settlement = {
        "id": "settlement-1",
        "transfer_id": "transfer-1",
        "transfer_reference": "TRF-20261002-TRANSFER",
        "status": "open",
        "source_property_id": "denizli",
        "source_property_name": "Denizli Oteli",
        "target_property_id": "fethiye",
        "target_property_name": "Fethiye Oteli",
        "source_booking_id": "source-booking",
        "target_booking_id": "target-booking",
        "currency_lines": [{"currency": "TRY", "amount": 1000}],
    }
    fake_db = SimpleNamespace(
        chain_transfer_settlements=_collection(find_one=settlement),
        reservation_transfers=_collection(),
        reservation_activity_log=_collection(),
        notifications=_collection(),
    )
    monkeypatch.setattr(router_module, "get_system_db", lambda: fake_db)
    monkeypatch.setattr(
        router_module,
        "resolve_chain_properties",
        AsyncMock(return_value=("denizli", [{"tenant_id": "denizli"}, {"tenant_id": "fethiye"}])),
    )

    result = await router_module.api_reconcile_transfer_settlement(
        "settlement-1",
        router_module.ReconcileTransferSettlementReq(method="bank_transfer", reference="DEC-100"),
        SimpleNamespace(id="finance-1", tenant_id="denizli", name="Finans"),
        None,
    )

    assert result["transfer_reference"] == "TRF-20261002-TRANSFER"
    assert fake_db.reservation_activity_log.insert_one.await_count == 2
    assert fake_db.notifications.insert_one.await_count == 2
    notifications = [call.args[0] for call in fake_db.notifications.insert_one.await_args_list]
    assert {row["tenant_id"] for row in notifications} == {"denizli", "fethiye"}
    assert all(row["metadata"]["transfer_reference"] == "TRF-20261002-TRANSFER" for row in notifications)


@pytest.mark.asyncio
async def test_transfer_reversal_restores_source_and_reverses_open_settlement(monkeypatch):
    transfer = {
        "id": "transfer-1",
        "transfer_reference": "TRF-20261003-TRANSFER",
        "status": "completed",
        "source_property": "denizli",
        "target_property": "fethiye",
        "source_booking_id": "source-booking",
        "target_booking_id": "target-booking",
        "settlement_id": "settlement-1",
        "original_booking": {"status": "confirmed"},
    }
    source_booking = {
        "id": "source-booking",
        "tenant_id": "denizli",
        "status": "cancelled",
        "transfer_id": "transfer-1",
        "room_id": "room-101",
        "check_in": "2026-10-10",
        "check_out": "2026-10-12",
    }
    target_booking = {
        "id": "target-booking",
        "tenant_id": "fethiye",
        "status": "confirmed",
        "transfer_id": "transfer-1",
    }
    bookings = _collection()
    bookings.find_one = AsyncMock(side_effect=[source_booking, target_booking])
    fake_db = SimpleNamespace(
        reservation_transfers=_collection(find_one=transfer),
        bookings=bookings,
        chain_transfer_settlements=_collection(find_one={"id": "settlement-1", "transfer_id": "transfer-1", "status": "open"}),
        room_night_locks=_collection(),
        reservation_activity_log=_collection(),
    )
    monkeypatch.setattr(service_module, "db", fake_db)
    monkeypatch.setattr(
        service_module,
        "_properties_for_transfer_user",
        AsyncMock(return_value=("denizli", [{"tenant_id": "denizli"}, {"tenant_id": "fethiye"}])),
    )
    monkeypatch.setattr(service_module, "_claim_night_or_get_owner", AsyncMock(return_value=(True, None)))

    result = await service_module.CentralReservationService().reverse_transfer(
        SimpleNamespace(id="user-1", name="Merkez", tenant_id="denizli"),
        "transfer-1",
        "Misafir tarihini değiştirdi",
    )

    assert result["success"] is True, result
    assert result["status"] == "reversed"
    assert result["settlement_status"] == "reversed"
    assert service_module._claim_night_or_get_owner.await_count == 2
    assert bookings.find_one.await_args_list[1].args[0]["transfer_id"] == "transfer-1"
    source_update = bookings.update_one.await_args_list[0]
    assert source_update.args[1]["$set"]["status"] == "confirmed"
    assert fake_db.chain_transfer_settlements.update_one.await_args.args[1]["$set"]["status"] == "reversed"
    assert fake_db.reservation_transfers.update_one.await_args.args[1]["$set"]["status"] == "reversed"
    assert fake_db.reservation_activity_log.insert_one.await_count == 2


@pytest.mark.asyncio
async def test_transfer_reversal_is_blocked_after_finance_reconciliation(monkeypatch):
    transfer = {
        "id": "transfer-1",
        "status": "completed",
        "source_property": "denizli",
        "target_property": "fethiye",
        "source_booking_id": "source-booking",
        "target_booking_id": "target-booking",
        "settlement_id": "settlement-1",
    }
    source_booking = {
        "id": "source-booking",
        "tenant_id": "denizli",
        "status": "cancelled",
        "transfer_id": "transfer-1",
    }
    target_booking = {
        "id": "target-booking",
        "tenant_id": "fethiye",
        "status": "confirmed",
        "transfer_id": "transfer-1",
    }
    bookings = _collection()
    bookings.find_one = AsyncMock(side_effect=[source_booking, target_booking])
    fake_db = SimpleNamespace(
        reservation_transfers=_collection(find_one=transfer),
        bookings=bookings,
        chain_transfer_settlements=_collection(find_one={"id": "settlement-1", "transfer_id": "transfer-1", "status": "reconciled"}),
    )
    monkeypatch.setattr(service_module, "db", fake_db)
    monkeypatch.setattr(
        service_module,
        "_properties_for_transfer_user",
        AsyncMock(return_value=("denizli", [{"tenant_id": "denizli"}, {"tenant_id": "fethiye"}])),
    )

    result = await service_module.CentralReservationService().reverse_transfer(
        SimpleNamespace(id="user-1", tenant_id="denizli"),
        "transfer-1",
        "Finansal ters fiş talebi",
    )

    assert result["success"] is False
    assert "ters muhasebe fişi" in result["error"]
    assert fake_db.bookings.find_one.await_count == 2
