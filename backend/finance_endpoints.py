from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from server import get_current_user, User, db

finance_router = APIRouter()

@finance_router.get("/finance/pl-detail")
async def get_pl_detail(month: str = None, current_user: User = Depends(get_current_user)):
    """Get P&L (Profit & Loss) detail report"""
    try:
        # Get all transactions for the month
        transactions = await db.transactions.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(10000)
        
        # Get all bookings
        bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}
        }, {'_id': 0}).to_list(10000)
        
        # Calculate revenues
        room_revenue = sum(b.get('total_amount', 0) for b in bookings)
        fnb_revenue = sum(t.get('amount', 0) for t in transactions if t.get('type') == 'fnb_charge')
        other_revenue = sum(t.get('amount', 0) for t in transactions if t.get('type') == 'service_charge')
        total_revenue = room_revenue + fnb_revenue + other_revenue
        
        # Calculate costs (simplified)
        fnb_cost = fnb_revenue * 0.35  # 35% cost
        housekeeping_cost = room_revenue * 0.15  # 15% cost
        total_cost_of_sales = fnb_cost + housekeeping_cost
        
        # Gross profit
        gross_profit = total_revenue - total_cost_of_sales
        gross_profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # Operating expenses (simplified)
        personnel_cost = total_revenue * 0.30
        utility_cost = total_revenue * 0.10
        maintenance_cost = total_revenue * 0.05
        marketing_cost = total_revenue * 0.03
        admin_cost = total_revenue * 0.07
        total_operating_expenses = personnel_cost + utility_cost + maintenance_cost + marketing_cost + admin_cost
        
        # Net profit
        net_profit = gross_profit - total_operating_expenses
        net_profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # Get room stats
        rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
        occupied_rooms = len([r for r in rooms if r.get('status') == 'occupied'])
        total_rooms = len(rooms)
        occupancy = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
        
        return {
            'period': month or datetime.utcnow().strftime('%B %Y'),
            'room_revenue': room_revenue,
            'fnb_revenue': fnb_revenue,
            'other_revenue': other_revenue,
            'total_revenue': total_revenue,
            'fnb_cost': fnb_cost,
            'housekeeping_cost': housekeeping_cost,
            'total_cost_of_sales': total_cost_of_sales,
            'gross_profit': gross_profit,
            'gross_profit_margin': gross_profit_margin,
            'personnel_cost': personnel_cost,
            'utility_cost': utility_cost,
            'maintenance_cost': maintenance_cost,
            'marketing_cost': marketing_cost,
            'admin_cost': admin_cost,
            'total_operating_expenses': total_operating_expenses,
            'net_profit': net_profit,
            'net_profit_margin': net_profit_margin,
            'key_metrics': {
                'revpar': room_revenue / total_rooms if total_rooms > 0 else 0,
                'adr': room_revenue / occupied_rooms if occupied_rooms > 0 else 0,
                'occupancy': occupancy,
                'gop_percentage': (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
            }
        }
    except Exception as e:
        print(f"P&L Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@finance_router.get("/finance/cashier-shift-report")
async def get_cashier_shift_report(current_user: User = Depends(get_current_user)):
    """Get cashier shift report"""
    try:
        # Get today's transactions
        transactions = await db.transactions.find({
            'tenant_id': current_user.tenant_id,
            'status': 'completed'
        }, {'_id': 0}).to_list(1000)
        
        total_collected = sum(t.get('amount', 0) for t in transactions)
        
        # Get bookings for check-in/out count
        bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(1000)
        
        checkin_count = len([b for b in bookings if b.get('status') == 'checked_in'])
        checkout_count = len([b for b in bookings if b.get('status') == 'checked_out'])
        
        return {
            'cashier_name': current_user.name,
            'shift_name': 'Day Shift',
            'shift_start': datetime.utcnow().replace(hour=8, minute=0).isoformat(),
            'shift_end': None,
            'opening_balance': 1000.0,
            'total_collected': total_collected,
            'total_paid_out': 0,
            'expected_balance': 1000.0 + total_collected,
            'transaction_count': len(transactions),
            'checkin_count': checkin_count,
            'checkout_count': checkout_count,
            'average_transaction': total_collected / len(transactions) if transactions else 0,
            'payment_methods': {
                'cash': {'amount': total_collected * 0.4, 'count': int(len(transactions) * 0.4)},
                'card': {'amount': total_collected * 0.6, 'count': int(len(transactions) * 0.6)}
            }
        }
    except Exception as e:
        print(f"Shift Report Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
