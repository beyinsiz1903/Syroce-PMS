import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

import os
import pytest
if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)

from core.database import db


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")


class TestReleaseRoomBlockBridge:
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

    def _pick_available_room(self):
        start_date = (datetime.utcnow().date() + timedelta(days=60)).isoformat()
        end_date = (datetime.utcnow().date() + timedelta(days=63)).isoformat()
        availability = self.session.get(
            f'{BASE_URL}/api/pms/rooms/availability?check_in={start_date}&check_out={end_date}'
        ).json()
        available_room = next((room for room in availability if room.get('available') is True), None)
        if not available_room:
            pytest.skip('No available room found for release test date range')
        return available_room, start_date, end_date

    def _build_block_payload(self, room_id: str, start_date: str, end_date: str):
        return {
            'room_id': room_id,
            'type': 'out_of_order',
            'reason': f'semantic-room-release-{uuid.uuid4().hex[:8]}',
            'details': 'Semantic room block release bridge test',
            'start_date': start_date,
            'end_date': end_date,
            'allow_sell': False,
        }

    def _create_block(self):
        room, start_date, end_date = self._pick_available_room()
        create_response = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks',
            json=self._build_block_payload(room['id'], start_date, end_date),
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'create-{uuid.uuid4()}'},
        )
        assert create_response.status_code == 200, create_response.text
        return room, start_date, end_date, create_response.json()['block']

    def test_happy_path_release_room_block_with_outbox_and_audit(self):
        room, _, _, block = self._create_block()
        release_response = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel',
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'release-{uuid.uuid4()}'},
        )
        assert release_response.status_code == 200, release_response.text
        data = release_response.json()

        assert data['room_block_id'] == block['id']
        assert data['block_id'] == block['id']
        assert data['status'] == 'released'
        assert data['property_id'] == self.tenant_id
        assert data['room_id'] == room['id']
        assert data['room_type'] == room['room_type']
        assert data['released_at']
        assert data['correlation_id']

        block_doc = self._find_one('room_blocks', {'id': block['id'], 'tenant_id': self.tenant_id})
        assert block_doc is not None
        assert block_doc['status'] == 'released'

        outbox = self._find_one('outbox_events', {'room_block_id': block['id'], 'event_type': 'inventory.released.v1'})
        assert outbox is not None
        assert outbox['tenant_id'] == self.tenant_id
        assert outbox['property_id'] == self.tenant_id
        assert outbox['released_at']
        assert outbox['payload']['source'] == 'semantic_inventory_service'
        assert outbox['payload']['release_scope']['room_id'] == room['id']
        assert outbox['payload']['effective_date_range']['start_date'] == block['start_date']
        assert outbox['payload']['effective_date_range']['end_date'] == block['end_date']
        assert outbox['payload']['actor_reference']['actor_id']

        audit = self._find_one('audit_logs', {'entity_type': 'room_block', 'entity_id': block['id'], 'action': 'room_block_released'})
        assert audit is not None
        assert audit['tenant_id'] == self.tenant_id

    def test_duplicate_request_same_idempotency_key_returns_same_release_response(self):
        _, _, _, block = self._create_block()
        headers = {'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'release-{uuid.uuid4()}'}

        first = self.session.post(f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel', headers=headers)
        second = self.session.post(f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel', headers=headers)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json() == second.json()

    def test_duplicate_release_with_new_idempotency_key_is_deterministic_and_no_duplicate_event(self):
        _, _, _, block = self._create_block()
        first = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel',
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'release-{uuid.uuid4()}'},
        )
        assert first.status_code == 200, first.text

        second = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel',
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'release-{uuid.uuid4()}'},
        )
        assert second.status_code == 200, second.text
        assert second.json()['room_block_id'] == first.json()['room_block_id']
        assert second.json()['released_at'] == first.json()['released_at']

        assert self._count_documents('outbox_events', {'room_block_id': block['id'], 'event_type': 'inventory.released.v1'}) == 1

    def test_missing_idempotency_key_rejected(self):
        _, _, _, block = self._create_block()
        response = self.session.post(f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel')
        assert response.status_code == 400
        assert 'Idempotency-Key' in response.text

    def test_wrong_property_scope_rejected_without_availability_effect(self):
        room, start_date, end_date, block = self._create_block()
        failed_release = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel',
            headers={
                'Authorization': f'Bearer {self.token}',
                'Idempotency-Key': f'release-{uuid.uuid4()}',
                'x-property-id': 'wrong-property',
            },
        )
        assert failed_release.status_code == 403

        availability = self.session.get(
            f'{BASE_URL}/api/pms/rooms/availability?check_in={start_date}&check_out={end_date}'
        )
        assert availability.status_code == 200
        rows = availability.json()
        blocked_room = next((row for row in rows if row.get('id') == room['id']), None)
        assert blocked_room is not None
        assert blocked_room.get('available') is False

    def test_wrong_tenant_cannot_release_demo_block_and_block_stays_active(self):
        _, _, _, block = self._create_block()
        register_suffix = uuid.uuid4().hex[:8]
        register_response = requests.post(
            f'{BASE_URL}/api/auth/register',
            json={
                'property_name': f'Semantic Release {register_suffix}',
                'email': f'release-{register_suffix}@example.com',
                'password': 'semantic123',
                'name': f'Semantic Release {register_suffix}',
                'phone': '+905550000000',
                'address': 'Test Address',
                'location': 'Test City',
            },
        )
        assert register_response.status_code == 200, register_response.text
        other_token = register_response.json()['access_token']

        response = requests.post(
            f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel',
            headers={
                'Authorization': f'Bearer {other_token}',
                'Content-Type': 'application/json',
                'Idempotency-Key': f'release-{uuid.uuid4()}',
            },
        )
        assert response.status_code == 404

        block_doc = self._find_one('room_blocks', {'id': block['id'], 'tenant_id': self.tenant_id})
        assert block_doc is not None
        assert block_doc['status'] == 'active'

    def test_availability_projection_effect_after_release(self):
        room, start_date, end_date, block = self._create_block()

        blocked_before_release = self.session.get(
            f'{BASE_URL}/api/pms/rooms/availability?check_in={start_date}&check_out={end_date}'
        )
        assert blocked_before_release.status_code == 200
        rows = blocked_before_release.json()
        blocked_room = next((row for row in rows if row.get('id') == room['id']), None)
        assert blocked_room is not None
        assert blocked_room.get('available') is False

        release_response = self.session.post(
            f'{BASE_URL}/api/pms/room-blocks/{block["id"]}/cancel',
            headers={'Authorization': f'Bearer {self.token}', 'Idempotency-Key': f'release-{uuid.uuid4()}'},
        )
        assert release_response.status_code == 200, release_response.text

        availability = self.session.get(
            f'{BASE_URL}/api/pms/rooms/availability?check_in={start_date}&check_out={end_date}'
        )
        assert availability.status_code == 200
        rows = availability.json()
        released_room = next((row for row in rows if row.get('id') == room['id']), None)
        assert released_room is not None
        assert released_room.get('available') is True