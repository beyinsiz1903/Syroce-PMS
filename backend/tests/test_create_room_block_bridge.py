import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

from core.database import db


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestCreateRoomBlockBridge:
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

    def _pick_available_room(self):
        start_date = (datetime.utcnow().date() + timedelta(days=40)).isoformat()
        end_date = (datetime.utcnow().date() + timedelta(days=42)).isoformat()
        availability = self.session.get(
            f'{BASE_URL}/api/pms/rooms/availability?check_in={start_date}&check_out={end_date}'
        ).json()
        available_room = next((room for room in availability if room.get('available') is True), None)
        if not available_room:
            pytest.skip('No available room found for future date range')
        return available_room, start_date, end_date

    def _build_payload(self, room_id: str, start_date: str, end_date: str):
        return {
            'room_id': room_id,
            'type': 'out_of_order',
            'reason': f'semantic-room-block-{uuid.uuid4().hex[:8]}',
            'details': 'Semantic room block bridge test',
            'start_date': start_date,
            'end_date': end_date,
            'allow_sell': False,
        }

    def test_happy_path_room_block_create_with_outbox_and_audit(self):
        room, start_date, end_date = self._pick_available_room()
        payload = self._build_payload(room['id'], start_date, end_date)
        idem_key = f'idem-{uuid.uuid4()}'

        response = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': idem_key},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['message'] == 'Room block created successfully'
        assert data['room_number'] == room['room_number']
        assert 'block' in data
        block = data['block']
        assert block['room_id'] == room['id']

        outbox = self._find_one('outbox_events', {'room_block_id': block['id'], 'event_type': 'inventory.blocked.v1'})
        assert outbox is not None
        assert outbox['tenant_id'] == self.tenant_id

        audit = self._find_one('audit_logs', {'entity_type': 'room_block', 'entity_id': block['id'], 'action': 'room_block_created'})
        assert audit is not None
        assert audit['tenant_id'] == self.tenant_id

    def test_duplicate_request_same_idempotency_key_returns_same_block(self):
        room, start_date, end_date = self._pick_available_room()
        payload = self._build_payload(room['id'], start_date, end_date)
        idem_key = f'idem-{uuid.uuid4()}'
        headers = {'Authorization': f'Bearer {self.token}', 'Idempotency-Key': idem_key}

        first = self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers)
        second = self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload, headers=headers)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()['block']['id'] == second.json()['block']['id']

    def test_missing_idempotency_key_rejected(self):
        room, start_date, end_date = self._pick_available_room()
        payload = self._build_payload(room['id'], start_date, end_date)
        response = self.session.post(f'{BASE_URL}/api/pms/room-blocks', json=payload)
        assert response.status_code == 400
        assert 'Idempotency-Key' in response.text

    def test_wrong_property_scope_rejected(self):
        room, start_date, end_date = self._pick_available_room()
        payload = self._build_payload(room['id'], start_date, end_date)
        response = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks',
            json=payload,
            headers={
                'Authorization': f'Bearer {self.token}',
                'Idempotency-Key': f'idem-{uuid.uuid4()}',
                'x-property-id': 'wrong-property',
            },
        )
        assert response.status_code == 403

    def test_invalid_date_range_rejected(self):
        room, start_date, end_date = self._pick_available_room()
        payload = self._build_payload(room['id'], end_date, start_date)
        response = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'idem-{uuid.uuid4()}'},
        )
        assert response.status_code == 400

    def test_wrong_tenant_cannot_block_demo_room(self):
        register_suffix = uuid.uuid4().hex[:8]
        register_response = requests.post(
            f'{BASE_URL}/api/auth/register',
            json={
                'property_name': f'Semantic Block {register_suffix}',
                'email': f'block-{register_suffix}@example.com',
                'password': 'semantic123',
                'name': f'Semantic Block {register_suffix}',
                'phone': '+905550000000',
                'address': 'Test Address',
                'location': 'Test City',
            },
        )
        assert register_response.status_code == 200, register_response.text
        other_token = register_response.json()['access_token']

        room, start_date, end_date = self._pick_available_room()
        payload = self._build_payload(room['id'], start_date, end_date)
        response = requests.post(
            f'{BASE_URL}/api/pms/room-blocks',
            json=payload,
            headers={
                'Authorization': f'Bearer {other_token}',
                'Content-Type': 'application/json',
                'Idempotency-Key': f'idem-{uuid.uuid4()}',
            },
        )
        assert response.status_code == 404

    def test_availability_projection_effect_after_block(self):
        room, start_date, end_date = self._pick_available_room()
        payload = self._build_payload(room['id'], start_date, end_date)
        response = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks',
            json=payload,
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'idem-{uuid.uuid4()}'},
        )
        assert response.status_code == 200, response.text

        availability = self.session.get(
            f'{BASE_URL}/api/pms/rooms/availability?check_in={start_date}&check_out={end_date}'
        )
        assert availability.status_code == 200
        rows = availability.json()
        blocked_room = next((row for row in rows if row.get('id') == room['id']), None)
        assert blocked_room is not None
        assert blocked_room.get('available') is False
        reason = blocked_room.get('reason', '')
        assert 'out_of_order' in reason or blocked_room.get('blocks') is not None