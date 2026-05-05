/**
 * Lightweight "last successful sync" tracker (V3).
 *
 * The offline banner shows "Çevrimdışı – son güncelleme X dk önce" using
 * this. We don't need millisecond accuracy or per-query granularity, so
 * the API is intentionally minimal: one timestamp shared across the app.
 */
import { useSyncExternalStore } from 'react';

let lastSyncAt: number | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const fn of listeners) fn();
}

export function markSync(at: number = Date.now()): void {
  lastSyncAt = at;
  emit();
}

export function getLastSync(): number | null {
  return lastSyncAt;
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useLastSync(): number | null {
  return useSyncExternalStore(subscribe, getLastSync, getLastSync);
}

export function formatAgo(ts: number | null, now: number = Date.now()): string {
  if (!ts) return '';
  const diffSec = Math.max(0, Math.floor((now - ts) / 1000));
  if (diffSec < 60) return `${diffSec} sn önce`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} dk önce`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} sa önce`;
  return `${Math.floor(diffSec / 86400)} gün önce`;
}
