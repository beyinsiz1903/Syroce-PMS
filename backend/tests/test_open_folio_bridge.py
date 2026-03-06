import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

from core.database import db


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestOpenFolioBridge:
    @pytest.fixture(autouse=True)
    def setup(self):
        if not BASE_URL:
            pytest.skip('REACT_APP_BACKEND_URL missing')

        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        login = self.session.post(f'{BASE_URL}/api/auth/login', json={
            'email': 'demo@hotel.com',
            'password': 'demo123',
        })
        if login.status_code != 200:
            pytest.skip(f'Login failed: {login.status_code}')
        self.token = login.json()['access_token']
        self.tenant_id = login.json()['user']['tenant_id']
        self.session.headers.update({'Authorization': f'Bearer {self.token}'})
        yield

    def _find_one(self, collection_name: str, query: dict):
        return db.delegate[collection_name].find_one(query, {'_id': 0})

    def _insert_company(self):
        company_id = str(uuid.uuid4())
        db.delegate['companies'].insert_one({
            'id': company_id,
            'tenant_id': self.tenant_id,
            'name': f'Semantic Company {uuid.uuid4().hex[:6]}',
            'status': 'active',
            'created_at': datetime.utcnow().isoformat(),
        })
        return company_id

    def _get_guest_and_room(self):
        guests = self.session.get(f'{BASE_URL}/api/pms/guests?limit=5').json()
        rooms = self.session.get(f'{BASE_URL}/api/pms/rooms?limit=5').json()
        if not guests or not rooms:
            pytest.skip('Need at least one guest and one room')
        return guests[0]['id'], rooms[0]['id']

    def _create_booking(self, company_id: str):
        guest_id, room_id = self._get_guest_and_room()
        check_in = (datetime.utcnow().date() + timedelta(days=55)).isoformat() + 'T14:00:00Z'
        check_out = (datetime.utcnow().date() + timedelta(days=58)).isoformat() + 'T12:00:00Z'
        payload = {
            'guest_id': guest_id,
            'room_id': room_id,
            'check_in': check_in,
            'check_out': check_out,
            'adults': 1,
            'children': 0,
            'children_ages': [],
            'guests_count': 1,
            'total_amount': 990.0,
            'special_requests': f'semantic-folio-open-{uuid.uuid4().hex[:8]}',
            'company_id': company_id,
        }
        response = self.session.post(
            f'{BASE_URL}/api/pms/bookings',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'booking-{uuid.uuid4()}'},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def _build_open_payload(self, booking_id: str, company_id: str):
        return {
            'booking_id': booking_id,
            'folio_type': 'company',
            'company_id': company_id,
            'notes': f'open-folio-{uuid.uuid4().hex[:8]}',
        }

    def test_happy_path_open_folio_with_outbox_and_audit(self):
        company_id = self._insert_company()
        booking = self._create_booking(company_id)
        payload = self._build_open_payload(booking['id'], company_id)
        idem_key = f'folio-{uuid.uuid4()}'

        response = self.session.post(
            f'{BASE_URL}/api/folio/create',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': idem_key},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        assert set(data.keys()) == {
            'id', 'tenant_id', 'booking_id', 'folio_number', 'folio_type', 'status',
            'guest_id', 'company_id', 'balance', 'notes', 'created_at', 'closed_at',
        }
        assert data['tenant_id'] == self.tenant_id
        assert data['booking_id'] == booking['id']
        assert data['folio_type'] == 'company'
        assert data['company_id'] == company_id
        assert data['status'] == 'open'

        folio_doc = self._find_one('folios', {'id': data['id'], 'tenant_id': self.tenant_id})
        assert folio_doc is not None
        assert folio_doc['currency']

        outbox = self._find_one('outbox_events', {'folio_id': data['id'], 'event_type': 'folio.opened.v1'})
        assert outbox is not None
        assert outbox['tenant_id'] == self.tenant_id
        assert outbox['payload']['currency'] == folio_doc['currency']
        assert outbox['payload']['reservation_id'] == booking['id']

        audit = self._find_one('audit_logs', {'entity_type': 'folio', 'entity_id': data['id'], 'action': 'folio_opened'})
        assert audit is not None
        assert audit['tenant_id'] == self.tenant_id

    def test_duplicate_request_same_idempotency_key_returns_same_folio(self):
        company_id = self._insert_company()
        booking = self._create_booking(company_id)
        payload = self._build_open_payload(booking['id'], company_id)
        idem_key = f'folio-{uuid.uuid4()}'
        headers = {'Authorization': f'Bearer {self.token}', 'Idempotency-Key': idem_key}

        first = self.session.post(f'{BASE_URL}/api/folio/create', json=payload, headers=headers)
        second = self.session.post(f'{BASE_URL}/api/folio/create', json=payload, headers=headers)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()['id'] == second.json()['id']

    def test_duplicate_open_folio_with_new_key_rejected(self):
        company_id = self._insert_company()
        booking = self._create_booking(company_id)
        payload = self._build_open_payload(booking['id'], company_id)

        first = self.session.post(
            f'{BASE_URL}/api/folio/create',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'folio-{uuid.uuid4()}'},
        )
        assert first.status_code == 200, first.text

        second = self.session.post(
            f'{BASE_URL}/api/folio/create',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'folio-{uuid.uuid4()}'},
        )
        assert second.status_code == 409
        assert 'Open folio already exists' in second.text

    def test_missing_idempotency_key_rejected(self):
        company_id = self._insert_company()
        booking = self._create_booking(company_id)
        payload = self._build_open_payload(booking['id'], company_id)

        response = self.session.post(f'{BASE_URL}/api/folio/create', json=payload)
        assert response.status_code == 400
        assert 'Idempotency-Key' in response.text

    def test_invalid_booking_reference_rejected(self):
        company_id = self._insert_company()
        response = self.session.post(
            f'{BASE_URL}/api/folio/create',
            json=self._build_open_payload(str(uuid.uuid4()), company_id),
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'folio-{uuid.uuid4()}'},
        )
        assert response.status_code == 404
        assert 'Booking not found' in response.text

    def test_wrong_property_scope_rejected(self):
        company_id = self._insert_company()
        booking = self._create_booking(company_id)
        response = self.session.post(
            f'{BASE_URL}/api/folio/create',
            json=self._build_open_payload(booking['id'], company_id),
            headers={
                'Authorization': f'Bearer {self.token}',
                'Idempotency-Key': f'folio-{uuid.uuid4()}',
                'x-property-id': 'wrong-property',
            },
        )
        assert response.status_code == 403

    def test_wrong_tenant_cannot_open_demo_booking_folio(self):
        company_id = self._insert_company()
        booking = self._create_booking(company_id)

        register_suffix = uuid.uuid4().hex[:8]
        register_response = requests.post(
            f'{BASE_URL}/api/auth/register',
            json={
                'property_name': f'Semantic Folio {register_suffix}',
                'email': f'folio-{register_suffix}@example.com',
                'password': 'semantic123',
                'name': f'Semantic Folio {register_suffix}',
                'phone': '+905550000000',
                'address': 'Test Address',
                'location': 'Test City',
            },
        )
        assert register_response.status_code == 200, register_response.text
        other_token = register_response.json()['access_token']

        response = requests.post(
            f'{BASE_URL}/api/folio/create',
            json={
                'booking_id': booking['id'],
                'folio_type': 'agency',
                'notes': 'wrong-tenant-attempt',
            },
            headers={
                'Authorization': f'Bearer {other_token}',
                'Content-Type': 'application/json',
                'Idempotency-Key': f'folio-{uuid.uuid4()}',
            },
        )
        assert response.status_code == 404