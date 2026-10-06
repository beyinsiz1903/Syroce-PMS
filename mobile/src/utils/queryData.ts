/**
 * Persisted React Query data can outlive a response-shape migration. Keep
 * list screens render-safe while the fresh request replaces an older cache.
 */
export function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

type WalkInBookingLike = {
  source?: unknown;
  check_in?: unknown;
};

/**
 * Count today's walk-ins without trusting API/cache field types. Legacy and
 * third-party records may contain nulls, numbers or nested values here; those
 * records should simply not count instead of taking down the whole dashboard.
 */
export function countTodayWalkIns(value: unknown, today: string): number {
  return asArray<WalkInBookingLike | null>(value).filter((booking) => {
    const source = String(booking?.source ?? '').toLowerCase();
    const checkIn = String(booking?.check_in ?? '').slice(0, 10);
    return source === 'walk_in' && checkIn === today;
  }).length;
}
