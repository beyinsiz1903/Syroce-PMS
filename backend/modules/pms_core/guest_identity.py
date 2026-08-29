"""Canonical guest identity matching used by PMS creation and search flows."""

from __future__ import annotations

import re
from typing import Any

from security.encrypted_lookup import decrypt_guest_doc, guest_pii_or_conditions

_PLACEHOLDER_EMAIL_SUFFIX = "@placeholder.local"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _clean_phone(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _clean_document(value: Any) -> str:
    return re.sub(r"[^0-9a-z]", "", str(value or "").casefold())


def guest_identity_tokens(guest: dict[str, Any], *, include_name_fallback: bool = False) -> set[str]:
    """Build privacy-safe in-memory comparison tokens from a decrypted guest."""
    tokens: set[str] = set()
    name = _clean_text(guest.get("name") or f"{guest.get('first_name', '')} {guest.get('last_name', '')}")
    document = _clean_document(guest.get("id_number") or guest.get("passport_number"))
    if document:
        tokens.add(f"document:{document}")

    email = _clean_text(guest.get("email"))
    if email and not email.endswith(_PLACEHOLDER_EMAIL_SUFFIX):
        tokens.add(f"email:{email}|name:{name}" if name else f"email:{email}")

    phone = _clean_phone(guest.get("phone"))
    if len(phone) >= 7:
        tokens.add(f"phone:{phone}|name:{name}" if name else f"phone:{phone}")

    if not tokens and include_name_fallback:
        if name:
            tokens.add(f"name-only:{name}")
    return tokens


def _canonical_guest_rank(guest: dict[str, Any]) -> tuple:
    identity_count = len(guest_identity_tokens(guest))
    return (
        int(guest.get("total_stays") or 0),
        float(guest.get("total_spend") or 0),
        identity_count,
        str(guest.get("updated_at") or guest.get("created_at") or ""),
    )


def deduplicate_guest_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse search-only duplicates while keeping the strongest profile.

    Strong identifiers (document, e-mail, phone) drive identity matching. When
    historical quick-booking rows contain no identifier at all, identical
    normalized names are collapsed only in the suggestion list; no database
    records are merged on name alone.
    """
    groups: list[tuple[set[str], dict[str, Any]]] = []
    for record in records:
        tokens = guest_identity_tokens(record, include_name_fallback=True)
        matching_indexes = [index for index, (known, _guest) in enumerate(groups) if known & tokens]
        if not matching_indexes:
            groups.append((set(tokens), record))
            continue

        first = matching_indexes[0]
        merged_tokens = set(tokens)
        candidates = [record]
        for index in reversed(matching_indexes):
            known, guest = groups.pop(index)
            merged_tokens.update(known)
            candidates.append(guest)
        canonical = max(candidates, key=_canonical_guest_rank)
        groups.insert(first, (merged_tokens, canonical))

    return [guest for _tokens, guest in groups]


async def find_existing_guest_by_identity(guest_collection, tenant_id: str, candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Find a tenant-local guest sharing a strong identity with ``candidate``.

    Name-only records are deliberately not reused automatically. Document
    number is sufficient; e-mail and phone additionally require the same name
    when both records have a name, preventing household contact details from
    silently joining different people.
    """
    candidate_tokens = guest_identity_tokens(candidate)
    if not candidate_tokens:
        return None

    branches: list[dict] = []
    for field in ("id_number", "passport_number", "email", "phone"):
        raw = str(candidate.get(field) or "").strip()
        if not raw or (field == "email" and raw.casefold().endswith(_PLACEHOLDER_EMAIL_SUFFIX)):
            continue
        variants = {raw}
        if field in {"id_number", "passport_number"}:
            variants.add(_clean_document(raw))
        elif field == "phone":
            variants.add(_clean_phone(raw))
        elif field == "email":
            variants.add(_clean_text(raw))
        for variant in variants:
            if variant:
                branches.extend(guest_pii_or_conditions(field, variant))
    if not branches:
        return None

    query = {
        "tenant_id": tenant_id,
        "archived": {"$ne": True},
        "status": {"$ne": "deleted"},
        "$or": branches,
    }
    rows = await guest_collection.find(query, {"_id": 0}).limit(50).to_list(50)
    candidate_name = _clean_text(candidate.get("name"))
    matches: list[dict[str, Any]] = []
    for raw_guest in rows:
        guest = decrypt_guest_doc(raw_guest)
        shared = candidate_tokens & guest_identity_tokens(guest)
        if not shared:
            continue
        document_match = any(token.startswith("document:") for token in shared)
        guest_name = _clean_text(guest.get("name") or f"{guest.get('first_name', '')} {guest.get('last_name', '')}")
        if document_match or not candidate_name or not guest_name or candidate_name == guest_name:
            matches.append(guest)
    return max(matches, key=_canonical_guest_rank) if matches else None
