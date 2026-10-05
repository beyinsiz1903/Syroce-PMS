"""Night-audit preparation must report the same physical inventory as PMS."""

from pathlib import Path


def test_preview_uses_the_canonical_active_inventory_contract():
    preview_source = Path("core/night_audit_hardened.py").read_text()
    snapshot_source = Path("modules/pms_core/operational_snapshot_service.py").read_text()

    preview_section = preview_source[preview_source.index("async def build_audit_preview"):]
    assert "build_operational_snapshot" in preview_section
    assert '"is_virtual": False' in snapshot_source
    assert '"is_virtual": {"$exists": False}' in snapshot_source
    assert '"is_active": True' in snapshot_source
    assert '"is_active": {"$exists": False}' in snapshot_source
