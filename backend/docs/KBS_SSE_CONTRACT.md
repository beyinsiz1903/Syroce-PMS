# KBS Queue SSE Contract — `GET /api/kbs/queue/stream`

> **Status:** Stable (v1) — published 2026-04-26.
> **Audience:** the Windows desktop KBS agent (and any future automated
> consumer of the KBS bildirim queue).
>
> This document is the source of truth. The agent team builds against
> this contract; the backend team treats any breaking change as a
> versioned rollout (`v2` endpoint side-by-side with `v1`).

---

## 1. Purpose

Replace polling of `GET /api/kbs/queue?status=pending` with a push-based
notification stream so the agent can react to a new check-in/check-out
job within ~hundreds of milliseconds instead of one polling interval.

The stream is a **notification channel only** — payloads are
intentionally minimal. The agent always uses the existing REST
endpoints (`GET /queue`, `POST /queue/{id}/claim`, …) to fetch full job
details and to perform state transitions.

---

## 2. Endpoint

```
GET /api/kbs/queue/stream
Host:           <backend>
Authorization:  Bearer <jwt>
Accept:         text/event-stream
```

- **Auth:** the same JWT used for every other `/api/kbs/*` call
  (operator session token). The user must have the `view_reports`
  permission. `tenant_id` is derived from the token; do **not** send
  it as a query parameter — the backend ignores it.
- **Multi-tenant safety:** the stream is scoped to a single tenant.
  An agent installed at Hotel A can never receive Hotel B's events,
  even if both hotels share a backend.
- **Response:** `200 OK` with `Content-Type: text/event-stream` and a
  long-lived chunked response.

### 2.1 Response headers

| Header              | Value                  | Why                              |
|---------------------|------------------------|----------------------------------|
| `Content-Type`      | `text/event-stream`    | SSE media type.                  |
| `Cache-Control`     | `no-cache, no-transform` | Defeat proxy caches.           |
| `X-Accel-Buffering` | `no`                   | Disable nginx response buffering.|
| `Connection`        | `keep-alive`           | Keep the TCP socket open.        |

---

## 3. Event types

Every event uses the standard SSE framing:

```
event: <type>
data: <JSON>
\n
```

### 3.1 `ready`

Sent **once** immediately after the connection is accepted. Lets the
client confirm the stream is alive without waiting up to 25 s for the
first heartbeat.

```json
{
  "instance": "ip-10-0-1-5-pid-12345",
  "ts": "2026-04-26T08:00:00.123456+00:00",
  "heartbeat_seconds": 25.0
}
```

### 3.2 `job.available`

A new job is ready to claim **right now**. Emitted on a fresh
`POST /api/kbs/queue` enqueue (status `pending`, no `next_retry_at`).

Retried jobs do **not** emit `job.available`; they emit
`job.retry_scheduled` (§ 3.5) at fail time so the agent knows the
exact moment they become claimable.

```json
{
  "type": "job.available",
  "tenant_id": "<tenant-uuid>",
  "job_id": "<queue-job-uuid>",
  "booking_id": "<booking-uuid>",
  "action": "checkin",
  "ts": "2026-04-26T08:00:01.456789+00:00",
  "instance": "ip-10-0-1-5-pid-12345"
}
```

> **Important:** the agent must still call
> `POST /api/kbs/queue/{job_id}/claim` to lease the job — the SSE
> notification is informational only and multiple agents may receive
> the same `job.available` event simultaneously. The claim endpoint
> is the single source of truth (atomic CAS on Mongo) and only one
> claim succeeds.

### 3.3 `job.completed`

Another worker (could be another agent instance for the same hotel,
or the same instance after a restart) reported success.

```json
{
  "type": "job.completed",
  "tenant_id": "<tenant-uuid>",
  "job_id": "<queue-job-uuid>",
  "booking_id": "<booking-uuid>",
  "action": "checkin",
  "ts": "2026-04-26T08:00:05.987654+00:00",
  "instance": "ip-10-0-1-5-pid-12345"
}
```

UI hint: drop this `job_id` from any local "to do" list.

### 3.4 `job.failed`

The job moved to terminal `dead` state (retries exhausted or
non-retryable). UI hint: surface this to the operator for manual
follow-up.

```json
{
  "type": "job.failed",
  "tenant_id": "<tenant-uuid>",
  "job_id": "<queue-job-uuid>",
  "booking_id": "<booking-uuid>",
  "action": "checkout",
  "ts": "2026-04-26T08:00:10.111111+00:00",
  "instance": "ip-10-0-1-5-pid-12345"
}
```

### 3.5 `job.retry_scheduled`

A previously-claimed job was reported as `fail` with `retry=true`,
the queue moved it back to `pending`, and **the next claim attempt
will only succeed at or after `next_retry_at`** (exponential
back-off). The agent uses this event to schedule a delayed local
reconcile/claim — emitting `job.available` here would be wrong
because the job is server-blocked from claiming until `next_retry_at`
and any immediate `POST /claim` would race-lose with HTTP 409.

