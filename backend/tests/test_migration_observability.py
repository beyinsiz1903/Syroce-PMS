import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

import os
import pytest
if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)

from core.database import db
from core.tenant_db import tenant_context
from shared_kernel.migration_observability import build_health_score, build_stale_pending_triage


BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")


class TestMigrationObservability:
    @pytest.fixture(autouse=True)
    def setup(self):
        if not BASE_URL:
            pytest.skip('VITE_BACKEND_URL missing')

        self.created_outbox_event_ids = []
        self.created_audit_log_ids = []

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
        if self.created_outbox_event_ids:
            with tenant_context(tenant_id):
                with tenant_context(tenant_id):
                    with tenant_context(tenant_id):
                        db.delegate['outbox_events'].delete_many({'event_id': {'$in': self.created_outbox_event_ids}})
        if self.created_audit_log_ids:
            with tenant_context(tenant_id):
                with tenant_context(tenant_id):
                    with tenant_context(tenant_id):
                        db.delegate['audit_logs'].delete_many({'id': {'$in': self.created_audit_log_ids}})

    def _insert_outbox_event(self, tenant_id: str, event_type: str, status: str = 'pending'):
        event_id = str(uuid.uuid4())
        with tenant_context(tenant_id):
            with tenant_context(tenant_id):
                with tenant_context(tenant_id):
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
        self.created_outbox_event_ids.append(event_id)
        return event_id

    def _insert_audit_log(self, tenant_id: str, action: str, entity_id: str):
        audit_id = str(uuid.uuid4())
        with tenant_context(tenant_id):
            with tenant_context(tenant_id):
                with tenant_context(tenant_id):
                    db.delegate['audit_logs'].insert_one({
                    'id': audit_id,
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
        self.created_audit_log_ids.append(audit_id)

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

        assert {'generated_at', 'health_score', 'outbox', 'audit', 'shadow'} <= set(payload.keys())
        assert {'status', 'display_status', 'calculated_at', 'time_window', 'reasons', 'reason_params', 'operational_guidance_key', 'signals'} <= set(payload['health_score'].keys())
        assert {'throughput', 'queue_depth', 'lifecycle', 'event_breakdown', 'retries', 'stale_triage', 'lag', 'recent_events'} <= set(payload['outbox'].keys())
        assert {'recent_count', 'audit_gap_count', 'actions_breakdown', 'recent_stream'} <= set(payload['audit'].keys())
        assert {'summary', 'recent_events'} <= set(payload['shadow'].keys())
        assert {'total_stale_pending', 'event_type_breakdown', 'property_breakdown', 'source_breakdown', 'delivery_signals', 'assessment'} <= set(payload['outbox']['stale_triage'].keys())
        assert {'pending_count', 'processing_count', 'processed_count', 'failed_count', 'parked_count', 'retry_attempts_total', 'oldest_pending_age_minutes', 'oldest_failed_age_minutes'} <= set(payload['outbox']['lifecycle'].keys())

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


def test_health_score_is_green_when_signals_are_healthy():
    score = build_health_score(
        generated_at=datetime.now(timezone.utc).isoformat(),
        failed_outbox_count=0,
        stale_pending_count=0,
        audit_gap_count=0,
        shadow_summary=[
            {'endpoint': 'availability', 'mismatch_rate_percent': 0.2, 'errors': 0},
            {'endpoint': 'folio', 'mismatch_rate_percent': 0.0, 'errors': 0},
        ],
    )

    assert score['status'] == 'green'
    assert score['display_status'] == 'Green'
    assert len(score['reasons']) == 3


def test_health_score_is_yellow_for_stale_pending_or_compare_error():
    score = build_health_score(
        generated_at=datetime.now(timezone.utc).isoformat(),
        failed_outbox_count=0,
        stale_pending_count=2,
        audit_gap_count=0,
        shadow_summary=[
            {'endpoint': 'availability', 'mismatch_rate_percent': 1.7, 'errors': 1},
            {'endpoint': 'folio', 'mismatch_rate_percent': 0.0, 'errors': 0},
        ],
    )

    assert score['status'] == 'yellow'
    assert 'stale_pending_event' in score['reasons']


def test_health_score_red_override_for_audit_gap():
    score = build_health_score(
        generated_at=datetime.now(timezone.utc).isoformat(),
        failed_outbox_count=0,
        stale_pending_count=0,
        audit_gap_count=1,
        shadow_summary=[
            {'endpoint': 'availability', 'mismatch_rate_percent': 0.0, 'errors': 0},
            {'endpoint': 'folio', 'mismatch_rate_percent': 0.0, 'errors': 0},
        ],
    )

    assert score['status'] == 'red'
    assert score['signals']['audit_gap_count'] == 1
    assert 'audit_gap_detected' in score['reasons']


def test_stale_pending_triage_classifies_semantic_backlog_without_delivery_signals():
    now = datetime.now(timezone.utc)
    triage = build_stale_pending_triage(
        generated_at=now.isoformat(),
        stale_events=[
            {
                'event_id': 'evt-1',
                'event_type': 'reservation.created.v1',
                'tenant_id': 'tenant-1',
                'property_id': 'property-1',
                'status': 'pending',
                'created_at': (now - timedelta(hours=2)).isoformat(),
                'reservation_id': 'res-1',
                'payload': {},
            },
            {
                'event_id': 'evt-2',
                'event_type': 'inventory.released.v1',
                'tenant_id': 'tenant-1',
                'property_id': 'property-1',
                'status': 'pending',
                'created_at': (now - timedelta(hours=1)).isoformat(),
                'room_block_id': 'block-1',
                'payload': {'source': 'semantic_inventory_service'},
            },
        ],
    )

    assert triage['total_stale_pending'] == 2
    assert triage['assessment']['backlog_shape'] == 'same_day_backlog'
    assert triage['origin_breakdown'][0]['origin'] == 'semantic'
    assert triage['delivery_signals']['has_delivery_lifecycle'] is False
    assert triage['assessment']['likely_root_cause_key'] == 'worker_not_connected'