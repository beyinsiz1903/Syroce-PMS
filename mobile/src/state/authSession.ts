// An account boundary invalidates old HTTP responses and serializes Keychain
// writes. A late refresh/login must never restore the previous account.
let revision = 0;
let writes: Promise<unknown> = Promise.resolve();
const expiredListeners = new Set<(revision: number) => void | Promise<void>>();

export class SessionChangedError extends Error {
  constructor() { super('Oturum değişti; işlemi güncel hesabınızla yeniden açın.'); }
}

export const currentAuthSession = () => revision;
export const beginAuthSession = () => ++revision;
export const isCurrentAuthSession = (value: number) => value === revision;
export function assertAuthSession(value: number) {
  if (!isCurrentAuthSession(value)) throw new SessionChangedError();
}

export function writeForAuthSession<T>(value: number, operation: () => Promise<T>): Promise<T | undefined> {
  const result = writes.then(() => isCurrentAuthSession(value) ? operation() : undefined);
  writes = result.catch(() => undefined);
  return result;
}

export function onAuthSessionExpired(listener: (revision: number) => void | Promise<void>) {
  expiredListeners.add(listener);
  return () => { expiredListeners.delete(listener); };
}

export async function expireAuthSession(value: number) {
  if (!isCurrentAuthSession(value)) return;
  const next = beginAuthSession();
  await Promise.all([...expiredListeners].map(listener => listener(next)));
}
