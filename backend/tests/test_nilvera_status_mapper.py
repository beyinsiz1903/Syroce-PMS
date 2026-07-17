
from core.integrations.nilvera.status_mapper import ProviderInvoiceOutcome, map_nilvera_status


def test_map_pending_status():
    assert map_nilvera_status("Kuyrukta", None) == ProviderInvoiceOutcome.PENDING
    assert map_nilvera_status("İşleniyor", None) == ProviderInvoiceOutcome.PENDING
    assert map_nilvera_status("  gönderim bekliyor  ", None) == ProviderInvoiceOutcome.PENDING
    assert map_nilvera_status("GİB'e Gönderildi", None) == ProviderInvoiceOutcome.PENDING


def test_map_accepted_status():
    assert map_nilvera_status("Başarılı", None) == ProviderInvoiceOutcome.ACCEPTED
    assert map_nilvera_status("Onaylandı", None) == ProviderInvoiceOutcome.ACCEPTED
    assert map_nilvera_status("kabul edildi", None) == ProviderInvoiceOutcome.ACCEPTED
    assert map_nilvera_status("Success", None) == ProviderInvoiceOutcome.ACCEPTED


def test_map_rejected_status():
    assert map_nilvera_status("Hatalı", None) == ProviderInvoiceOutcome.REJECTED
    assert map_nilvera_status("Reddedildi", None) == ProviderInvoiceOutcome.REJECTED
    assert map_nilvera_status("FAILED", None) == ProviderInvoiceOutcome.REJECTED


def test_map_cancelled_status():
    assert map_nilvera_status("İptal Edildi", None) == ProviderInvoiceOutcome.CANCELLED
    assert map_nilvera_status("CANCELLED", None) == ProviderInvoiceOutcome.CANCELLED


def test_map_unknown_status():
    # Unexpected status value
    assert map_nilvera_status("Bilinmeyen bir durum", None) == ProviderInvoiceOutcome.UNKNOWN
    # Missing/empty
    assert map_nilvera_status("", None) == ProviderInvoiceOutcome.UNKNOWN
    assert map_nilvera_status(None, None) == ProviderInvoiceOutcome.UNKNOWN


def test_map_case_and_whitespace_insensitivity():
    assert map_nilvera_status("  bAşArIlı  ", None) == ProviderInvoiceOutcome.ACCEPTED
    assert map_nilvera_status("\nReddedildi\t", None) == ProviderInvoiceOutcome.REJECTED


def test_map_from_fixtures():
    import json
    from pathlib import Path

    fixtures_dir = Path(__file__).parent / "fixtures" / "nilvera_sale_status"

    with open(fixtures_dir / "pending.json") as f:
        data = json.load(f)
        assert map_nilvera_status(data.get("Status"), data.get("StatusCode")) == ProviderInvoiceOutcome.PENDING

    with open(fixtures_dir / "accepted.json") as f:
        data = json.load(f)
        assert map_nilvera_status(data.get("Status"), data.get("StatusCode")) == ProviderInvoiceOutcome.ACCEPTED

    with open(fixtures_dir / "rejected.json") as f:
        data = json.load(f)
        assert map_nilvera_status(data.get("Status"), data.get("StatusCode")) == ProviderInvoiceOutcome.REJECTED

    with open(fixtures_dir / "cancelled.json") as f:
        data = json.load(f)
        assert map_nilvera_status(data.get("Status"), data.get("StatusCode")) == ProviderInvoiceOutcome.CANCELLED

    with open(fixtures_dir / "unknown.json") as f:
        data = json.load(f)
        assert map_nilvera_status(data.get("Status"), data.get("StatusCode")) == ProviderInvoiceOutcome.UNKNOWN
