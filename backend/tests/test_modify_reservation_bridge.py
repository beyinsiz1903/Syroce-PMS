import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

from core.database import db


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestModifyReservationBridge:
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

    def _count_documents(self, collection_name: str, query: dict) -> int:
        return db.delegate[collection_name].count_documents(query)

    def _get_guest_and_rooms(self):
        guests = self.session.get(f'{BASE_URL}/api/pms/guests?limit=5').json()
        rooms = self.session.get(f'{BASE_URL}/api/pms/rooms?limit=20').json()
        if not guests or len(rooms) < 2:
            pytest.skip('Need at least one guest and two rooms')
        return guests[0]['id'], rooms[0], rooms[1]

    def _build_create_payload(self, guest_id: str, room_id: str):
        check_in = (datetime.utcnow().date() + timedelta(days=40)).isoformat() + 'T14:00:00Z'
        check_out = (datetime.utcnow().date() + timedelta(days=42)).isoformat() + 'T12:00:00Z'
        return {
            'guest_id': guest_id,
            'room_id': room_id,
            'check_in': check_in,
            'check_out': check_out,
            'adults': 2,
            'children': 0,
            'children_ages': [],
            'guests_count': 2,
            'total_amount': 1450.0,
            'special_requests': f'semantic-modify-create-{uuid.uuid4().hex[:8]}',
        }

    def _create_booking(self):
        guest_id, original_room, updated_room = self._get_guest_and_rooms()
        response = self.session.post(
            f'{BASE_URL}/api/pms/bookings',
            json=self._build_create_payload(guest_id, original_room['id']),
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'create-{uuid.uuid4()}'},
        )
        assert response.status_code == 200, response.text
        return guest_id, original_room, updated_room, response.json()

    def test_happy_path_modify_reservation_with_outbox_and_audit(self):
        _, _, updated_room, booking = self._create_booking()
        new_total = booking['total_amount'] + 275.0
        new_note = f'semantic-modify-{uuid.uuid4().hex[:8]}'

        response = self.session.put(
            f'{BASE_URL}/api/pms/bookings/{booking["id"]}',
            json={
                'room_id': updated_room['id'],
                'total_amount': new_total,
                'special_requests': new_note,
            },
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'modify-{uuid.uuid4()}'},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        assert data['id'] == booking['id']
        assert data['room_id'] == updated_room['id']
        assert data['room_number'] == updated_room['room_number']
        assert data['total_amount'] == new_total
        assert data['special_requests'] == new_note

        outbox = self._find_one('outbox_events', {'reservation_id': booking['id'], 'event_type': 'reservation.modified.v1'})
        assert outbox is not None
        assert outbox['tenant_id'] == self.tenant_id
        assert outbox['property_id'] == self.tenant_id
        assert outbox['payload']['source'] == 'semantic_reservations_service'
        assert 'room_id' in outbox['payload']['changed_fields']
        assert outbox['payload']['changes']['room_id']['to'] == updated_room['id']

        audit = self._find_one('audit_logs', {'entity_type': 'reservation', 'entity_id': booking['id'], 'action': 'reservation_modified'})
        assert audit is not None
        assert audit['tenant_id'] == self.tenant_id
        assert 'room_id' in audit['metadata']['changed_fields']

    def test_duplicate_request_same_idempotency_key_returns_same_reservation(self):
        _, _, updated_room, booking = self._create_booking()
        headers = {'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'modify-{uuid.uuid4()}'}
        payload = {
            'room_id': updated_room['id'],
            'special_requests': f'semantic-idem-{uuid.uuid4().hex[:8]}',
        }

        first = self.session.put(f'{BASE_URL}/api/pms/bookings/{booking["id"]}', json=payload, headers=headers)
        second = self.session.put(f'{BASE_URL}/api/pms/bookings/{booking["id"]}', json=payload, headers=headers)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json() == second.json()
        assert self._count_documents('outbox_events', {'reservation_id': booking['id'], 'event_type': 'reservation.modified.v1'}) == 1

    def test_same_target_state_with_new_idempotency_key_is_deterministic_and_no_duplicate_event(self):
        _, _, updated_room, booking = self._create_booking()
        payload = {
            'room_id': updated_room['id'],
            'special_requests': f'semantic-deterministic-{uuid.uuid4().hex[:8]}',
        }

        first = self.session.put(
            f'{BASE_URL}/api/pms/bookings/{booking["id"]}',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'modify-{uuid.uuid4()}'},
        )
        assert first.status_code == 200, first.text

        second = self.session.put(
            f'{BASE_URL}/api/pms/bookings/{booking["id"]}',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'modify-{uuid.uuid4()}'},
        )
        assert second.status_code == 200, second.text
        assert second.json()['id'] == first.json()['id']
        assert second.json()['room_id'] == first.json()['room_id']
        assert second.json()['special_requests'] == first.json()['special_requests']
        assert self._count_documents('outbox_events', {'reservation_id': booking['id'], 'event_type': 'reservation.modified.v1'}) == 1

    def test_missing_idempotency_key_rejected(self):
        _, _, updated_room, booking = self._create_booking()
        response = self.session.put(
            f'{BASE_URL}/api/pms/bookings/{booking["id"]}',
            json={'room_id': updated_room['id']},
        )
        assert response.status_code == 400
        assert 'Idempotency-Key' in response.text

    def test_wrong_property_scope_rejected_without_mutating_booking(self):
        _, original_room, updated_room, booking = self._create_booking()
        response = self.session.put(
            f'{BASE_URL}/api/pms/bookings/{booking["id"]}',
            json={'room_id': updated_room['id']},
            headers={
                'Authorization': f'Bearer {self.token}',
                'Idempotency-Key': f'modify-{uuid.uuid4()}',
                'x-property-id': 'wrong-property',
            },
        )
        assert response.status_code == 403

        booking_doc = self._find_one('bookings', {'id': booking['id'], 'tenant_id': self.tenant_id})
        assert booking_doc is not None
        assert booking_doc['room_id'] == original_room['id']

    def test_wrong_tenant_cannot_modify_demo_reservation(self):
        _, _, updated_room, booking = self._create_booking()
        register_suffix = uuid.uuid4().hex[:8]
        register_response = requests.post(
            f'{BASE_URL}/api/auth/register',
            json={
                'property_name': f'Semantic Modify {register_suffix}',
                'email': f'modify-{register_suffix}@example.com',
                'password': 'semantic123',
                'name': f'Semantic Modify {register_suffix}',
                'phone': '+905550000000',
                'address': 'Test Address',
                'location': 'Test City',
            },
        )
        assert register_response.status_code == 200, register_response.text
        other_token = register_response.json()['access_token']

        response = requests.put(
            f'{BASE_URL}/api/pms/bookings/{booking["id"]}',
            json={'room_id': updated_room['id']},
            headers={
                'Authorization': f'Bearer {other_token}',
                'Content-Type': 'application/json',
                'Idempotency-Key': f'modify-{uuid.uuid4()}',
            },
        )
        assert response.status_code == 404

        booking_doc = self._find_one('bookings', {'id': booking['id'], 'tenant_id': self.tenant_id})
        assert booking_doc is not None
        assert booking_doc['room_id'] == booking['room_id']