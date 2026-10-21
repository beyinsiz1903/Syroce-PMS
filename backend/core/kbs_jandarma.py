"""Jandarma's published SOAP contract; no browser, cookies or configurable URL.

Source: https://vatandas.jandarma.gov.tr/KBS_Tesis_Servis/SrvShsYtkTml.svc?wsdl
Connection verification uses ParametreListele, never a synthetic guest check-in.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from defusedxml import ElementTree

from core.kbs_payload_validation import _is_foreign_identity_card, _is_turkish_nationality, validate_kbs_payload
from integrations.xchange.safety import safe_post_async

ENDPOINT = "https://vatandas.jandarma.gov.tr/KBS_Tesis_Servis/SrvShsYtkTml.svc"
NS = "http://tempuri.org/"
DATA_NS = "http://schemas.datacontract.org/2004/07/KBS_Tesis_Servis"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
COUNTRIES = {
    "TR": "TURKIYE",
    "TC": "TURKIYE",
    "TUR": "TURKIYE",
    "TURKIYE": "TURKIYE",
    "DE": "GERMANY",
    "DEU": "GERMANY",
    "ALMANYA": "GERMANY",
    "GB": "UNITED_KINGDOM",
    "GBR": "UNITED_KINGDOM",
    "INGILTERE": "UNITED_KINGDOM",
    "US": "UNITED_STATES",
    "USA": "UNITED_STATES",
    "ABD": "UNITED_STATES",
    "FR": "FRANCE",
    "FRA": "FRANCE",
    "FRANSA": "FRANCE",
    "RU": "RUSSIAN_FEDERATION",
    "RUS": "RUSSIAN_FEDERATION",
    "RUSSIA": "RUSSIAN_FEDERATION",
    "NL": "NETHERLANDS",
    "NLD": "NETHERLANDS",
    "HOLLANDA": "NETHERLANDS",
    "BE": "BELGIUM",
    "BEL": "BELGIUM",
    "AT": "AUSTRIA",
    "AUT": "AUSTRIA",
    "CH": "SWITZERLAND",
    "CHE": "SWITZERLAND",
    "IT": "ITALY",
    "ITA": "ITALY",
    "ES": "SPAIN",
    "ESP": "SPAIN",
    "UA": "UKRAINE",
    "UKR": "UKRAINE",
    "IR": "IRAN",
    "IRN": "IRAN",
    "IQ": "IRAQ",
    "IRQ": "IRAQ",
    "SY": "SYRIAN_ARAB_REPUBLIC",
    "SYR": "SYRIAN_ARAB_REPUBLIC",
    "AZ": "AZERBAIJAN",
    "AZE": "AZERBAIJAN",
    "GE": "GEORGIA",
    "GEO": "GEORGIA",
}


class JandarmaError(Exception):
    """Safe error code only. Never expose an XML body, credential or guest PII."""

    def __init__(self, code: str, *, uncertain: bool = False):
        self.code = code
        self.uncertain = uncertain
        super().__init__(code)


def _date(value) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Europe/Istanbul"))
        return parsed.astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        raise JandarmaError("invalid_date") from None


def _country(value) -> str:
    key = str(value or "TC").strip().upper().translate(str.maketrans("ÇĞİÖŞÜ", "CGIOSU"))
    key = re.sub(r"[\s-]+", "_", key)
    if key in COUNTRIES:
        return COUNTRIES[key]
    if re.fullmatch(r"[A-Z_]{4,60}", key):
        return key  # Official enum symbols are ultimately validated by Jandarma.
    raise JandarmaError("unsupported_country")


def build_request(credentials: dict, payload: dict | None = None, action: str = "checkin") -> tuple[str, str]:
    if not re.fullmatch(r"[0-9]{11}", str(credentials.get("user_tc", ""))):
        raise JandarmaError("invalid_user_tc")
    facility = str(credentials.get("facility_code", ""))
    if not re.fullmatch(r"[0-9]{1,19}", facility) or not 0 < int(facility) <= 9223372036854775807:
        raise JandarmaError("invalid_facility_code")
    if not credentials.get("password"):
        raise JandarmaError("missing_web_service_password")
    fields = ""
    if payload is None:
        method = "ParametreListele"
        fields = "<parametreTuru>ULKELER</parametreTuru>"
    else:
        valid, missing = validate_kbs_payload(payload, action)
        if not valid:
            raise JandarmaError("invalid_payload:" + ",".join(missing))
        identity = _is_turkish_nationality(payload.get("nationality")) or _is_foreign_identity_card(payload.get("id_type"))
        method = ("MusteriKimlikNo" if identity else "MusteriYabanci") + ("Giris" if action == "checkin" else "Cikis")
        values = {}
        if action == "checkout":
            values = {
                "BELGENO" if not identity else "KIMLIKNO": payload.get("passport_number") if not identity else payload.get("id_number"),
                "CKSTIP": "TESISTENCIKIS",
                "CKSTRH": _date(payload.get("check_out")),
            }
        else:
            if not identity:
                names = str(payload.get("guest_name", "")).split()
                if len(names) < 2:
                    raise JandarmaError("foreign_guest_name_requires_surname")
                gender = str(payload.get("gender", "")).upper()
                if gender not in {"F", "FEMALE", "K", "KADIN", "M", "MALE", "E", "ERKEK"}:
                    raise JandarmaError("unsupported_gender")
                values.update(
                    {
                        "ADI": " ".join(names[:-1]),
                        "ANAADI": payload.get("mother_name", ""),
                        "BABADI": payload.get("father_name", ""),
                        "BELGENO": payload["passport_number"],
                        "CINSIYET": "KADIN" if gender in {"F", "FEMALE", "K", "KADIN"} else "ERKEK",
                        "DOGUMTARIHI": _date(payload["birth_date"]),
                    }
                )
            checkin = _date(payload["check_in"])
            phone = re.sub(r"\D", "", str(payload.get("phone", "")))
            values.update(
                {
                    "GRSTRH": checkin,
                    "ILERITARIHLI": str(datetime.fromisoformat(checkin) > datetime.now(UTC)).lower(),
                    **({"KIMLIKNO": payload["id_number"]} if identity else {}),
                    "KULLANIMSEKLI": "KONAKLAMA",
                    "ODANO": payload["room_number"],
                    "PLKNO": payload.get("plate_number", ""),
                    "TELNO": phone if 7 <= len(phone) <= 15 else "",
                    **({"SOYADI": names[-1]} if not identity else {}),
                    "ULKKOD": _country(payload.get("nationality")),
                }
            )
        # DataContractSerializer uses alphabetical member order.
        fields = '<musteri xmlns:d="' + DATA_NS + '">' + "".join(f"<d:{key}>{escape(str(value or ''))}</d:{key}>" for key, value in sorted(values.items())) + "</musteri>"
    auth = "".join(f"<{tag}>{escape(str(credentials[key]))}</{tag}>" for tag, key in (("KullaniciTC", "user_tc"), ("TssKod", "facility_code"), ("Sifre", "password")))
    xml = f'<s:Envelope xmlns:s="{SOAP_NS}"><s:Body><{method} xmlns="{NS}">{auth}{fields}</{method}></s:Body></s:Envelope>'
    return method, xml


def parse_response(content: bytes, method: str) -> dict:
    if len(content) > 2_000_000:
        raise JandarmaError("response_too_large", uncertain=True)
    try:
        root = ElementTree.fromstring(content)
    except Exception:
        raise JandarmaError("invalid_response", uncertain=True) from None
    result = root.find(f"./{{{SOAP_NS}}}Body/{{{NS}}}{method}Response/{{{NS}}}{method}Result")
    if result is None:
        raise JandarmaError("invalid_response", uncertain=True)
    # Check the operation result only, not arbitrary nodes elsewhere in the XML.
    outcome = result.find(f"{{{DATA_NS}}}sonuc")
    if outcome is None:
        outcome = result
    ok = outcome.findtext(f"{{{DATA_NS}}}Basarili", "").lower() == "true"
    code = outcome.findtext(f"{{{DATA_NS}}}HataKodu", "")
    if not ok or code not in {"100", "Basarili"}:
        safe_code = code if re.fullmatch(r"[A-Za-z0-9_]{1,60}", code) else "unknown"
        raise JandarmaError("jandarma_" + safe_code)
    return {"code": code, "method": method}


async def call_jandarma(credentials: dict, payload: dict | None = None, action: str = "checkin") -> dict:
    method, xml = build_request(credentials, payload, action)
    try:
        response = await safe_post_async(
            ENDPOINT,
            timeout=30,
            content=xml.encode(),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS}ISrvShsYtkTml/{method}"'},
        )
    except Exception:
        # The request might already have reached Jandarma. Never blindly retry.
        raise JandarmaError("delivery_unknown_check_authority", uncertain=payload is not None) from None
    if response.status_code != 200:
        raise JandarmaError(f"authority_http_{response.status_code}", uncertain=payload is not None)
    return parse_response(response.content, method)
