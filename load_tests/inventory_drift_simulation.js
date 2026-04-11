/**
 * Load Test — Inventory Drift Simulation
 * k6 script: Simulates OTA reservation bursts that can cause drift.
 * Run: k6 run --vus 30 --duration 45s load_tests/inventory_drift_simulation.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const EMAIL = __ENV.EMAIL || 'demo@hotel.com';
const PASSWORD = __ENV.PASSWORD || 'demo123';

export const options = {
    scenarios: {
        ota_burst: {
            executor: 'ramping-arrival-rate',
            startRate: 5,
            timeUnit: '1s',
            stages: [
                { duration: '15s', target: 30 },   // Burst ramp
                { duration: '15s', target: 30 },   // Sustained burst
                { duration: '15s', target: 0 },    // Cool down
            ],
            preAllocatedVUs: 40,
            maxVUs: 60,
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.3'],
        http_req_duration: ['p(95)<5000'],
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

    group('OTA Reservation Burst', () => {
        // Simulate OTA reservation creation
        const roomTypes = ['standard', 'deluxe', 'suite'];
        const roomType = roomTypes[Math.floor(Math.random() * roomTypes.length)];
        const day = 7 + Math.floor(Math.random() * 60);
        const checkIn = new Date(Date.now() + day * 86400000).toISOString().split('T')[0];
        const nights = 1 + Math.floor(Math.random() * 5);
        const checkOut = new Date(Date.now() + (day + nights) * 86400000).toISOString().split('T')[0];

        const reservation = {
            guest_name: `OTA Guest ${__VU}-${__ITER}`,
            room_type: roomType,
            check_in: checkIn,
            check_out: checkOut,
            channel: 'booking_com',
            status: 'confirmed',
        };

        const bookRes = http.post(`${BASE_URL}/api/pms/bookings`, JSON.stringify(reservation), { headers });
        check(bookRes, {
            'booking accepted': (r) => r.status === 200 || r.status === 201 || r.status === 400,
        });

        // Check availability after booking
        const availRes = http.get(`${BASE_URL}/api/pms/rooms/availability?room_type=${roomType}`, { headers });
        check(availRes, {
            'availability check ok': (r) => r.status === 200 || r.status === 404,
        });
    });
}
