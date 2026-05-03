"""Auto-split from misc_router.py — backward-compatible sub-router."""
import html as _html
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.helpers import require_module
from core.security import get_current_user, security
from models.enums import ROLE_PERMISSIONS, CompanyStatus, Permission, UserRole
from models.schemas import Company, CompanyCreate, CreatePropertyRequest, User
from modules.pms_core.role_permission_service import require_module as require_module_v101
from modules.pms_core.role_permission_service import require_op

from ._common import (
    DEFAULT_PUSH_CHANNELS, PingTestRequest,
    has_permission, calculate_folio_balance, get_folio_details,
    _scrub_encrypted, cached,
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
    company = Company(
        tenant_id=current_user.tenant_id,
        **company_data.model_dump()
    )
    company_dict = company.model_dump()
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

    update_data = company_data.model_dump()
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

