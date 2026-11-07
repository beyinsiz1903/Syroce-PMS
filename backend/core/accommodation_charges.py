"""Distinguish agreed stay nights from separately sold room services."""


def is_base_room_charge(charge: dict) -> bool:
    """An upgrade earns room revenue, but never replaces a booked room night.

    Keep category-only legacy nightly rows compatible. Reporting deliberately
    retains the upgrade's ``room`` category; pricing reconciliation must use
    its explicit type instead of treating all room revenue as the base stay.
    """
    return charge.get("charge_type") != "room_upgrade" and (
        charge.get("charge_type") == "room_charge" or charge.get("charge_category") == "room"
    )
