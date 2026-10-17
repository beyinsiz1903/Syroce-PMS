"""Two different checks must not share a name (module/licence inventory).

* ``core.helpers.require_module``: is the hotel LICENSED for the module.
* ``modules.pms_core.role_permission_service.require_module_role``: which
  ROLES may use a module area (MODULE_ROLES allowlist).
"""

import re
from pathlib import Path

from modules.pms_core import role_permission_service

BACKEND = Path(__file__).resolve().parents[2]


def test_role_check_has_its_own_name():
    assert hasattr(role_permission_service, "require_module_role")
    assert not hasattr(role_permission_service, "require_module")


def test_no_code_imports_a_role_check_under_the_licence_name():
    offenders = []
    # Single-line and parenthesised imports from the role service only.
    imports = re.compile(r"from modules\.pms_core\.role_permission_service import (\([^)]*\)|[^\n]*)")
    for path in BACKEND.rglob("*.py"):
        if ".venv" in path.parts or path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for block in imports.findall(text):
            if re.search(r"\brequire_module\b(?!_role)", block):
                offenders.append(str(path.relative_to(BACKEND)))
    assert offenders == []
