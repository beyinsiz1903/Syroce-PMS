"""Keep both image-processing services on the patched Pillow release line."""

from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFESTS = ("backend/requirements/reports.txt", "quick-id/backend/requirements.txt")


def _pillow_pin(manifest: str) -> Version:
    requirements = [
        Requirement(line.strip())
        for line in (REPO_ROOT / manifest).read_text().splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    ]
    matches = [req for req in requirements if req.name.lower() == "pillow"]
    assert len(matches) == 1, f"Expected one Pillow dependency in {manifest}"
    pins = list(matches[0].specifier)
    assert len(pins) == 1 and pins[0].operator == "=="
    return Version(pins[0].version)


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_pillow_security_fix_is_pinned_in_each_service(manifest):
    assert _pillow_pin(manifest) >= Version("13.0.0")


def test_pms_and_quick_id_pillow_pins_stay_in_sync():
    assert _pillow_pin(MANIFESTS[0]) == _pillow_pin(MANIFESTS[1])
