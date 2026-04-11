"""
Shared utilities for Rate Manager routers (Exely + HotelRunner).
Extracted from hr_rate_manager_router.py and rate_manager_router.py to eliminate duplication.
"""
from collections import defaultdict
from datetime import datetime, timedelta

import holidays as holidays_lib
from dateutil.easter import easter
from pydantic import BaseModel

# ══════════════════════════════════════════════════════════════════════
# Shared Pydantic Models
# ══════════════════════════════════════════════════════════════════════

class RoomTypeValuesItem(BaseModel):
    room_type_code: str
    rate_plan_codes: list[str]
    rate: float | None = None
    availability: int | None = None
    min_stay: int | None = None
    max_stay: int | None = None
    stop_sell: bool | None = None
    cta: bool | None = None
    ctd: bool | None = None


class RoomTypeSelection(BaseModel):
    room_type_code: str
    rate_plan_codes: list[str]


class BulkGridUpdateRequest(BaseModel):
    room_type_codes: list[str] | None = None
    rate_plan_codes: list[str] | None = None
    selections: list[RoomTypeSelection] | None = None
    per_room_values: list[RoomTypeValuesItem] | None = None
    start_date: str
    end_date: str
    selected_days: list[int] | None = None
    rate: float | None = None
    availability: int | None = None
    min_stay: int | None = None
    max_stay: int | None = None
    stop_sell: bool | None = None
    cta: bool | None = None
    ctd: bool | None = None
    update_fields: list[str] = []


class PricingSettingItem(BaseModel):
    room_type_code: str
    pricing_type: str


class PricingSettingsRequest(BaseModel):
    settings: list[PricingSettingItem]


class StopSaleScheduleCreate(BaseModel):
    name: str
    holiday_key: str | None = None
    start_date: str
    end_date: str
    room_type_codes: list[str]
    auto_apply: bool = True


class StopSaleScheduleUpdate(BaseModel):
    name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    room_type_codes: list[str] | None = None
    auto_apply: bool | None = None


# ══════════════════════════════════════════════════════════════════════
# Date Grouping
# ══════════════════════════════════════════════════════════════════════

def group_consecutive_dates(date_strings: list[str]) -> list[tuple[str, str]]:
    """Group sorted date strings into consecutive ranges.

    Returns list of (range_start, range_end) tuples.
    Example: ['2025-01-04', '2025-01-11', '2025-01-12'] ->
             [('2025-01-04','2025-01-04'), ('2025-01-11','2025-01-12')]
    """
    if not date_strings:
        return []
    ranges: list[tuple[str, str]] = []
    sorted_dates = sorted(date_strings)
    range_start = sorted_dates[0]
    prev = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()
    for ds in sorted_dates[1:]:
        curr = datetime.strptime(ds, "%Y-%m-%d").date()
        if (curr - prev).days != 1:
            ranges.append((range_start, prev.strftime("%Y-%m-%d")))
            range_start = ds
        prev = curr
    ranges.append((range_start, prev.strftime("%Y-%m-%d")))
    return ranges


# ══════════════════════════════════════════════════════════════════════
# Holiday Periods
# ══════════════════════════════════════════════════════════════════════

TR_HOLIDAY_NAMES = {
    "New Year's Day": "Yilbasi",
    "Eid al-Fitr": "Ramazan Bayrami",
    "Eid al-Adha": "Kurban Bayrami",
    "National Sovereignty and Children's Day": "23 Nisan Ulusal Egemenlik ve Cocuk Bayrami",
    "Labour and Solidarity Day": "1 Mayis Isci Bayrami",
    "Commemoration of Atatürk, Youth and Sports Day": "19 Mayis Ataturk'u Anma",
    "Democracy and National Unity Day": "15 Temmuz Demokrasi Bayrami",
    "Victory Day": "30 Agustos Zafer Bayrami",
    "Republic Day": "29 Ekim Cumhuriyet Bayrami",
}


def get_holiday_periods(year: int) -> list:
    """Build grouped holiday periods for given year.

    Includes Turkish public holidays + international tourism holidays.
    """
    tr = holidays_lib.Turkey(years=[year])

    groups = defaultdict(list)
    for d, name in sorted(tr.items()):
        parts = [n.strip() for n in name.split(";")]
        for part in parts:
            groups[part].append(d)

    periods = []
    for en_name, dates in groups.items():
        sorted_dates = sorted(dates)
        tr_name = TR_HOLIDAY_NAMES.get(en_name, en_name)
        key = en_name.lower().replace(" ", "_").replace("'", "")
        periods.append({
            "key": f"tr_{key}_{year}",
            "name": tr_name,
            "category": "turkey",
            "start_date": sorted_dates[0].isoformat(),
            "end_date": sorted_dates[-1].isoformat(),
            "days": len(sorted_dates),
            "year": year,
        })

    easter_date = easter(year)
    orthodox_easter = easter(year, method=2)

    intl = [
        {"key": f"easter_{year}", "name": "Paskalya (Bati)", "category": "international",
         "start_date": (easter_date - timedelta(days=2)).isoformat(),
         "end_date": (easter_date + timedelta(days=1)).isoformat(), "days": 4, "year": year},
        {"key": f"orthodox_easter_{year}", "name": "Ortodoks Paskalya", "category": "international",
         "start_date": (orthodox_easter - timedelta(days=2)).isoformat(),
         "end_date": (orthodox_easter + timedelta(days=1)).isoformat(), "days": 4, "year": year},
        {"key": f"christmas_{year}", "name": "Noel Tatili", "category": "international",
         "start_date": f"{year}-12-23", "end_date": f"{year}-12-26", "days": 4, "year": year},
        {"key": f"russian_newyear_{year}", "name": "Rus Yilbasi Tatili", "category": "international",
         "start_date": f"{year}-01-01", "end_date": f"{year}-01-08", "days": 8, "year": year},
        {"key": f"summer_peak_{year}", "name": "Yaz Sezonu (Yuksek)", "category": "season",
         "start_date": f"{year}-07-01", "end_date": f"{year}-08-31", "days": 62, "year": year},
        {"key": f"winter_break_{year}", "name": "Soemestr Tatili", "category": "season",
         "start_date": f"{year}-01-20", "end_date": f"{year}-02-03", "days": 15, "year": year},
    ]
    periods.extend(intl)
    periods.sort(key=lambda x: x["start_date"])
    return periods
