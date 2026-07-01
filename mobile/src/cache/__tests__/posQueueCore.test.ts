// Unit coverage for the offline-durable POS queue core (Task #361). Runs in
// plain Node via the built-in test runner (see `yarn test:unit` /
// tsconfig.unit.json) — no RN, no render harness. We back the queue with an
// in-memory map that simulates the on-disk store; "kill + restart" is modelled
// by reading the SAME map through a fresh code path after re-(de)serialization.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  POS_QUEUE_KEY,
  decideFromStatus,
  enqueue,
  loadQueue,
  makeIdempotencyKey,
  parseQueue,
  removeFromQueue,
  replayQueue,
  type DurableKV,
  type PosQueueEntry,
  type SendOutcome,
} from '../posQueueCore';

// A disk-like store: a plain Map. Persists across "restarts" because we keep
// the same Map instance — exactly the durability MMKV/AsyncStorage provides.
function memKV(initial?: Map<string, string>): { kv: DurableKV; store: Map<string, string> } {
  const store = initial ?? new Map<string, string>();
  const kv: DurableKV = {
    getItem: async (k) => (store.has(k) ? (store.get(k) as string) : null),
    setItem: async (k, v) => {
      store.set(k, v);
    },
    removeItem: async (k) => {
      store.delete(k);
    },
  };
  return { kv, store };
}

function entry(over: Partial<PosQueueEntry> = {}): PosQueueEntry {
  return {
    id: over.id ?? over.idempotency_key ?? 'id-1',
    type: over.type ?? 'pos_quick_order',
    payload: over.payload ?? { outlet_id: 'o1', items: [{ item_id: 'm1', quantity: 1 }] },
    idempotency_key: over.idempotency_key ?? over.id ?? 'id-1',
    createdAt: over.createdAt ?? 1_700_000_000_000,
  };
}

// ── decideFromStatus: server-authoritative classification ───────────────────
test('decideFromStatus: 2xx and 4xx drop, network/5xx retain', () => {
  assert.equal(decideFromStatus(200), 'drop');
  assert.equal(decideFromStatus(201), 'drop');
  assert.equal(decideFromStatus(400), 'drop');
  assert.equal(decideFromStatus(409), 'drop');
  assert.equal(decideFromStatus(422), 'drop');
  assert.equal(decideFromStatus(0), 'retain_stop'); // network
  assert.equal(decideFromStatus(500), 'retain_stop');
  assert.equal(decideFromStatus(503), 'retain_stop');
});

// ── parseQueue: corruption-safe ─────────────────────────────────────────────
test('parseQueue tolerates null, junk and bad shapes', () => {
  assert.deepEqual(parseQueue(null), []);
  assert.deepEqual(parseQueue('not json'), []);
  assert.deepEqual(parseQueue('{"a":1}'), []);
  assert.deepEqual(parseQueue('[{"id":1}]'), []); // wrong field types
  const good = JSON.stringify([entry({ id: 'a', idempotency_key: 'a' })]);
  assert.equal(parseQueue(good).length, 1);
});

// ── enqueue de-dupes on idempotency_key ─────────────────────────────────────
test('enqueue stores once; a same-key re-enqueue is a no-op', async () => {
  const { kv } = memKV();
  await enqueue(kv, entry({ id: 'k1', idempotency_key: 'k1' }));
  await enqueue(kv, entry({ id: 'k1', idempotency_key: 'k1' })); // duplicate
  const q = await loadQueue(kv);
  assert.equal(q.length, 1);
});

test('removeFromQueue drops by id', async () => {
  const { kv } = memKV();
  await enqueue(kv, entry({ id: 'a', idempotency_key: 'a' }));
  await enqueue(kv, entry({ id: 'b', idempotency_key: 'b' }));
  await removeFromQueue(kv, 'a');
  const q = await loadQueue(kv);
  assert.deepEqual(
    q.map((e) => e.id),
    ['b'],
  );
});

// ── core scenario: offline add → kill → restart + reconnect → sent ONCE ─────
test('offline enqueue survives a restart and replays exactly once', async () => {
  const { store } = memKV();

  // 1) Offline: enqueue through one "session".
  const session1 = memKV(store).kv;
  await enqueue(session1, entry({ id: 'order-1', idempotency_key: 'mob-quick-order-1' }));
  assert.equal(store.get(POS_QUEUE_KEY) !== undefined, true, 'persisted to disk');

  // 2) App killed: drop the in-memory session entirely. The map (= disk)
  //    still holds the entry.
  // 3) Restart + reconnect: a brand-new session reads the SAME disk and replays.
  const session2 = memKV(store).kv;
  const sent: string[] = [];
  const send = async (e: PosQueueEntry): Promise<SendOutcome> => {
    sent.push(e.idempotency_key);
    return { ok: true };
  };
  const report = await replayQueue(session2, send);

  assert.equal(report.dropped, 1);
  assert.deepEqual(sent, ['mob-quick-order-1']);
  assert.equal((await loadQueue(session2)).length, 0, 'queue drained after success');

  // A second replay (e.g. a later reconnect) must NOT re-send — no duplicate.
  const report2 = await replayQueue(session2, send);
  assert.equal(report2.processed, 0);
  assert.deepEqual(sent, ['mob-quick-order-1']);
});

