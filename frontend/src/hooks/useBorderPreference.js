import { useEffect, useSyncExternalStore } from 'react';

export const BORDER_PREFERENCE_KEY = 'syroce-prominent-borders';
const CHANGE_EVENT = 'syroce-border-preference-change';
let fallback = false;
let storageBlocked = false;

function getSnapshot() {
  if (storageBlocked) return fallback;
  try {
    return window.localStorage.getItem(BORDER_PREFERENCE_KEY) === 'true';
  } catch {
    return fallback;
  }
}

function subscribe(callback) {
  const onStorage = event => {
    if (event.key === BORDER_PREFERENCE_KEY || event.key === null) {
      storageBlocked = false;
      callback();
    }
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(CHANGE_EVENT, callback);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(CHANGE_EVENT, callback);
  };
}

export function setBorderPreference(enabled) {
  fallback = Boolean(enabled);
  try {
    window.localStorage.setItem(BORDER_PREFERENCE_KEY, String(fallback));
    storageBlocked = false;
  } catch {
    storageBlocked = true;
    // Storage may be blocked; retain this preference for the current session.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function useBorderPreference() {
  const enabled = useSyncExternalStore(subscribe, getSnapshot, () => false);
  useEffect(() => {
    document.documentElement.toggleAttribute('data-prominent-borders', enabled);
  }, [enabled]);
  return [enabled, setBorderPreference];
}
