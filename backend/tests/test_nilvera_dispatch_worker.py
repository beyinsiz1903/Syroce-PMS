import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.integrations.invoice_dispatch_service import InvoiceDispatchService
from core.integrations.invoice_dispatch_worker import InvoiceDispatchWorker
from core.integrations.nilvera.errors import NilveraApiError
from models.schemas.invoice_sync import InvoiceDocumentKind, InvoiceProvider, InvoiceSyncState


@pytest.fixture
def mock_db(monkeypatch):
    db_mock = MagicMock()

    import core.integrations.invoice_dispatch_service as ids
    import core.integrations.invoice_dispatch_worker as idw
    import core.integrations.invoice_sync_repository as isr
    import core.integrations.nilvera.provisioner as inp

    monkeypatch.setattr(idw, "get_system_db", lambda: db_mock)
    monkeypatch.setattr(ids, "get_db_for_tenant", lambda t: db_mock)
    monkeypatch.setattr(isr, "get_db_for_tenant", lambda t: db_mock)
    monkeypatch.setattr(inp, "get_system_db", lambda: db_mock)

    return db_mock


@pytest.fixture
def worker():
    w = InvoiceDispatchWorker(poll_interval=0.1, batch_size=5)
    return w


@pytest.mark.asyncio
async def test_worker_claim_and_dispatch_success(worker, mock_db):
    dispatch_id = str(uuid.uuid4())

    # To avoid infinite loop, side_effect must return the doc then None.
    mock_db.invoice_sync.find_one_and_update = AsyncMock(side_effect=[
        {
            "id": dispatch_id,
            "tenant_id": "test-tenant",
            "invoice_id": str(uuid.uuid4()),
            "provider": InvoiceProvider.NILVERA,
            "state": InvoiceSyncState.SENDING
        },
        None
    ])

    # Run again with side_effect
    with patch("core.integrations.invoice_dispatch_worker.InvoiceDispatchService.execute_dispatch", new_callable=AsyncMock) as m_exec:
        m_exec.return_value = True
        processed_count = await worker._process_batch()

    assert processed_count == 1
    m_exec.assert_called_once_with("test-tenant", dispatch_id, worker_id=worker.worker_id)


@pytest.mark.asyncio
async def test_worker_stuck_recovery(worker, mock_db):
    mock_db.invoice_sync.update_many = AsyncMock(return_value=MagicMock(modified_count=2))

    recovered = await worker._recover_stuck()
    assert recovered == 2
    mock_db.invoice_sync.update_many.assert_called_once()

    call_args = mock_db.invoice_sync.update_many.call_args[0]
    assert call_args[0]["state"] == InvoiceSyncState.SENDING
    assert "lease_expires_at" in call_args[0]
    assert call_args[1]["$set"]["state"] == InvoiceSyncState.RETRYABLE_ERROR


