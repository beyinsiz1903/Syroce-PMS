"""
k6 Load Test — System Health Dashboard
Simulates 50 concurrent users polling the health dashboard.
Run: k6 run load_tests/system_health_dashboard_load.js
"""

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

const errorRate = new Rate('errors');
const dashboardLatency = new Trend('dashboard_latency');

export const options = {
  stages: [
    { duration: '10s', target: 10 },
    { duration: '30s', target: 50 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    errors: ['rate<0.05'],
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

export default function(data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  // Role-based dashboard
  const roleRes = http.get(`${BASE_URL}/api/system-health/role-dashboard`, { headers });
  check(roleRes, { 'role-dashboard 200': (r) => r.status === 200 });
  dashboardLatency.add(roleRes.timings.duration);
  errorRate.add(roleRes.status !== 200);

  // Normalized overview
  const overviewRes = http.get(`${BASE_URL}/api/system-health/normalized/overview`, { headers });
  check(overviewRes, { 'normalized-overview 200': (r) => r.status === 200 });
  dashboardLatency.add(overviewRes.timings.duration);
  errorRate.add(overviewRes.status !== 200);

  // Security check
  const secRes = http.get(`${BASE_URL}/api/system-health/normalized/security`, { headers });
  check(secRes, { 'security 200': (r) => r.status === 200 });
  errorRate.add(secRes.status !== 200);

  // Workers check
  const wkRes = http.get(`${BASE_URL}/api/system-health/normalized/workers`, { headers });
  check(wkRes, { 'workers 200': (r) => r.status === 200 });
  errorRate.add(wkRes.status !== 200);

  sleep(1);
}
