"""Bounded, offline decoder regressions for CVE-2026-114605/106435.

Cases follow the producers' stated fixed behavior, not a network exploit:
https://github.com/rthalley/dnspython/commit/b485e46
https://github.com/mongodb/mongo-python-driver/commit/bb8d4e1
"""
import array
import mmap
import struct
from importlib.metadata import version

import bson
import dns.name
import pytest
from packaging.version import Version


@pytest.fixture(autouse=True)
def require_patched_decoders():
    # Fail clearly on an uninstalled requirements update before exercising any
    # malformed native-buffer input on an older, potentially unsafe decoder.
    assert Version(version('pymongo')) >= Version('4.18.3'), 'Install patched backend requirements first'
    assert Version(version('dnspython')) >= Version('2.9.0'), 'Install patched backend requirements first'


def test_dns_root_at_compression_limit_still_decodes():
    chain = b'\0\0' + b''.join(bytes([0xC0, offset]) for offset in range(0, 32, 2))
    name, consumed = dns.name.from_wire(chain, len(chain) - 2)
    assert name == dns.name.root and consumed == 2


def test_dns_one_excess_pointer_is_rejected_without_network_or_large_input():
    chain = b'\0\0' + b''.join(bytes([0xC0, offset]) for offset in range(0, 34, 2))
    with pytest.raises(dns.name.PointerChainTooLong):
        dns.name.from_wire(chain, len(chain) - 2)


@pytest.mark.parametrize('pattern', ['', 'a', 'oda'])
def test_bson_truncated_regex_rejects_every_supported_buffer(pattern):
    short = bytearray(bson.encode({'room': bson.Regex(pattern, '')}))
    short = short[:-2]  # Unterminated flags and absent document terminator.
    short[:4] = struct.pack('<i', len(short))
    wire = bytes(short)
    for source in (wire, bytearray(wire), memoryview(wire), array.array('B', wire)):
        for decode in (bson.decode, bson.decode_all):
            with pytest.raises(bson.errors.InvalidBSON):
                decode(source)
    with mmap.mmap(-1, len(wire)) as mapped:
        mapped.write(wire)
        for decode in (bson.decode, bson.decode_all):
            with pytest.raises(bson.errors.InvalidBSON):
                decode(mapped)


def test_valid_bson_regex_empty_flags_still_roundtrips():
    value = {'room': bson.Regex('102', '')}
    wire = bson.encode(value)
    assert bson.decode(wire) == value
    with mmap.mmap(-1, len(wire)) as mapped:
        mapped.write(wire)
        assert bson.decode(mapped) == value and bson.decode_all(mapped) == [value]
