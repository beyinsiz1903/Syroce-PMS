"""Read-only search aliases for the one reviewed presentation tenant.

No stored guest, booking, finance, external identity or audit source is renamed.
The normal readers' tenant/visibility/deleted guards still apply.
"""
import json
import unicodedata
from pathlib import Path

from security.search_normalize import normalize_search_value

REGISTRY = json.loads(Path(__file__).with_name("frontdesk_presentation.json").read_text())
TENANT = REGISTRY["tenant_id"]


def _fold(value):
    text = normalize_search_value(value) or ""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).replace("ı", "i")


def guest_alias_matches(tenant_id, query):
    if tenant_id != TENANT or not isinstance(query, str):
        return []
    normalized = _fold(query.strip())
    if not 2 <= len(normalized) <= 200:
        return []
    return [guest for guest in REGISTRY["guests"] if normalized in _fold(guest["display"])]


def guest_alias_conditions(tenant_id, query):
    conditions = []
    for guest in guest_alias_matches(tenant_id, query):
        first, _, last = guest["original"].partition(" ")
        # A stale first/last companion must not override a separately renamed
        # canonical name. Split-name fallback is only for legacy rows without it.
        conditions.append({"id": guest["id"], "$or": [
            {"name": guest["original"]},
            {"$and": [
                {"$or": [{"name": {"$exists": False}}, {"name": None}, {"name": ""}]},
                {"first_name": first, "last_name": last},
            ]},
        ]})
    return conditions
