"""The production API image must not reintroduce the affected tracing parser."""
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version


@pytest.mark.parametrize('package', [
    'opentelemetry-api',
    'opentelemetry-sdk',
    'opentelemetry-exporter-otlp-proto-grpc',
    'opentelemetry-exporter-otlp-proto-common',
])
def test_production_tracing_pins_use_one_patched_release_set(package):
    path = Path(__file__).resolve().parents[2] / 'requirements/api-runtime.txt'
    pins = {req.name: req for line in path.read_text().splitlines()
            if line.strip() and not line.startswith(('#', '-'))
            for req in [Requirement(line)]}
    assert Version('1.44.0') not in pins[package].specifier
    assert Version('1.45.0') not in pins[package].specifier
    assert str(pins[package].specifier) == '==1.45.1'
