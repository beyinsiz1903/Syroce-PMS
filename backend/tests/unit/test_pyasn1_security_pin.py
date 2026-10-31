"""Bounded, offline decoder compatibility checks for the 0.6.5 security floor.

The four upstream fixes are documented at
https://github.com/pyasn1/pyasn1/releases/tag/v0.6.5 . These small fixtures do
not send attacker-controlled data to a server or use wall-clock thresholds.
"""
import sys
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version
from pyasn1 import __version__
from pyasn1.codec.ber import decoder as ber
from pyasn1.codec.cer import decoder as cer
from pyasn1.codec.der import decoder as der
from pyasn1.codec.der.encoder import encode
from pyasn1.type import tag, univ

ROOT = Path(__file__).resolve().parents[2]
CODECS = (ber, cer, der)


def _tlv(identifier, content):
    size = len(content)
    if size < 128:
        length = bytes([size])
    else:
        encoded = size.to_bytes((size.bit_length() + 7) // 8, 'big')
        length = bytes([128 + len(encoded)]) + encoded
    return bytes([identifier]) + length + content


def test_pyasn1_pin_and_installer_reject_the_affected_runtime():
    lines = (ROOT / 'requirements/base.txt').read_text().splitlines()
    pin = next(Requirement(line) for line in lines if line.startswith('pyasn1=='))
    assert Version('0.6.4') not in pin.specifier
    assert Version('0.6.5') in pin.specifier
    assert "Version(pyasn1.__version__) >= Version('0.6.5')" in (
        ROOT / 'scripts/post_install.sh').read_text()


def test_installed_decoder_meets_the_security_floor():
    assert Version(__version__) >= Version('0.6.5')


@pytest.mark.parametrize('codec', CODECS)
def test_binary_real_retains_sign_scale_and_large_mantissa(codec):
    mantissa = bytes(range(1, 129)) * 8
    wire = _tlv(9, b'\x80\x00' + mantissa)
    value, rest = codec.decode(wire)
    assert tuple(value) == (int.from_bytes(mantissa, 'big'), 2, 0)
    assert rest == b''


@pytest.mark.parametrize('codec', (ber, cer))
def test_constructed_bit_string_retains_fragment_values(codec):
    # Conforming CER fragment sizing; the last fragment may be shorter.
    first = _tlv(3, b'\x00' + b'\xa5' * 999)
    last = _tlv(3, b'\x03\xa8')
    wire = b'\x23\x80' + first + last + b'\x00\x00'
    value, rest = codec.decode(wire)
    assert len(value) == 999 * 8 + 5
    assert int(value) == (int.from_bytes(b'\xa5' * 999, 'big') << 5) | 21
    assert rest == b''


def test_schema_driven_der_bit_string_preserves_legacy_permissive_decoding():
    # This is not valid DER, but pyasn1's schema-driven path accepts it.
    wire = _tlv(0x23, _tlv(3, b'\x00\x5a') * 64)
    value, rest = der.decode(wire, asn1Spec=univ.BitString())
    assert value.asOctets() == b'\x5a' * 64
    assert rest == b''


@pytest.mark.parametrize('codec', (ber, cer))
def test_constructed_octets_keep_order_and_nested_decoded_values(codec):
    fragment = _tlv(4, b'z' * 1000)
    nested = b'\x24\x80' + fragment + b'\x00\x00'
    wire = b'\x24\x80' + nested + _tlv(4, b'end') + b'\x00\x00'
    value, rest = codec.decode(wire)
    assert value.asOctets() == b'z' * 1000 + b'end'
    assert rest == b''


@pytest.mark.parametrize('codec', (ber, cer))
def test_indefinite_any_keeps_content_and_consumes_only_its_end_marker(codec):
    wire = b'\x30\x80' + _tlv(4, b'qa') * 128 + b'\x00\x00'
    following = _tlv(2, b'\x01')
    value, rest = codec.decode(wire + following, asn1Spec=univ.Any())
    # The public ANY decoder returns encoded header/content without its EOC.
    assert bytes(value) == wire[:-2]
    assert rest == following


@pytest.mark.parametrize('codec', CODECS)
def test_schemaless_colliding_tags_have_bounded_type_tracking(codec, monkeypatch):
    comparisons = 0
    original = tag.TagSet.__eq__

    def counted_eq(self, other):
        nonlocal comparisons
        comparisons += 1
        return original(self, other)

    monkeypatch.setattr(tag.TagSet, '__eq__', counted_eq)
    count = 96
    ids = [32 + index * sys.hash_info.modulus for index in range(count)]
    components = []
    for tag_id in ids:
        value = univ.OctetString(b'qa').subtype(explicitTag=tag.Tag(
            tag.tagClassContext, tag.tagFormatConstructed, tag_id))
        components.append(encode(value))
    value, rest = codec.decode(_tlv(0x30, b''.join(components)))
    assert rest == b'' and len(value) == count
    components = [value.getComponentByPosition(index) for index in range(count)]
    assert [item.asOctets() for item in components] == [b'qa'] * count
    assert [item.tagSet[-1].tagId for item in components] == ids
    # 0.6.4 accumulates every colliding tag in a set (quadratic comparisons).
    # Allow ample codec overhead without timing-sensitive performance assertions.
    assert comparisons < count * 20


def test_rsa_pkcs1_roundtrip_and_signature_remain_compatible():
    import rsa

    public, private = rsa.newkeys(2048)
    assert rsa.PublicKey.load_pkcs1(public.save_pkcs1()) == public
    assert rsa.PrivateKey.load_pkcs1(private.save_pkcs1()) == private
    message = b'local-only synthetic compatibility fixture'
    signature = rsa.sign(message, private, 'SHA-256')
    assert rsa.verify(message, signature, public) == 'SHA-256'
