import { ApiError } from '../api/client';

function userSafeMessage(message: string | undefined, fallback: string): string {
  const value = (message || '').trim();
  if (!value) return fallback;

  // Subscription services sometimes append an internal module key such as
  // `revenue_management`. That key is useful in logs, not in the hotel UI.
  if (/plan(?:ınıza|iniza).*dahil değil/i.test(value)) {
    return 'Bu özellik otelinizin paketinde etkin değil.';
  }

  // Never expose JavaScript exceptions, bundle locations or native stack
  // frames to guests/staff. Error monitoring still receives the original
  // exception; the UI gets the contextual fallback supplied by the screen.
  if (
    /\b(TypeError|ReferenceError|SyntaxError|RangeError):/i.test(value) ||
    /\/var\/mobile\/Containers\//i.test(value) ||
    /\.bundle:\d+/i.test(value) ||
    /\n\s*at\s+/i.test(value)
  ) {
    return fallback;
  }

  return value;
}

export function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return userSafeMessage(e.message, fallback);
  if (e instanceof Error) return userSafeMessage(e.message, fallback);
  if (typeof e === 'string') return userSafeMessage(e, fallback);
  return fallback;
}

export function errorStatus(e: unknown): number | null {
  if (e instanceof ApiError) return e.status;
  return null;
}

export function isOffline(e: unknown): boolean {
  return errorStatus(e) === 0;
}
