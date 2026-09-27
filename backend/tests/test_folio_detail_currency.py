from modules.pms_core.folio_detail_service import FolioDetailService, _enrich_payment_currency


def test_enrich_payment_currency_prefers_structured_fields():
    payment = _enrich_payment_currency(
        {
            "amount": 145.45,
            "currency": "EUR",
            "received_amount": 165.71,
            "received_currency": "USD",
            "exchange_rate": 1.1393,
        },
        "EUR",
    )
    assert payment["currency"] == "EUR"
    assert payment["received_amount"] == 165.71
    assert payment["received_currency"] == "USD"
    assert payment["exchange_rate"] == 1.1393


def test_enrich_payment_currency_backfills_legacy_converter_note():
    payment = _enrich_payment_currency(
        {
            "amount": 145.45,
            "notes": "[Döviz Çevirici] 145.45 EUR = 165.71 USD. Kur: 1 EUR = 1.1393 USD",
        },
        "EUR",
    )
    assert payment["currency"] == "EUR"
    assert payment["received_amount"] == 165.71
    assert payment["received_currency"] == "USD"
    assert payment["exchange_rate"] == 1.1393


def test_voided_legacy_receipt_only_note_uses_received_currency_for_display():
    payment = _enrich_payment_currency(
        {
            "amount": 8085.25,
            "notes": "[Döviz Çevirici] 8085.25 TL tahsil edildi. Kur: 1.0000",
            "voided": True,
        },
        "EUR",
    )
    assert payment["currency"] == "EUR"
    assert payment["received_amount"] == 8085.25
    assert payment["received_currency"] == "TRY"
    assert payment["legacy_received_only"] is True

    timeline = FolioDetailService()._build_timeline([], [payment])
    assert timeline[0]["display_amount"] == 8085.25
    assert timeline[0]["display_currency"] == "TRY"


def test_timeline_preserves_ledger_and_received_currencies():
    service = FolioDetailService()
    timeline = service._build_timeline(
        [{"id": "charge", "amount": 145.45, "currency": "EUR", "date": "2026-09-26"}],
        [{
            "id": "payment",
            "amount": 145.45,
            "currency": "EUR",
            "received_amount": 165.71,
            "received_currency": "USD",
            "exchange_rate": 1.1393,
            "processed_at": "2026-09-27",
        }],
    )
    assert timeline[0]["currency"] == "EUR"
    assert timeline[1]["currency"] == "EUR"
    assert timeline[1]["received_currency"] == "USD"
    assert timeline[1]["received_amount"] == 165.71
    assert timeline[1]["running_balance"] == 0
