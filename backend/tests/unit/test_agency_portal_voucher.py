import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import agency_portal as portal


@pytest.fixture
def setup(monkeypatch):
    from security import encrypted_lookup
    bookings = SimpleNamespace(find_one=AsyncMock(return_value={'id': 'b', 'guest_name': '<Guest>', 'confirmation_code': 'ABC'}))
    monkeypatch.setattr(portal, 'db', SimpleNamespace(bookings=bookings, tenants=SimpleNamespace(find_one=AsyncMock(return_value={'name': 'Hotel'}))))
    monkeypatch.setattr(portal, '_require_agency_user', lambda user: None)
    monkeypatch.setattr(portal, '_active_agency_for', AsyncMock(return_value={'id': 'a'}))
    monkeypatch.setattr(encrypted_lookup, 'decrypt_booking_doc', lambda doc: doc)
    return SimpleNamespace(tenant_id='t', agency_id='a'), bookings


@pytest.mark.asyncio
async def test_voucher_is_scoped_to_tenant_and_agency(setup):
    user, bookings = setup
    doc = await portal._portal_voucher_booking('b', user)
    assert doc['hotel_name'] == 'Hotel'
    bookings.find_one.assert_awaited_once_with({'id': 'b', 'tenant_id': 't', 'agency_id': 'a', 'source_channel': 'agency'}, {'_id': 0})
    bookings.find_one.return_value = None
    with pytest.raises(HTTPException) as error:
        await portal._portal_voucher_booking('other-agency-booking', user)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_unscoped_preview_cannot_fetch_voucher(setup):
    user, bookings = setup
    user.agency_id = None
    with pytest.raises(HTTPException) as error:
        await portal._portal_voucher_booking('b', user)
    assert error.value.status_code == 403
    bookings.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_pdf_response_escapes_guest_data(setup, monkeypatch):
    user, _ = setup
    captured = []
    def html(**kwargs):
        captured.append(kwargs['string'])
        return SimpleNamespace(write_pdf=lambda: b'%PDF-test')
    monkeypatch.setitem(sys.modules, 'weasyprint', SimpleNamespace(HTML=html))
    response = await portal.agency_portal_voucher_pdf('b', user)
    assert response.media_type == 'application/pdf' and response.body == b'%PDF-test'
    assert '&lt;Guest&gt;' in captured[0] and '<Guest>' not in captured[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('sent', [True, False])
async def test_email_checks_provider_sent_status(setup, monkeypatch, sent):
    import core.email
    user, _ = setup
    mail = AsyncMock(return_value={'sent': sent})
    monkeypatch.setattr(core.email, 'send_email', mail)
    data = portal.PortalVoucherEmailRequest(email='guest@example.com')
    if sent:
        assert (await portal.agency_portal_voucher_email('b', data, user))['ok']
    else:
        with pytest.raises(HTTPException) as error:
            await portal.agency_portal_voucher_email('b', data, user)
        assert error.value.status_code == 502
    assert mail.call_args.kwargs['sensitive']
