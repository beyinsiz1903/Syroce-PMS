import { ApiError } from '../api/client';
import { userSafeErrorMessage } from './userSafeErrorMessage';

export function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return userSafeErrorMessage(e.message, fallback);
  if (e instanceof Error) return userSafeErrorMessage(e.message, fallback);
  if (typeof e === 'string') return userSafeErrorMessage(e, fallback);
  return fallback;
}

export function errorStatus(e: unknown): number | null {
  if (e instanceof ApiError) return e.status;
  return null;
}

export function isOffline(e: unknown): boolean {
  return errorStatus(e) === 0;
}
