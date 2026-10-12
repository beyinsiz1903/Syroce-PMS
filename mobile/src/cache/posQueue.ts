/**
 * Offline-durable POS action queue — RN wiring (Task #361).
 *
 * Binds the pure core (`posQueueCore.ts`) to:
 *   1. a durable disk store — MMKV when the native binary is present
 *      (production / EAS dev-client), AsyncStorage otherwise (Expo Go / web).
 *      Mirrors the persister.ts storage-selection strategy.
 *   2. the real POS API senders (`openQuickOrder` / `closeOrder`), each given
 *      the entry's STABLE idempotency key so a replay is deduped server-side.
 *   3. a tiny subscribable pending-count store for the POS badge.
 *
 * Only the two in-scope writes are durable: quick-order open and order close.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';
import { ApiError } from '../api/client';
import { closeOrder, openQuickOrder, type PaymentMethod } from '../api/posFnb';
import {
  enqueue as coreEnqueue,
  loadQueue,
  POS_QUEUE_KEY,
  replayQueue,
  type DurableKV,
  type PosQueueEntry,
  type SendOutcome,
} from './posQueueCore';

function buildDurableKV(): DurableKV {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require('react-native-mmkv');
    if (mod && typeof mod.MMKV === 'function') {
      const mmkv = new mod.MMKV({ id: 'syroce-pos-queue' });
      return {
        getItem: async (k) => {
          const v = mmkv.getString(k);
          return v === undefined ? null : v;
        },
        setItem: async (k, v) => {
          mmkv.set(k, v);
        },
        removeItem: async (k) => {
          mmkv.delete(k);
        },
      };
    }
  } catch {
    // fall through to AsyncStorage
  }
  return {
    getItem: (k) => AsyncStorage.getItem(k),
    setItem: (k, v) => AsyncStorage.setItem(k, v),
    removeItem: (k) => AsyncStorage.removeItem(k),
  };
}

const kv = buildDurableKV();

// ── pending-count store (badge) ─────────────────────────────────────────────
const _listeners = new Set<() => void>();
const _counts = new Map<string, number>();

function emit(): void {
  for (const fn of _listeners) fn();
}
export type QueueScope = { tenantId: string; userId: string };

function scopeKey(scope: QueueScope): string {
  return `syroce.pos.queue.v2.${encodeURIComponent(scope.tenantId)}.${encodeURIComponent(scope.userId)}`;
}

export function useScopedPosQueueCount(scope: QueueScope): number {
  const key = scopeKey(scope);
  const subscribeScoped = (cb: () => void) => {
    _listeners.add(cb);
    return () => _listeners.delete(cb);
  };
  return useSyncExternalStore(subscribeScoped, () => _counts.get(key) || 0, () => 0);
}

/** Re-read the queue from disk and publish its size to subscribers. */
export async function refreshPosQueueCount(scope: QueueScope): Promise<number> {
  const entries = await loadQueue(kv, scopeKey(scope));
  _counts.set(scopeKey(scope), entries.length);
  emit();
  return entries.length;
}

// Records written by the previous device-wide queue have no account owner.
// Preserve them for operator reconciliation; never submit them under the
// currently signed-in account.
export async function getLegacyPosQueueCount(): Promise<number> {
  return (await loadQueue(kv, POS_QUEUE_KEY)).length;
}

// ── enqueue helpers ─────────────────────────────────────────────────────────
export type QuickOrderPayload = {
  outlet_id: string;
  table_number?: string;
  items: { item_id: string; quantity: number }[];
  notes?: string;
};

export type CloseOrderPayload = {
  order_id: string;
  payment_method: PaymentMethod;
};

export async function enqueueQuickOrder(
  payload: QuickOrderPayload,
  idempotencyKey: string,
  scope: QueueScope,
): Promise<void> {
  await coreEnqueue(kv, {
    id: idempotencyKey,
    type: 'pos_quick_order',
    payload,
    idempotency_key: idempotencyKey,
    createdAt: Date.now(),
  }, scopeKey(scope));
  await refreshPosQueueCount(scope);
}

export async function enqueueCloseOrder(
  payload: CloseOrderPayload,
  idempotencyKey: string,
  scope: QueueScope,
): Promise<void> {
  await coreEnqueue(kv, {
    id: idempotencyKey,
    type: 'pos_close_order',
    payload,
    idempotency_key: idempotencyKey,
    createdAt: Date.now(),
  }, scopeKey(scope));
  await refreshPosQueueCount(scope);
}

// ── replay ──────────────────────────────────────────────────────────────────
async function sendEntry(entry: PosQueueEntry): Promise<SendOutcome> {
  try {
    if (entry.type === 'pos_quick_order') {
      const p = entry.payload as QuickOrderPayload;
      await openQuickOrder({ ...p, idempotency_key: entry.idempotency_key });
    } else {
      const p = entry.payload as CloseOrderPayload;
      await closeOrder({ ...p, idempotency_key: entry.idempotency_key });
    }
    return { ok: true };
  } catch (e: unknown) {
    if (e instanceof ApiError) return { ok: false, status: e.status };
    return { ok: false, status: 0 };
  }
}

const _flushingScopes = new Set<string>();

/**
 * Drain the queue. Safe to call repeatedly (reconnect, app start, manual): a
 * re-entrancy latch prevents two concurrent flushes from double-sending the
 * head entry. The count is always re-published afterwards.
 */
export async function flushPosQueue(scope: QueueScope): Promise<void> {
  const key = scopeKey(scope);
  if (_flushingScopes.has(key)) return;
  _flushingScopes.add(key);
  try {
    await replayQueue(kv, sendEntry, key);
  } finally {
    _flushingScopes.delete(key);
    await refreshPosQueueCount(scope);
  }
}
