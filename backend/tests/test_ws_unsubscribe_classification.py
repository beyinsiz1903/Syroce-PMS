import logging

import pytest

from infra.ws_redis_adapter import WebSocketRedisAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_level"),
    [
        (RuntimeError("unable to perform operation on <TCPTransport closed=True>"), logging.WARNING),
        (RuntimeError("command not allowed for this role"), logging.ERROR),
    ],
)
async def test_unsubscribe_classifies_closed_transport_without_hiding_other_errors(
    caplog, failure, expected_level
):
    class BrokenPubSub:
        async def unsubscribe(self, _channel):
            raise failure

    adapter = WebSocketRedisAdapter()
    adapter._active = True
    adapter._pubsub = BrokenPubSub()
    channel = f"{adapter.CHANNEL_PREFIX}room-1"
    adapter._subscribed_channels.add(channel)
    adapter._channel_refcounts[channel] = 1

    with caplog.at_level(logging.WARNING):
        await adapter.unsubscribe("room-1")

    records = [record for record in caplog.records if "WS unsubscribe" in record.message]
    assert len(records) == 1
    assert records[0].levelno == expected_level
    assert channel not in adapter._channel_refcounts
