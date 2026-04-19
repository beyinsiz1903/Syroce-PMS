"""Partner registry — capability matrix and per-tenant config.

Catalog is hard-coded (sertifikasyon hattındaki partner listesi),
per-tenant credentials/endpoints live in MongoDB
(`xchange_partner_configs`).
"""
from __future__ import annotations

from typing import Any

from .schemas import Direction, MessageType, PartnerCapability


class PartnerDefinition:
    def __init__(
        self,
        code: str,
        name: str,
        category: str,
        adapter_module: str,
        capabilities: list[PartnerCapability],
        description: str = "",
        cert_status: str = "in_development",  # in_development / uat / certified
        config_schema: dict[str, Any] | None = None,
    ):
        self.code = code
        self.name = name
        self.category = category  # gds / crs / erp / pos / loyalty / channel / generic
        self.adapter_module = adapter_module
        self.capabilities = capabilities
        self.description = description
        self.cert_status = cert_status
        self.config_schema = config_schema or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "cert_status": self.cert_status,
            "config_schema": self.config_schema,
            "capabilities": [
                {
                    "message_type": c.message_type.value,
                    "direction": c.direction.value,
                    "certified": c.certified,
                }
                for c in self.capabilities
            ],
        }


_OUT = Direction.OUTBOUND
_IN = Direction.INBOUND


PARTNERS: dict[str, PartnerDefinition] = {
    "sabre_synxis": PartnerDefinition(
        code="sabre_synxis",
        name="Sabre SynXis (CRS)",
        category="gds",
        adapter_module="integrations.xchange.adapters.sabre_synxis",
        description=(
            "Sabre SynXis Central Reservation System — HTNG 2024B XML "
            "üzerinden rezervasyon/inventory/rate çift yönlü senkron."
        ),
        cert_status="uat",
        capabilities=[
            PartnerCapability(message_type=MessageType.RESERVATION_CREATE, direction=_OUT),
            PartnerCapability(message_type=MessageType.RESERVATION_MODIFY, direction=_OUT),
            PartnerCapability(message_type=MessageType.RESERVATION_CANCEL, direction=_OUT),
            PartnerCapability(message_type=MessageType.RESERVATION_CREATE, direction=_IN),
            PartnerCapability(message_type=MessageType.RESERVATION_MODIFY, direction=_IN),
            PartnerCapability(message_type=MessageType.RESERVATION_CANCEL, direction=_IN),
            PartnerCapability(message_type=MessageType.INVENTORY_UPDATE, direction=_OUT),
            PartnerCapability(message_type=MessageType.RATE_UPDATE, direction=_OUT),
        ],
        config_schema={
            "endpoint": {"label": "SynXis Endpoint URL", "type": "url",
                         "default": "https://synxis-uat.sabre.com/htng/v2024b"},
            "username": {"label": "Username", "type": "text"},
            "password": {"label": "Password", "type": "secret"},
            "hotel_code": {"label": "SynXis Hotel Code", "type": "text"},
        },
    ),
    "sap_s4hana": PartnerDefinition(
        code="sap_s4hana",
        name="SAP S/4HANA Finance",
        category="erp",
        adapter_module="integrations.xchange.adapters.sap_s4hana",
        description=(
            "Gece denetimi sonu finans defteri (Journal Entry) ve "
            "günlük posting akışı için SAP S/4HANA OData V4 entegrasyonu."
        ),
        cert_status="uat",
        capabilities=[
            PartnerCapability(message_type=MessageType.POSTING_CHARGE, direction=_OUT),
            PartnerCapability(message_type=MessageType.POSTING_PAYMENT, direction=_OUT),
            PartnerCapability(message_type=MessageType.NIGHT_AUDIT_CLOSE, direction=_OUT),
        ],
        config_schema={
            "base_url": {"label": "SAP OData base URL", "type": "url",
                         "default": "https://my-s4hana.example.com/sap/opu/odata4/sap"},
            "company_code": {"label": "Company Code (BUKRS)", "type": "text"},
            "ledger": {"label": "Ledger (RLDNR)", "type": "text", "default": "0L"},
            "client_id": {"label": "OAuth Client ID", "type": "text"},
            "client_secret": {"label": "OAuth Client Secret", "type": "secret"},
            "token_url": {"label": "OAuth Token URL", "type": "url"},
        },
    ),
    "generic_webhook": PartnerDefinition(
        code="generic_webhook",
        name="Generic Webhook (Zapier/Make/n8n)",
        category="generic",
        adapter_module="integrations.xchange.adapters.generic_webhook",
        description=(
            "HMAC imzalı outbound JSON webhook — Zapier, Make, n8n veya "
            "kendi HTTP endpoint'inize standart Syroce zarfı gönderir."
        ),
        cert_status="certified",
        capabilities=[
            PartnerCapability(message_type=mt, direction=_OUT, certified=True)
            for mt in MessageType
        ],
        config_schema={
            "url": {"label": "Webhook URL", "type": "url"},
            "secret": {"label": "HMAC Shared Secret", "type": "secret"},
        },
    ),
}


def list_partners() -> list[dict[str, Any]]:
    return [p.to_dict() for p in PARTNERS.values()]


def get_partner(code: str) -> PartnerDefinition | None:
    return PARTNERS.get(code)
