import asyncio
from types import SimpleNamespace

from models.schemas.guests import GuestCreate
from routers import missing_endpoints_compat as compat
from security.field_encryption import ENCRYPTED_FIELDS


class _Collection:
    def __init__(self, document=None):
        self.document = document
        self.updated = None

    async def find_one(self, *_args, **_kwargs):
        return self.document

    async def update_one(self, query, update):
        self.updated = (query, update)


class _Database:
    def __init__(self):
        self.bookings = _Collection({"id": "booking-1", "tenant_id": "tenant-1"})
        self.guests = _Collection()


class _IdentityEncryption:
    def encrypt_document(self, document, collection):
        assert collection == "bookings"
        return document


def test_quick_id_guest_fields_are_accepted_by_guest_schema():
    guest = GuestCreate(
        name="Ada Lovelace",
        id_number="P123",
        id_type="passport",
        nationality="GBR",
        birth_date="1815-12-10",
        gender="F",
        birth_place="London",
        document_expiry_date="2030-01-01",
        scanned_via_quick_id=True,
    )

    assert guest.birth_date == "1815-12-10"
    assert guest.scanned_via_quick_id is True


def test_booking_guest_patch_accepts_and_persists_ocr_fields(monkeypatch):
    fake_db = _Database()
    monkeypatch.setattr(compat, "db", fake_db)
    monkeypatch.setattr(
        "security.field_encryption.get_field_encryption_service",
        lambda: _IdentityEncryption(),
    )
    body = compat.GuestInfoPatch(
        guest_first_name="Ada",
        guest_last_name="Lovelace",
        guest_id_number="P123",
        guest_id_type="passport",
        guest_nationality="GBR",
        guest_birth_date="1815-12-10",
        guest_gender="F",
    )

    result = asyncio.run(
        compat.patch_booking_guest_info(
            "booking-1",
            body,
            current_user=SimpleNamespace(tenant_id="tenant-1"),
            _perm=None,
        )
    )

    stored = fake_db.bookings.updated[1]["$set"]
    assert result["updated"] is True
    assert stored["guest_name"] == "Ada Lovelace"
    assert stored["guest_id_number"] == "P123"
    assert stored["guest_birth_date"] == "1815-12-10"


def test_quick_id_pii_fields_are_in_encryption_policy():
    guests = {field["field"] for field in ENCRYPTED_FIELDS["guests"]}
    bookings = {field["field"] for field in ENCRYPTED_FIELDS["bookings"]}

    assert {"id_number", "birth_date", "birth_place"} <= guests
    assert {"guest_id_number", "guest_birth_date", "guest_birth_place"} <= bookings
