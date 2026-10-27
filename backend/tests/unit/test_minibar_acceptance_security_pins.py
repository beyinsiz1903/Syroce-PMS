"""Keep the patched dependency set installable without weakening the CI gate."""
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]


def requirements(filename):
    return {item.name.lower(): item for line in (ROOT / 'requirements' / filename).read_text().splitlines()
        if line.strip() and not line.startswith(('#', '-')) for item in [Requirement(line)]}


def test_litellm_pin_rejects_affected_version_and_retains_compatible_sdk_set():
    pins = requirements('integrations.txt')
    assert Version('1.96.2') not in pins['litellm'].specifier
    assert Version('1.100.4') in pins['litellm'].specifier
    assert Version('2.20.0') in pins['openai'].specifier
    for package, version in [('boto3', '1.43.1'), ('botocore', '1.43.1'), ('s3transfer', '0.17.0')]:
        assert Version(version) in pins[package].specifier
    post_install = (ROOT / 'scripts' / 'post_install.sh').read_text()
    assert "Version(version('litellm')) == Version('1.100.4')" in post_install


def test_msgpack_pin_rejects_affected_decoder_and_checks_installed_runtime():
    specifier = requirements('base.txt')['msgpack'].specifier
    assert Version('1.2.1') not in specifier and Version('1.2.2') not in specifier
    assert Version('1.2.3') in specifier
    assert "Version(version('msgpack')) >= Version('1.2.3')" in (ROOT / 'scripts' / 'post_install.sh').read_text()


@pytest.mark.parametrize('package,affected,patched', [
    ('dnspython', '2.8.0', '2.9.0'),
    ('pymongo', '4.18.2', '4.18.3'),
])
def test_dns_and_bson_pins_require_the_patched_decoder(package, affected, patched):
    pins = requirements('base.txt')
    assert Version(affected) not in pins[package].specifier
    assert Version(patched) in pins[package].specifier
    post_install = (ROOT / 'scripts' / 'post_install.sh').read_text()
    if package == 'pymongo':
        assert "Version(pymongo.version) >= Version('4.18.3')" in post_install
    else:
        assert "Version(version('dnspython')) >= Version('2.9.0')" in post_install