// ── 4xx → dropped from the queue (server-authoritative reject) ──────────────
test('a 4xx reject removes the entry — never replays garbage in a loop', async () => {
  const { kv } = memKV();
  await enqueue(kv, entry({ id: 'bad', idempotency_key: 'bad' }));
  const send = async (): Promise<SendOutcome> => ({ ok: false, status: 422 });
  const report = await replayQueue(kv, send);
  assert.equal(report.dropped, 1);
  assert.equal((await loadQueue(kv)).length, 0);
});

// ── network error → retained, then retried successfully ─────────────────────
test('a network failure retains the entry and a later replay drains it', async () => {
  const { kv } = memKV();
  await enqueue(kv, entry({ id: 'n1', idempotency_key: 'n1' }));

  let online = false;
  const send = async (): Promise<SendOutcome> => (online ? { ok: true } : { ok: false, status: 0 });

  const r1 = await replayQueue(kv, send);
  assert.equal(r1.retained, 1);
  assert.equal(r1.stopped, true);
  assert.equal((await loadQueue(kv)).length, 1, 'kept while offline');

  online = true;
  const r2 = await replayQueue(kv, send);
  assert.equal(r2.dropped, 1);
  assert.equal((await loadQueue(kv)).length, 0, 'drained once back online');
});

// ── replay stops at the first retained entry, preserving FIFO order ──────────
test('replay stops at the first network failure and keeps the tail', async () => {
  const { kv } = memKV();
  await enqueue(kv, entry({ id: 'a', idempotency_key: 'a' }));
  await enqueue(kv, entry({ id: 'b', idempotency_key: 'b' }));
  await enqueue(kv, entry({ id: 'c', idempotency_key: 'c' }));

  // a → ok, b → network (stop), c → never attempted this run.
  const attempted: string[] = [];
  const send = async (e: PosQueueEntry): Promise<SendOutcome> => {
    attempted.push(e.id);
    if (e.id === 'b') return { ok: false, status: 0 };
    return { ok: true };
  };
  const report = await replayQueue(kv, send);
  assert.deepEqual(attempted, ['a', 'b']);
  assert.equal(report.dropped, 1);
  assert.equal(report.retained, 1);
  assert.deepEqual(
    (await loadQueue(kv)).map((e) => e.id),
    ['b', 'c'],
  );
});

// ── exactly-once under a lost response (relies on the stable key) ───────────
test('a committed-but-lost-response retry reuses the key and processes once', async () => {
  const { kv } = memKV();
  const idem = 'mob-quick-lost-1';
  await enqueue(kv, entry({ id: idem, idempotency_key: idem }));

  // Server-side ledger keyed by idempotency_key. First attempt commits but the
  // response is "lost" (we surface a network error). The retry hits the same
  // key → server returns the existing result, no second row.
  const committed = new Set<string>();
  let attempt = 0;
  const send = async (e: PosQueueEntry): Promise<SendOutcome> => {
    attempt += 1;
    committed.add(e.idempotency_key); // server commits (deduped by Set)
    if (attempt === 1) return { ok: false, status: 0 }; // response lost
    return { ok: true }; // dedupe hit on replay
  };

  await replayQueue(kv, send); // attempt 1: retained
  await replayQueue(kv, send); // attempt 2: drained

  assert.equal(committed.size, 1, 'processed exactly once server-side');
  assert.equal((await loadQueue(kv)).length, 0);
});

// ── idempotency key generation ──────────────────────────────────────────────
test('makeIdempotencyKey is unique, typed-prefixed and seed-bound', () => {
  const a = makeIdempotencyKey('pos_quick_order');
  const b = makeIdempotencyKey('pos_quick_order');
  assert.notEqual(a, b, 'two keys must differ');
  assert.ok(a.startsWith('mob-quick-'));
  const close = makeIdempotencyKey('pos_close_order', 'ord-9');
  assert.ok(close.startsWith('mob-close-ord-9-'));
});
