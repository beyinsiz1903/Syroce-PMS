"""
reports

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Department-Specific Endpoints Router
Front Office, Housekeeping Manager, Finance, Revenue, F&B, Maintenance,
Sales, HR, IT/Security department dashboards.
Extracted from server.py for modularity.
"""
import io as _io
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from core.business_date_service import ensure_business_date_initialized
from core.csv_safe import xlsx_safe
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from core.utils import _XLSX_MAX_CELL_LEN, _xlsx_sanitize_str, calculate_folio_balance, create_excel_workbook, excel_response
from models.schemas import User
from modules.pms_core.report_money import add_amount, currency_code, resolve_ledger_currencies, rounded, rounded_totals, single_amount
from modules.pms_core.reporting_financials import REPORTING_CURRENCY, report_payment_day_match, report_payment_period_match, reporting_collection_summary
from modules.pms_core.reporting_ledger import charge_amount, charge_category, posted_revenue_rows
from modules.pms_core.role_permission_service import RolePermissionService, require_op
from modules.pms_core.stay_night_metrics import NON_COMMERCIAL_STATUSES, allocated_revenue_for_night, as_date, booking_nights, load_stay_night_metrics

logger = logging.getLogger(__name__)

_role_perm = RolePermissionService()


def _enforce(role: str, op: str):
    """Bug CU (v60) — Departments/Reports/Rates/POS RBAC zorunlu."""
    _role_perm.enforce_permission(getattr(role, "role", role), op, getattr(role, "granted_permissions", None))


try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
except ImportError:
    Workbook = None

try:
    from cache_manager import cache, cached
except ImportError:
    cache = None  # type: ignore

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


security = HTTPBearer()


# ==================== DEPARTMENT-SPECIFIC ENDPOINTS ====================

# rbac-allow: cache-rbac — FO dashboard operasyonel, hotel staff geneli görür (FO/HK/manager/admin)

# rbac-allow: cache-rbac — HK dashboard operasyonel, FO/HK/manager/admin görür


# NOTE: /ai/dashboard/briefing duplicate removed (R10b) — canonical implementation
# lives in `domains/ai/endpoints.py::get_daily_briefing` with @cached(ttl=300) and
# parallel `_asyncio.gather` over 4 collections.


# rbac-allow: cache-rbac — booking için müsait odalar operasyonel (FO/HK/manager)


# rbac-allow: cache-rbac — HK aktif temizlik timer'ları operasyonel (HK/FO/manager)


# rbac-allow: cache-rbac — task kanban operasyonel cross-role (FO/HK/maintenance/manager)

router = APIRouter(prefix="/api", tags=["departments"])


def _report_dates(start_date, end_date):
    try:
        start = datetime.fromisoformat(str(start_date)[:10]).date()
        end = datetime.fromisoformat(str(end_date)[:10]).date()
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Tarihler YYYY-MM-DD formatında olmalı") from exc
    if start > end:
        raise HTTPException(status_code=422, detail="Başlangıç tarihi bitiş tarihinden sonra olamaz")
    return start, end


def _booking_currency_stats(bookings, field, fallback):
    groups = {}
    for booking in bookings:
        nights = booking_nights(booking)
        if not nights:
            continue
        key = str(booking.get(field) or fallback)
        code = currency_code(booking.get("currency"))
        entry = groups.setdefault(key, {"bookings": 0, "nights": 0, "revenue_by_currency": {}, "nights_by_currency": {}, "bookings_by_currency": {}})
        entry["bookings"] += 1
        entry["nights"] += nights
        entry["nights_by_currency"][code] = entry["nights_by_currency"].get(code, 0) + nights
        entry["bookings_by_currency"][code] = entry["bookings_by_currency"].get(code, 0) + 1
        add_amount(entry["revenue_by_currency"], code, 0 if booking.get("is_complimentary") else booking.get("total_amount", 0))
    for entry in groups.values():
        entry["revenue_by_currency"] = rounded_totals(entry["revenue_by_currency"])
        entry["adr_by_currency"] = {code: rounded(amount / entry["nights_by_currency"][code]) for code, amount in entry["revenue_by_currency"].items()}
        entry["revenue"] = single_amount(entry["revenue_by_currency"])
        entry["adr"] = single_amount(entry["adr_by_currency"])
    return groups


# ── GET /reports/market-segment ──
@router.get("/reports/market-segment")
@cached(ttl=900, key_prefix="report_market_segment_v2")
async def get_market_segment_report(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v84 DT: market segment performance
    _nocache: bool = Query(False, alias="nocache"),
):
    """Market Segment & Rate Type Performance Report"""
    start, end = _report_dates(start_date, end_date)
    bookings = await db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "check_in": {"$gte": start.isoformat(), "$lt": (end + timedelta(days=1)).isoformat()},
            "status": {"$nin": list(NON_COMMERCIAL_STATUSES)},
        }
    ).to_list(None)

    segment_data = _booking_currency_stats(bookings, "market_segment", "other")
    rate_type_data = _booking_currency_stats(bookings, "rate_type", "bar")

    return {"start_date": start_date, "end_date": end_date, "total_bookings": len(bookings), "market_segments": segment_data, "rate_types": rate_type_data}


