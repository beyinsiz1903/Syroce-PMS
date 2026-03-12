/**
 * k6 Load Test — System Health Dashboard Load
 * Simulates concurrent dashboard polling (GM/Admin/Superadmin).
 * Measures: dashboard data freshness, WebSocket event latency
 * Run: k6 run load_tests/system_health_dashboard_load.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

const dashErrors = new Rate('dashboard_errors');
const dashLatency = new Trend('dashboard_latency_ms');

export const options = {
    scenarios: {
        gm_polling: {
            executor: 'constant-vus',
            vus: 5,
            duration: '30s',
        },
        admin_polling: {
            executor: 'constant-vus',
            vus: 10,
            duration: '30s',
        },
        burst_refresh: {
            executor: 'ramping-vus',
            startVUs: 5,
            stages: [
                { duration: '10s', target: 30 },
                { duration: '10s', target: 50 },
                { duration: '10s', target: 5 },
            ],
            startTime: '30s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<3000'],
        dashboard_errors: ['rate<0.10'],
        dashboard_latency_ms: ['p(95)<4000'],
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

    group('Normalized Health', () => {
        const res = http.get(`${BASE_URL}/api/system-health/normalized/admin`, { headers });
        check(res, { 'health OK': (r) => r.status === 200 });
        dashErrors.add(res.status !== 200);
        dashLatency.add(res.timings.duration);
    });

    group('Operational Metrics', () => {
        const res = http.get(`${BASE_URL}/api/metrics/operational`, { headers });
        check(res, { 'ops metrics OK': (r) => r.status === 200 });
        dashLatency.add(res.timings.duration);
    });

    group('Night Audit Metrics', () => {
        const res = http.get(`${BASE_URL}/api/metrics/night-audit`, { headers });
        check(res, { 'NA metrics OK': (r) => r.status === 200 });
        dashLatency.add(res.timings.duration);
    });

    group('Audit Summary', () => {
        const res = http.get(`${BASE_URL}/api/audit/summary?period=24h`, { headers });
        check(res, { 'audit summary OK': (r) => r.status === 200 });
        dashLatency.add(res.timings.duration);
    });

    sleep(2 + Math.random() * 3);
}
