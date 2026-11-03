/**
 * Push notification registration & deep-link routing for the Syroce mobile
 * app (V3). Uses expo-notifications. In Expo Go on SDK 53+ remote push is
 * limited — for full support build a development client with EAS.
 *
 * Backend ⇄ mobile contract:
 *   * Backend stores the device's `ExponentPushToken[...]` in
 *     `push_device_tokens` (POST /api/notifications/push/register).
 *   * Backend dispatches via `services/expo_push.py` whenever an event
 *     should reach a phone (vip_arrival, no_show_risk, damage_report,
 *     guest_message, eod_ready).
 *   * Backend payload `data` includes a `type` field. We use that here to
 *     route the user to the appropriate screen on tap.
 */
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import { getOrCreateDeviceId } from '../api/client';
import { registerPushDevice } from '../api/auth';
import { notificationTarget, type PushPayload, type NotificationTarget, type NotificationUser } from '../navigation/notificationRoutes';
import { currentAuthSession, isCurrentAuthSession } from '../state/authSession';

let _handlerSet = false;
let _tapSub: Notifications.Subscription | null = null;
let _fgSub: Notifications.Subscription | null = null;

/**
 * Tracks the outcome of the most recent `registerForPush()` call so the
 * Settings ("Daha") screen can surface a status indicator without having
 * to re-run the registration flow on every mount. Pure in-memory; reset
 * on app restart.
 */
export type PushRegistrationStatus =
  | 'unknown'
  | 'registered'
  | 'denied'
  | 'unavailable'
  | 'error';
let _lastPushStatus: PushRegistrationStatus = 'unknown';
const statusListeners = new Set<(status: PushRegistrationStatus) => void>();
function setPushStatus(status: PushRegistrationStatus) {
  _lastPushStatus = status;
  statusListeners.forEach(listener => listener(status));
}
export const resetPushStatus = () => setPushStatus('unknown');
export function subscribePushStatus(listener: (status: PushRegistrationStatus) => void) {
  statusListeners.add(listener);
  return () => { statusListeners.delete(listener); };
}

type PushRouter = {
  push: (target: never) => void;
};

export function getLastPushStatus(): PushRegistrationStatus {
  return _lastPushStatus;
}

function setForegroundHandler() {
  if (_handlerSet) return;
  _handlerSet = true;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      // Show a banner even when the app is in the foreground so urgent
      // events (no-show risk, damage reports) don't get silently swallowed.
      shouldShowAlert: true,
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}

async function ensureAndroidChannel() {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync('default', {
    name: 'Genel',
    importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 250, 250, 250],
    lightColor: '#3b82f6',
    sound: 'default',
  }).catch(() => {});
}

/**
 * Ask for permission, get the Expo push token, and POST it to the backend.
 * Returns the token on success or null when push is unavailable (web,
 * simulator without Expo Go push entitlement, permission denied, …).
 */
export async function registerForPush({ requestPermission = true } = {}): Promise<string | null> {
  const revision = currentAuthSession();
  const status = (value: PushRegistrationStatus) => { if (isCurrentAuthSession(revision)) setPushStatus(value); };
  if (Platform.OS === 'web') {
    status('unavailable');
    return null;
  }
  try {
    setForegroundHandler();
    await ensureAndroidChannel();
    let perms = await Notifications.getPermissionsAsync();
    if (!isCurrentAuthSession(revision)) return null;
    if (perms.status !== 'granted' && requestPermission) {
      perms = await Notifications.requestPermissionsAsync();
    }
    if (perms.status !== 'granted') {
      status(perms.status === 'denied' ? 'denied' : 'unknown');
      return null;
    }

    const projectId = Constants.expoConfig?.extra?.eas?.projectId || Constants.easConfig?.projectId;
    const tokenResp = await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
    const token = tokenResp?.data;
    if (!token) {
      status('unavailable');
      return null;
    }
    const deviceId = await getOrCreateDeviceId();
    if (!isCurrentAuthSession(revision)) return null;
    const posted = await registerPushDevice({
      device_id: deviceId,
      push_token: token,
      platform: Platform.OS,
      app_version: Constants.expoConfig?.version,
      os_version: String(Platform.Version),
      device_name: Constants.deviceName ?? undefined,
    });
    status(posted ? 'registered' : 'error');
    return posted ? token : null;
  } catch {
    status('error');
    return null;
  }
}

function navigateTo(router: PushRouter, target: NotificationTarget | null) {
  if (!target) return;
  try {
    if (typeof target === 'string') router.push(target as never);
    else router.push(target as never);
  } catch {
    // Routing may fail before the navigation tree is mounted; ignore.
  }
}

let _lastHandledResponse: string | null = null;

/**
 * Wire up tap + foreground listeners so a push notification can route the
 * user to the relevant screen via expo-router. Idempotent — calling twice
 * tears down the previous listeners first.
 *
 * V3: also handles the cold-start case via
 * `getLastNotificationResponseAsync()`. When the OS launches the app
 * because the user tapped a push, the ResponseReceived listener won't
 * fire (the event was already dispatched before JS booted), so we read
 * it on attach, requiring matching recipient context. A response-ID guard
 * prevents later permission refreshes from replaying the same navigation.
 */
export function attachPushListeners(router: PushRouter, user: NotificationUser): () => void {
  if (Platform.OS === 'web') return () => {};
  const revision = currentAuthSession();
  let disposed = false;
  setForegroundHandler();
  if (_tapSub) {
    _tapSub.remove();
    _tapSub = null;
  }
  if (_fgSub) {
    _fgSub.remove();
    _fgSub = null;
  }
  const handle = (response: Notifications.NotificationResponse | null, coldStart = false) => {
    if (!response || disposed || !isCurrentAuthSession(revision)) return;
    const key = `${response.notification.request.identifier}:${response.actionIdentifier}`;
    if (_lastHandledResponse === key) return;
    const data = (response.notification.request.content.data ?? {}) as PushPayload;
    const target = notificationTarget(data, user, coldStart);
    if (!target) return;
    _lastHandledResponse = key;
    navigateTo(router, target);
  };
  _tapSub = Notifications.addNotificationResponseReceivedListener(response => handle(response));
  _fgSub = Notifications.addNotificationReceivedListener(() => {
    // No-op for now — we just rely on the OS banner. Hook-point for
    // V4 in-app toasts / unread-count refresh.
  });

  // Root waits for navigator readiness before attaching; no timing guess.
  void Notifications.getLastNotificationResponseAsync().then(response => handle(response, true)).catch(() => {});

  return () => {
    disposed = true;
    _tapSub?.remove();
    _fgSub?.remove();
    _tapSub = null;
    _fgSub = null;
  };
}
