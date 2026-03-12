/**
 * Load Test — Rate Update Storm
 * k6 script: Simulates high-frequency ARI (Availability/Rates/Inventory) updates.
 * Run: k6 run --vus 20 --duration 60s load_tests/rate_update_storm.js
 */
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const EMAIL = __ENV.EMAIL || 'demo@hotel.com';
const PASSWORD = __ENV.PASSWORD || 'demo123';

export const options = {
    scenarios: {
        rate_storm: {
            executor: 'constant-arrival-rate',
            rate: 100,              // 100 iterations/second
            timeUnit: '1s',
            duration: '60s',
            preAllocatedVUs: 30,
            maxVUs: 50,
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.1'],
        http_req_duration: ['p(99)<5000'],
    },
};

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

    const roomTypes = ['standard', 'deluxe', 'suite', 'superior', 'family'];
    const roomType = roomTypes[Math.floor(Math.random() * roomTypes.length)];
    const rate = 100 + Math.random() * 500;
    const day = Math.floor(Math.random() * 365);
    const dateStr = new Date(Date.now() + day * 86400000).toISOString().split('T')[0];

    const rateUpdate = {
        room_type: roomType,
        date: dateStr,
        rate: Math.round(rate * 100) / 100,
        currency: 'TRY',
    };

    const res = http.post(`${BASE_URL}/api/channel-manager/ari-update`, JSON.stringify(rateUpdate), { headers });

    check(res, {
        'rate update accepted': (r) => r.status === 200 || r.status === 201,
        'fast response': (r) => r.timings.duration < 1000,
    });
}
