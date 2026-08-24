from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domains.guest import loyalty_router


def _user():
    return SimpleNamespace(tenant_id="tenant-a", id="user-a", email="admin@example.com")


@pytest.mark.asyncio
async def test_earn_uses_atomic_increment_and_completes_idempotency():
    members = MagicMock()
    members.find_one = AsyncMock(
        side_effect=[
            {"guest_id": "guest-a", "points_balance": 100, "points_lifetime": 100},
            {"guest_id": "guest-a", "points_balance": 150, "points_lifetime": 150, "tier_name": "Mini"},
        ]
    )
    members.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
    transactions = MagicMock()
    transactions.insert_one = AsyncMock()
    fake_db = MagicMock(loyalty_members=members, loyalty_transactions=transactions)
    fake_guard = SimpleNamespace(complete=AsyncMock(), release=AsyncMock())

    with (
        patch.object(loyalty_router, "_ensure_indexes", new=AsyncMock()),
        patch.object(loyalty_router, "get_system_db", return_value=fake_db),
        patch.object(loyalty_router, "_resolve_tier", new=AsyncMock(return_value=None)),
        patch.object(loyalty_router, "begin_idempotency", new=AsyncMock(return_value=(fake_guard, None))),
    ):
        result = await loyalty_router.earn_points(
            request=MagicMock(),
            body=loyalty_router.EarnBody(guest_id="guest-a", points=50, source="manual"),
            user=_user(),
        )

    update = members.update_one.await_args_list[0].args[1]
    assert update == {"$inc": {"points_balance": 50, "points_lifetime": 50}}
    assert result == {"awarded": 50, "balance": 150, "tier": "Mini"}
    fake_guard.complete.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_redeem_restores_points_when_stock_is_lost_concurrently():
    rewards = MagicMock()
    rewards.find_one = AsyncMock(return_value={
        "id": "reward-a", "name": "Upgrade", "points_cost": 500, "stock": 1,
    })
    rewards.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=0))
    members = MagicMock()
    members.find_one = AsyncMock(return_value={"guest_id": "guest-a", "points_balance": 1000})
    members.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
    fake_db = MagicMock(
        loyalty_rewards=rewards,
        loyalty_members=members,
        loyalty_redemptions=MagicMock(),
    )
    fake_db.loyalty_redemptions.find_one = AsyncMock(return_value=None)
    fake_guard = SimpleNamespace(complete=AsyncMock(), release=AsyncMock())

    with (
        patch.object(loyalty_router, "_ensure_indexes", new=AsyncMock()),
        patch.object(loyalty_router, "get_system_db", return_value=fake_db),
        patch.object(loyalty_router, "get_idempotency_key", return_value="retry-key"),
        patch.object(loyalty_router, "begin_idempotency", new=AsyncMock(return_value=(fake_guard, None))),
    ):
        with pytest.raises(Exception) as exc:
            await loyalty_router.redeem_reward(
                request=MagicMock(),
                body=loyalty_router.RedeemBody(guest_id="guest-a", reward_id="reward-a"),
                user=_user(),
            )

    assert getattr(exc.value, "status_code", None) == 409
    assert members.update_one.await_count == 2
    compensation = members.update_one.await_args_list[1].args[1]
    assert compensation == {"$inc": {"points_balance": 500}}
    fake_guard.release.assert_awaited_once()
