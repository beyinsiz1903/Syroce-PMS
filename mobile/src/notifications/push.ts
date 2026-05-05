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
import type { Router } from 'expo-router';
import { getOrCreateDeviceId } from '../api/client';
import { registerPushDevice } from '../api/auth';
import { ROUTES, rootForRole } from '../navigation/routes';
import type { AppRole } from '../state/authStore';

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
export async function registerForPush(): Promise<string | null> {
  setForegroundHandler();
  await ensureAndroidChannel();

  if (Platform.OS === 'web') {
    _lastPushStatus = 'unavailable';
    return null;
  }

  let perms = await Notifications.getPermissionsAsync();
  if (perms.status !== 'granted') {
    perms = await Notifications.requestPermissionsAsync();
  }
  if (perms.status !== 'granted') {
    _lastPushStatus = 'denied';
    return null;
  }

  // EAS builds and the legacy Constants.manifest both expose the projectId.
  // We tolerate it being missing (Expo Go on first run) — the call still
  // returns a valid token when the device is paired with an EAS account.
  const projectId =
    (Constants.expoConfig as { extra?: { eas?: { projectId?: string } } } | null)?.extra?.eas
      ?.projectId ||
    (Constants as unknown as { easConfig?: { projectId?: string } }).easConfig?.projectId;

  let tokenResp;
  try {
    tokenResp = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
  } catch {
    _lastPushStatus = 'error';
    return null;
  }
  const token = tokenResp?.data;
  if (!token) {
    _lastPushStatus = 'unavailable';
    return null;
  }

  // Backend POST failure must surface as 'error' so the More-screen
  // indicator (and the smoke test that asserts on it) doesn't silently
  // collapse a broken /push/register endpoint into "not yet attempted".
  // `registerPushDevice` returns false on HTTP failure; we additionally
  // try/catch in case a future refactor lets a SecureStore error escape
  // `getOrCreateDeviceId()`.
  let posted = false;
  try {
    const deviceId = await getOrCreateDeviceId();
    posted = await registerPushDevice({
      device_id: deviceId,
      push_token: token,
      platform: Platform.OS,
      app_version: Constants.expoConfig?.version,
      os_version: String(Platform.Version),
      device_name: Constants.deviceName ?? undefined,
    });
  } catch {
    _lastPushStatus = 'error';
    return null;
  }
  if (!posted) {
    _lastPushStatus = 'error';
    return null;
  }

  _lastPushStatus = 'registered';
  return token;
}

type PushPayload = {
  type?: string;
  booking_id?: string;
  room_id?: string;
  damage_report_id?: string;
  thread_id?: string;
  business_date?: string;
};

type RouteTarget = string | { pathname: string; params?: Record<string, string> };

/**
 * Pick the deep-link target for an incoming push payload, **scoped to the
 * recipient's role**. This matters because `AuthGate` in `_layout.tsx`
 * force-redirects users back to their role's group root whenever the
 * current segment doesn't match `groupForRole(role)`. So a damage_report
 * push that hard-routes to `/(housekeeping)` would be silently ejected
 * for a GM recipient (who only has access to `/(gm)`), losing the deep
 * link entirely.
 *
 * Rule of thumb: every returned route MUST live inside the user's own
 * group — when no domain-specific screen exists for that role we fall
 * back to the role root (still better than no-op or a redirect loop).
 */
function routeForRole(payload: PushPayload, role: AppRole): RouteTarget | null {
  const type = (payload.type || '').toLowerCase();
  const home: RouteTarget = rootForRole(role) as unknown as RouteTarget;

  switch (type) {
    case 'vip_arrival':
      // Front-desk + GM both receive this push. FD lands on the today
      // overview (arrivals row); GM lands on the GM overview. HK doesn't
      // receive this type but if it ever does, send them home safely.
      return home;

    case 'no_show_risk':
      // FD can pre-fill the check-in form; everybody else lands on home.
      if (role === 'front_desk' && payload.booking_id) {
        return { pathname: ROUTES.checkin, params: { bookingId: payload.booking_id } };
      }
      return home;

    case 'damage_report':
      // HK has the dedicated damage screen; GM sees damage in their
      // overview; engineering/maintenance share the HK group in V3.
      if (role === 'housekeeping') {
        return ROUTES.housekeeping;
      }
      return home;

    case 'guest_message': {
      // Guest taps go to their thread; staff stay inside their own group
      // (no shared cross-role thread screen exists yet — V4).
      if (role === 'guest_app') {
        const bookingId = payload.booking_id || payload.thread_id;
        return bookingId
          ? { pathname: ROUTES.guestMessageThread, params: { bookingId } }
          : ROUTES.guestMessages;
      }
      return home;
    }

    case 'eod_ready':
      // Only GM receives EOD pushes; for any other role just go home.
      return home;

    default:
      return null;
  }
}

function navigateTo(router: Router, target: RouteTarget | null) {
  if (!target) return;
  try {
    if (typeof target === 'string') router.push(target as never);
    else router.push(target as never);
  } catch {
    // Routing may fail before the navigation tree is mounted; ignore.
  }
}

let _coldStartHandled = false;

/**
 * Wire up tap + foreground listeners so a push notification can route the
 * user to the relevant screen via expo-router. Idempotent — calling twice
 * tears down the previous listeners first.
 *
 * V3: also handles the cold-start case via
 * `getLastNotificationResponseAsync()`. When the OS launches the app
 * because the user tapped a push, the ResponseReceived listener won't
 * fire (the event was already dispatched before JS booted), so we read
 * it explicitly on first attach. Guarded by `_coldStartHandled` so a
 * later re-attach (e.g. on hot reload or login state change) does not
 * re-route to the original notification.
 */
export function attachPushListeners(router: Router, role: AppRole): () => void {
  setForegroundHandler();
  if (_tapSub) {
    _tapSub.remove();
    _tapSub = null;
  }
  if (_fgSub) {
    _fgSub.remove();
    _fgSub = null;
  }
  _tapSub = Notifications.addNotificationResponseReceivedListener((response) => {
    const data = (response.notification.request.content.data ?? {}) as PushPayload;
    navigateTo(router, routeForRole(data, role));
  });
  _fgSub = Notifications.addNotificationReceivedListener(() => {
    // No-op for now — we just rely on the OS banner. Hook-point for
    // V4 in-app toasts / unread-count refresh.
  });

  if (!_coldStartHandled) {
    _coldStartHandled = true;
    // Defer one tick so expo-router's navigation tree has mounted before
    // we try to push. The async chain is intentionally fire-and-forget.
    setTimeout(() => {
      Notifications.getLastNotificationResponseAsync()
        .then((response) => {
          if (!response) return;
          const data = (response.notification.request.content.data ?? {}) as PushPayload;
          navigateTo(router, routeForRole(data, role));
        })
        .catch(() => {
          // Cold-start push read failed (no permission yet, etc.) — ignore.
        });
    }, 0);
  }

  return () => {
    _tapSub?.remove();
    _fgSub?.remove();
    _tapSub = null;
    _fgSub = null;
  };
}
