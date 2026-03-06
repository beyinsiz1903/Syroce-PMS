import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

from core.database import db


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestMigrationObservability:
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

    def _insert_outbox_event(self, tenant_id: str, event_type: str, status: str = 'pending'):
        event_id = str(uuid.uuid4())
        db.delegate['outbox_events'].insert_one({
            'event_id': event_id,
            'event_type': event_type,
            'tenant_id': tenant_id,
            'correlation_id': f'corr-{uuid.uuid4()}',
            'payload': {'seed': True},
            'status': status,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'reservation_id': str(uuid.uuid4()),
        })
        return event_id

    def _insert_audit_log(self, tenant_id: str, action: str, entity_id: str):
        db.delegate['audit_logs'].insert_one({
            'id': str(uuid.uuid4()),
            'actor_id': 'observer-test',
            'tenant_id': tenant_id,
            'property_id': tenant_id,
            'entity_type': 'reservation',
            'entity_id': entity_id,
            'action': action,
            'metadata': {'seed': True},
            'correlation_id': f'corr-{uuid.uuid4()}',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })

    def test_observability_endpoint_returns_expected_sections(self):
        self._insert_outbox_event(self.tenant_id, 'reservation.created.v1')
        entity_id = str(uuid.uuid4())
        self._insert_audit_log(self.tenant_id, 'reservation_created', entity_id)

        folio_rows = self.session.get(f'{BASE_URL}/api/folio/list?limit=1').json().get('folios', [])
        if folio_rows:
            self.session.get(f"{BASE_URL}/api/folio/{folio_rows[0]['id']}")
        check_in = datetime.now(timezone.utc).date().isoformat()
        check_out = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        self.session.get(f'{BASE_URL}/api/pms/rooms/availability?check_in={check_in}&check_out={check_out}')

        response = self.session.get(f'{BASE_URL}/api/reports/migration-observability')
        assert response.status_code == 200, response.text
        payload = response.json()

        assert {'generated_at', 'outbox', 'audit', 'shadow'} <= set(payload.keys())
        assert {'throughput', 'queue_depth', 'event_breakdown', 'retries', 'lag', 'recent_events'} <= set(payload['outbox'].keys())
        assert {'recent_count', 'actions_breakdown', 'recent_stream'} <= set(payload['audit'].keys())
        assert {'summary', 'recent_events'} <= set(payload['shadow'].keys())

        breakdown_types = {item['event_type'] for item in payload['outbox']['event_breakdown']}
        assert 'reservation.created.v1' in breakdown_types
        audit_entity_ids = {item['entity_id'] for item in payload['audit']['recent_stream']}
        assert entity_id in audit_entity_ids

        shadow_endpoints = {item['endpoint'] for item in payload['shadow']['summary']}
        assert {'availability', 'folio'} <= shadow_endpoints

    def test_observability_endpoint_enforces_tenant_isolation(self):
        foreign_tenant_id = str(uuid.uuid4())
        foreign_entity_id = str(uuid.uuid4())
        self._insert_outbox_event(foreign_tenant_id, 'folio.opened.v1')
        self._insert_audit_log(foreign_tenant_id, 'folio_opened', foreign_entity_id)

        response = self.session.get(f'{BASE_URL}/api/reports/migration-observability')
        assert response.status_code == 200, response.text
        payload = response.json()

        recent_audit_ids = {item['entity_id'] for item in payload['audit']['recent_stream']}
        assert foreign_entity_id not in recent_audit_ids