/**
 * k6 Load Test — POS/F&B Burst
 * Simulates restaurant peak hour: concurrent order reads, KDS polling, inventory checks.
 * Measures: order processing latency, KDS refresh time, stock read speed
 * Run: k6 run load_tests/pos_fnb_burst.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

const posErrors = new Rate('pos_errors');
const posLatency = new Trend('pos_latency_ms');

export const options = {
    scenarios: {
        lunch_rush: {
            executor: 'ramping-vus',
            startVUs: 5,
            stages: [
                { duration: '10s', target: 20 },
                { duration: '20s', target: 50 },
                { duration: '10s', target: 5 },
            ],
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<2500'],
        pos_errors: ['rate<0.10'],
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

    group('FnB Dashboard', () => {
        const res = http.get(`${BASE_URL}/api/fnb/dashboard`, { headers });
        check(res, { 'fnb dash OK': (r) => r.status === 200 });
        posErrors.add(res.status !== 200);
        posLatency.add(res.timings.duration);
    });

    group('Active Orders', () => {
        const res = http.get(`${BASE_URL}/api/pos/mobile/active-orders`, { headers });
        check(res, { 'active orders OK': (r) => r.status === 200 });
        posLatency.add(res.timings.duration);
    });

    group('KDS Kitchen Display', () => {
        const res = http.get(`${BASE_URL}/api/pos/kds/kitchen-display`, { headers });
        check(res, { 'kds OK': (r) => r.status === 200 });
        posLatency.add(res.timings.duration);
    });

    group('Stock Levels', () => {
        const res = http.get(`${BASE_URL}/api/pos/mobile/stock-levels`, { headers });
        check(res, { 'stock OK': (r) => r.status === 200 });
        posLatency.add(res.timings.duration);
    });

    group('Low Stock Alerts', () => {
        const res = http.get(`${BASE_URL}/api/pos/mobile/low-stock-alerts`, { headers });
        check(res, { 'alerts OK': (r) => r.status === 200 });
        posLatency.add(res.timings.duration);
    });

    sleep(0.3 + Math.random() * 0.7);
}
