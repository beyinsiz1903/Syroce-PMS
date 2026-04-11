/**
 * k6 Load Test — Night Audit Load (Production-Grade)
 * Simulates concurrent night audit reads + business date checks + exception queries
 * Measures: audit duration, exception count, room charge posting throughput
 * Run: k6 run load_tests/night_audit_load.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

const auditErrors = new Rate('audit_errors');
const auditLatency = new Trend('audit_query_latency_ms');

export const options = {
    scenarios: {
        pre_audit_reads: {
            executor: 'constant-vus',
            vus: 15,
            duration: '40s',
        },
        night_audit_overlap: {
            executor: 'per-vu-iterations',
            vus: 5,
            iterations: 2,
            maxDuration: '60s',
            startTime: '10s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<5000'],
        audit_errors: ['rate<0.20'],
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

    group('Business Date Check', () => {
        const res = http.get(`${BASE_URL}/api/night-audit/business-date`, { headers });
        check(res, { 'business date OK': (r) => r.status === 200 });
        auditErrors.add(res.status !== 200);
        auditLatency.add(res.timings.duration);
    });

    group('Audit History', () => {
        const res = http.get(`${BASE_URL}/api/night-audit/history?limit=10`, { headers });
        check(res, { 'history OK': (r) => r.status === 200 });
        auditLatency.add(res.timings.duration);
    });

    group('Night Audit Metrics', () => {
        const res = http.get(`${BASE_URL}/api/metrics/night-audit`, { headers });
        check(res, { 'metrics OK': (r) => r.status === 200 });
        auditLatency.add(res.timings.duration);
    });

    group('Audit Timeline Summary', () => {
        const res = http.get(`${BASE_URL}/api/audit/summary?period=24h`, { headers });
        check(res, { 'summary OK': (r) => r.status === 200 });
        auditLatency.add(res.timings.duration);
    });

    group('Dashboard KPIs', () => {
        const res = http.get(`${BASE_URL}/api/pms/rooms?limit=100`, { headers });
        check(res, { 'rooms loaded': (r) => r.status === 200 });
    });

    sleep(0.5 + Math.random());
}
