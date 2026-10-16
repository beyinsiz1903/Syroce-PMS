import { useSyncExternalStore } from 'react';
import { onlineManager } from '@tanstack/react-query';

const subscribe = (onChange: () => void) => onlineManager.subscribe(() => onChange());
const getSnapshot = () => onlineManager.isOnline();
const getServerSnapshot = () => true;

/** Share the NetInfo-backed connection state used by React Query. */
export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
