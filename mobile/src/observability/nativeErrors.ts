import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { apiRequest } from '../api/client';

let route = '/mobile';
let installed = false;

export function setNativeErrorRoute(value: string) { route = value.slice(0, 160) || '/mobile'; }

export function captureNativeError(error: unknown, kind: 'render' | 'fatal' | 'unhandled' = 'render') {
  const raw = error instanceof Error ? error.message : String(error || 'Unknown error');
  const message = raw.replace(/[\r\n\t]+/g, ' ').slice(0, 500);
  // Best effort only: diagnostics must never affect the operator's workflow.
  void apiRequest('/api/observability/rum/native-errors', {
    method: 'POST', body: { kind, route, message, platform: Platform.OS, app_version: Constants.expoConfig?.version || 'unknown' },
  }).catch(() => undefined);
}

export function installNativeErrorTracking() {
  if (installed) return;
  installed = true;
  const utils = (globalThis as any).ErrorUtils;
  if (!utils?.getGlobalHandler || !utils?.setGlobalHandler) return;
  const previous = utils.getGlobalHandler();
  utils.setGlobalHandler((error: unknown, isFatal?: boolean) => {
    captureNativeError(error, isFatal ? 'fatal' : 'unhandled');
    previous(error, isFatal);
  });
}
