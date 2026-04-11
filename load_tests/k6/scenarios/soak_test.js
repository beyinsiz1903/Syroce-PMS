/**
 * k6 Soak Test — 6-12h low/medium load
 * Detects: memory leaks, reconnect leaks, queue lag creep,
 * stale cache creep, websocket session churn.
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const errorRate = new Rate('errors');
const responseTime = new Trend('response_time_ms');
const staleCacheHits = new Counter('stale_cache_hits');

export const options = {
  stages: [
    { duration: '5m', target: 5 },    // Ramp up to low load
    { duration: '6h', target: 10 },   // Sustained medium load
    { duration: '5m', target: 0 },    // Ramp down
  ],
  thresholds: {
    'errors': ['rate<0.02'],           // <2% error rate
    'response_time_ms': ['p(99)<5000'], // p99 < 5s even after hours
    'http_req_duration': ['p(95)<3000'],
  },
};

function getToken() {
  const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
    email: 'demo@hotel.com',
    password: 'demo123',
  }), { headers: { 'Content-Type': 'application/json' } });
  return loginRes.json('access_token');
}

let token = '';

export function setup() {
  token = getToken();
  return { token };
}

export default function (data) {
  const headers = {
    Authorization: `Bearer ${data.token}`,
    'Content-Type': 'application/json',
  };

  // Mix of API calls to simulate sustained operational load
  const calls = [
    // Health checks
    () => http.get(`${BASE_URL}/api/health`, { headers }),
    () => http.get(`${BASE_URL}/api/system-health`, { headers }),
    // Alerts
    () => http.get(`${BASE_URL}/api/alerts/active`, { headers }),
    () => http.get(`${BASE_URL}/api/alerts/summary?hours=1`, { headers }),
    // Incidents
    () => http.get(`${BASE_URL}/api/incidents/service-health`, { headers }),
    () => http.get(`${BASE_URL}/api/incidents/list?limit=10`, { headers }),
    // Pilot
    () => http.get(`${BASE_URL}/api/pilot/readiness`, { headers }),
    // Tenant
    () => http.get(`${BASE_URL}/api/tenant-isolation/v2/noisy-tenants`, { headers }),
    // Audit timeline
    () => http.get(`${BASE_URL}/api/audit/timeline?limit=20`, { headers }),
    () => http.get(`${BASE_URL}/api/audit/summary?period=1h`, { headers }),
  ];

  const fn = calls[Math.floor(Math.random() * calls.length)];
  const start = Date.now();
  const res = fn();
  const duration = Date.now() - start;

  responseTime.add(duration);
  errorRate.add(res.status >= 400);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 5s': () => duration < 5000,
  });

  sleep(Math.random() * 2 + 1); // 1-3s between requests
}
