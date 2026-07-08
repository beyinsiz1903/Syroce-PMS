import uuid
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/sustainability", tags=["Sustainability"])

# Hardcoded emission factors for demonstration purposes
# Factors represent kgCO2e per unit
EMISSION_FACTORS = {
    "electricity": {"name": "Purchased Electricity", "scope": 2, "unit": "kWh", "factor": 0.429}, # Example factor
    "natural_gas": {"name": "Natural Gas", "scope": 1, "unit": "m3", "factor": 2.02266},
    "water": {"name": "Water Consumption", "scope": 3, "unit": "m3", "factor": 0.344}, # Scope 3 upstream
    "waste": {"name": "General Waste", "scope": 3, "unit": "kg", "factor": 0.450}
}

# In-memory storage for demonstration
_records = []

class FactorOut(BaseModel):
    id: str
    name: str
    scope: int
    unit: str
    factor: float

class RecordIn(BaseModel):
    consumption_type: str = Field(..., description="E.g., electricity, natural_gas")
    period_start: date
    period_end: date
    amount: float
    evidence_url: Optional[str] = None

class RecordOut(RecordIn):
    id: str
    scope: int
    emissions_kg_co2e: float

class ReportOut(BaseModel):
    total_scope_1: float
    total_scope_2: float
    total_scope_3: float
    total_emissions: float
    total_room_nights: int
    emissions_per_room_night: float

@router.get("/factors", response_model=List[FactorOut])
async def list_factors():
    return [{"id": k, **v} for k, v in EMISSION_FACTORS.items()]

@router.post("/records", response_model=RecordOut)
async def create_record(record_in: RecordIn):
    if record_in.consumption_type not in EMISSION_FACTORS:
        raise HTTPException(status_code=400, detail="Invalid consumption type.")
    
    factor_info = EMISSION_FACTORS[record_in.consumption_type]
    emissions = record_in.amount * factor_info["factor"]
    
    record = RecordOut(
        id=str(uuid.uuid4()),
        scope=factor_info["scope"],
        emissions_kg_co2e=round(emissions, 2),
        **record_in.model_dump()
    )
    _records.append(record)
    return record

@router.get("/records", response_model=List[RecordOut])
async def list_records():
    return _records

@router.get("/report", response_model=ReportOut)
async def generate_report(start_date: date, end_date: date):
    # Filter records by date (simple overlap check for demo)
    relevant_records = [
        r for r in _records 
        if not (r.period_end < start_date or r.period_start > end_date)
    ]
    
    scope_1 = sum(r.emissions_kg_co2e for r in relevant_records if r.scope == 1)
    scope_2 = sum(r.emissions_kg_co2e for r in relevant_records if r.scope == 2)
    scope_3 = sum(r.emissions_kg_co2e for r in relevant_records if r.scope == 3)
    
    total = scope_1 + scope_2 + scope_3
    
    # Mocking room nights logic - in reality, we'd query `pms_bookings` or similar
    # to find total occupied room nights between start_date and end_date.
    # Let's say 100 room nights per day as a mock value.
    days = (end_date - start_date).days + 1
    mock_room_nights = max(days * 100, 1)
    
    return ReportOut(
        total_scope_1=round(scope_1, 2),
        total_scope_2=round(scope_2, 2),
        total_scope_3=round(scope_3, 2),
        total_emissions=round(total, 2),
        total_room_nights=mock_room_nights,
        emissions_per_room_night=round(total / mock_room_nights, 4)
    )
