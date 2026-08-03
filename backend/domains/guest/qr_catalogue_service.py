import datetime as dt
import logging
import zoneinfo

from pydantic import ValidationError

from core.database import _raw_db as raw_db
from domains.guest.qr_catalogue_defaults import get_default_catalogue
from models.schemas.qr_catalogue import ChoiceConfig, DateConstraints, DateTimeConstraints, GuestServiceCatalogueSettings, GuestServiceDepartment, GuestServiceItem, QuantityConfig, TimeConstraints

logger = logging.getLogger(__name__)

def _utc_now():
    from datetime import UTC
    return dt.datetime.now(UTC)

async def resolve_catalogue_mode(tenant_id: str, property_id: str) -> str:
    raw_settings = await raw_db["guest_service_catalogue_settings"].find_one({"tenant_id": tenant_id, "property_id": property_id})
    mode = "default"
    if raw_settings:
        raw_settings.pop("_id", None)
        try:
            settings_obj = GuestServiceCatalogueSettings.model_validate(raw_settings)
            mode = settings_obj.mode
        except ValidationError as e:
            logger.warning(f"[room_qr] Catalogue settings validation failed: group=catalogue_parse_error error_class={e.__class__.__name__}")
            return "disabled"
    return mode

def is_service_available(service_hours: dict | None, prop_tz: str) -> bool:
    if not service_hours:
        return True
    start_str = service_hours.get("start")
    end_str = service_hours.get("end")
    if not start_str or not end_str:
        return True
    if start_str == end_str:
        return False

    try:
        tz = zoneinfo.ZoneInfo(prop_tz)
        now_local = _utc_now().astimezone(tz).time()
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_t = dt.time(sh, sm)
        end_t = dt.time(eh, em)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return False

    if start_t < end_t:
        return start_t <= now_local < end_t
    else:
        return now_local >= start_t or now_local < end_t

async def fetch_catalogue_data(tenant_id: str, property_id: str, mode: str) -> tuple[list[dict], list[dict]]:
    depts_out = []
    services_out = []

    if mode == "default":
        default_cat = get_default_catalogue()
        depts_out = default_cat["departments"]
        services_out = default_cat["services"]
    elif mode == "configured":
        raw_depts = await raw_db["guest_service_departments"].find({"tenant_id": tenant_id, "property_id": property_id}).to_list(length=None)
        raw_items = await raw_db["guest_service_items"].find({"tenant_id": tenant_id, "property_id": property_id}).to_list(length=None)

        if not raw_depts and not raw_items:
            default_cat = get_default_catalogue()
            depts_out = default_cat["departments"]
            services_out = default_cat["services"]
        else:
            for rd in raw_depts:
                rd.pop("_id", None)
                try:
                    depts_out.append(GuestServiceDepartment.model_validate(rd).model_dump())
                except ValidationError as e:
                    logger.warning(f"[room_qr] Catalogue record validation failed: group=catalogue_parse_error error_class={e.__class__.__name__}")
            for ri in raw_items:
                ri.pop("_id", None)
                try:
                    services_out.append(GuestServiceItem.model_validate(ri).model_dump())
                except ValidationError as e:
                    logger.warning(f"[room_qr] Catalogue record validation failed: group=catalogue_parse_error error_class={e.__class__.__name__}")

    depts_out.sort(key=lambda x: (x.get("display_order", 0), x.get("department_code", "")))
    services_out.sort(key=lambda x: (x.get("display_order", 0), x.get("service_code", "")))
    return depts_out, services_out

def process_lang(labels: dict | None, lang: str, prop_lang: str) -> str:
    if not labels:
        return ""
    if lang and labels.get(lang):
        return labels[lang]
    if prop_lang and labels.get(prop_lang):
        return labels[prop_lang]
    if labels.get("tr"):
        return labels["tr"]
    if labels.get("en"):
        return labels["en"]
    for k in sorted(labels.keys()):
        if labels[k]:
            return labels[k]
    return ""

def process_lang_dict(data: dict | None, lang: str, prop_lang: str) -> str | None:
    if not data:
        return None
    return process_lang(data, lang, prop_lang)

