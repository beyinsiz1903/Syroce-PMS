/**
 * Load Test — Night Audit Load
 * k6 script: Simulates concurrent night audit operations across tenants.
 * Run: k6 run --vus 10 --duration 30s load_tests/night_audit_load.js
 */
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const EMAIL = __ENV.EMAIL || 'demo@hotel.com';
const PASSWORD = __ENV.PASSWORD || 'demo123';

export const options = {
    scenarios: {
        night_audit: {
            executor: 'per-vu-iterations',
            vus: 10,
            iterations: 3,
            maxDuration: '2m',
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.3'],
        http_req_duration: ['p(95)<10000'],
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

    // Step 1: Get dashboard KPIs (read-heavy)
    const dashRes = http.get(`${BASE_URL}/api/pms/rooms?limit=100`, { headers });
    check(dashRes, { 'rooms loaded': (r) => r.status === 200 });

    // Step 2: Get today's arrivals
    const today = new Date().toISOString().split('T')[0];
    const arrivalsRes = http.get(`${BASE_URL}/api/frontdesk/arrivals/${today}`, { headers });
    check(arrivalsRes, { 'arrivals loaded': (r) => r.status === 200 || r.status === 404 });

    // Step 3: Get housekeeping status
    const hkRes = http.get(`${BASE_URL}/api/housekeeping/tasks?limit=50`, { headers });
    check(hkRes, { 'housekeeping loaded': (r) => r.status === 200 });

    sleep(1);
}
