"""Night-audit preparation must report the same physical inventory as PMS."""

from pathlib import Path


def test_preview_excludes_virtual_rooms_from_inventory_pipeline():
    source = Path("core/night_audit_hardened.py").read_text()

    preview_section = source[source.index("async def build_audit_preview"):]
    assert '"is_virtual": False' in preview_section
    assert '"is_virtual": {"$exists": False}' in preview_section
