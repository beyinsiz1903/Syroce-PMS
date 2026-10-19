import asyncio
import ssl
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.messaging.providers import SMTPEmailProvider


@pytest.fixture
def smtp(monkeypatch):
    credentials = {"smtp_host": "smtppro.zoho.eu", "smtp_port": 587,
                   "smtp_username": "synthetic@example.test", "smtp_password": "synthetic-secret",
                   "from_email": "synthetic@example.test", "use_tls": True}
    client = MagicMock()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr("integrations.xchange.safety.assert_safe_host", MagicMock(return_value="185.230.212.129"))
    monkeypatch.setattr("modules.messaging.providers.smtplib.SMTP", factory)
    return SMTPEmailProvider(), credentials, client, factory


@pytest.mark.asyncio
async def test_connect_timeout_is_actionable_and_does_not_leak_exception_locals(smtp, caplog):
    provider, creds, client, factory = smtp
    factory.side_effect = TimeoutError("private-message-body synthetic-secret")
    result = await provider.send("recipient@example.test", "synthetic body", credentials=creds)
    assert not result["success"] and not result["outcome_unknown"]
    assert result["error_class"] == "timeout"
    assert result["error_code"] == "smtp_connect_timeout"
    assert "Zoho HTTPS" in result["error"]
    assert "private-message-body" not in str(result) + caplog.text
    assert "synthetic-secret" not in str(result) + caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    client.login.assert_not_called()
    client.sendmail.assert_not_called()


@pytest.mark.asyncio
async def test_success_keeps_dns_pinning_and_verifies_original_hostname(smtp):
    provider, creds, client, factory = smtp
    result = await provider.send("recipient@example.test", "synthetic body", credentials=creds)
    assert result["success"]
    factory.assert_called_once_with("185.230.212.129", 587, timeout=15)
    assert client._host == "smtppro.zoho.eu"
    context = client.starttls.call_args.kwargs["context"]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_teardown_failure_after_acceptance_is_still_success(smtp):
    provider, creds, client, _ = smtp
    client.quit.side_effect = TimeoutError("QUIT timed out")
    result = await provider.send("recipient@example.test", "test", credentials=creds)
    assert result["success"]
    client.sendmail.assert_called_once()
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_timeout_during_submission_is_unknown_not_retryable_failure(smtp):
    provider, creds, client, _ = smtp
    client.sendmail.side_effect = TimeoutError("response lost after submission")
    result = await provider.send("recipient@example.test", "test", credentials=creds)
    assert not result["success"] and result["outcome_unknown"]
    assert result["error_code"] == "smtp_delivery_unknown"
    assert "yeniden denemeyin" in result["error"]
    client.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("smtp_code,retryable", [(550, False), (451, True)])
async def test_definitive_data_rejection_is_not_unknown(smtp, smtp_code, retryable):
    import smtplib

    provider, creds, client, _ = smtp
    client.sendmail.side_effect = smtplib.SMTPDataError(smtp_code, b"rejected")
    result = await provider.send("recipient@example.test", "test", credentials=creds)
    assert not result["success"] and not result["outcome_unknown"]
    assert result["error_code"] == "smtp_rejected" and result["retryable"] is retryable


@pytest.mark.asyncio
async def test_sandbox_never_opens_smtp(smtp):
    provider, creds, _, factory = smtp
    result = await provider.send("recipient@example.test", "test", credentials=creds, mode="sandbox")
    assert result["success"] and result["mode"] == "sandbox"
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_health_respects_tls_setting_and_never_sends_mail(smtp):
    provider, creds, client, _ = smtp
    creds["use_tls"] = False
    result = await provider.check_health(creds)
    assert result["status"] == "healthy"
    client.starttls.assert_not_called()
    client.sendmail.assert_not_called()
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_health_timeout_has_same_diagnostic(smtp):
    provider, creds, _, factory = smtp
    factory.side_effect = TimeoutError("timed out")
    result = await provider.check_health(creds)
    assert result["status"] == "unhealthy" and result["error_code"] == "smtp_connect_timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["send", "check_health"])
