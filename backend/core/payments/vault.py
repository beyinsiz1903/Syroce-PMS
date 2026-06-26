"""Kart kasasi (vault) token soyutlamasi.

Uygulama kodu kart bilgisini DOLASTIRMAZ; yalnizca opak bir kasa referansi
(vault_card_ref) tasir. Ham PAN/CVV YALNIZCA adapter sinirinda, tahsilat
aninda cozulur; bellekte omru minimumdur ve ASLA loglanmaz.

Mevcut AES-256-GCM alan sifrelemesi (vcc_cards) korunur; bu modul yalnizca
cozumleme/maskeleme yardimcilarini ekler (additive, Zero Bloat).
"""
from __future__ import annotations

from dataclasses import dataclass

from security.field_encryption import get_field_encryption_service

from .contracts import PaymentError

_REF_PREFIX = "vault_v1:"


class VaultCardNotFound(PaymentError):
    """vault_card_ref tenant icinde bulunamadi (fail-closed)."""

    error_code = "vault_card_not_found"
    http_status = 404


def mask_pan(number: str | None) -> str:
    """PAN'i maskele: ilk 6 + son 4 hane gorunur, gerisi yildiz."""
    if not number:
        return "****"
    clean = number.replace(" ", "").replace("-", "")
    if len(clean) <= 10:
        return clean[:2] + "*" * max(len(clean) - 4, 0) + clean[-2:]
    return clean[:6] + "*" * (len(clean) - 10) + clean[-4:]


def make_vault_card_ref(card_id: str) -> str:
    """Bir kasa kart id'sinden opak referans uret."""
    if not card_id:
        raise VaultCardNotFound("bos card_id")
    return f"{_REF_PREFIX}{card_id}"


def parse_vault_card_ref(ref: str) -> str:
    """Opak referanstan kasa kart id'sini cozumle (prefix'li/prefix'siz)."""
    if not ref or not isinstance(ref, str):
        raise VaultCardNotFound("gecersiz vault_card_ref")
    if ref.startswith(_REF_PREFIX):
        return ref[len(_REF_PREFIX):]
    return ref


@dataclass
class CardMaterial:
    """Cozulmus kart bilgisi — yalnizca adapter sinirinda, gecici kullanim.

    repr/str maskelidir; PAN/CVV log/exception/trace'e sizmaz. Kullanim sonrasi
    `clear()` ile alanlar None'a cekilmelidir (try/finally).
    """

    pan: str | None
    expiry: str | None
    holder: str | None = None
    cvv: str | None = None
    card_type: str = "virtual"
    source: str | None = None

    @property
    def masked(self) -> str:
        return mask_pan(self.pan)

    def clear(self) -> None:
        self.pan = None
        self.expiry = None
        self.cvv = None
        self.holder = None

    def __repr__(self) -> str:
        return (
            f"CardMaterial(masked={self.masked!r}, card_type={self.card_type!r}, "
            f"has_cvv={bool(self.cvv)})"
        )

    __str__ = __repr__


async def resolve_card_material(
    db, *, tenant_id: str, vault_card_ref: str
) -> CardMaterial:
    """Kasa referansini cozup kart bilgisini dondurur (tenant-kapsamli).

    AES-256-GCM cozumleme yalnizca burada yapilir. Cagiran (adapter) sonucu
    minimum sure tutmali ve `clear()` cagirmalidir. Bulunamayan kart fail-closed
    `VaultCardNotFound` atar; ASLA bos/sahte kart donmez.
    """
    if not tenant_id:
        raise VaultCardNotFound("tenant_id zorunlu")
    card_id = parse_vault_card_ref(vault_card_ref)

    doc = await db.vcc_cards.find_one(
        {"id": card_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not doc:
        raise VaultCardNotFound("kasa kart referansi bulunamadi")

    enc = get_field_encryption_service()
    pan = enc.decrypt_value(doc.get("card_number_enc", ""))
    expiry = enc.decrypt_value(doc.get("expiry_enc", ""))
    holder = (
        enc.decrypt_value(doc.get("card_holder_enc", ""))
        if doc.get("card_holder_enc")
        else None
    )
    cvv = (
        enc.decrypt_value(doc.get("cvv_enc", "")) if doc.get("cvv_enc") else None
    )

    return CardMaterial(
        pan=pan,
        expiry=expiry,
        holder=holder,
        cvv=cvv,
        card_type=doc.get("card_type", "virtual"),
        source=doc.get("source"),
    )
