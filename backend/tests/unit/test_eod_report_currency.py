from routers.eod_report import _build_html, _currency_code, _format_breakdown


def test_currency_code_normalizes_legacy_tl():
    assert _currency_code("tl") == "TRY"


def test_format_breakdown_keeps_currencies_separate():
    assert _format_breakdown({"USD": 125.5, "EUR": 100}) == "100.00 EUR · 125.50 USD"


def test_eod_html_does_not_relabel_mixed_currency_as_try():
    html = _build_html(
        {
            "business_date": "2026-09-27",
            "occupancy_rate": 50,
            "occupied": 5,
            "rooms_total": 10,
            "revenue_total": 220,
            "revenue_by_currency": {"EUR": 100, "USD": 120},
            "payments_total": 220,
            "payments_by_currency": {"EUR": 100, "USD": 120},
            "payments_by_method": {"cash": 220},
            "payments_by_method_currency": {"cash": {"EUR": 100, "USD": 120}},
            "cash_total": 220,
            "extras_total": 0,
            "extras_by_currency": {},
            "currency": "TRY",
            "arrivals": 1,
            "actual_checkins": 1,
            "departures": 1,
            "actual_checkouts": 1,
            "no_shows": 0,
            "cancels": 0,
            "open_folios": 0,
            "open_handovers": 0,
        }
    )
    assert "100.00 EUR · 120.00 USD" in html
    assert "220.00 TL" not in html