# ── GET /reports/market-segment/excel ──
@router.get("/reports/market-segment/excel")
async def export_market_segment_excel(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v84 DT: market segment export
):
    """Export Market Segment Report to Excel"""
    report_data = await get_market_segment_report.__wrapped__(start_date, end_date, current_user)

    # Create workbook with multiple sheets
    wb = Workbook()

    # Sheet 1: Market Segments
    ws1 = wb.active
    ws1.title = "Market Segments"

    headers1 = ["Segment", "Currency", "Bookings", "Nights", "Revenue", "ADR"]
    data1 = []
    for segment, stats in report_data["market_segments"].items():
        for code, amount in stats["revenue_by_currency"].items():
            data1.append([_xlsx_sanitize_str(xlsx_safe(segment.title())), code, stats["bookings_by_currency"][code], stats["nights_by_currency"][code], amount, stats["adr_by_currency"][code]])

    # Add title and headers
    ws1.merge_cells("A1:F1")
    title_cell = ws1["A1"]
    title_cell.value = f"Market Segment Report ({start_date} to {end_date})"
    title_cell.font = Font(size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")

    for col_num, header in enumerate(headers1, 1):
        cell = ws1.cell(row=2, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")

    for row_num, row_data in enumerate(data1, 3):
        for col_num, value in enumerate(row_data, 1):
            ws1.cell(row=row_num, column=col_num, value=value)

    # Sheet 2: Rate Types
    ws2 = wb.create_sheet("Rate Types")

    headers2 = ["Rate Type", "Currency", "Bookings", "Nights", "Revenue", "ADR"]
    data2 = []
    for rate_type, stats in report_data["rate_types"].items():
        for code, amount in stats["revenue_by_currency"].items():
            data2.append([_xlsx_sanitize_str(xlsx_safe(rate_type.upper())), code, stats["bookings_by_currency"][code], stats["nights_by_currency"][code], amount, stats["adr_by_currency"][code]])

    ws2.merge_cells("A1:F1")
    title_cell = ws2["A1"]
    title_cell.value = f"Rate Type Report ({start_date} to {end_date})"
    title_cell.font = Font(size=14, bold=True)
    title_cell.alignment = Alignment(horizontal="center")

    for col_num, header in enumerate(headers2, 1):
        cell = ws2.cell(row=2, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")

    for row_num, row_data in enumerate(data2, 3):
        for col_num, value in enumerate(row_data, 1):
            ws2.cell(row=row_num, column=col_num, value=value)

    filename = f"market_segment_report_{start_date}_to_{end_date}.xlsx"
    return excel_response(wb, filename)


# ── Helper: safe date coercion (Task #246) ──
def _coerce_to_date(v):
    """Coerce mixed-type `created_at` values to date. Stress env may store
    `created_at` as native BSON datetime (motor returns datetime obj) rather
    than ISO string — `datetime.fromisoformat()` raises TypeError in that
    case. Returns None for unparseable/missing values so caller can skip.
    """
    from datetime import date as _date

    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, _date):
        return v
    if isinstance(v, str):
        try:
            # Tolerate trailing 'Z' (UTC suffix); fromisoformat accepts it on 3.11+
            return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            return None
    return None


# ── Pure helper: company-aging compute (Task #246) ──
async def _compute_company_aging(tenant_id: str) -> dict:
    """Pure async data builder for Company AR Aging Report.

    Extracted from `get_company_aging_report` so the Excel export route can
    re-use the computation without invoking another `@cached`+`@router.get`
    decorated route handler directly (anti-pattern that broke under stress
    when decorator semantics shifted, and obscured tracebacks).
    """
    business_state = await ensure_business_date_initialized(db, tenant_id)
    today = datetime.fromisoformat(str(business_state["business_date"])[:10]).date()

    # AR aging is a financial control; a hard list cap would silently hide
    # overdue company debt for high-volume properties.
    folios = await db.folios.find(
        {"tenant_id": tenant_id, "folio_type": "company", "status": "open"}
    ).to_list(None)

    company_balances: dict[tuple[str | None, str], dict] = {}
    total_by_currency = {}
    failed_folios = []

    for folio in folios:
        try:
            balance = await calculate_folio_balance(folio["id"], tenant_id)
        except Exception:
            logger.exception("calculate_folio_balance failed for folio=%s tenant=%s", folio.get("id"), tenant_id)
            failed_folios.append(str(folio.get("id")))
            continue

        if balance <= 0:
            continue

        company_id = folio.get("company_id")

        # Task #246: tenant_id scope on company lookup (architect review #3) —
        # company ID collisions across tenants would otherwise leak metadata.
        company = await db.companies.find_one({"id": company_id, "tenant_id": tenant_id}, {"_id": 0}) if company_id else None
        if not company:
            # Missing metadata must never make a real receivable disappear.
            company = {"name": "Şirket kaydı bulunamadı", "corporate_code": "—"}

        aging_anchor = _coerce_to_date(folio.get("due_date") or folio.get("invoice_date") or folio.get("created_at"))
        if aging_anchor is None:
            # Unparseable date → treat as oldest bucket; do not crash export.
            age_days = 99999
        else:
            age_days = max((today - aging_anchor).days, 0)

        if age_days <= 7:
            aging_bucket = "0-7 days"
        elif age_days <= 14:
            aging_bucket = "8-14 days"
        elif age_days <= 30:
            aging_bucket = "15-30 days"
        else:
            aging_bucket = "30+ days"

        code = currency_code(folio.get("currency"))
        group_key = (company_id, code)
        if group_key not in company_balances:
            company_balances[group_key] = {
                "company_id": company_id,
                "currency": code,
                "company_name": company.get("name", "N/A"),
                "corporate_code": company.get("corporate_code", "N/A"),
                "total_balance": 0,
                "aging": {
                    "0-7 days": 0,
                    "8-14 days": 0,
                    "15-30 days": 0,
                    "30+ days": 0,
                },
                "folio_count": 0,
            }

        company_balances[group_key]["total_balance"] += balance
        company_balances[group_key]["aging"][aging_bucket] += balance
        company_balances[group_key]["folio_count"] += 1
        add_amount(total_by_currency, code, balance)

    sorted_companies = sorted(
        company_balances.values(),
        key=lambda x: (x["currency"], -x["total_balance"], x["company_name"]),
    )

    return {
        "report_date": today.isoformat(),
        "total_ar": single_amount(total_by_currency) if not failed_folios else None,
        "total_ar_by_currency": rounded_totals(total_by_currency),
        "company_count": len({key[0] for key in company_balances}),
        "companies": sorted_companies,
        "complete": not failed_folios,
        "failed_folio_ids": failed_folios,
    }


# ── GET /reports/company-aging ──
@router.get("/reports/company-aging")
@cached(ttl=900, key_prefix="report_company_aging_v2")
async def get_company_aging_report(
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_finance_reports")),
):
    """Company Accounts Receivable Aging Report"""
    _enforce(current_user, "view_finance_reports")  # Bug CU
    try:
        return await _compute_company_aging(current_user.tenant_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("company_aging report failed for tenant=%s", current_user.tenant_id)
        raise HTTPException(status_code=500, detail="report_failed")


# ── GET /reports/company-aging/excel ──
# Task #246: @cached REMOVED — decorator serializes the StreamingResponse
# object via `repr()` ("<starlette.responses.StreamingResponse object at 0x…>")
# so the second call within the TTL returned non-XLSX garbage with HTTP 200.
# Excel-shape rendering is cheap enough to recompute; underlying data builder
# (_compute_company_aging) is itself called by the cached JSON route and can
# be wrapped separately if hot-path caching becomes necessary.
@router.get("/reports/company-aging/excel")
async def export_company_aging_excel(
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_finance_reports")),
):
    """Export Company Aging Report to Excel"""
    _enforce(current_user, "view_finance_reports")  # Bug CU
    try:
        # Use shared pure helper instead of calling cached route handler directly
        # (Task #246 — `@cached` decorated route handler MUST NOT be invoked
        # directly; cache key derivation + Depends sentinel handling are fragile).
        report_data = await _compute_company_aging(current_user.tenant_id)
        if not report_data["complete"]:
            raise HTTPException(status_code=503, detail="Bazı folyo bakiyeleri doğrulanamadı; eksik toplam dışa aktarılamaz")

        headers = ["Company", "Corporate Code", "Currency", "Total Balance", "0-7 Days", "8-14 Days", "15-30 Days", "30+ Days", "Folios"]
        data = []

        for company in report_data["companies"]:
            data.append(
                [
                    company["company_name"],
                    company["corporate_code"],
                    company["currency"],
                    round(company["total_balance"], 2),
                    round(company["aging"]["0-7 days"], 2),
                    round(company["aging"]["8-14 days"], 2),
                    round(company["aging"]["15-30 days"], 2),
                    round(company["aging"]["30+ days"], 2),
                    company["folio_count"],
                ]
            )

        # Add total row
        for code, total in report_data["total_ar_by_currency"].items():
            data.append(["TOTAL", "", code, total, "", "", "", "", ""])

        wb = create_excel_workbook(title=f"Company Aging Report - {report_data['report_date']}", headers=headers, data=data, sheet_name="Company Aging")

        # Task #253 (tur-2): belt-and-suspenders save retry. create_excel_workbook
        # already sanitizes via _xlsx_sanitize_str, but if any future code path
        # bypasses it (e.g. company.get('name') with a control char that lands
        # post-sanitize, or any non-string field that openpyxl rejects), retry
        # once with full re-scrub. Outer try/except logs the true traceback.
        buf = _io.BytesIO()
        try:
            wb.save(buf)
            buf.seek(0)
        except Exception:
            logger.exception(
                "company_aging excel save failed, retrying with full re-scrub tenant=%s rows=%s",
                current_user.tenant_id,
                len(report_data.get("companies", [])),
            )
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for cell in row:
                        if isinstance(cell.value, str):
                            cell.value = ILLEGAL_CHARACTERS_RE.sub("", cell.value)[:_XLSX_MAX_CELL_LEN]
            buf = _io.BytesIO()
            wb.save(buf)
            buf.seek(0)

        filename = f"company_aging_report_{report_data['report_date']}.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "company_aging excel export failed for tenant=%s",
            current_user.tenant_id,
        )
        raise HTTPException(status_code=500, detail="report_export_failed")


# ── GET /reports/finance-snapshot ──
@router.get("/reports/finance-snapshot")
@cached(ttl=600, key_prefix="report_finance_snapshot_v2")
async def get_finance_snapshot(
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_finance_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    """
    Finance Snapshot for GM Dashboard
    Returns: Total Pending AR, Overdue Invoices (categorized), Today's Collections
    """
    _enforce(current_user, "view_finance_reports")  # Bug CU
    business_state = await ensure_business_date_initialized(db, current_user.tenant_id)
    today = datetime.fromisoformat(str(business_state["business_date"])[:10]).date()

    # 1. Calculate Total Pending AR from company folios
    company_folios = await db.folios.find(
        {"tenant_id": current_user.tenant_id, "folio_type": "company", "status": "open"}
    ).to_list(None)

    overdue_invoices_count = 0
    pending_ar_by_currency: dict[str, dict[str, float | int]] = {}

    for folio in company_folios:
        balance = await calculate_folio_balance(folio["id"], current_user.tenant_id)

        if balance > 0:
            currency = currency_code(folio.get("currency"))
            bucket = pending_ar_by_currency.setdefault(
                currency,
                {
                    "total": 0.0,
                    "0-30_days": 0.0,
                    "30-60_days": 0.0,
                    "60_plus_days": 0.0,
                    "overdue_invoices_count": 0,
                },
            )
            bucket["total"] = float(bucket["total"]) + balance

            # Calculate aging
            aging_anchor = _coerce_to_date(folio.get("due_date") or folio.get("invoice_date") or folio.get("created_at"))
            age_days = max((today - aging_anchor).days, 0) if aging_anchor else 99999

            if age_days > 0:  # Any overdue
                overdue_invoices_count += 1
                bucket["overdue_invoices_count"] = int(bucket["overdue_invoices_count"]) + 1

                if age_days <= 30:
                    bucket["0-30_days"] = float(bucket["0-30_days"]) + balance
                elif age_days <= 60:
                    bucket["30-60_days"] = float(bucket["30-60_days"]) + balance
                else:
                    bucket["60_plus_days"] = float(bucket["60_plus_days"]) + balance

    # 2. Calculate Today's Collections (payments received today)
    todays_payments = await db.payments.find(
        {
            "tenant_id": current_user.tenant_id,
            **report_payment_day_match(today.isoformat()),
        }
    ).to_list(None)

    todays_payments = await resolve_ledger_currencies(todays_payments, current_user.tenant_id, database=db, fallback_currency=REPORTING_CURRENCY)
    today_summary = reporting_collection_summary(todays_payments)

    # 3. Calculate MTD (Month-to-Date) Collections
    month_start = today.replace(day=1)

    mtd_payments = await db.payments.find(
        {
            "tenant_id": current_user.tenant_id,
            **report_payment_period_match(month_start.isoformat(), today.isoformat()),
        }
    ).to_list(None)

    mtd_payments = await resolve_ledger_currencies(mtd_payments, current_user.tenant_id, database=db, fallback_currency=REPORTING_CURRENCY)
    mtd_summary = reporting_collection_summary(mtd_payments)
    mtd_collections = float(mtd_summary["amount"])

    # 4. Calculate Collection Rate (MTD Collections / MTD Revenue)
    mtd_charges = await posted_revenue_rows(current_user.tenant_id, month_start, today, database=db, fallback_currency=REPORTING_CURRENCY)

    mtd_revenue_by_currency = {}
    for charge in mtd_charges:
        add_amount(mtd_revenue_by_currency, charge.get("currency"), charge_amount(charge))
    # A ratio is meaningful only in one currency, and is unknown if some
    # collections could not be converted with immutable historical evidence.
    mtd_revenue = float(mtd_revenue_by_currency.get(REPORTING_CURRENCY, 0))
    rate_complete = not mtd_summary["conversion_issue_count"] and not any(code != REPORTING_CURRENCY and amount for code, amount in mtd_revenue_by_currency.items())
    collection_rate = ((mtd_collections / mtd_revenue * 100) if mtd_revenue > 0 else 0) if rate_complete else None

    # 5. Get Accounting Invoices (E-Fatura ready)
    pending_invoices = await db.accounting_invoices.find(
        {"tenant_id": current_user.tenant_id, "status": {"$in": ["pending", "partial"]}}
    ).to_list(None)

    pending_invoice_count = len(pending_invoices)
    pending_invoice_by_currency: dict[str, float] = {}
    for invoice in pending_invoices:
        remaining = max(float(invoice.get("total") or 0) - float(invoice.get("amount_paid") or 0), 0)
        add_amount(pending_invoice_by_currency, invoice.get("currency"), remaining)

    return {
        "report_date": today.isoformat(),
        "business_date": today.isoformat(),
        "pending_ar": {
            "total": single_amount({code: bucket["total"] for code, bucket in pending_ar_by_currency.items()}),
            "by_currency": {
                currency: {
                    key: round(float(value), 2) if key != "overdue_invoices_count" else value
                    for key, value in totals.items()
                }
                for currency, totals in pending_ar_by_currency.items()
            },
            "overdue_breakdown": {key: single_amount({code: bucket[key] for code, bucket in pending_ar_by_currency.items()}) for key in ("0-30_days", "30-60_days", "60_plus_days")},
            "overdue_invoices_count": overdue_invoices_count,
        },
        "todays_collections": {
            **today_summary,
        },
        "mtd_collections": {
            **mtd_summary,
            "collection_rate_percentage": round(collection_rate, 2) if collection_rate is not None else None,
            "collection_rate_currency": REPORTING_CURRENCY,
            "collection_rate_complete": rate_complete,
            "revenue_by_currency": rounded_totals(mtd_revenue_by_currency),
        },
        "accounting_invoices": {
            "pending_count": pending_invoice_count,
            "pending_total": single_amount(pending_invoice_by_currency),
            # Preserve the established empty-state response shape. Consumers
            # only need a currency breakdown when an invoice exists.
            **(
                {
                    "by_currency": {
                        currency: rounded(total) for currency, total in pending_invoice_by_currency.items()
                    }
                }
                if pending_invoice_by_currency
                else {}
            ),
        },
    }


# ── GET /reports/revenue-detail/excel ──
@router.get("/reports/revenue-detail/excel")
async def export_revenue_detail_excel(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    """Detailed booked room revenue by stay date, room type and rate code."""
    business_state = await ensure_business_date_initialized(db, current_user.tenant_id)
    business_day = datetime.fromisoformat(str(business_state["business_date"])[:10]).date()
    if not end_date:
        end_date = business_day.isoformat()
    if not start_date:
        start_date = (business_day - timedelta(days=29)).isoformat()
    _enforce(current_user, "view_finance_reports")  # Bug CU
    start, end = _report_dates(start_date, end_date)
    next_day = (end + timedelta(days=1)).isoformat()
    # Reservation-production detail.  Revenue is allocated once across the
    # stay nights and clipped to the requested period; checkout is exclusive.
    bookings = await db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house", "checked_out"]},
            "check_in": {"$lt": next_day},
            "check_out": {"$gt": start.isoformat()},
        },
        {
            "_id": 0,
            "check_in": 1,
            "check_out": 1,
            "total_amount": 1,
            "currency": 1,
            "is_complimentary": 1,
            "status": 1,
            "room_type": 1,
            "rate_plan": 1,
            "rate_type": 1,
            "market_segment": 1,
            "room_number": 1,
        },
    ).to_list(None)

    rows = {}
    for b in bookings:
        ci = as_date(b.get("check_in"))
        co = as_date(b.get("check_out"))
        nights = booking_nights(b)
        if not ci or not co or not nights:
            continue
        cursor = max(ci, start)
        stop = min(co, end + timedelta(days=1))
        while cursor < stop:
            room_type = str(b.get("room_type") or "Belirtilmemiş")
            rate_code = str(b.get("rate_plan") or b.get("rate_type") or "Standart")
            key = (cursor.isoformat(), room_type, rate_code, currency_code(b.get("currency")))
            item = rows.setdefault(key, {"date": key[0], "room_type": room_type, "rate_code": rate_code, "currency": key[3], "room_nights": 0, "revenue": 0.0})
            item["room_nights"] += 1
            item["revenue"] += float(allocated_revenue_for_night(b, cursor))
            cursor += timedelta(days=1)

    data = []
    for item in sorted(rows.values(), key=lambda row: (row["date"], row["room_type"], row["rate_code"])):
        revenue = round(item["revenue"], 2)
        data.append([item["date"], item["room_type"], item["rate_code"], item["currency"], item["room_nights"], revenue, round(revenue / item["room_nights"], 2)])
    wb = create_excel_workbook(
        title=f"Revenue Detail {start_date} to {end_date}",
        headers=["Date", "Room Type", "Rate Code", "Currency", "Room Nights", "Booked Revenue", "ADR"],
        data=data,
        sheet_name="Revenue Detail",
    )
    return excel_response(wb, f"revenue_detail_{start_date}_to_{end_date}.xlsx")


# ── GET /reports/forecast-detail/excel ──
@router.get("/reports/forecast-detail/excel")
async def export_forecast_detail_excel(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    """Forecasted occupancy and booked revenue by stay date."""
    business_state = await ensure_business_date_initialized(db, current_user.tenant_id)
    business_day = datetime.fromisoformat(str(business_state["business_date"])[:10]).date()
    if not start_date:
        start_date = business_day.isoformat()
    if not end_date:
        end_date = (business_day + timedelta(days=29)).isoformat()
    _enforce(current_user, "view_finance_reports")  # Bug CU
    start, end = _report_dates(start_date, end_date)
    forecast_response = await load_stay_night_metrics(db, current_user.tenant_id, start, end)

    headers = ["Date", "Expected Occupancy %", "Currency", "Expected Revenue"]
    data: list[list[Any]] = []

    items = forecast_response
    for item in items:
        if not isinstance(item, dict):
            continue
        for code, amount in (item.get("revenue_by_currency") or {"TRY": item.get("revenue", 0)}).items():
            data.append([item.get("date"), item.get("occupancy_rate", 0), code, amount])

    title = f"Forecast Detail {start_date} to {end_date}"
    wb = create_excel_workbook(
        title=title,
        headers=headers,
        data=data,
        sheet_name="Forecast Detail",
    )

    filename = f"forecast_detail_{start_date}_to_{end_date}.xlsx"
    return excel_response(wb, filename)


# ── GET /reports/operations-daily-summary/excel ──
@router.get("/reports/operations-daily-summary/excel")
async def export_operations_daily_summary_excel(
    date: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    """Daily operations summary: arrivals, departures, in-house guests."""
    target = datetime.fromisoformat(date)
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)

    day_key = target.date().isoformat()
    next_key = (target.date() + timedelta(days=1)).isoformat()
    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "$or": [{"check_in": {"$gte": day_key, "$lt": next_key}}, {"check_out": {"$gte": day_key, "$lt": next_key}}, {"check_in": {"$lte": day_key}, "check_out": {"$gt": day_key}}]},
        {"_id": 0},
    ).to_list(None)
    arrivals = sum(1 for booking in bookings if as_date(booking.get("check_in")) == target.date() and str(booking.get("status") or "").lower() not in NON_COMMERCIAL_STATUSES)
    departures = sum(1 for booking in bookings if as_date(booking.get("check_out")) == target.date() and str(booking.get("status") or "").lower() not in NON_COMMERCIAL_STATUSES)
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, target.date(), target.date(), actual_only=True)
    in_house = metrics[0]["occupied_rooms"] if metrics else 0

    headers = ["Metric", "Value"]
    data = [
        ["Date", target.date().isoformat()],
        ["", ""],
        ["Arrivals", arrivals],
        ["Departures", departures],
        ["Occupied Rooms", in_house],
    ]

    title = f"Operations Daily Summary {target.date().isoformat()}"
    wb = create_excel_workbook(
        title=title,
        headers=headers,
        data=data,
        sheet_name="Operations Summary",
    )

    filename = f"operations_daily_summary_{target.date().isoformat()}.xlsx"
    return excel_response(wb, filename)


