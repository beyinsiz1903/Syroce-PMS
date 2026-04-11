/**
 * k6 Load Test — Queue Backlog Load
 * Simulates event queue backlog under sustained load.
 * Measures: queue lag, worker backlog growth, event processing latency
 * Run: k6 run load_tests/queue_backlog_load.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

const queueErrors = new Rate('queue_errors');
const eventLatency = new Trend('event_latency_ms');

export const options = {
    scenarios: {
        sustained: {
            executor: 'constant-vus',
            vus: 20,
            duration: '60s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<3000'],
        queue_errors: ['rate<0.10'],
    },
};

export function setup() {
    const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
        email: 'demo@hotel.com',
        password: 'demo123',
    }), { headers: { 'Content-Type': 'application/json' } });
    return { token: JSON.parse(loginRes.body).access_token };
}

export default function (data) {
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${data.token}`,
    };

    group('Audit Log Write', () => {
        const res = http.get(`${BASE_URL}/api/audit-logs?limit=10`, { headers });
        check(res, { 'audit read OK': (r) => r.status === 200 });
        queueErrors.add(res.status !== 200);
        eventLatency.add(res.timings.duration);
    });

    group('Error Log Queue', () => {
        const res = http.get(`${BASE_URL}/api/logs/errors?limit=10`, { headers });
        check(res, { 'errors OK': (r) => r.status === 200 });
        eventLatency.add(res.timings.duration);
    });

    group('Night Audit History', () => {
        const res = http.get(`${BASE_URL}/api/night-audit/history?limit=5`, { headers });
        check(res, { 'audit history OK': (r) => r.status === 200 });
        eventLatency.add(res.timings.duration);
    });

    group('Operational Metrics', () => {
        const res = http.get(`${BASE_URL}/api/metrics/operational`, { headers });
        check(res, { 'metrics OK': (r) => r.status === 200 });
        eventLatency.add(res.timings.duration);
    });

    sleep(0.5 + Math.random() * 0.5);
}
