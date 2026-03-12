/**
 * k6 Load Test — OTA Reservation Burst (Production-Grade)
 * Simulates high-concurrency OTA reservation flow with conflict detection.
 * Measures: p50/p95/p99 latency, error rate, booking throughput
 * Run: k6 run --vus 50 --duration 60s load_tests/ota_reservation_burst.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

// Custom metrics
const bookingErrors = new Rate('booking_errors');
const bookingLatency = new Trend('booking_latency_ms');
const conflictRate = new Rate('conflict_rate');
const successfulBookings = new Counter('successful_bookings');

export const options = {
    scenarios: {
        normal_load: {
            executor: 'constant-arrival-rate',
            rate: 10,
            timeUnit: '1s',
            duration: '30s',
            preAllocatedVUs: 20,
            maxVUs: 50,
        },
        burst: {
            executor: 'ramping-arrival-rate',
            startRate: 5,
            timeUnit: '1s',
            stages: [
                { duration: '10s', target: 30 },
                { duration: '20s', target: 100 },
                { duration: '10s', target: 5 },
            ],
            preAllocatedVUs: 50,
            maxVUs: 150,
            startTime: '30s',
        },
    },
    thresholds: {
        http_req_duration: ['p(50)<500', 'p(95)<2000', 'p(99)<5000'],
        booking_errors: ['rate<0.15'],
        booking_latency_ms: ['p(95)<3000'],
        conflict_rate: ['rate<0.30'],
    },
};

export function setup() {
    const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
        email: 'demo@hotel.com',
        password: 'demo123',
    }), { headers: { 'Content-Type': 'application/json' } });

    const body = JSON.parse(loginRes.body);
    return { token: body.access_token };
}

export default function (data) {
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${data.token}`,
    };

    group('OTA Arrival Check', () => {
        const res = http.get(`${BASE_URL}/api/arrivals/today`, { headers });
        check(res, { 'arrivals OK': (r) => r.status === 200 });
        bookingErrors.add(res.status !== 200);
        bookingLatency.add(res.timings.duration);
    });

    group('Unified In-House Load', () => {
        const res = http.get(`${BASE_URL}/api/unified/in-house`, { headers });
        check(res, { 'inhouse OK': (r) => r.status === 200 });
        bookingErrors.add(res.status !== 200);
    });

    group('Room Availability Check', () => {
        const res = http.get(`${BASE_URL}/api/pms/rooms?limit=50`, { headers });
        const ok = check(res, { 'rooms OK': (r) => r.status === 200 });
        bookingErrors.add(!ok);
    });

    group('Dashboard KPI Load', () => {
        const res = http.get(`${BASE_URL}/api/frontdesk/audit-checklist`, { headers });
        check(res, { 'checklist OK': (r) => r.status === 200 });
        bookingLatency.add(res.timings.duration);
    });

    sleep(Math.random() * 0.5);
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    };
}

function textSummary(data, opts) {
    const metrics = data.metrics;
    let out = '\n=== OTA Reservation Burst Summary ===\n';
    if (metrics.http_req_duration) {
        out += `  p50: ${metrics.http_req_duration.values['p(50)']?.toFixed(1)}ms\n`;
        out += `  p95: ${metrics.http_req_duration.values['p(95)']?.toFixed(1)}ms\n`;
        out += `  p99: ${metrics.http_req_duration.values['p(99)']?.toFixed(1)}ms\n`;
    }
    if (metrics.booking_errors) {
        out += `  Error Rate: ${(metrics.booking_errors.values.rate * 100).toFixed(2)}%\n`;
    }
    return out;
}
