from routers.regulatory import _resolve_regulatory_capacity


def test_regulatory_capacity_prefers_ministry_license() -> None:
    rooms, beds, source = _resolve_regulatory_capacity(
        {"licensed_room_count": 16, "licensed_bed_count": 32},
        operational_rooms=17,
        operational_beds=34,
    )

    assert (rooms, beds, source) == (16, 32, "ministry_license")


def test_regulatory_capacity_falls_back_to_operational_inventory() -> None:
    rooms, beds, source = _resolve_regulatory_capacity(
        {},
        operational_rooms=17,
        operational_beds=34,
    )

    assert (rooms, beds, source) == (17, 34, "operational_inventory")
