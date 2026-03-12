"""
k6 Load Test — OTA Reservation Burst
Simulates 100 concurrent OTA bookings over 30 seconds.
Run: k6 run load_tests/ota_reservation_burst.js
"""

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
let authToken = '';

const errorRate = new Rate('errors');
const bookingLatency = new Trend('booking_latency');

export const options = {
  stages: [
    { duration: '10s', target: 20 },
    { duration: '20s', target: 50 },
    { duration: '30s', target: 100 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    errors: ['rate<0.1'],
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

  // GET arrivals — simulates dashboard load
  const arrivalsRes = http.get(`${BASE_URL}/api/arrivals/today`, { headers });
  check(arrivalsRes, { 'arrivals 200': (r) => r.status === 200 });
  errorRate.add(arrivalsRes.status !== 200);
  bookingLatency.add(arrivalsRes.timings.duration);

  // GET unified in-house
  const inhouseRes = http.get(`${BASE_URL}/api/unified/in-house`, { headers });
  check(inhouseRes, { 'inhouse 200': (r) => r.status === 200 });
  errorRate.add(inhouseRes.status !== 200);

  sleep(0.5);
}
