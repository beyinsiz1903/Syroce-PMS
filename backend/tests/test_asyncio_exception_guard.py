import asyncio
import logging
import socket

import pytest

from core.asyncio_exception_guard import (
    TransientAsyncioDnsGuard,
    is_transient_unretrieved_dns_failure,
)


def _dns_context() -> dict[str, object]:
    return {
        "message": "Future exception was never retrieved",
        "exception": socket.gaierror(getattr(socket, "EAI_AGAIN", -3), "temporary failure"),
    }


def test_matches_only_unretrieved_retryable_dns_failure():
    assert is_transient_unretrieved_dns_failure(_dns_context())
    assert not is_transient_unretrieved_dns_failure({"message": "Future exception was never retrieved"})
    assert not is_transient_unretrieved_dns_failure(
        {"message": "Task exception was never retrieved", "exception": _dns_context()["exception"]}
    )
    assert not is_transient_unretrieved_dns_failure(
        {"message": "Future exception was never retrieved", "exception": ValueError("bug")}
    )


@pytest.mark.asyncio
async def test_guard_demotes_isolated_dns_hiccup_and_escalates_burst(caplog):
    guard = TransientAsyncioDnsGuard(threshold=2)
    loop = asyncio.get_running_loop()
    old_handler = loop.get_exception_handler()
    try:
        guard.install(loop)
        with caplog.at_level(logging.WARNING, logger="asyncio.transient_dns"):
            loop.call_exception_handler(_dns_context())
            loop.call_exception_handler(_dns_context())
        records = [record for record in caplog.records if record.name == "asyncio.transient_dns"]
        assert records[0].levelno == logging.WARNING
        assert records[1].levelno == logging.ERROR
        assert "will retry next tick" in records[0].getMessage()
        assert "sustained transient db error" in records[1].getMessage()
    finally:
        loop.set_exception_handler(old_handler)
        if hasattr(loop, "_syroce_transient_dns_guard"):
            delattr(loop, "_syroce_transient_dns_guard")


@pytest.mark.asyncio
async def test_guard_delegates_every_unrelated_exception():
    received: list[dict[str, object]] = []
    loop = asyncio.get_running_loop()
    old_handler = loop.get_exception_handler()
    try:
        loop.set_exception_handler(lambda _loop, context: received.append(context))
        TransientAsyncioDnsGuard().install(loop)
        context = {"message": "Task exception was never retrieved", "exception": ValueError("bug")}
        loop.call_exception_handler(context)
        assert received == [context]
    finally:
        loop.set_exception_handler(old_handler)
        if hasattr(loop, "_syroce_transient_dns_guard"):
            delattr(loop, "_syroce_transient_dns_guard")
