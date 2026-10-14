"""Same-day turnover must not consume the arriving guest's room-night."""

import os
import uuid

import pytest

from core.stay_overlap import stay_overlap_filter

pymongo = pytest.importorskip("pymongo")


@pytest.fixture
def bookings():
    client = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=1500)
    try:
        client.server_info()
    except Exception:
        pytest.skip("MongoDB is not reachable")
    name = f"stay_overlap_{uuid.uuid4().hex[:8]}"
    yield client[name].bookings
    client.drop_database(name)
    client.close()


def _matching(collection, check_in, check_out):
    return sorted(doc["id"] for doc in collection.find(stay_overlap_filter(check_in, check_out)))


@pytest.mark.parametrize(
    "stored_in,stored_out",
    [
        ("2026-10-13T14:00:00+00:00", "2026-10-15T12:00:00+00:00"),  # PMS format
        ("2026-10-13T14:00:00", "2026-10-15T11:00:00"),  # agency format
        ("2026-10-13", "2026-10-15"),  # date-only legacy rows
    ],
)
def test_departure_day_is_free_and_occupied_nights_conflict(bookings, stored_in, stored_out):
    bookings.insert_one({"id": "departing", "check_in": stored_in, "check_out": stored_out})

    assert _matching(bookings, "2026-10-15", "2026-10-17") == []  # arrives on departure day
    assert _matching(bookings, "2026-10-14", "2026-10-16") == ["departing"]  # shares night of 14th
    assert _matching(bookings, "2026-10-11", "2026-10-13") == []  # leaves on arrival day
    assert _matching(bookings, "2026-10-12", "2026-10-14") == ["departing"]


def test_overlap_filter_keeps_index_friendly_range_bounds():
    query = stay_overlap_filter("2026-10-15", "2026-10-17")
    assert query["check_in"] == {"$lt": "2026-10-18"}
    assert query["check_out"] == {"$gt": "2026-10-15"}
    assert "$expr" in query
