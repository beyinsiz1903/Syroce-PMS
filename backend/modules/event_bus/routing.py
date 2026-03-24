"""
Tenant-Aware Event Routing.
Routes events based on tenant, property, and role context.
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("event_bus.routing")


class EventRouter:
    """Manages tenant-aware, property-scoped event routing rules."""

    def __init__(self):
        self._routing_rules: Dict[str, List[dict]] = {}

    def add_rule(self, tenant_id: str, event_type: str,
                 target_roles: List[str], property_ids: Optional[List[str]] = None,
                 priority_override: Optional[str] = None) -> dict:
        """Add a custom routing rule for a tenant."""
        rule = {
            "event_type": event_type,
            "target_roles": target_roles,
            "property_ids": property_ids,
            "priority_override": priority_override,
        }
        if tenant_id not in self._routing_rules:
            self._routing_rules[tenant_id] = []
        self._routing_rules[tenant_id].append(rule)
        return rule

    def get_rules(self, tenant_id: str) -> List[dict]:
        return self._routing_rules.get(tenant_id, [])

    def should_route(self, tenant_id: str, event_type: str,
                     session_roles: List[str],
                     session_property_ids: List[str],
                     event_property_id: Optional[str] = None) -> bool:
        """Check if an event should be routed to a specific session."""
        rules = self._routing_rules.get(tenant_id, [])
        matching_rules = [r for r in rules if r["event_type"] == event_type]

        if not matching_rules:
            return True  # no custom rules, use default routing

        for rule in matching_rules:
            role_match = any(r in rule["target_roles"] for r in session_roles)
            if not role_match:
                continue
            if rule["property_ids"] and event_property_id:
                if event_property_id not in rule["property_ids"]:
                    continue
            return True

        return False

    def get_routing_summary(self) -> dict:
        return {
            "total_tenants_with_rules": len(self._routing_rules),
            "total_rules": sum(len(r) for r in self._routing_rules.values()),
            "tenants": {
                tid: len(rules) for tid, rules in self._routing_rules.items()
            },
        }


event_router = EventRouter()