def validate_input_value(input_type: str, input_config: dict, value_obj: dict | None, prop_tz: str) -> dict:
    if value_obj is None:
        value_obj = {}

    if input_type == "one_tap":
        return {}

    if input_type == "quantity":
        qty = value_obj.get("quantity")
        if not isinstance(qty, int):
            raise ValueError("quantity must be an integer")
        cfg = QuantityConfig.model_validate(input_config)
        if qty < cfg.min or qty > cfg.max:
            raise ValueError(f"quantity must be between {cfg.min} and {cfg.max}")
        return {"quantity": qty}

    if input_type in ("single_choice", "multi_choice"):
        selected = value_obj.get("selected_options")
        if not isinstance(selected, list):
            raise ValueError("selected_options must be a list")
        cfg = ChoiceConfig.model_validate(input_config)

        valid_codes = {opt.code for opt in cfg.options}
        if not all(code in valid_codes for code in selected):
            raise ValueError("Invalid selected options")
        if len(set(selected)) != len(selected):
            raise ValueError("Duplicate options selected")

        if len(selected) < cfg.min_selections or len(selected) > cfg.max_selections:
            raise ValueError(f"Number of selections must be between {cfg.min_selections} and {cfg.max_selections}")
        return {"selected_options": selected}

    tz = zoneinfo.ZoneInfo(prop_tz)
    now_local = _utc_now().astimezone(tz)
    now_local_date = now_local.date()

    if input_type == "date":
        date_val = value_obj.get("date_value")
        if not isinstance(date_val, str):
            raise ValueError("date_value must be a string")
        cfg = DateConstraints.model_validate(input_config)
        try:
            d = dt.date.fromisoformat(date_val)
        except ValueError:
            raise ValueError("Invalid date format, expected YYYY-MM-DD")

        min_date = now_local_date + dt.timedelta(days=cfg.min_days_ahead)
        max_date = now_local_date + dt.timedelta(days=cfg.max_days_ahead)
        if d < min_date or d > max_date:
            raise ValueError(f"Date must be between {min_date} and {max_date}")
        return {"date_value": d.isoformat()}

    if input_type == "time":
        time_val = value_obj.get("time_value")
        if not isinstance(time_val, str):
            raise ValueError("time_value must be a string")
        cfg = TimeConstraints.model_validate(input_config)
        try:
            t = dt.time.fromisoformat(time_val)
        except ValueError:
            raise ValueError("Invalid time format, expected HH:MM")

        total_minutes = t.hour * 60 + t.minute
        if total_minutes % cfg.interval_minutes != 0:
            raise ValueError(f"Time must be in increments of {cfg.interval_minutes} minutes")
        return {"time_value": t.strftime("%H:%M")}

    if input_type == "datetime":
        dt_val = value_obj.get("datetime_value")
        if not isinstance(dt_val, str):
            raise ValueError("datetime_value must be a string")
        cfg = DateTimeConstraints.model_validate(input_config)
        try:
            val_dt = dt.datetime.fromisoformat(dt_val)
            if val_dt.tzinfo is None:
                val_dt = val_dt.replace(tzinfo=tz)
            else:
                val_dt = val_dt.astimezone(tz)
        except ValueError:
            raise ValueError("Invalid datetime format")

        if val_dt < now_local:
            raise ValueError("Datetime cannot be in the past")

        d = val_dt.date()
        min_date = now_local_date + dt.timedelta(days=cfg.min_days_ahead)
        max_date = now_local_date + dt.timedelta(days=cfg.max_days_ahead)
        if d < min_date or d > max_date:
            raise ValueError(f"Date must be between {min_date} and {max_date}")

        t = val_dt.time()
        total_minutes = t.hour * 60 + t.minute
        if total_minutes % cfg.interval_minutes != 0:
            raise ValueError(f"Time must be in increments of {cfg.interval_minutes} minutes")

        return {"datetime_value": val_dt.isoformat()}

    raise ValueError("Unknown input_type")