# ── GET /reports/channel-distribution/excel ──
@router.get("/reports/channel-distribution/excel")
async def export_channel_distribution_excel(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    """Sales channel distribution report (OTA, Direct, Corporate, etc.)."""
    _enforce(current_user, "view_finance_reports")  # Bug CU
    state = await ensure_business_date_initialized(db, current_user.tenant_id)
    business_day = datetime.fromisoformat(str(state["business_date"])[:10]).date()
    start, end = _report_dates(start_date or (business_day - timedelta(days=29)).isoformat(), end_date or business_day.isoformat())
    start_date, end_date = start.isoformat(), end.isoformat()

    bookings = await db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house", "checked_out"]},
            "check_in": {"$gte": start.isoformat(), "$lt": (end + timedelta(days=1)).isoformat()},
        },
        {
            "_id": 0,
            "total_amount": 1,
            "currency": 1,
            "channel": 1,
            "booking_source": 1,
            "source_channel": 1,
            "ota_channel": 1,
            "market_segment": 1,
        },
    ).to_list(None)

    channel_stats: dict[str, dict[str, Any]] = {}

    for b in bookings:
        channel = str(b.get("ota_channel") or b.get("source_channel") or b.get("booking_source") or b.get("channel") or "DIRECT")
        code = currency_code(b.get("currency"))
        group_key = (channel, code)
        if group_key not in channel_stats:
            channel_stats[group_key] = {
                "channel": channel,
                "currency": code,
                "bookings": 0,
                "revenue": 0.0,
            }
        channel_stats[group_key]["bookings"] += 1
        channel_stats[group_key]["revenue"] += float(b.get("total_amount") or 0.0)

    total_revenue = {}
    for row in channel_stats.values():
        add_amount(total_revenue, row["currency"], row["revenue"])

    headers = [
        "Channel",
        "Currency",
        "Bookings",
        "Revenue",
        "Share %",
    ]

    data: list[list[Any]] = []
    for key, row in sorted(channel_stats.items(), key=lambda x: x[0]):
        currency_total = float(total_revenue[row["currency"]])
        share = row["revenue"] / currency_total * 100 if currency_total else 0
        data.append(
            [
                row["channel"],
                row["currency"],
                row["bookings"],
                round(row["revenue"], 2),
                round(share, 2),
            ]
        )

    title = f"Channel Distribution {start_date} to {end_date}"
    wb = create_excel_workbook(
        title=title,
        headers=headers,
        data=data,
        sheet_name="Channels",
    )

    filename = f"channel_distribution_{start_date}_to_{end_date}.xlsx"
    return excel_response(wb, filename)


