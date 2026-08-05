from unittest.mock import MagicMock

import pytest

import core.tenant_db as tenant_db
from core.tenant_db import (
    SchemaOnlyCollection,
    TenantAwareDBProxy,
    TenantViolationError,
    clear_tenant_context,
)


@pytest.mark.parametrize(
    "collection_name",
    ("incoming_invoices", "incoming_invoice_lines", "incoming_invoice_sync_state"),
)
def test_incoming_invoice_collections_require_tenant_context(collection_name):
    clear_tenant_context()
    original_strict_mode = tenant_db.STRICT_TENANT_MODE
    tenant_db.STRICT_TENANT_MODE = True
    try:
        proxy = TenantAwareDBProxy(MagicMock())
        collection = getattr(proxy, collection_name)
        assert isinstance(collection, SchemaOnlyCollection)
        with pytest.raises(TenantViolationError):
            _ = collection.find_one
    finally:
        tenant_db.STRICT_TENANT_MODE = original_strict_mode
