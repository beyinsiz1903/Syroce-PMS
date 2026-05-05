"""
Domain Router: HR Operations

HR complete suite, F&B complete suite for department managers.
"""
import base64
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v96 DW

router = APIRouter(prefix="/api", tags=["hr-operations"])

# ============= HR COMPLETE SUITE =============

async def _get_staff_map(tenant_id: str):
    staff = await db.staff_members.find({'tenant_id': tenant_id}, {'_id': 0}).to_list(500)
    return {member['id']: member for member in staff}


@router.post("/hr/clock-in")
async def clock_in(staff_data: dict, current_user: User = Depends(get_current_user)):
    """Personel giris kaydi"""
    record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_data['staff_id'],
        'date': date.today().isoformat(),
        'clock_in': datetime.now(UTC).isoformat(),
        'clock_out': None,
        'status': 'present',
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.attendance_records.insert_one(record)
    return {'success': True, 'message': 'Clock-in recorded', 'time': record['clock_in']}

@router.post("/hr/clock-out")
async def clock_out(staff_data: dict, current_user: User = Depends(get_current_user)):
    # v109 Bug DAK round-6 (T08 P1): cross-tenant clock-out.
    # Previously find_one filtered only by staff_id without tenant_id, so
    # tenant B could clock-out tenant A's staff by guessing/knowing staff_id.
    # Both find AND update now scope to current_user.tenant_id.
    record = await db.attendance_records.find_one({
        'tenant_id': current_user.tenant_id,
        'staff_id': staff_data['staff_id'],
        'date': date.today().isoformat(),
        'clock_out': None,
    })
    if record:
        clock_out_time = datetime.now(UTC)
        clock_in_time = datetime.fromisoformat(record['clock_in'].replace('Z', '+00:00'))
        hours = (clock_out_time - clock_in_time).total_seconds() / 3600
        await db.attendance_records.update_one(
            {'id': record['id'], 'tenant_id': current_user.tenant_id},
            {'$set': {'clock_out': clock_out_time.isoformat(), 'total_hours': round(hours, 2)}}
        )
        return {'success': True, 'hours_worked': round(hours, 2)}
    return {'success': False, 'message': 'Clock-in record not found'}

@router.post("/hr/leave-request")
async def create_leave_request(leave_data: dict, current_user: User = Depends(get_current_user)):
    # Calculate total days if not provided
    if 'total_days' not in leave_data:
        from datetime import datetime
        start = datetime.fromisoformat(leave_data['start_date'])
        end = datetime.fromisoformat(leave_data['end_date'])
        total_days = (end - start).days + 1
    else:
        total_days = leave_data['total_days']

    leave = {
        'id': str(uuid.uuid4()), 'tenant_id': current_user.tenant_id,
        'staff_id': leave_data['staff_id'], 'staff_name': leave_data.get('staff_name', 'Unknown'),
        'leave_type': leave_data['leave_type'],
        'start_date': leave_data['start_date'], 'end_date': leave_data['end_date'],
        'total_days': total_days, 'reason': leave_data.get('reason'),
        'status': 'pending', 'created_at': datetime.now(UTC).isoformat()
    }
    await db.leave_requests.insert_one(leave)
    return {'success': True, 'leave_id': leave['id'], 'total_days': total_days}

# NOTE: The dynamic `GET /hr/payroll/{month}` is intentionally declared
# AFTER `GET /hr/payroll/export` (further below) so that FastAPI matches
# the static "export" path first. Keeping the dynamic route here used to
# silently swallow the export call (month="export" → empty payroll JSON);
# see Task #133 for the route-shadowing CI guard that prevents regressions.


def _parse_date_range(start: str | None, end: str | None, days: int = 7):
    today = date.today()
    start_date = datetime.fromisoformat(start).date() if start else today - timedelta(days=days)
    end_date = datetime.fromisoformat(end).date() if end else today
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


@router.get("/hr/attendance/records")
async def get_attendance_records(
    start_date: str | None = None,
    end_date: str | None = None,
    staff_id: str | None = None,
    limit: int = 500,
    current_user: User = Depends(get_current_user)
):
    start_dt, end_dt = _parse_date_range(start_date, end_date, days=7)
    query: dict[str, Any] = {
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()}
    }
    if staff_id:
        query['staff_id'] = staff_id
    records = await db.attendance_records.find(query, {'_id': 0}).sort('clock_in', -1).limit(limit).to_list(limit)
    staff_map = await _get_staff_map(current_user.tenant_id)
    for record in records:
        staff = staff_map.get(record['staff_id'])
        if staff:
            record['staff_name'] = staff.get('name')
            record['department'] = staff.get('department')
            record['position'] = staff.get('position')
    return {
        'records': records,
        'total': len(records),
        'range': {'start': start_dt.isoformat(), 'end': end_dt.isoformat()}
    }


