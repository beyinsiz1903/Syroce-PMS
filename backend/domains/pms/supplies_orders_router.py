"""Hotel supplies orders: opt-in marketplace, not a POS/F&B product.

The bootstrap registry applies the procurement user scope. Keep the existing
API and stored order contract while enforcing separate read/write permissions.
"""

from fastapi import APIRouter, Depends

from core.database import db
from core.helpers import require_feature
from core.security import get_current_user
from models.schemas import Order, OrderCreate, User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(
    prefix="/api/marketplace/orders",
    tags=["supplies-marketplace"],
    dependencies=[Depends(require_feature("hidden_marketplace"))],
)


@router.post("", response_model=Order, dependencies=[Depends(require_op("manage_procurement"))])
async def create_order(order_data: OrderCreate, current_user: User = Depends(get_current_user)):
    order = Order(tenant_id=current_user.tenant_id, **order_data.model_dump())
    await db.orders.insert_one(order.model_dump(mode="json"))
    return order


@router.get("", response_model=list[Order], dependencies=[Depends(require_op("view_procurement"))])
async def get_orders(current_user: User = Depends(get_current_user)):
    # Read through so a newly created order is immediately visible. The old
    # five-minute cache had no invalidation after order creation.
    return await db.orders.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