async def test_smtp_wait_does_not_block_event_loop(smtp, method):
    provider, creds, client, factory = smtp
    release = threading.Event()

    def blocked_connect(*_args, **_kwargs):
        release.wait(1)
        return client

    factory.side_effect = blocked_connect
    task = asyncio.create_task(provider.send("recipient@example.test", "test", credentials=creds)
                               if method == "send" else provider.check_health(creds))
    try:
        await asyncio.sleep(0.02)
        assert not task.done(), "SMTP blocked the event loop until the connect completed"
    finally:
        release.set()
        await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_service_returns_the_same_actionable_failure_that_it_records(monkeypatch):
    from modules.messaging.service import MessagingService

    logs = SimpleNamespace(insert_one=AsyncMock(), update_one=AsyncMock())
    service = MessagingService(SimpleNamespace(messaging_delivery_logs=logs))
    service._check_consent = AsyncMock(return_value=True)
    service._check_rate_limit = AsyncMock(return_value=True)
    service._get_provider_config = AsyncMock(return_value={"is_sandbox": False})
    service._load_credentials = AsyncMock(return_value={})
    failure = {"success": False, "error": "SMTP bağlantısı zaman aşımına uğradı; Zoho HTTPS API kullanın.",
               "error_class": "timeout", "error_code": "smtp_connect_timeout", "delivery_stage": "connect"}
    monkeypatch.setattr(SMTPEmailProvider, "send", AsyncMock(return_value=failure))
    result = await service.send_message("hotel", "email", "recipient@example.test", body="synthetic")
    assert result["error"] == failure["error"] and result["error_code"] == "smtp_connect_timeout"
    recorded = logs.update_one.call_args.args[1]["$set"]
    assert recorded["error_message"] == result["error"] and recorded["delivery_stage"] == "connect"


@pytest.mark.asyncio
async def test_health_diagnostic_is_persisted_with_tenant_filter(monkeypatch):
    from modules.messaging.service import MessagingService

    configs = SimpleNamespace(
        find=MagicMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[{
            "id": "config", "provider_type": "smtp_email", "credentials_encrypted": {},
        }]))), update_one=AsyncMock(),
    )
    monkeypatch.setattr(SMTPEmailProvider, "check_health", AsyncMock(return_value={
        "status": "unhealthy", "error": "SMTP bağlantısı zaman aşımına uğradı.", "error_code": "smtp_connect_timeout",
    }))
    await MessagingService(SimpleNamespace(messaging_provider_configs=configs)).check_all_providers("hotel")
    query, update = configs.update_one.call_args.args
    assert query == {"id": "config", "tenant_id": "hotel"}
    assert update["$set"]["health_error_code"] == "smtp_connect_timeout"


@pytest.mark.asyncio
async def test_retry_does_not_reschedule_permanent_smtp_error(monkeypatch):
    from modules.messaging.service import MessagingService

    logs = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "delivery", "status": "failed", "retry_count": 0,
                                        "provider_type": "smtp_email", "channel": "email",
                                        "recipient": "recipient@example.test", "body": "synthetic"}),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
    )
    service = MessagingService(SimpleNamespace(messaging_delivery_logs=logs))
    service._check_consent = AsyncMock(return_value=True)
    service._get_provider_config = AsyncMock(return_value={"is_sandbox": False})
    service._load_credentials = AsyncMock(return_value={})
    monkeypatch.setattr(SMTPEmailProvider, "send", AsyncMock(return_value={
        "success": False, "error": "SMTP kimlik doğrulaması başarısız.", "retryable": False,
        "error_class": "authentication_error", "error_code": "smtp_authentication_error",
        "delivery_stage": "authenticate",
    }))
    await service.retry_failed("hotel", "delivery")
    query, update = logs.update_one.call_args.args
    assert query == {"id": "delivery", "tenant_id": "hotel"}
    assert update["$set"]["next_retry_at"] is None
    assert update["$set"]["error_code"] == "smtp_authentication_error"
