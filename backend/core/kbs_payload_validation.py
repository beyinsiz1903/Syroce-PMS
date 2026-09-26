"""KBS payload validation helpers.

Giriş ve çıkışın resmî KBS sözleşmeleri aynı alanları istemez. Özellikle
Jandarma SOAP çıkışı yalnız kimlik/belge ile gerçek çıkış zamanını taşır;
oda, ad ve giriş zamanı istemek geçerli bir bildirimi PMS içinde engeller.

Bu modül her iki taşıyıcının ortak asgari şartlarını action bazında doğrular.
Taşıyıcıya özgü enum/eşleme kontrolleri kurum çağrısından hemen önce adapter
tarafında fail-closed yapılır.
"""

from __future__ import annotations

from fastapi import HTTPException


def _norm(v: object) -> str:
    return str(v).strip() if v is not None else ""


def _is_turkish_nationality(value: object) -> bool:
    normalized = _norm(value).upper().translate(str.maketrans("ÇĞİÖŞÜ", "CGIOSU"))
    return normalized in {"", "TC", "TR", "TUR", "TURKIYE"}


def _is_foreign_identity_card(value: object) -> bool:
    normalized = _norm(value).lower().replace("-", "_").replace(" ", "_")
    return normalized in {
        "foreign_identity_card",
        "foreign_id",
        "yabanci_kimlik",
        "yabanci_kimlik_karti",
        "ykn",
    }


def validate_kbs_payload(snapshot: dict, action: str = "checkin") -> tuple[bool, list[str]]:
    """Return (ok, missing_fields). Missing list boşsa payload uygundur."""
    missing: list[str] = []
    if action not in {"checkin", "checkout"}:
        return False, ["action_invalid"]

    required = ("room_number", "check_in") if action == "checkin" else ("check_out",)
    for field in required:
        if not _norm(snapshot.get(field)):
            missing.append(field)

    nationality = snapshot.get("nationality")
    id_type = snapshot.get("id_type")
    id_number = _norm(snapshot.get("id_number"))
    passport_number = _norm(snapshot.get("passport_number"))

    if _is_turkish_nationality(nationality):
        if not id_number:
            missing.append("id_number")
        elif not (id_number.isdigit() and len(id_number) == 11):
            missing.append("id_number_invalid")
    else:
        # Türkiye'de verilen yabancı kimlik numarası (YKN) taşıyan kişiler
        # pasaportla değil, KBS'deki "YKN olan Yabancı" akışıyla bildirilir.
        # Belge türü açıkça YKN ise 11 haneli kimlik numarası zorunludur;
        # diğer yabancı belgelerde pasaport kuralı korunur.
        foreign_identity_card = _is_foreign_identity_card(id_type)
        if foreign_identity_card:
            if not id_number:
                missing.append("id_number")
            elif not (id_number.isdigit() and len(id_number) == 11):
                missing.append("id_number_invalid")
        elif not passport_number:
            missing.append("passport_number")
        # Jandarma'nin "YKN olan Yabanci" servisi kimlik numarasi, oda ve
        # giris zamaniyla calisir. Dogum tarihi/cinsiyet/ad yalnız pasaportlu
        # yabanci bildiriminde kurum sozlesmesinin zorunlu alanlaridir.
        if action == "checkin" and not foreign_identity_card:
            if not _norm(snapshot.get("guest_name")):
                missing.append("guest_name")
            if not _norm(snapshot.get("birth_date")):
                missing.append("birth_date")
            if not _norm(snapshot.get("gender")):
                missing.append("gender")

    return (len(missing) == 0, missing)


def validate_or_raise(snapshot: dict, action: str = "checkin") -> None:
    """Geçersizse 422 fırlat. Geçerliyse no-op."""
    ok, missing = validate_kbs_payload(snapshot, action)
    if not ok:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "kbs_payload_incomplete",
                "missing_fields": missing,
                "message": ("KBS bildirimi için zorunlu alanlar eksik veya geçersiz: " + ", ".join(missing)),
            },
        )
