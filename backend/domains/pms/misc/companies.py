"""Auto-split from misc_router.py — backward-compatible sub-router."""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.enums import CompanyStatus
from models.schemas import Company, CompanyCreate, User
from modules.pms_core.role_permission_service import require_op

from ._common import (
    cached,
)

logger = logging.getLogger(__name__)

sub_router = APIRouter()

# NOT: /payments/installment-calculator ucu kaldırıldı (kullanılmıyordu ve
# return ifadesi de eksikti — total/installments hesaplanıp atılıyordu).


@sub_router.post("/companies", response_model=Company)
async def create_company(company_data: CompanyCreate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Create a new company. Status is 'pending' by default for quick-created companies from booking form."""
    # Wave 9 (ürün kararı): kurumsal hesabın vergi numarası tenant içinde
    # tekildir. Yalnız değer verildiğinde uygulanır — tax_number opsiyonel bir
    # alandır ve numarasız çok sayıda şirket olabilir (geriye-uyumlu). Boş /
    # whitespace değerler muaftır; saklanan değer de normalize edilir.
    tax_no = (company_data.tax_number or "").strip()
    if tax_no:
        existing = await db.companies.find_one({
            'tenant_id': current_user.tenant_id,
            'tax_number': tax_no,
        })
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Bu vergi numarası ({tax_no}) ile kayıtlı kurumsal hesap zaten var.",
            )
    company = Company(
        tenant_id=current_user.tenant_id,
        **company_data.model_dump()
    )
    company_dict = company.model_dump()
    # Normalize: store the stripped value, or None for empty/whitespace-only —
    # never persist a dirty whitespace tax_number (keeps the uniqueness key clean).
    company_dict['tax_number'] = tax_no or None
    company_dict['created_at'] = company_dict['created_at'].isoformat()
    company_dict['updated_at'] = company_dict['updated_at'].isoformat()
    await db.companies.insert_one(company_dict)
    return company



@sub_router.get("/companies")
@cached(ttl=600, key_prefix="companies_list")  # Cache for 10 minutes
async def get_companies(
    search: str | None = None,
    status: CompanyStatus | None = None,
    limit: int = 1000,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_corporate_accounts")),  # v86 DV: corporate companies
):
    """Get all companies with optional search, status filter, and pagination."""
    query = {'tenant_id': current_user.tenant_id}

    if status:
        query['status'] = status

    from security.query_safety import safe_search_term
    if (s := safe_search_term(search)):
        query['$or'] = [
            {'name': {'$regex': s, '$options': 'i'}},
            {'corporate_code': {'$regex': s, '$options': 'i'}}
        ]

    companies = await db.companies.find(query, {'_id': 0}).skip(offset).limit(limit).to_list(limit)
    # Remove response_model validation to allow flexible contracted_rate types
    return companies

# Alias for PMS module compatibility


@sub_router.get("/companies/{company_id}", response_model=Company)
async def get_company(company_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific company by ID."""
    company = await db.companies.find_one({
        'id': company_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return company



@sub_router.put("/companies/{company_id}", response_model=Company)
async def update_company(
    company_id: str,
    company_data: CompanyCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Update company information. Used by sales team to complete pending company profiles."""
    company = await db.companies.find_one({
        'id': company_id,
        'tenant_id': current_user.tenant_id
    })

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Wave 9: vergi numarası tenant içinde tekil kalır — başka bir kayda ait
    # tax_number'a güncelleme 409 döner (yalnız değer verildiğinde).
    new_tax = (company_data.tax_number or "").strip()
    if new_tax:
        dup = await db.companies.find_one({
            'tenant_id': current_user.tenant_id,
            'tax_number': new_tax,
            'id': {'$ne': company_id},
        })
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Bu vergi numarası ({new_tax}) ile kayıtlı başka bir kurumsal hesap var.",
            )

    update_data = company_data.model_dump()
    # Same normalization as create: stripped value or None (no dirty whitespace).
    update_data['tax_number'] = new_tax or None
    update_data['updated_at'] = datetime.now(UTC).isoformat()

    await db.companies.update_one(
        {'id': company_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    updated_company = await db.companies.find_one({
        'id': company_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    return updated_company

