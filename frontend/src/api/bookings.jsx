// frontend/src/api/bookings.js

const DEFAULT_BASE_URL =
  (typeof process !== "undefined" && process.env && import.meta.env.VITE_BACKEND_URL) ||
  "";

function _joinUrl(baseUrl, path) {
  const b = (baseUrl || "").replace(/\/+$/, "");
  const p = (path || "").startsWith("/") ? path : `/${path}`;
  return `${b}${p}`;
}

async function _fetchJson(url, { method = "GET", token, body } = {}) {
  const headers = {
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  // Try to parse JSON but don't hard-fail if response isn't JSON
  let data = null;
  const text = await res.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }

  if (!res.ok) {
    const msg =
      (data && (data.detail || data.message || data.error)) ||
      `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    err.data = data;
    throw err;
  }

  return data;
}

/**
 * List pending bookings.
 * Assumption: GET /api/bookings?status=pending
 * If your backend path differs, only change this one line.
 */
export async function listPendingBookings({ baseUrl = DEFAULT_BASE_URL, token } = {}) {
  const url = _joinUrl(baseUrl, "/api/bookings?status=pending");
  return _fetchJson(url, { method: "GET", token });
}

export async function approveBooking({ baseUrl = DEFAULT_BASE_URL, token, bookingId }) {
  const url = _joinUrl(baseUrl, `/api/bookings/${encodeURIComponent(bookingId)}/approve`);
  return _fetchJson(url, { method: "POST", token });
}

export async function rejectBooking({
  baseUrl = DEFAULT_BASE_URL,
  token,
  bookingId,
  reason_code,
  reason_note,
}) {
  const url = _joinUrl(baseUrl, `/api/bookings/${encodeURIComponent(bookingId)}/reject`);
  return _fetchJson(url, {
    method: "POST",
    token,
    body: { reason_code, reason_note },
  });
}
