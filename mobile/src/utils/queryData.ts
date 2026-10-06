/**
 * Persisted React Query data can outlive a response-shape migration. Keep
 * list screens render-safe while the fresh request replaces an older cache.
 */
export function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}
