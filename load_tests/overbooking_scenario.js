/**
 * Load Test — Overbooking Scenario
 * k6 script: Simulates concurrent booking attempts.
 * Run: k6 run --vus 50 --duration 30s load_tests/overbooking_scenario.js
 */
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const EMAIL = __ENV.EMAIL || 'demo@hotel.com';
const PASSWORD = __ENV.PASSWORD || 'demo123';

export const options = {
    scenarios: {
        overbooking_burst: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '10s', target: 50 },   // Ramp up
                { duration: '30s', target: 50 },   // Sustained load
                { duration: '10s', target: 0 },    // Ramp down
            ],
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.5'],
        http_req_duration: ['p(95)<3000'],
    },
};

let token = null;

export function setup() {
    const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
        email: EMAIL, password: PASSWORD,
    }), { headers: { 'Content-Type': 'application/json' } });

    const body = JSON.parse(loginRes.body);
    return { token: body.access_token };
}

export default function (data) {
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${data.token}`,
    };

    // Try to create a booking
    const booking = {
        guest_id: `loadtest-guest-${__VU}`,
        room_id: 'load-test-room',
        check_in: '2026-06-01',
        check_out: '2026-06-02',
        status: 'confirmed',
    };

    const res = http.post(`${BASE_URL}/api/pms/bookings`, JSON.stringify(booking), { headers });

    check(res, {
        'status is 200 or 409': (r) => r.status === 200 || r.status === 409,
        'response time < 2s': (r) => r.timings.duration < 2000,
    });

    sleep(0.5);
}
