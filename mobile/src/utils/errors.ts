import { ApiError } from '../api/client';

export function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message || fallback;
  if (e instanceof Error) return e.message || fallback;
  if (typeof e === 'string') return e;
  return fallback;
}

export function errorStatus(e: unknown): number | null {
  if (e instanceof ApiError) return e.status;
  return null;
}

export function isOffline(e: unknown): boolean {
  return errorStatus(e) === 0;
}
