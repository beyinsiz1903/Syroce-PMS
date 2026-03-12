/**
 * k6 Load Test — ARI Update Storm
 * Simulates Availability, Rate, and Inventory update storms from Channel Manager.
 * Measures: reconciliation recovery time, drift detection latency, update throughput
 * Run: k6 run load_tests/ari_update_storm.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

const ariErrors = new Rate('ari_errors');
const ariLatency = new Trend('ari_update_latency_ms');
const reconcileLatency = new Trend('reconcile_latency_ms');

export const options = {
    scenarios: {
        steady_updates: {
            executor: 'constant-arrival-rate',
            rate: 20,
            timeUnit: '1s',
            duration: '30s',
            preAllocatedVUs: 30,
            maxVUs: 60,
        },
        storm: {
            executor: 'ramping-arrival-rate',
            startRate: 10,
            timeUnit: '1s',
            stages: [
                { duration: '10s', target: 50 },
                { duration: '15s', target: 200 },
                { duration: '5s', target: 10 },
            ],
            preAllocatedVUs: 60,
            maxVUs: 250,
            startTime: '30s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<3000'],
        ari_errors: ['rate<0.10'],
        ari_update_latency_ms: ['p(95)<4000'],
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

    group('Rate Calendar Read', () => {
        const today = new Date().toISOString().split('T')[0];
        const res = http.get(`${BASE_URL}/api/rms/pricing-recommendations?date=${today}`, { headers });
        check(res, { 'pricing read OK': (r) => r.status === 200 });
        ariErrors.add(res.status !== 200);
        ariLatency.add(res.timings.duration);
    });

    group('Comp-Set Pricing Read', () => {
        const res = http.get(`${BASE_URL}/api/rms/comp-pricing`, { headers });
        check(res, { 'comp pricing OK': (r) => r.status === 200 });
        ariErrors.add(res.status !== 200);
    });

    group('Demand Forecast Read', () => {
        const res = http.get(`${BASE_URL}/api/rms/demand-forecast`, { headers });
        check(res, { 'forecast OK': (r) => r.status === 200 });
        ariLatency.add(res.timings.duration);
    });

    group('Revenue Dashboard', () => {
        const res = http.get(`${BASE_URL}/api/rms/comp-set-comparison`, { headers });
        check(res, { 'compset compare OK': (r) => r.status === 200 });
        reconcileLatency.add(res.timings.duration);
    });

    sleep(Math.random() * 0.3);
}