@router.get("/hr/attendance/summary")
async def get_attendance_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    start_dt, end_dt = _parse_date_range(start_date, end_date, days=30)
    query = {
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()}
    }
    records = await db.attendance_records.find(query, {'_id': 0}).to_list(2000)
    staff_map = await _get_staff_map(current_user.tenant_id)

    summary: dict[str, Any] = {}
    for record in records:
        staff_id = record['staff_id']
        summary.setdefault(staff_id, {
            'staff_id': staff_id,
            'total_hours': 0,
            'days_present': 0,
            'overtime_hours': 0,
            'late_count': 0
        })
        summary[staff_id]['total_hours'] += record.get('total_hours', 0)
        summary[staff_id]['days_present'] += 1

    for staff_id, data in summary.items():
        staff = staff_map.get(staff_id, {})
        data['staff_name'] = staff.get('name', staff_id)
        data['department'] = staff.get('department', 'unknown')
        data['position'] = staff.get('position', 'Staff')
        overtime_threshold = staff.get('monthly_hours', 160)
        if data['total_hours'] > overtime_threshold:
            data['overtime_hours'] = round(data['total_hours'] - overtime_threshold, 2)
        data['average_daily_hours'] = round(
            data['total_hours'] / data['days_present'], 2
        ) if data['days_present'] else 0

    summary_list = sorted(summary.values(), key=lambda x: x['staff_name'])
    total_hours = round(sum(item['total_hours'] for item in summary_list), 2)
    avg_hours = round(total_hours / len(summary_list), 2) if summary_list else 0

    return {
        'summary': summary_list,
        'range': {'start': start_dt.isoformat(), 'end': end_dt.isoformat()},
        'metrics': {
            'staff_count': len(summary_list),
            'total_hours': total_hours,
            'avg_hours_per_staff': avg_hours
        }
    }


@router.get("/hr/payroll/export")
async def export_payroll(
    month: str | None = None,
    format: str = 'json',
    current_user: User = Depends(get_current_user)
):
    today = date.today()
    if month:
        start_dt = datetime.fromisoformat(f"{month}-01").date()
    else:
        start_dt = date(today.year, today.month, 1)
    next_month = start_dt.replace(day=28) + timedelta(days=4)
    end_dt = next_month - timedelta(days=next_month.day)

    query = {
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_dt.isoformat(), '$lte': end_dt.isoformat()}
    }
    records = await db.attendance_records.find(query, {'_id': 0}).to_list(5000)
    staff_map = await _get_staff_map(current_user.tenant_id)

    payroll_rows = {}
    for record in records:
        staff_id = record['staff_id']
        payroll_rows.setdefault(staff_id, 0)
        payroll_rows[staff_id] += record.get('total_hours', 0)

    payroll = []
    for staff_id, total_hours in payroll_rows.items():
        staff = staff_map.get(staff_id, {})
        hourly_rate = staff.get('hourly_rate', 12)
        overtime_hours = max(0, total_hours - staff.get('monthly_hours', 160))
        overtime_rate = staff.get('overtime_rate', hourly_rate * 1.5)
        base_hours = total_hours - overtime_hours
        gross_pay = (base_hours * hourly_rate) + (overtime_hours * overtime_rate)
        payroll.append({
            'staff_id': staff_id,
            'staff_name': staff.get('name', staff_id),
            'department': staff.get('department', 'unknown'),
            'total_hours': round(total_hours, 2),
            'overtime_hours': round(overtime_hours, 2),
            'hourly_rate': hourly_rate,
            'overtime_rate': overtime_rate,
            'gross_pay': round(gross_pay, 2)
        })

    response = {
        'month': start_dt.strftime('%Y-%m'),
        'payroll': payroll,
        'staff_count': len(payroll),
        'total_gross_pay': round(sum(row['gross_pay'] for row in payroll), 2)
    }

    if format == 'csv':
        import csv
        from io import StringIO
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(payroll[0].keys()) if payroll else [
            'staff_id', 'staff_name', 'department', 'total_hours', 'overtime_hours',
            'hourly_rate', 'overtime_rate', 'gross_pay'
        ])
        # Bug AN: payroll rows include user-supplied staff_name etc.
        from core.csv_safe import safe_dict_writerow
        writer.writeheader()
        for row in payroll:
            safe_dict_writerow(writer, row)
        response['csv'] = base64.b64encode(buffer.getvalue().encode()).decode()

    return response


