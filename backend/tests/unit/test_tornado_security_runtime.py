"""Bounded, socket-free Tornado 6.6 security and Flower compatibility checks.

Upstream: https://www.tornadoweb.org/en/stable/releases/v6.6.0.html
No external server, broker, task worker or production data is used.
"""
import asyncio
import re
from importlib.metadata import metadata, requires, version
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]


def test_tornado_security_pin_and_post_install_guard():
    pins = [Requirement(line) for line in (ROOT / 'requirements/worker.txt').read_text().splitlines()
            if line.strip() and not line.startswith(('#', '-'))]
    pin = next(item for item in pins if item.name == 'tornado')
    assert Version('6.5.9') not in pin.specifier
    assert Version('6.6.0') in pin.specifier
    assert "Version(tornado.version) >= Version('6.6.0')" in (ROOT / 'scripts/post_install.sh').read_text()


@pytest.fixture
def patched_runtime():
    assert Version(version('tornado')) >= Version('6.6.0'), 'Install patched worker requirements first'


def test_flower_requirement_and_image_python_floor_accept_the_patch(patched_runtime):
    dependency = next(Requirement(item) for item in requires('flower') if Requirement(item).name == 'tornado')
    assert Version(version('tornado')) in dependency.specifier
    python_range = SpecifierSet(metadata('tornado')['Requires-Python'])
    assert Version('3.11') in python_range
    for filename in ('backend/Dockerfile', 'worker/Dockerfile'):
        images = re.findall(r'^FROM python:([\d.]+)', (ROOT.parent / filename).read_text(), re.M)
        assert images and all(Version(item) in python_range for item in images)


@pytest.mark.parametrize('continuation', [' continued', '\tcontinued'])
def test_obsolete_folded_header_is_rejected(patched_runtime, continuation):
    from tornado.httputil import HTTPHeaders, HTTPInputError

    headers = HTTPHeaders()
    headers.parse_line('X-Test: original')
    with pytest.raises(HTTPInputError, match='folding not supported'):
        headers.parse_line(continuation)
    assert headers['X-Test'] == 'original'


def test_normal_headers_still_parse(patched_runtime):
    from tornado.httputil import HTTPHeaders

    headers = HTTPHeaders.parse('Content-Type: application/json\r\nContent-Length: 2\r\n')
    assert headers['Content-Type'] == 'application/json' and headers['Content-Length'] == '2'


@pytest.mark.parametrize('template,capture', [
    ('/{0}/destination', '/example.invalid'),
    ('/{0}/destination', '\\example.invalid'),
    ('https://trusted.invalid{0}', '@example.invalid/'),
    ('{0}', 'https://example.invalid/'),
])
def test_redirect_substitution_cannot_change_origin(patched_runtime, template, capture):
    from tornado.web import HTTPError, RedirectHandler

    handler = SimpleNamespace(_url=template, _permanent=True,
                              request=SimpleNamespace(query_arguments={}), redirect=Mock())
    with pytest.raises(HTTPError) as exc:
        RedirectHandler.get(handler, capture)
    assert exc.value.status_code == 400
    handler.redirect.assert_not_called()


def test_relative_redirect_retains_query(patched_runtime):
    from tornado.web import RedirectHandler

    handler = SimpleNamespace(_url='/safe/{0}', _permanent=True,
        request=SimpleNamespace(query_arguments={'view': [b'workers']}), redirect=Mock())
    RedirectHandler.get(handler, 'dashboard')
    handler.redirect.assert_called_once_with('/safe/dashboard?view=workers', permanent=True)


class BufferedStream:
    """Already-arrived tiny input; completed reads must not themselves yield."""
    max_buffer_size = 4096

    def __init__(self, body):
        self.body = body

    def set_close_callback(self, callback):
        self.close_callback = callback

    def read_bytes(self, count, **_kwargs):
        assert len(self.body) >= count
        result, self.body = self.body[:count], self.body[count:]
        future = asyncio.get_running_loop().create_future()
        future.set_result(result)
        return future

    def read_until(self, delimiter, **_kwargs):
        return self.read_bytes(self.body.index(delimiter) + len(delimiter))


def test_small_chunks_are_coalesced_and_yield_without_large_payload(patched_runtime):
    from tornado.http1connection import HTTP1Connection, HTTP1ConnectionParameters

    async def check():
        # Only512 data bytes / ~3KiB wire. This is a parser test, not a load test.
        stream = BufferedStream(b'1\r\na\r\n' * 512 + b'0\r\n\r\n')
        connection = HTTP1Connection(stream, False, HTTP1ConnectionParameters(chunk_size=16, max_body_size=1024))
        received, scheduled = [], []
        asyncio.get_running_loop().call_soon(scheduled.append, True)
        await connection._read_chunked_body(SimpleNamespace(data_received=received.append))
        assert b''.join(received) == b'a' * 512
        assert len(received) == 32
        assert scheduled == [True], 'The parser must give the event loop a turn'
        assert not stream.body
    asyncio.run(check())


@pytest.mark.parametrize('body', [b'1\r\naXX', b'0\r\nXX'])
def test_bad_chunk_terminator_is_a_protocol_error(patched_runtime, body):
    from tornado.http1connection import HTTP1Connection, HTTP1ConnectionParameters
    from tornado.httputil import HTTPInputError

    async def check():
        connection = HTTP1Connection(BufferedStream(body), False, HTTP1ConnectionParameters(max_body_size=1024))
        with pytest.raises(HTTPInputError, match='improperly terminated'):
            await connection._read_chunked_body(SimpleNamespace(data_received=lambda _data: None))
    asyncio.run(check())


def test_flower_application_initializes_without_starting_broker_or_listener(patched_runtime):
    from celery import Celery
    from flower.app import Flower

    async def check():
        celery = Celery('socket-free-tornado-compatibility', broker='memory://', backend='cache+memory://')
        with patch.object(celery, 'connection_for_read', side_effect=AssertionError('No broker I/O allowed')):
            app = Flower(capp=celery)
            try:
                assert not app.started
                assert not app.events.is_alive()
                assert not app.events.timer.is_running()
                assert app.capp is celery
            finally:
                app.executor.shutdown(wait=True)
    asyncio.run(check())