@pytest.mark.asyncio
async def test_dispatch_service_retryable_error(mock_db, monkeypatch):
    tenant_id = "test-tenant-err"
    dispatch_id = str(uuid.uuid4())
    invoice_id = str(uuid.uuid4())

    mock_db.invoice_sync.find_one = AsyncMock(return_value={
        "id": dispatch_id,
        "tenant_id": tenant_id,
        "invoice_id": invoice_id,
        "provider": InvoiceProvider.NILVERA,
        "document_kind": InvoiceDocumentKind.E_INVOICE,
        "idempotency_key": "k",
        "request_uuid": str(uuid.uuid4()),
        "state": InvoiceSyncState.SENDING,
        "attempt_count": 1,
        "prepared_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    })

    mock_db.tenant_settings.find_one = AsyncMock(return_value={
        "tenant_id": tenant_id,
        "nilvera": {"enabled": True, "api_key_enc": "dummy", "seller": {"vkn": "1111111111", "name": "N", "tax_office": "O", "address": "A", "city": "C", "country": "TR"}}
    })

    mock_db.invoices.find_one = AsyncMock(return_value={
        "id": invoice_id,
        "tenant_id": tenant_id,
        "invoice_number": "TEST2024000000001",
        "invoice_type": "SATIS",
        "profile": "TICARIFATURA",
        "series": "ABC",
        "currency": "TRY",
        "issue_date": datetime.now(UTC),
        "buyer_tax_number": "1111111111",
        "buyer_alias": "urn:mail:customer-specific@example.test",
        "buyer_legal_name": "Test Buyer",
        "buyer_country_name": "Türkiye",
        "buyer_city": "İstanbul",
        "buyer_address": "Test Adres",
        "payable_total": 100.0,
        "items": [{"description": "X", "quantity": 1, "tax_quantity": 1, "unit_code": "C62", "unit_price": 100.0, "tax_unit_price": 100.0, "discount_amount": 0.0, "kdv_rate": 20.0, "kdv_amount": 20.0, "total": 100.0}],
    })

    mock_db.invoice_sync.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    with patch("core.integrations.nilvera.provisioner.get_crypto_service") as m_crypto, \
         patch("core.integrations.invoice_dispatch_service.NilveraHttpClient") as m_client_cls, \
         patch("core.integrations.invoice_dispatch_service.NilveraInvoiceMapper") as m_mapper:

        m_crypto.return_value.decrypt.return_value = "mock_api_key"

        m_mapper.map_to_nilvera.return_value = MagicMock()

        m_client = AsyncMock()
        err = NilveraApiError(http_status=429, message="Rate Limit", provider_code="429")
        err.retryable = True
        m_client.post.side_effect = err
        m_client_cls.return_value.__aenter__.return_value = m_client

        success = await InvoiceDispatchService.execute_dispatch(tenant_id, dispatch_id)

    assert not success
    mock_db.invoice_sync.update_one.assert_called()
    update_args = mock_db.invoice_sync.update_one.call_args[0][1]
    assert update_args["$set"]["state"] == InvoiceSyncState.RETRYABLE_ERROR.value
    assert update_args["$set"]["last_error_retryable"] is True
    assert update_args["$set"]["last_error_code"] == "429"


@pytest.mark.asyncio
async def test_dispatch_service_permanent_error(mock_db, monkeypatch):
    tenant_id = "test-tenant-perm"
    dispatch_id = str(uuid.uuid4())
    invoice_id = str(uuid.uuid4())

    mock_db.invoice_sync.find_one = AsyncMock(return_value={
        "id": dispatch_id,
        "tenant_id": tenant_id,
        "invoice_id": invoice_id,
        "provider": InvoiceProvider.NILVERA,
        "document_kind": InvoiceDocumentKind.E_INVOICE,
        "idempotency_key": "k",
        "request_uuid": str(uuid.uuid4()),
        "state": InvoiceSyncState.SENDING,
        "attempt_count": 1,
        "prepared_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    })

    mock_db.tenant_settings.find_one = AsyncMock(return_value={
        "tenant_id": tenant_id,
        "nilvera": {"enabled": True, "api_key_enc": "dummy", "seller": {"vkn": "1111111111", "name": "N", "tax_office": "O", "address": "A", "city": "C", "country": "TR"}}
    })

    mock_db.invoices.find_one = AsyncMock(return_value={
        "id": invoice_id,
        "tenant_id": tenant_id,
        "invoice_number": "TEST2024000000002",
        "invoice_type": "SATIS",
        "profile": "TICARIFATURA",
        "series": "ABC",
        "currency": "TRY",
        "issue_date": datetime.now(UTC),
        "buyer_tax_number": "1111111111",
        "buyer_alias": "urn:mail:customer-specific@example.test",
        "buyer_legal_name": "Test Buyer",
        "buyer_country_name": "Türkiye",
        "buyer_city": "İstanbul",
        "buyer_address": "Test Adres",
        "payable_total": 100.0,
        "items": [{"description": "X", "quantity": 1, "tax_quantity": 1, "unit_code": "C62", "unit_price": 100.0, "tax_unit_price": 100.0, "discount_amount": 0.0, "kdv_rate": 20.0, "kdv_amount": 20.0, "total": 100.0}],
    })

    mock_db.invoice_sync.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    with patch("core.integrations.nilvera.provisioner.get_crypto_service") as m_crypto, \
         patch("core.integrations.invoice_dispatch_service.NilveraHttpClient") as m_client_cls, \
         patch("core.integrations.invoice_dispatch_service.NilveraInvoiceMapper") as m_mapper:

        m_crypto.return_value.decrypt.return_value = "mock_api_key"

        m_mapper.map_to_nilvera.return_value = MagicMock()

        m_client = AsyncMock()
        err = NilveraApiError(http_status=400, message="Validation Failed", provider_code="400")
        err.retryable = False
        m_client.post.side_effect = err
        m_client_cls.return_value.__aenter__.return_value = m_client

        success = await InvoiceDispatchService.execute_dispatch(tenant_id, dispatch_id)

    assert not success
    mock_db.invoice_sync.update_one.assert_called()
    update_args = mock_db.invoice_sync.update_one.call_args[0][1]
    assert update_args["$set"]["state"] == InvoiceSyncState.PERMANENT_ERROR.value
    assert update_args["$set"]["last_error_retryable"] is False
    assert update_args["$set"]["last_error_code"] == "400"


@pytest.mark.asyncio
async def test_dispatch_service_409_duplicate(mock_db, monkeypatch):
    tenant_id = "test-tenant-409"
    dispatch_id = str(uuid.uuid4())

    mock_db.invoice_sync.find_one = AsyncMock(return_value={
        "id": dispatch_id, "tenant_id": tenant_id, "invoice_id": str(uuid.uuid4()),
        "provider": InvoiceProvider.NILVERA, "document_kind": InvoiceDocumentKind.E_INVOICE,
        "idempotency_key": "k", "request_uuid": str(uuid.uuid4()), "state": InvoiceSyncState.SENDING,
        "attempt_count": 1, "prepared_at": datetime.now(UTC), "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    })

    mock_db.tenant_settings.find_one = AsyncMock(return_value={"tenant_id": tenant_id, "nilvera": {"enabled": True, "api_key_enc": "dummy", "seller": {"vkn": "1111111111", "name": "N", "tax_office": "O", "address": "A", "city": "C", "country": "TR"}}})
    mock_db.invoices.find_one = AsyncMock(return_value={
        "id": str(uuid.uuid4()), "tenant_id": tenant_id, "invoice_number": "T1", "invoice_type": "SATIS",
        "profile": "TICARIFATURA", "series": "ABC", "currency": "TRY", "issue_date": datetime.now(UTC),
        "buyer_tax_number": "1", "buyer_alias": "urn:mail:customer-specific@example.test", "buyer_legal_name": "N", "buyer_country_name": "TR", "buyer_city": "IST",
        "buyer_address": "A", "payable_total": 100, "items": [{"description": "X", "quantity": 1, "tax_quantity": 1, "unit_code": "C62", "unit_price": 100.0, "tax_unit_price": 100.0, "discount_amount": 0.0, "kdv_rate": 20.0, "kdv_amount": 20.0, "total": 100.0}]
    })
    mock_db.invoice_sync.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    with patch("core.integrations.nilvera.provisioner.get_crypto_service") as m_crypto, \
         patch("core.integrations.invoice_dispatch_service.NilveraHttpClient") as m_client_cls, \
         patch("core.integrations.invoice_dispatch_service.NilveraInvoiceMapper") as m_mapper:

        m_crypto.return_value.decrypt.return_value = "mock_api_key"
        m_mapper.map_to_nilvera.return_value = MagicMock()

        m_client = AsyncMock()
        err = NilveraApiError(http_status=409, message="Conflict", provider_code="409")
        m_client.post.side_effect = err
        m_client_cls.return_value.__aenter__.return_value = m_client

        success = await InvoiceDispatchService.execute_dispatch(tenant_id, dispatch_id)

    assert not success
    update_args = mock_db.invoice_sync.update_one.call_args[0][1]
    assert update_args["$set"]["state"] == InvoiceSyncState.PERMANENT_ERROR.value
    assert update_args["$set"]["last_error_category"] == "DUPLICATE"

@pytest.mark.asyncio
async def test_dispatch_service_credential_error(mock_db, monkeypatch):
    tenant_id = "test-tenant-cred"
    dispatch_id = str(uuid.uuid4())

    mock_db.invoice_sync.find_one = AsyncMock(return_value={
        "id": dispatch_id, "tenant_id": tenant_id, "invoice_id": str(uuid.uuid4()),
        "provider": InvoiceProvider.NILVERA, "document_kind": InvoiceDocumentKind.E_INVOICE,
        "idempotency_key": "k", "request_uuid": str(uuid.uuid4()), "state": InvoiceSyncState.SENDING,
        "attempt_count": 3, "prepared_at": datetime.now(UTC), "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    })

    # Missing enabled flag or api_key
    mock_db.tenant_settings.find_one = AsyncMock(return_value={"tenant_id": tenant_id, "nilvera": {"enabled": False}})
    mock_db.invoice_sync.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    success = await InvoiceDispatchService.execute_dispatch(tenant_id, dispatch_id)

    assert not success
    update_args = mock_db.invoice_sync.update_one.call_args[0][1]
    assert update_args["$set"]["state"] == InvoiceSyncState.RETRYABLE_ERROR.value
    assert update_args["$set"]["last_error_category"] == "AUTHENTICATION"
    assert "$inc" not in update_args or "attempt_count" not in update_args.get("$inc", {})

@pytest.mark.asyncio
async def test_worker_graceful_shutdown(worker, mock_db):
    fut = asyncio.Future()
    worker._task = fut

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        await worker.stop()

    assert worker._stop.is_set()
    assert worker._task is None
    assert fut.cancelled()

@pytest.mark.asyncio
async def test_worker_concurrency(worker, mock_db):
    # If find_one_and_update returns None, it means another worker took it
    mock_db.invoice_sync.find_one_and_update = AsyncMock(return_value=None)
    processed = await worker._process_batch()
    assert processed == 0

@pytest.mark.asyncio
async def test_dispatch_service_missing_seller_info(mock_db, monkeypatch):
    tenant_id = "test-tenant-no-seller"
    dispatch_id = str(uuid.uuid4())

    mock_db.invoice_sync.find_one = AsyncMock(return_value={
        "id": dispatch_id, "tenant_id": tenant_id, "invoice_id": str(uuid.uuid4()),
        "provider": InvoiceProvider.NILVERA, "document_kind": InvoiceDocumentKind.E_INVOICE,
        "idempotency_key": "k", "request_uuid": str(uuid.uuid4()), "state": InvoiceSyncState.SENDING,
        "attempt_count": 1, "prepared_at": datetime.now(UTC), "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    })

    # 3. Seller eksikse HTTP çağrısı yapılmadığını kanıtlayan test eklenmeli
    mock_db.tenant_settings.find_one = AsyncMock(return_value={
        "tenant_id": tenant_id,
        "nilvera": {"enabled": True, "api_key_enc": "dummy"} # company_info is missing!
    })

    mock_db.invoices.find_one = AsyncMock(return_value={
            "id": str(uuid.uuid4()), "tenant_id": tenant_id, "invoice_number": "T1", "invoice_type": "SATIS",
            "profile": "TICARIFATURA", "series": "ABC", "currency": "TRY", "issue_date": datetime.now(UTC),
            "buyer_tax_number": "1", "buyer_alias": "urn:mail:customer-specific@example.test", "buyer_legal_name": "N", "buyer_country_name": "TR", "buyer_city": "IST",
            "buyer_address": "A", "payable_total": 100, "items": [{"description": "X", "quantity": 1, "tax_quantity": 1, "unit_code": "C62", "unit_price": 100.0, "tax_unit_price": 100.0, "discount_amount": 0.0, "kdv_rate": 20.0, "kdv_amount": 20.0, "total": 100.0}]
        })
    mock_db.invoice_sync.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    with patch("core.integrations.nilvera.provisioner.get_crypto_service") as m_crypto,          patch("core.integrations.invoice_dispatch_service.NilveraHttpClient") as m_client_cls:
        
        m_crypto.return_value.decrypt.return_value = "mock_api_key"
        success = await InvoiceDispatchService.execute_dispatch(tenant_id, dispatch_id)

    assert not success
    m_client_cls.assert_not_called() # 3. HTTP çağrısı kesinlikle yapılmamalı

    update_args = mock_db.invoice_sync.update_one.call_args[0][1]
    assert update_args["$set"]["state"] == InvoiceSyncState.PERMANENT_ERROR.value
    assert update_args["$set"]["last_error_category"] == "VALIDATION"
    assert "Tenant company info" in update_args["$set"]["last_error_message"]
