import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from pydantic import ValidationError

from models.schemas.qr_catalogue import (
    GuestServiceItem, GuestServiceDepartment, GuestServiceCatalogueSettings, CatalogueMode,
    InputType, QuantityConfig, ChoiceConfig, ChoiceOption, EmptyConfig, AutoPriority
)
from domains.guest.qr_catalogue_defaults import get_default_catalogue
from core.database import _raw_db as raw_db
from routers.room_qr_requests import _ensure_indexes

import asyncio

@pytest.fixture(autouse=True)
def clear_db():
    async def _clear():
        await raw_db["guest_service_catalogue_settings"].delete_many({})
        await raw_db["guest_service_departments"].delete_many({})
        await raw_db["guest_service_items"].delete_many({})
    
    asyncio.run(_clear())
    yield
    asyncio.run(_clear())

def test_schema_validations():
    # quantity min greater than max
    with pytest.raises(ValidationError):
        QuantityConfig(min=5, max=1, default=3)
    
    # quantity default outside bounds
    with pytest.raises(ValidationError):
        QuantityConfig(min=1, max=5, default=10)
        
    # empty choice options
    with pytest.raises(ValidationError):
        ChoiceConfig(options=[], min_selections=1, max_selections=1)
        
    # duplicate choice option codes
    with pytest.raises(ValidationError):
        ChoiceConfig(
            options=[
                ChoiceOption(code="opt1", labels={"en": "One"}),
                ChoiceOption(code="opt1", labels={"en": "Two"})
            ],
            min_selections=1, max_selections=1
        )
        
    # invalid icon
    with pytest.raises(ValidationError):
        GuestServiceDepartment(
            tenant_id="t", property_id="p", department_code="d",
            labels={"en": "l"}, icon="invalid icon!", created_at=datetime.now(), updated_at=datetime.now()
        )

def test_default_catalogue_mutation_protection():
    cat1 = get_default_catalogue()
    cat2 = get_default_catalogue()
    
    cat1["departments"][0]["icon"] = "mutated"
    assert cat2["departments"][0]["icon"] != "mutated"
    
def test_ensure_indexes():
    async def _run():
        await _ensure_indexes()
        await _ensure_indexes()
        idx = await raw_db["guest_service_catalogue_settings"].index_information()
        assert "gsc_settings_lookup" in idx
    asyncio.run(_run())

def test_api_modes_and_security():
    pass