async def _compute_mtd_cost_summary(tenant_id: str) -> dict:
    """Build one canonical MTD cost view for both legacy API paths."""
    business_state = await ensure_business_date_initialized(db, tenant_id)
    today = datetime.fromisoformat(str(business_state["business_date"])[:10]).date()
    month_start = today.replace(day=1)
    month_start_dt = datetime.combine(month_start, datetime.min.time()).replace(tzinfo=UTC)
    next_day = today + timedelta(days=1)

    purchase_orders = await db.purchase_orders.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["approved", "received", "completed"]},
            "$or": [{"created_at": {"$gte": month_start.isoformat(), "$lt": next_day.isoformat()}},
                    {"created_at": {"$gte": month_start_dt, "$lt": datetime.combine(next_day, datetime.min.time(), UTC)}}],
        }
    # Cost and revenue totals are control figures; never silently truncate a
    # high-volume property's purchase ledger.
    ).to_list(None)

    # Map purchase order categories to cost categories
    category_mapping = {
        "cleaning": "Housekeeping",
        "linens": "Housekeeping",
        "amenities": "Housekeeping",
        "food": "F&B",
        "beverage": "F&B",
        "kitchen": "F&B",
        "maintenance": "Technical",
        "electrical": "Technical",
        "plumbing": "Technical",
        "hvac": "Technical",
        "furniture": "General Expenses",
        "office": "General Expenses",
        "it": "General Expenses",
        "other": "General Expenses",
    }

    # Aggregate costs by category
    cost_categories = {"Housekeeping": 0, "F&B": 0, "Technical": 0, "General Expenses": 0}
    costs_by_currency = {}
    categories_by_currency = {}

    total_mtd_costs = 0

    for po in purchase_orders:
        category = str(po.get("category") or "other").strip().lower()
        cost_category = category_mapping.get(category, "General Expenses")
        total_amount = float(po.get("total_amount") or 0)
        code = currency_code(po.get("currency"))
        add_amount(costs_by_currency, code, total_amount)
        add_amount(categories_by_currency.setdefault(cost_category, {}), code, total_amount)

        cost_categories[cost_category] += total_amount
        total_mtd_costs += total_amount

    # 2. Sort categories to get top 3
    sorted_categories = sorted([{"name": k, "amount": v} for k, v in cost_categories.items()], key=lambda x: x["amount"], reverse=True)

    top_3_categories = sorted_categories[:3]

    metrics = await load_stay_night_metrics(db, tenant_id, month_start, today, actual_only=True)
    total_room_nights = sum(day["occupied_rooms"] for day in metrics)
    total_available_room_days = sum(day["total_rooms"] for day in metrics)

    per_room_cost = (total_mtd_costs / total_room_nights) if total_room_nights > 0 else 0

    mtd_charges = await posted_revenue_rows(tenant_id, month_start, today, database=db, fallback_currency=REPORTING_CURRENCY)
    total_revenue = sum(charge_amount(charge) for charge in mtd_charges)
    revenue_by_currency, room_revenue_by_currency = {}, {}
    for charge in mtd_charges:
        add_amount(revenue_by_currency, charge.get("currency"), charge_amount(charge))
        if charge_category(charge) == "room":
            add_amount(room_revenue_by_currency, charge.get("currency"), charge_amount(charge))

    mtd_revpar = (sum(float(value) for value in room_revenue_by_currency.values()) / total_available_room_days) if total_available_room_days > 0 else 0

    # 5. Calculate Cost to Revenue Ratio
    cost_to_revenue_ratio = (total_mtd_costs / total_revenue * 100) if total_revenue > 0 else 0

    # 6. Calculate profit margin
    gross_profit = total_revenue - total_mtd_costs
    profit_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0

    costs_by_currency = rounded_totals(costs_by_currency)
    revenue_by_currency = rounded_totals(revenue_by_currency)
    currencies = set(costs_by_currency) | set(revenue_by_currency)
    mixed = len(currencies) > 1
    financial_by_currency = {}
    for code in sorted(currencies):
        cost, revenue = costs_by_currency.get(code, 0), revenue_by_currency.get(code, 0)
        financial_by_currency[code] = {
            "mtd_costs": cost, "mtd_revenue": revenue, "gross_profit": rounded(revenue - cost),
            "profit_margin_percentage": round((revenue - cost) / revenue * 100, 1) if revenue else 0,
            "cost_to_revenue_ratio": round(cost / revenue * 100, 1) if revenue else 0,
        }
    return {
        "report_date": today.isoformat(),
        "period": f"{month_start.isoformat()} to {today.isoformat()}",
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "mixed_currency": mixed,
        "total_mtd_costs": single_amount(costs_by_currency),
        "total_mtd_costs_by_currency": costs_by_currency,
        "cost_categories_by_currency": {name: rounded_totals(values) for name, values in categories_by_currency.items()},
        "cost_categories": {
            key: single_amount(categories_by_currency.get(name, {}))
            for key, name in (("housekeeping", "Housekeeping"), ("fnb", "F&B"), ("technical", "Technical"), ("general_expenses", "General Expenses"))
        },
        "top_3_categories": [
            {"name": cat["name"], "amount": round(cat["amount"], 2), "percentage": round((cat["amount"] / total_mtd_costs * 100), 1) if total_mtd_costs > 0 else 0} for cat in top_3_categories
        ] if len(costs_by_currency) <= 1 else [],
        "top_3_categories_by_currency": {
            code: sorted([
                {"name": name, "amount": rounded(values.get(code, 0))}
                for name, values in categories_by_currency.items() if code in values
            ], key=lambda row: row["amount"], reverse=True)[:3] for code in costs_by_currency
        },
        "per_room_metrics": {
            "total_room_nights": total_room_nights,
            "cost_per_room_night": single_amount({code: amount / total_room_nights if total_room_nights else 0 for code, amount in costs_by_currency.items()}),
            "cost_per_room_night_by_currency": {code: rounded(amount / total_room_nights) if total_room_nights else 0 for code, amount in costs_by_currency.items()},
            "mtd_revpar": single_amount({code: float(amount) / total_available_room_days if total_available_room_days else 0 for code, amount in room_revenue_by_currency.items()}),
            "mtd_revpar_by_currency": {code: rounded(float(amount) / total_available_room_days) if total_available_room_days else 0 for code, amount in room_revenue_by_currency.items()},
            "cost_to_revpar_ratio": None if mixed else (round((per_room_cost / mtd_revpar * 100), 1) if mtd_revpar > 0 else 0),
        },
        "financial_metrics": {
            "mtd_revenue": single_amount(revenue_by_currency),
            "mtd_costs": single_amount(costs_by_currency),
            "gross_profit": None if mixed else round(gross_profit, 2),
            "profit_margin_percentage": None if mixed else round(profit_margin, 1),
            "cost_to_revenue_ratio": None if mixed else round(cost_to_revenue_ratio, 1),
            "by_currency": financial_by_currency,
        },
    }


# ── GET /reports/cost-summary ──
@router.get("/reports/cost-summary")
@cached(ttl=600, key_prefix="report_cost_summary_v2")
async def get_cost_summary(
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_finance_reports")),
):
    """Cost summary for the current PMS month."""
    _enforce(current_user, "view_finance_reports")
    return await _compute_mtd_cost_summary(current_user.tenant_id)


# ── GET /finance/mtd-cost-summary ──
@router.get("/finance/mtd-cost-summary")
@cached(ttl=600, key_prefix="finance_mtd_cost_summary_v2")
async def get_mtd_cost_summary(
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_op("view_finance_reports")),
):
    """Month-to-date cost summary by category with per-room metrics."""
    _enforce(current_user, "view_finance_reports")
    return await _compute_mtd_cost_summary(current_user.tenant_id)
