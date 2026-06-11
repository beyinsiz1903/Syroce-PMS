/**
 * Offline-durable POS action queue — pure core (Task #361).
 *
 * This module holds the storage-agnostic, side-effect-free logic for the
 * mobile POS write queue so it can be unit-tested in plain Node (see
 * `yarn test:unit`). All durable storage and the real API senders live in
 * the RN wiring layer (`posQueue.ts`), which injects a `DurableKV` and a
 * `send` callback into the functions here.
 *
 * Design contract (server-authoritative, exactly-once on replay):
 *   - A queued entry carries a STABLE `idempotency_key`. The same key is sent
 *     on the first direct attempt AND on every replay, so the backend (Phase 1
 *     idempotency) collapses a "committed but response lost" retry into a
 *     single processed order — no client-side conflict merge needed.
 *   - On 2xx OR any 4xx the entry is DROPPED (the server made an authoritative
 *     decision — success or a permanent reject). On a network failure (status
 *     0) or 5xx the entry is RETAINED and the run stops, to be retried on the
 *     next reconnect / app start.
 */

export type PosQueueType = 'pos_quick_order' | 'pos_close_order';

export interface PosQueueEntry {
  id: string;
  type: PosQueueType;
  payload: unknown;
  idempotency_key: string;
  createdAt: number;
}

/**
 * Minimal async key/value contract the queue persists through. Backed by
 * MMKV (production) or AsyncStorage (Expo Go / web) in the wiring layer; an
 * in-memory map in tests.
 */
export interface DurableKV {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export const POS_QUEUE_KEY = 'syroce.pos.queue.v1';

function isValidEntry(e: unknown): e is PosQueueEntry {
  if (!e || typeof e !== 'object') return false;
  const o = e as Record<string, unknown>;
  return (
    typeof o.id === 'string' &&
    (o.type === 'pos_quick_order' || o.type === 'pos_close_order') &&
    typeof o.idempotency_key === 'string' &&
    typeof o.createdAt === 'number' &&
    'payload' in o
  );
}

/** Parse + sanitize the persisted JSON. Never throws — corrupt data → []. */
export function parseQueue(raw: string | null): PosQueueEntry[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isValidEntry);
  } catch {
    return [];
  }
}

export async function loadQueue(kv: DurableKV): Promise<PosQueueEntry[]> {
  return parseQueue(await kv.getItem(POS_QUEUE_KEY));
}

export async function saveQueue(kv: DurableKV, entries: PosQueueEntry[]): Promise<void> {
  await kv.setItem(POS_QUEUE_KEY, JSON.stringify(entries));
}

/**
 * Append an entry, de-duplicating on `idempotency_key` so a double-tap or a
 * re-enqueue after a failed direct send never stores the same order twice.
 */
export async function enqueue(kv: DurableKV, entry: PosQueueEntry): Promise<PosQueueEntry[]> {
  const entries = await loadQueue(kv);
  if (entries.some((e) => e.idempotency_key === entry.idempotency_key)) return entries;
  const next = [...entries, entry];
  await saveQueue(kv, next);
  return next;
}

export async function removeFromQueue(kv: DurableKV, id: string): Promise<PosQueueEntry[]> {
  const entries = await loadQueue(kv);
  const next = entries.filter((e) => e.id !== id);
  if (next.length !== entries.length) await saveQueue(kv, next);
  return next;
}

export type ReplayDecision = 'drop' | 'retain_stop';

/**
 * Server-authoritative replay decision from an HTTP status.
 *   2xx → drop (processed); 4xx → drop (permanent reject — never replay garbage
 *   into a loop); network (0) / 5xx → retain + stop (transient, retry later).
 */
export function decideFromStatus(status: number): ReplayDecision {
  if (status >= 200 && status < 300) return 'drop';
  if (status >= 400 && status < 500) return 'drop';
  return 'retain_stop';
}

export type SendOutcome = { ok: true } | { ok: false; status: number };

export interface ReplayReport {
  processed: number;
  dropped: number;
  retained: number;
  stopped: boolean;
}

/**
 * Replay the queue in order. Stops at the first retained entry so we preserve
 * FIFO ordering and don't hammer a downed backend — the next reconnect / app
 * start resumes from the same head.
 */
export async function replayQueue(
  kv: DurableKV,
  send: (entry: PosQueueEntry) => Promise<SendOutcome>,
): Promise<ReplayReport> {
  const entries = await loadQueue(kv);
  let dropped = 0;
  let retained = 0;
  let stopped = false;
  for (const entry of entries) {
    let decision: ReplayDecision;
    try {
      const outcome = await send(entry);
      decision = outcome.ok ? 'drop' : decideFromStatus(outcome.status);
    } catch {
      // An unexpected sender throw is treated as a transient network failure.
      decision = 'retain_stop';
    }
    if (decision === 'drop') {
      await removeFromQueue(kv, entry.id);
      dropped += 1;
    } else {
      retained += 1;
      stopped = true;
      break;
    }
  }
  return { processed: dropped + retained, dropped, retained, stopped };
}

let _seq = 0;

/** Monotonic-ish unique token; deterministic-friendly for tests via injection. */
export function makeId(now: number = Date.now(), rand: () => number = Math.random): string {
  _seq = (_seq + 1) % 1_000_000;
  return `${now.toString(36)}-${_seq.toString(36)}-${Math.floor(rand() * 1e9).toString(36)}`;
}

/**
 * Build a STABLE idempotency key. Generated once before the first send attempt
 * and reused on every replay so the backend dedupes a lost-response retry.
 */
export function makeIdempotencyKey(
  type: PosQueueType,
  seed?: string,
  now: number = Date.now(),
  rand: () => number = Math.random,
): string {
  const prefix = type === 'pos_close_order' ? 'mob-close' : 'mob-quick';
  const unique = makeId(now, rand);
  return seed ? `${prefix}-${seed}-${unique}` : `${prefix}-${unique}`;
}
