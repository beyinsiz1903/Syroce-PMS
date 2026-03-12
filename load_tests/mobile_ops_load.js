/**
 * k6 Load Test — Mobile Ops Load
 * Simulates mobile dashboard usage: GM, frontdesk, housekeeping, maintenance.
 * Measures: notification latency, mobile dashboard freshness, SLA queries
 * Run: k6 run load_tests/mobile_ops_load.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

const mobileErrors = new Rate('mobile_errors');
const mobileLatency = new Trend('mobile_latency_ms');

export const options = {
    scenarios: {
        gm_mobile: {
            executor: 'constant-vus',
            vus: 3,
            duration: '30s',
        },
        frontdesk_mobile: {
            executor: 'constant-vus',
            vus: 5,
            duration: '30s',
        },
        hk_mobile: {
            executor: 'constant-vus',
            vus: 8,
            duration: '30s',
        },
        maintenance_mobile: {
            executor: 'constant-vus',
            vus: 3,
            duration: '30s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<3000'],
        mobile_errors: ['rate<0.10'],
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

    const scenario = __VU % 4;

    if (scenario === 0) {
        group('GM Critical Issues', () => {
            const res = http.get(`${BASE_URL}/api/dashboard/mobile/critical-issues`, { headers });
            check(res, { 'gm issues OK': (r) => r.status === 200 });
            mobileErrors.add(res.status !== 200);
            mobileLatency.add(res.timings.duration);
        });
        group('GM Notifications', () => {
            const res = http.get(`${BASE_URL}/api/notifications/mobile/gm`, { headers });
            check(res, { 'gm notif OK': (r) => r.status === 200 });
            mobileLatency.add(res.timings.duration);
        });
    } else if (scenario === 1) {
        group('FD Early Checkin', () => {
            const res = http.get(`${BASE_URL}/api/frontdesk/mobile/early-checkin-requests`, { headers });
            check(res, { 'early checkin OK': (r) => r.status === 200 });
            mobileErrors.add(res.status !== 200);
            mobileLatency.add(res.timings.duration);
        });
        group('FD Notifications', () => {
            const res = http.get(`${BASE_URL}/api/notifications/mobile/frontdesk`, { headers });
            check(res, { 'fd notif OK': (r) => r.status === 200 });
            mobileLatency.add(res.timings.duration);
        });
    } else if (scenario === 2) {
        group('HK Delayed Rooms', () => {
            const res = http.get(`${BASE_URL}/api/housekeeping/mobile/sla-delayed-rooms`, { headers });
            check(res, { 'hk delayed OK': (r) => r.status === 200 });
            mobileErrors.add(res.status !== 200);
            mobileLatency.add(res.timings.duration);
        });
        group('HK Team Assignments', () => {
            const res = http.get(`${BASE_URL}/api/housekeeping/mobile/team-assignments`, { headers });
            check(res, { 'hk teams OK': (r) => r.status === 200 });
            mobileLatency.add(res.timings.duration);
        });
    } else {
        group('Maint PM Schedule', () => {
            const res = http.get(`${BASE_URL}/api/maintenance/mobile/preventive-maintenance-schedule`, { headers });
            check(res, { 'maint sched OK': (r) => r.status === 200 });
            mobileErrors.add(res.status !== 200);
            mobileLatency.add(res.timings.duration);
        });
        group('Maint SLA Config', () => {
            const res = http.get(`${BASE_URL}/api/maintenance/mobile/sla-configurations`, { headers });
            check(res, { 'sla config OK': (r) => r.status === 200 });
            mobileLatency.add(res.timings.duration);
        });
    }

    sleep(1 + Math.random() * 2);
}
