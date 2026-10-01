from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from domains.guest import operations_router
from models.schemas import LoyaltyTransactionCreate


def _user():
    return SimpleNamespace(tenant_id="tenant-a", id="user-a")


def test_loyalty_transaction_schema_rejects_invalid_points_and_type():
    with pytest.raises(ValidationError):
        LoyaltyTransactionCreate(guest_id="guest-a", points=0, transaction_type="earned", description="bonus")
    with pytest.raises(ValidationError):
        LoyaltyTransactionCreate(guest_id="guest-a", points=10, transaction_type="other", description="bonus")


@pytest.mark.asyncio
async def test_redeem_rejects_insufficient_balance_without_recording_transaction():
    programs = MagicMock()
    programs.find_one = AsyncMock(return_value={"guest_id": "guest-a", "points": 20})
    programs.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=0))
    transactions = MagicMock(insert_one=AsyncMock())
    audit_logs = MagicMock(insert_one=AsyncMock())
    fake_db = MagicMock(loyalty_programs=programs, loyalty_transactions=transactions, audit_logs=audit_logs)

    with patch.object(operations_router, "db", fake_db):
        with pytest.raises(operations_router.HTTPException) as exc:
            await operations_router.create_loyalty_transaction(
                LoyaltyTransactionCreate(
                    guest_id="guest-a",
                    points=50,
                    transaction_type="redeemed",
                    description="Ödül kullanımı",
                ),
                current_user=_user(),
            )

    assert exc.value.status_code == 400
    transactions.insert_one.assert_not_awaited()
    audit_logs.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_earned_points_update_balance_and_write_audit_log():
    programs = MagicMock()
    programs.find_one = AsyncMock(return_value={"guest_id": "guest-a", "points": 20})
    programs.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
    transactions = MagicMock(insert_one=AsyncMock())
    audit_logs = MagicMock(insert_one=AsyncMock())
    fake_db = MagicMock(loyalty_programs=programs, loyalty_transactions=transactions, audit_logs=audit_logs)

    with patch.object(operations_router, "db", fake_db):
        result = await operations_router.create_loyalty_transaction(
            LoyaltyTransactionCreate(
                guest_id="guest-a",
                points=50,
                transaction_type="earned",
                description="Konaklama bonusu",
            ),
            current_user=_user(),
        )

    assert result.points == 50
    update = programs.update_one.await_args.args[1]
    assert update["$inc"] == {"points": 50, "lifetime_points": 50}
    transactions.insert_one.assert_awaited_once()
    audit_logs.insert_one.assert_awaited_once()
