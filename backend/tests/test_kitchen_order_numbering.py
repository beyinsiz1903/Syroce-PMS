from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb_router import kitchen_numbering


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        self.rows.sort(key=lambda row: row["order_number"], reverse=True)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, count):
        return self.rows[:count]


class _Orders:
    def __init__(self, values):
        self.values = values

    def find(self, query, projection):
        assert query["order_number"] == {"$type": "number"}
        return _Cursor([{"order_number": value} for value in self.values if isinstance(value, (int, float))])


class _Counters:
    def __init__(self):
        self.seq = None

    async def create_index(self, *_args, **_kwargs):
        return "uq_kitchen_order_counter"

    async def update_one(self, _key, update, upsert=False):
        assert upsert is True
        floor = update["$max"]["seq"]
        self.seq = floor if self.seq is None else max(self.seq, floor)
        return SimpleNamespace()

    async def find_one_and_update(self, _key, update, return_document=None):
        self.seq += update["$inc"]["seq"]
        return {"seq": self.seq}


@pytest.fixture(autouse=True)
def _reset_index_flag():
    kitchen_numbering._KITCHEN_COUNTER_INDEX_READY = False
    yield
    kitchen_numbering._KITCHEN_COUNTER_INDEX_READY = False


@pytest.mark.asyncio
async def test_legacy_string_numbers_do_not_reset_sequence(monkeypatch):
    fake_db = SimpleNamespace(
        kitchen_orders=_Orders(["ORD-202605241829-5E58", 1, "ORD-202605241830-F85A"]),
        pos_kitchen_counters=_Counters(),
    )
    monkeypatch.setattr(kitchen_numbering, "db", fake_db)

    assert await kitchen_numbering.next_kitchen_order_number("tenant-a") == 2
    assert await kitchen_numbering.next_kitchen_order_number("tenant-a") == 3


@pytest.mark.asyncio
async def test_counter_is_raised_when_numeric_legacy_rows_are_ahead(monkeypatch):
    counters = _Counters()
    counters.seq = 4
    fake_db = SimpleNamespace(
        kitchen_orders=_Orders([2, 9, "legacy"]),
        pos_kitchen_counters=counters,
    )
    monkeypatch.setattr(kitchen_numbering, "db", fake_db)

    assert await kitchen_numbering.next_kitchen_order_number("tenant-a") == 10