@router.get("/hr/payroll/{month}")
async def get_payroll(month: str, current_user: User = Depends(get_current_user)):
    """Per-month payroll lookup.

    Declared after `/hr/payroll/export` on purpose: FastAPI matches in
    declaration order and a `{month}` placeholder declared first would
    silently swallow the static `/hr/payroll/export` GET (Task #133).
    """
    payroll = await db.payroll_records.find({'tenant_id': current_user.tenant_id, 'period_month': month}, {'_id': 0}).to_list(200)
    total = sum([p.get('net_salary', 0) for p in payroll])
    return {'payroll': payroll, 'total': total, 'count': len(payroll)}


@router.post("/hr/job-posting")
async def create_job_posting(job_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    job = {
        'id': str(uuid.uuid4()), 'tenant_id': current_user.tenant_id,
        **job_data, 'status': 'active', 'applicants_count': 0,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.job_postings.insert_one(job)
    return {'success': True, 'job_id': job['id']}


# ============= F&B COMPLETE SUITE =============

async def _get_ingredient_map(tenant_id: str):
    ingredients = await db.ingredients.find({'tenant_id': tenant_id}, {'_id': 0}).to_list(1000)
    return {ing['id']: ing for ing in ingredients}, ingredients


def _enrich_recipe_cost(recipe: dict, ingredient_map: dict[str, dict]):
    enriched_lines = []
    total_cost = 0
    for line in recipe.get('ingredients', []):
        ingredient = ingredient_map.get(line.get('ingredient_id'))
        unit_cost = line.get('unit_cost') or (ingredient.get('unit_cost') if ingredient else 0)
        quantity = line.get('quantity', 1)
        waste_pct = line.get('waste_pct', 0)
        line_cost = unit_cost * quantity * (1 + waste_pct / 100)
        total_cost += line_cost

        enriched_lines.append({
            'ingredient_id': line.get('ingredient_id'),
            'ingredient_name': line.get('ingredient_name') or (ingredient.get('name') if ingredient else 'Unknown'),
            'unit': line.get('unit') or (ingredient.get('unit') if ingredient else ''),
            'quantity': quantity,
            'unit_cost': round(unit_cost, 2),
            'waste_pct': waste_pct,
            'line_cost': round(line_cost, 2),
            'supplier': ingredient.get('supplier') if ingredient else None
        })

    recipe['cost_breakdown'] = enriched_lines
    recipe['total_cost'] = round(total_cost, 2)
    selling_price = recipe.get('selling_price', 0)
    recipe['gp_percentage'] = round(((selling_price - total_cost) / selling_price * 100), 1) if selling_price else 0
    recipe['ingredient_count'] = len(enriched_lines)
    return recipe


@router.post("/fnb/recipes")
async def create_recipe(recipe_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    ingredient_map, _ = await _get_ingredient_map(current_user.tenant_id)

    recipe = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'dish_name': recipe_data.get('recipe_name') or recipe_data.get('dish_name', 'Unnamed Recipe'),
        'category': recipe_data.get('category', 'general'),
        'portion_size': recipe_data.get('portion_size', '1 portion'),
        'preparation_time': recipe_data.get('preparation_time', 15),
        'ingredients': recipe_data.get('ingredients', []),
        'selling_price': recipe_data.get('selling_price', 0),
        'active': True,
        'created_at': datetime.now(UTC).isoformat()
    }

    recipe = _enrich_recipe_cost(recipe, ingredient_map)
    await db.recipes.insert_one(recipe)

    return {
        'success': True,
        'recipe_id': recipe['id'],
        'gp_percentage': recipe['gp_percentage'],
        'total_cost': recipe['total_cost']
    }


@router.get("/fnb/recipes")
async def get_recipes(current_user: User = Depends(get_current_user)):
    ingredient_map, _ = await _get_ingredient_map(current_user.tenant_id)
    recipes = await db.recipes.find(
        {'tenant_id': current_user.tenant_id, 'active': True},
        {'_id': 0}
    ).sort('dish_name', 1).to_list(200)

    enriched = [_enrich_recipe_cost(dict(recipe), ingredient_map) for recipe in recipes]
    avg_gp = sum([r.get('gp_percentage', 0) for r in enriched]) / len(enriched) if enriched else 0
    avg_food_cost = sum([r.get('total_cost', 0) for r in enriched]) / len(enriched) if enriched else 0

    return {
        'recipes': enriched,
        'total': len(enriched),
        'avg_gp': round(avg_gp, 1),
        'avg_food_cost': round(avg_food_cost, 2)
    }


@router.get("/fnb/recipes/{recipe_id}")
async def get_recipe(recipe_id: str, current_user: User = Depends(get_current_user)):
    recipe = await db.recipes.find_one({'tenant_id': current_user.tenant_id, 'id': recipe_id}, {'_id': 0})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    ingredient_map, _ = await _get_ingredient_map(current_user.tenant_id)
    recipe = _enrich_recipe_cost(recipe, ingredient_map)
    return {'recipe': recipe}


@router.put("/fnb/recipes/{recipe_id}")
async def update_recipe(recipe_id: str, recipe_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v96 DW
):
    recipe = await db.recipes.find_one({'tenant_id': current_user.tenant_id, 'id': recipe_id})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    updated = {**recipe, **recipe_data}
    ingredient_map, _ = await _get_ingredient_map(current_user.tenant_id)
    updated = _enrich_recipe_cost(updated, ingredient_map)

    await db.recipes.update_one(
        {'tenant_id': current_user.tenant_id, 'id': recipe_id},
        {'$set': updated}
    )
    updated.pop('_id', None)
    return {'success': True, 'recipe': updated}

@router.post("/fnb/beo")
async def create_beo(beo_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    beo = {
        'id': str(uuid.uuid4()), 'tenant_id': current_user.tenant_id,
        **beo_data, 'status': 'confirmed',
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.banquet_event_orders.insert_one(beo)
    return {'success': True, 'beo_id': beo['id'], 'message': 'BEO olusturuldu'}

# NOTE: Kitchen Display System endpoints (/fnb/kitchen-display, /fnb/kitchen-order,
# /fnb/kitchen-order/{id}/status) and their helpers were moved to
# backend/domains/pms/pos_fnb_router.py where the rest of the F&B / POS surface
# lives. This file now only owns true HR endpoints + the F&B "ingredients" set.


@router.get("/fnb/ingredients")
async def list_ingredients(current_user: User = Depends(get_current_user)):
    ingredients = await db.ingredients.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('name', 1).to_list(500)

    low_stock = [ing for ing in ingredients if ing.get('current_stock', 0) <= ing.get('reorder_point', 0)]
    total_value = sum((ing.get('current_stock', 0) * ing.get('unit_cost', 0)) for ing in ingredients)

    categories = {}
    for ing in ingredients:
        cat = ing.get('category', 'other')
        categories.setdefault(cat, 0)
        categories[cat] += 1

    return {
        'ingredients': ingredients,
        'summary': {
            'total_items': len(ingredients),
            'low_stock': len(low_stock),
            'inventory_value': round(total_value, 2),
            'categories': categories
        }
    }


@router.post("/fnb/ingredients")
async def add_ingredient(ing_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    ingredient = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'name': ing_data['name'],
        'category': ing_data.get('category', 'general'),
        'unit': ing_data.get('unit', 'kg'),
        'current_stock': ing_data.get('current_stock', 0),
        'par_level': ing_data.get('par_level', 0),
        'reorder_point': ing_data.get('reorder_point', 0),
        'unit_cost': ing_data.get('unit_cost', 0),
        'supplier': ing_data.get('supplier'),
        'last_order_date': ing_data.get('last_order_date'),
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.ingredients.insert_one(ingredient)
    ingredient.pop('_id', None)
    return {'success': True, 'ingredient': ingredient}


@router.put("/fnb/ingredients/{ingredient_id}")
async def update_ingredient(ingredient_id: str, ing_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    ingredient = await db.ingredients.find_one({'tenant_id': current_user.tenant_id, 'id': ingredient_id})
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    updated = {**ingredient, **ing_data}
    await db.ingredients.update_one(
        {'tenant_id': current_user.tenant_id, 'id': ingredient_id},
        {'$set': updated}
    )
    updated.pop('_id', None)
    return {'success': True, 'ingredient': updated}

