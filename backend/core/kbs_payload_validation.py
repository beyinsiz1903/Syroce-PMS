"""KBS payload validation helpers.

Polise gönderilecek misafir bilgisinin enqueue zamanında eksiksiz olduğunu
doğrular. Eksikse iş kuyruğa girmesin diye `validate_kbs_payload()` çağrılır.

Kurallar (EGM/Jandarma KBS minimum şeması):
  * `guest_name`               — boş olamaz
  * `birth_date`               — boş olamaz (YYYY-MM-DD)
  * `nationality == "TC"`      → `id_number` 11 hane (numeric)
  * `nationality != "TC"`      → `passport_number` boş olamaz
  * `check_in` / `check_out`   — boş olamaz

Yardımcı: `validate_or_raise()` 422 HTTPException fırlatır (router için).
"""
from __future__ import annotations

from fastapi import HTTPException


REQUIRED_BASE_FIELDS = ("guest_name", "birth_date", "check_in", "check_out")


def _norm(v: object) -> str:
    return (str(v).strip() if v is not None else "")


def validate_kbs_payload(snapshot: dict) -> tuple[bool, list[str]]:
    """Return (ok, missing_fields). Missing list boşsa payload uygundur."""
    missing: list[str] = []
    for field in REQUIRED_BASE_FIELDS:
        if not _norm(snapshot.get(field)):
            missing.append(field)

    nationality = _norm(snapshot.get("nationality")).upper() or "TC"
    id_number = _norm(snapshot.get("id_number"))
    passport_number = _norm(snapshot.get("passport_number"))

    if nationality == "TC":
        if not id_number:
            missing.append("id_number")
        elif not (id_number.isdigit() and len(id_number) == 11):
            missing.append("id_number_invalid")
    else:
        if not passport_number:
            missing.append("passport_number")

    return (len(missing) == 0, missing)


def validate_or_raise(snapshot: dict) -> None:
    """Geçersizse 422 fırlat. Geçerliyse no-op."""
    ok, missing = validate_kbs_payload(snapshot)
    if not ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "kbs_payload_incomplete",
                "missing_fields": missing,
                "message": (
                    "KBS bildirimi için zorunlu alanlar eksik veya geçersiz: "
                    + ", ".join(missing)
                ),
            },
        )
