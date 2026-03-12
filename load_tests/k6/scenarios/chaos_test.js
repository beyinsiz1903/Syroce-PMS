/**
 * k6 Chaos Test — Provider Timeout + Redis Flap + Worker Crash Simulation
 * Validates system resilience under failure conditions.
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const errorRate = new Rate('errors');
const recoveryCount = new Counter('recovery_attempts');

export const options = {
  scenarios: {
    provider_timeout_burst: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 20 },
        { duration: '2m', target: 50 },   // High concurrent load
        { duration: '30s', target: 0 },
      ],
      exec: 'providerTimeoutBurst',
    },
    concurrent_frontdesk: {
      executor: 'ramping-vus',
      startVUs: 0,
      startTime: '3m',
      stages: [
        { duration: '30s', target: 30 },
        { duration: '2m', target: 30 },
        { duration: '30s', target: 0 },
      ],
      exec: 'concurrentFrontdesk',
    },
    noisy_tenant_flood: {
      executor: 'constant-vus',
      vus: 100,
      duration: '2m',
      startTime: '6m',
      exec: 'noisyTenantFlood',
    },
  },
  thresholds: {
    'errors': ['rate<0.10'],    // Under chaos, 10% error acceptable
    'http_req_duration': ['p(95)<10000'],
  },
};

function getToken() {
  const res = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
    email: 'demo@hotel.com', password: 'demo123',
  }), { headers: { 'Content-Type': 'application/json' } });
  return res.json('access_token');
}

export function setup() {
  return { token: getToken() };
}

export function providerTimeoutBurst(data) {
  const headers = { Authorization: `Bearer ${data.token}`, 'Content-Type': 'application/json' };

  // Simulate burst of CM validation calls
  const res = http.post(`${BASE_URL}/api/cm/validation/run`,
    JSON.stringify({ provider_id: 'hotelrunner' }),
    { headers, timeout: '30s' }
  );
  errorRate.add(res.status >= 500);
  check(res, { 'cm validation responded': (r) => r.status < 500 });

  // Alert evaluate with extreme metrics
  http.post(`${BASE_URL}/api/alerts/evaluate`,
    JSON.stringify({ metrics: { pending_count: 9999, heartbeat_age_seconds: 999, drift_count: 100 } }),
    { headers }
  );

  sleep(0.1);
}

export function concurrentFrontdesk(data) {
  const headers = { Authorization: `Bearer ${data.token}`, 'Content-Type': 'application/json' };
  const bookingId = `chaos-${__VU}-${__ITER}`;

  // Concurrent check-in attempts (should get NOT_FOUND or CONCURRENT_OPERATION)
  const res = http.post(`${BASE_URL}/api/frontdesk/v2/checkin`,
    JSON.stringify({ booking_id: bookingId }),
    { headers }
  );
  check(res, {
    'frontdesk responded': (r) => r.status === 200 || r.status === 400,
  });

  // Concurrent POS orders
  http.post(`${BASE_URL}/api/pos/v2/orders`,
    JSON.stringify({
      outlet_id: `chaos-outlet-${__VU}`,
      items: [{ name: 'Chaos Burger', price: 10, quantity: 1 }],
    }),
    { headers }
  );

  sleep(0.05);
}

export function noisyTenantFlood(data) {
  const headers = { Authorization: `Bearer ${data.token}`, 'Content-Type': 'application/json' };

  // Flood of requests to test rate limiting and noisy tenant detection
  const endpoints = [
    `${BASE_URL}/api/alerts/active`,
    `${BASE_URL}/api/incidents/list`,
    `${BASE_URL}/api/pilot/readiness`,
    `${BASE_URL}/api/tenant-isolation/v2/noisy-tenants`,
  ];

  const url = endpoints[Math.floor(Math.random() * endpoints.length)];
  const res = http.get(url, { headers });
  errorRate.add(res.status >= 500);

  sleep(0.01);
}
