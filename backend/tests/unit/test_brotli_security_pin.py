import os
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

os.environ.setdefault('JWT_SECRET', 'unit-test-secret-key-at-least-32-chars!!')


def test_brotli_runtime_pin_requires_the_patched_decoder():
    path = Path(__file__).resolve().parents[2] / 'requirements' / 'api.txt'
    requirements = [Requirement(line) for line in path.read_text().splitlines()
                    if line.strip() and not line.startswith(('#', '-'))]
    brotli = next(item for item in requirements if item.name.lower() == 'brotli')
    assert Version('1.2.0') not in brotli.specifier
    assert Version('1.2.1') in brotli.specifier
