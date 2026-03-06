import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

from core.database import db


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestCreateReservationBridge:
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

    def _get_guest_and_room(self):
        guests = self.session.get(f'{BASE_URL}/api/pms/guests?limit=5').json()
        rooms = self.session.get(f'{BASE_URL}/api/pms/rooms?limit=5').json()
        if not guests or not rooms:
            pytest.skip('Need at least one guest and one room')
        return guests[0]['id'], rooms[0]['id']

    def _build_payload(self, guest_id: str, room_id: str):
        check_in = (datetime.utcnow().date() + timedelta(days=30)).isoformat() + 'T14:00:00Z'
        check_out = (datetime.utcnow().date() + timedelta(days=32)).isoformat() + 'T12:00:00Z'
        return {
            'guest_id': guest_id,
            'room_id': room_id,
            'check_in': check_in,
            'check_out': check_out,
            'adults': 2,
            'children': 0,
            'children_ages': [],
            'guests_count': 2,
            'total_amount': 1200.0,
            'special_requests': f'semantic-create-test-{uuid.uuid4().hex[:8]}',
        }

    def _find_one(self, collection_name: str, query: dict):
        collection = db.delegate[collection_name]
        return collection.find_one(query, {'_id': 0})

    def test_happy_path_create_reservation_with_outbox_and_audit(self):
        guest_id, room_id = self._get_guest_and_room()
        payload = self._build_payload(guest_id, room_id)
        idem_key = f'idem-{uuid.uuid4()}'

        response = self.session.post(
            f'{BASE_URL}/api/pms/bookings',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': idem_key},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        assert data['tenant_id'] == self.tenant_id
        assert data['guest_id'] == guest_id
        assert data['room_id'] == room_id
        assert 'id' in data
        assert 'qr_code' in data
        assert 'qr_code_data' in data

        outbox = self._find_one('outbox_events', {'reservation_id': data['id'], 'event_type': 'reservation.created.v1'})
        assert outbox is not None
        assert outbox['tenant_id'] == self.tenant_id

        audit = self._find_one('audit_logs', {'entity_type': 'reservation', 'entity_id': data['id'], 'action': 'reservation_created'})
        assert audit is not None
        assert audit['tenant_id'] == self.tenant_id

    def test_duplicate_request_same_idempotency_key_returns_same_reservation(self):
        guest_id, room_id = self._get_guest_and_room()
        payload = self._build_payload(guest_id, room_id)
        idem_key = f'idem-{uuid.uuid4()}'
        headers = {'Authorization': f'Bearer {self.token}', 'Idempotency-Key': idem_key}

        first = self.session.post(f'{BASE_URL}/api/pms/bookings', json=payload, headers=headers)
        second = self.session.post(f'{BASE_URL}/api/pms/bookings', json=payload, headers=headers)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()['id'] == second.json()['id']

    def test_missing_idempotency_key_rejected(self):
        guest_id, room_id = self._get_guest_and_room()
        payload = self._build_payload(guest_id, room_id)
        response = self.session.post(f'{BASE_URL}/api/pms/bookings', json=payload)
        assert response.status_code == 400
        assert 'Idempotency-Key' in response.text

    def test_wrong_property_scope_rejected(self):
        guest_id, room_id = self._get_guest_and_room()
        payload = self._build_payload(guest_id, room_id)
        response = self.session.post(
            f'{BASE_URL}/api/pms/bookings',
            json=payload,
            headers={
                'Authorization': f'Bearer {self.token}',
                'Idempotency-Key': f'idem-{uuid.uuid4()}',
                'x-property-id': 'wrong-property',
            },
        )
        assert response.status_code == 403

    def test_missing_required_field_returns_422(self):
        guest_id, room_id = self._get_guest_and_room()
        payload = self._build_payload(guest_id, room_id)
        payload.pop('room_id')
        response = self.session.post(
            f'{BASE_URL}/api/pms/bookings',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'idem-{uuid.uuid4()}'},
        )
        assert response.status_code == 422

    def test_wrong_tenant_cannot_create_with_demo_entities(self):
        register_suffix = uuid.uuid4().hex[:8]
        register_response = requests.post(
            f'{BASE_URL}/api/auth/register',
            json={
                'property_name': f'Semantic Create {register_suffix}',
                'email': f'create-{register_suffix}@example.com',
                'password': 'semantic123',
                'name': f'Semantic Create {register_suffix}',
                'phone': '+905550000000',
                'address': 'Test Address',
                'location': 'Test City',
            },
        )
        assert register_response.status_code == 200, register_response.text
        other_token = register_response.json()['access_token']

        guest_id, room_id = self._get_guest_and_room()
        payload = self._build_payload(guest_id, room_id)
        response = requests.post(
            f'{BASE_URL}/api/pms/bookings',
            json=payload,
            headers={
                'Authorization': f'Bearer {other_token}',
                'Content-Type': 'application/json',
                'Idempotency-Key': f'idem-{uuid.uuid4()}',
            },
        )
        assert response.status_code == 404