```json
{
  "type": "job.retry_scheduled",
  "tenant_id": "<tenant-uuid>",
  "job_id": "<queue-job-uuid>",
  "booking_id": "<booking-uuid>",
  "action": "checkin",
  "next_retry_at": "2026-04-26T08:00:40.000000+00:00",
  "attempts": 1,
  "max_attempts": 5,
  "ts": "2026-04-26T08:00:35.000000+00:00",
  "instance": "ip-10-0-1-5-pid-12345"
}
```

Recommended agent behaviour:

```
delay = max(0, next_retry_at - now)
schedule_after(delay, lambda: try_claim(job_id))
```

If the agent process restarts before `next_retry_at` it can
rediscover the job via the standard `GET /queue?status=pending`
reconcile call — that endpoint already filters out
`next_retry_at > now`, so a too-early claim is impossible.

### 3.6 `heartbeat`

Sent every **25 seconds** when no other event has been emitted. Use it
as a liveness signal: if the agent has not received any frame
(heartbeat or otherwise) for **>60 s**, close the socket and
reconnect.

```json
{ "ts": "2026-04-26T08:00:25.000000+00:00" }
```

### 3.7 `server_rotate`

Sent when the server-side max stream age (6 hours) is reached. The
agent should reconnect immediately. This exists so long-running agents
periodically refresh their JWT and re-establish a clean state.

```json
{ "reason": "max_stream_age" }
```

---

## 4. Reconnect strategy

SSE has no built-in replay in this implementation (no `Last-Event-ID`
header support yet). On any disconnect — network blip, reverse-proxy
timeout, the 6-hour `server_rotate`, the operator locking the laptop
overnight — the agent should:

1. Wait `min(2^attempt, 30) * jitter(0.5..1.5)` seconds (exponential
   back-off with jitter).
2. Reopen `GET /api/kbs/queue/stream`.
3. **Reconcile**: immediately call
   `GET /api/kbs/queue?status=pending` and process anything newer than
   the last `job_id` already handled. This recovers events that were
   dropped during the disconnect window.

The reconcile call is cheap (≈1 RTT to MongoDB) and is the explicit
trade-off for a dead-simple stream — we never persist event backlogs
on the server.

---

## 5. Concurrency & idempotency

- Multiple agents per tenant are supported. Every connected agent
  receives every event for that tenant.
- `claim`, `complete`, and `fail` already use atomic CAS plus
  `Idempotency-Key` headers — the SSE layer adds no new concurrency
  guarantees and assumes the agent uses those endpoints correctly.
- Backpressure: each subscriber has a 256-event in-memory buffer on
  the backend. If a slow agent fills it, oldest events are dropped to
  keep the publish path non-blocking; the periodic reconcile call
  recovers from this.

---

## 6. Multi-worker correctness

The backend runs multiple uvicorn workers behind a load balancer.
Events published on worker W2 must reach a stream subscriber on worker
W1. This is implemented by the Redis pub/sub bridge in
`backend/infra/kbs_queue_pubsub.py`:

- Channel: `kbs:queue:events`
- Loop guard: each worker tags its own publishes with a unique
  `instance_id` and ignores echoes of its own messages from the
  Redis listener.
- Local fan-out is always done first so a Redis outage degrades the
  stream to single-worker correctness instead of breaking it.

---

## 7. Quick test (curl / EventSource)

```bash
# Replace <jwt> with a real operator token (must have view_reports).
curl -N \
  -H "Authorization: Bearer <jwt>" \
  -H "Accept: text/event-stream" \
  "$CLOUD_DEV_DOMAIN/api/kbs/queue/stream"
```

Expected initial output:

```
event: ready
data: {"instance":"...","ts":"...","heartbeat_seconds":25.0}

event: heartbeat
data: {"ts":"..."}
```

Then enqueue a job in another terminal:

```bash
curl -X POST \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"booking_id":"<booking>","action":"checkin","payload":{...}}' \
  "$CLOUD_DEV_DOMAIN/api/kbs/queue"
```

The first terminal should immediately print:

```
event: job.available
data: {"type":"job.available","tenant_id":"...","job_id":"...", ...}
```

---

## 8. Browser EventSource example

```js
const es = new EventSource("/api/kbs/queue/stream", {
  withCredentials: true,
});
es.addEventListener("ready", e => console.log("ready", JSON.parse(e.data)));
es.addEventListener("job.available", e => {
  const ev = JSON.parse(e.data);
  // fetch full job + claim
});
es.addEventListener("heartbeat", () => { /* reset liveness timer */ });
es.onerror = () => { /* EventSource will auto-reconnect */ };
```

> **Note:** native browser `EventSource` does not support custom
> headers. For the JWT-protected endpoint use either:
> 1. A polyfill that supports headers (`event-source-polyfill`), or
> 2. A short-lived signed query parameter (not implemented here), or
> 3. The desktop agent's HTTP client (preferred — it has full control
>    over headers).

---

## 9. Versioning

This is **v1**. Any breaking change (event payload field rename, new
required field, transport switch to WebSocket) ships at a new path
(`/api/kbs/queue/stream/v2`) and v1 stays available for at least one
agent release cycle. Additive changes (new event types, new optional
payload fields) do **not** require a version bump — the agent must
ignore unknown event types and unknown payload fields.
