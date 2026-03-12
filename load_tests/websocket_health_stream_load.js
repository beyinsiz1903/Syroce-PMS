/**
 * k6 Load Test — WebSocket Health Stream Load
 * Simulates concurrent WebSocket dashboard polling via HTTP fallback.
 * Measures: websocket event latency, dashboard stale data count
 * Run: k6 run load_tests/websocket_health_stream_load.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

const wsErrors = new Rate('ws_errors');
const wsLatency = new Trend('ws_poll_latency_ms');

export const options = {
    scenarios: {
        concurrent_polls: {
            executor: 'constant-vus',
            vus: 20,
            duration: '45s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<2000'],
        ws_errors: ['rate<0.10'],
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

    group('Health Snapshot', () => {
        const res = http.get(`${BASE_URL}/api/system-health/normalized/admin`, { headers });
        check(res, { 'health snapshot OK': (r) => r.status === 200 });
        wsErrors.add(res.status !== 200);
        wsLatency.add(res.timings.duration);
    });

    group('Live System Health', () => {
        const res = http.get(`${BASE_URL}/api/system-health/live`, { headers });
        const ok = check(res, { 'live health OK': (r) => r.status === 200 });
        wsErrors.add(!ok);
        wsLatency.add(res.timings.duration);
    });

    sleep(1 + Math.random() * 2);
}
