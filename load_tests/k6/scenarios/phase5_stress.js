/**
 * k6 Stress Test — Phase 5 endpoints
 * Concurrent front desk mutations, POS bursts, alert evaluation storms.
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const errorRate = new Rate('errors');
const p95Latency = new Trend('p95_latency');

export const options = {
  scenarios: {
    frontdesk_stress: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 200,
      stages: [
        { duration: '1m', target: 20 },   // Ramp to 20 rps
        { duration: '3m', target: 50 },   // Push to 50 rps
        { duration: '1m', target: 100 },  // Spike to 100 rps
        { duration: '30s', target: 0 },
      ],
      exec: 'frontdeskStress',
    },
    pos_burst: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 30,
      maxVUs: 100,
      startTime: '5m',
      stages: [
        { duration: '1m', target: 30 },
        { duration: '2m', target: 80 },
        { duration: '30s', target: 0 },
      ],
      exec: 'posBurst',
    },
    alert_storm: {
      executor: 'constant-arrival-rate',
      rate: 20,
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 20,
      maxVUs: 50,
      startTime: '8m',
      exec: 'alertStorm',
    },
  },
  thresholds: {
    'errors': ['rate<0.05'],
    'http_req_duration': ['p(95)<5000'],
    'p95_latency': ['p(95)<3000'],
  },
};

function getToken() {
  const res = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
    email: 'demo@hotel.com', password: 'demo123',
  }), { headers: { 'Content-Type': 'application/json' } });
  return res.json('access_token');
}

export function setup() { return { token: getToken() }; }

export function frontdeskStress(data) {
  const headers = { Authorization: `Bearer ${data.token}`, 'Content-Type': 'application/json' };
  const actions = [
    () => http.post(`${BASE_URL}/api/frontdesk/v2/checkin`,
      JSON.stringify({ booking_id: `stress-${__VU}-${__ITER}` }), { headers }),
    () => http.post(`${BASE_URL}/api/frontdesk/v2/no-show`,
      JSON.stringify({ booking_id: `stress-${__VU}-${__ITER}` }), { headers }),
    () => http.post(`${BASE_URL}/api/frontdesk/v2/walk-in`,
      JSON.stringify({
        guest_name: `Stress Guest ${__VU}`,
        room_id: `stress-room-${__VU}`,
        nights: 1,
        rate_amount: 100,
      }), { headers }),
  ];
  const fn = actions[Math.floor(Math.random() * actions.length)];
  const start = Date.now();
  const res = fn();
  p95Latency.add(Date.now() - start);
  errorRate.add(res.status >= 500);
  check(res, { 'no 5xx': (r) => r.status < 500 });
}

export function posBurst(data) {
  const headers = { Authorization: `Bearer ${data.token}`, 'Content-Type': 'application/json' };
  const res = http.post(`${BASE_URL}/api/pos/v2/orders`,
    JSON.stringify({
      outlet_id: `stress-outlet-${__VU % 5}`,
      items: [
        { name: 'Steak', price: 120, quantity: 1 },
        { name: 'Wine', price: 80, quantity: 2 },
      ],
      guest_name: `POS Guest ${__VU}`,
    }), { headers });
  p95Latency.add(Date.now());
  errorRate.add(res.status >= 500);
  check(res, { 'order created or validated': (r) => r.status < 500 });
}

export function alertStorm(data) {
  const headers = { Authorization: `Bearer ${data.token}`, 'Content-Type': 'application/json' };
  const metrics = {
    pending_count: Math.random() * 2000,
    heartbeat_age_seconds: Math.random() * 300,
    drift_count: Math.random() * 50,
    failure_count: Math.random() * 20,
    rate_limit_hits: Math.random() * 200,
  };
  http.post(`${BASE_URL}/api/alerts/evaluate`,
    JSON.stringify({ metrics }), { headers });
  http.get(`${BASE_URL}/api/alerts/active`, { headers });
  http.get(`${BASE_URL}/api/alerts/summary?hours=1`, { headers });
}
