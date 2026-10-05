import re

with open("backend/tests/test_reservation_cari_transfer_ledger.py", "r") as f:
    content = f.read()

# Replace SimpleNamespace(bookings=bookings, ... ) with the new collections

old_ns = """        SimpleNamespace(
            bookings=bookings,
            cari_accounts=cari_accounts,
            payments=payments,
            cari_transactions=cari_transactions,
        )"""

new_ns = """        SimpleNamespace(
            bookings=bookings,
            cari_accounts=cari_accounts,
            payments=payments,
            cari_transactions=cari_transactions,
            city_ledger_accounts=SimpleNamespace(
                find_one=AsyncMock(return_value=None),
                update_one=AsyncMock()
            ),
            city_ledger_transactions=SimpleNamespace(insert_one=AsyncMock()),
        )"""
content = content.replace(old_ns, new_ns)

# There's another one in test_cari_transfer_duplicate_click_fails_before_financial_writes
old_db2 = """    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "folio-a", "booking_id": "booking-a"}),
            insert_one=AsyncMock(),
        ),
        cari_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "cari-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        cari_transactions=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
    )"""

new_db2 = """    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "folio-a", "booking_id": "booking-a"}),
            insert_one=AsyncMock(),
        ),
        cari_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "cari-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        cari_transactions=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
        city_ledger_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value=None),
            update_one=AsyncMock(),
        ),
        city_ledger_transactions=SimpleNamespace(insert_one=AsyncMock()),
    )"""
content = content.replace(old_db2, new_db2)

# There's also one in test_cari_transfer_duplicate_key_is_safe_conflict
old_db3 = """    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "paid_amount": 0.0,
                }
            ),
            update_one=AsyncMock(),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "folio-a", "booking_id": "booking-a"}),
            insert_one=AsyncMock(),
        ),
        cari_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "cari-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        cari_transactions=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
    )"""

new_db3 = """    database = SimpleNamespace(
        bookings=SimpleNamespace(
            find_one=AsyncMock(
                return_value={
                    "id": "booking-a",
                    "tenant_id": "tenant-a",
                    "paid_amount": 0.0,
                }
            ),
            update_one=AsyncMock(),
        ),
        folios=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "folio-a", "booking_id": "booking-a"}),
            insert_one=AsyncMock(),
        ),
        cari_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "cari-a", "tenant_id": "tenant-a"}),
            update_one=AsyncMock(),
        ),
        cari_transactions=SimpleNamespace(insert_one=AsyncMock()),
        payments=SimpleNamespace(insert_one=AsyncMock()),
        city_ledger_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value=None),
            update_one=AsyncMock(),
        ),
        city_ledger_transactions=SimpleNamespace(insert_one=AsyncMock()),
    )"""
content = content.replace(old_db3, new_db3)


# Also in test_cari_transfer_creates_open_folio_and_payment 
old_db_first = """    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            bookings=bookings,
            folios=folios,
            cari_accounts=cari_accounts,
            payments=payments,
            cari_transactions=cari_transactions,
        ),
    )"""

new_db_first = """    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            bookings=bookings,
            folios=folios,
            cari_accounts=cari_accounts,
            payments=payments,
            cari_transactions=cari_transactions,
            city_ledger_accounts=SimpleNamespace(
                find_one=AsyncMock(return_value=None),
                update_one=AsyncMock()
            ),
            city_ledger_transactions=SimpleNamespace(insert_one=AsyncMock()),
        ),
    )"""
content = content.replace(old_db_first, new_db_first)


with open("backend/tests/test_reservation_cari_transfer_ledger.py", "w") as f:
    f.write(content)
