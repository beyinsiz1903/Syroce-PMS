"""Explicit canonical contract. Unknown columns never become Mongo keys."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .formats import MigrationError, column_key

FIELDS = {
    "guests": {
        "source_id",
        "name",
        "email",
        "phone",
        "id_number",
        "nationality",
        "address",
        "birth_date",
        "notes",
        "preferences",
        "company_source_id",
        "agency_source_id",
        "marketing_consent",
        "consent_date",
        "consent_reference",
    },
    "companies": {"source_id", "name", "email", "phone", "address", "tax_number"},
    "agencies": {"source_id", "name", "email", "phone", "address", "tax_number"},
    "rooms": {"source_id", "room_number", "room_type", "floor", "capacity"},
    "reservations": {"source_id", "guest_source_id", "room_source_id", "company_source_id", "agency_source_id", "check_in", "check_out", "status", "adults", "children", "total_amount", "currency"},
    "folios": {"source_id", "reservation_source_id", "currency", "balance", "charged_amount", "paid_amount"},
    "daily_rates": {"source_id", "reservation_source_id", "rate_date", "amount", "currency"},
    "transactions": {"source_id", "folio_source_id", "transaction_date", "kind", "amount", "currency", "description", "reference"},
    "balances": {"source_id", "guest_source_id", "company_source_id", "agency_source_id", "balance_date", "kind", "amount", "currency"},
}
REQUIRED = {
    "guests": {"source_id", "name"},
    "companies": {"source_id", "name"},
    "agencies": {"source_id", "name"},
    "rooms": {"source_id", "room_number", "room_type"},
    "reservations": {"source_id", "guest_source_id", "check_in", "check_out", "status", "total_amount", "currency"},
    "folios": {"source_id", "reservation_source_id", "currency", "balance"},
    "daily_rates": {"source_id", "reservation_source_id", "rate_date", "amount", "currency"},
    "transactions": {"source_id", "folio_source_id", "transaction_date", "kind", "amount", "currency"},
    "balances": {"source_id", "balance_date", "kind", "amount", "currency"},
}
REFERENCES = {
    "guest_source_id": "guests",
    "room_source_id": "rooms",
    "company_source_id": "companies",
    "agency_source_id": "agencies",
    "reservation_source_id": "reservations",
    "folio_source_id": "folios",
}
CURRENCIES = set("TRY EUR USD GBP CHF CAD AUD JPY CNY AED SAR RUB KWD BHD QAR SEK NOK DKK PLN CZK HUF RON BGN INR NZD ZAR SGD HKD BRL MXN THB KRW ISK OMR".split())
STATUSES = {"checked_out", "cancelled", "no_show", "confirmed", "checked_in", "pending"}
FINANCIAL = {"transactions", "balances", "folios"}
ALIASES = {
    "source_id": ["kayit no", "kayit id", "eski id", "external id", "profile id", "record id"],
    "name": ["ad soyad", "misafir adi", "unvan", "full name", "guest name"],
    "email": ["e posta", "eposta", "email address"],
    "phone": ["telefon", "gsm", "mobile"],
    "id_number": ["tc kimlik", "kimlik no", "passport no"],
    "nationality": ["uyruk"],
    "address": ["adres"],
    "birth_date": ["dogum tarihi"],
    "notes": ["notlar"],
    "room_number": ["oda no", "oda numarasi"],
    "room_type": ["oda tipi"],
    "check_in": ["giris tarihi", "arrival"],
    "check_out": ["cikis tarihi", "departure"],
    "currency": ["doviz", "para birimi"],
    "amount": ["tutar"],
    "balance": ["bakiye"],
    "total_amount": ["toplam tutar", "reservation amount"],
    "status": ["durum"],
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record_id(tenant_id, namespace, entity, source_id):
    return private_fingerprint([tenant_id, namespace, entity, source_id])


def private_fingerprint(value):
    # Source IDs sometimes contain document numbers; don't expose dictionary-
    # attackable plain hashes in archive metadata. Reuse the platform blind index.
    from security.field_encryption import get_field_encryption_service

    # The search service case-folds strings. Hash the exact canonical bytes first
    # so case-sensitive source IDs and case-only source edits remain distinct.
    return get_field_encryption_service().compute_search_hash("data-migration:" + digest(value))


def suggest_mapping(entity, headers):
    result = {}
    for target in sorted(FIELDS[entity]):
        aliases = {column_key(target), *(column_key(a) for a in ALIASES.get(target, []))}
        matches = [h for h in headers if column_key(h) in aliases]
        if len(matches) == 1:
            result[target] = matches[0]
    return result


def money(value, currency, decimal_separator="."):
    raw = str(value).strip()
    # No guessed grouping separator: 1,234 could mean two different amounts.
    pattern = r"[+-]?\d+(?:\.\d+)?" if decimal_separator == "." else r"[+-]?\d+(?:,\d+)?"
    if not re.fullmatch(pattern, raw):
        raise MigrationError("Tutar biçimi geçersiz; binlik ayırıcı kullanmayın.")
    try:
        amount = Decimal(raw.replace(",", "."))
        precision = 0 if currency in {"JPY", "KRW", "ISK"} else 3 if currency in {"KWD", "BHD", "OMR"} else 2
        quantum = Decimal(1).scaleb(-precision)
        if not amount.is_finite() or abs(amount) > Decimal("999999999999") or amount.quantize(quantum) != amount:
            raise MigrationError("Tutar büyüklüğü veya para birimi hassasiyeti geçersiz.")
        return format(amount.quantize(quantum), "f")
    except InvalidOperation as exc:
        raise MigrationError("Geçersiz tutar.") from exc


def normalize(entity, raw, mapping, *, date_format="%Y-%m-%d", decimal_separator=".", value_mapping=None):
    if set(mapping) - FIELDS[entity] or len(set(mapping.values())) != len(mapping):
        raise MigrationError("Alan eşleştirmesi geçersiz veya bir sütun birden fazla alana bağlı.")
    data = {field: str(raw.get(column, "")).strip() for field, column in mapping.items()}
    for field in REQUIRED[entity]:
        if not data.get(field):
            raise MigrationError(f"Zorunlu alan boş: {field}")
    for field in ("source_id", *REFERENCES):
        if data.get(field) and (len(data[field]) > 160 or any(c in data[field] for c in "\x00\r\n")):
            raise MigrationError(f"Kaynak kayıt numarası geçersiz: {field}")
    for field in ("status", "kind", "currency"):
        if field in data:
            data[field] = (value_mapping or {}).get(field, {}).get(data[field], data[field])
    if "currency" in data:
        data["currency"] = data["currency"].upper()
        if data["currency"] not in CURRENCIES:
            raise MigrationError("Desteklenmeyen para birimi.")
    for field in ("amount", "total_amount", "balance", "charged_amount", "paid_amount"):
        if field in data:
            data[field] = money(data[field], data["currency"], decimal_separator)
            if field == "total_amount" and Decimal(data[field]) < 0:
                raise MigrationError("Rezervasyon bedeli negatif olamaz.")
    for field in ("birth_date", "consent_date", "check_in", "check_out", "transaction_date", "balance_date", "rate_date"):
        if data.get(field):
            try:
                # Excel's typed dates are emitted as ISO; text follows the explicit format.
                value = data[field]
                data[field] = (datetime.fromisoformat(value).date() if "T" in value else datetime.strptime(value, date_format).date()).isoformat()
            except ValueError as exc:
                raise MigrationError(f"Tarih biçimi geçersiz: {field}") from exc
    if entity == "reservations":
        if data["status"] not in STATUSES:
            raise MigrationError("Rezervasyon durum kodunu eşleştirin.")
        if date.fromisoformat(data["check_out"]) <= date.fromisoformat(data["check_in"]):
            raise MigrationError("Çıkış tarihi girişten sonra olmalı.")
    for field in ("adults", "children", "capacity", "floor"):
        if data.get(field):
            try:
                number = int(data[field])
            except ValueError as exc:
                raise MigrationError(f"Tam sayı gerekli: {field}") from exc
            if not -10 <= number <= 10000 or field != "floor" and number < (1 if field == "capacity" else 0):
                raise MigrationError(f"Sayı aralık dışında: {field}")
            data[field] = number
    if entity == "transactions":
        if data["kind"] not in {"charge", "payment", "refund", "adjustment"}:
            raise MigrationError("Hareket türü charge/payment/refund/adjustment olmalı.")
        if data["kind"] != "adjustment" and Decimal(data["amount"]) < 0:
            raise MigrationError("Yön hareket türüyle belirtilir; tutar negatif olamaz.")
    if entity == "balances":
        if data["kind"] not in {"receivable", "payable", "deposit"}:
            raise MigrationError("Bakiye türü receivable/payable/deposit olmalı.")
        if sum(bool(data.get(f)) for f in ("guest_source_id", "company_source_id", "agency_source_id")) != 1:
            raise MigrationError("Bakiye tam olarak bir misafir, şirket veya acenteye bağlanmalı.")
    if entity == "guests":
        consent = data.get("marketing_consent", "").lower()
        if consent not in {"", "true", "false", "1", "0", "evet", "hayir", "hayır"}:
            raise MigrationError("İzin alanı true/false olmalı.")
        data["marketing_consent"] = consent in {"true", "1", "evet"}
        if data["marketing_consent"] and not (data.get("consent_date") and data.get("consent_reference")):
            raise MigrationError("Pazarlama izni için tarih ve kanıt referansı gerekli.")
    return data
