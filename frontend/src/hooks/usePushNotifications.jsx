import { useEffect } from 'react';
import axios from 'axios';

const isPushSupported = () =>
  typeof window !== 'undefined' &&
  'serviceWorker' in navigator &&
  'PushManager' in window &&
  typeof window.Notification !== 'undefined';

const base64ToUint8Array = (base64String) => {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
};

/**
 * Subscribe the active staff user to internal-message web push so urgent
 * messages reach the OS notification centre even when no tab is open.
 *
 * The subscription endpoint and VAPID key are both served by the backend's
 * `messaging/internal/push/*` API. We re-subscribe whenever the user changes.
 */
export default function usePushNotifications(user) {
  useEffect(() => {
    if (!user || !isPushSupported()) return undefined;
    // Guests don't get internal messages, so don't bother prompting them.
    const role = user.role || (user.roles && user.roles[0]);
    if (!role || role === 'guest') return undefined;
    // Don't auto-prompt: only proceed if the user already accepted notifications
    // (the bell in NotificationCenter has the explicit opt-in button).
    if (Notification.permission !== 'granted') return undefined;

    let cancelled = false;

    const enablePush = async () => {
      try {
        const keyRes = await axios.get('/messaging/internal/push/vapid-public-key');
        const vapidKey = keyRes.data?.public_key;
        if (!vapidKey) return;

        const registration = await navigator.serviceWorker.ready;
        let subscription = await registration.pushManager.getSubscription();

        if (subscription) {
          // If the existing subscription was made with a different VAPID key
          // (e.g. server regenerated keys), drop and re-subscribe.
          const currentKey = subscription.options?.applicationServerKey;
          const sameKey = currentKey
            ? new Uint8Array(currentKey).every(
                (v, i) => v === base64ToUint8Array(vapidKey)[i],
              )
            : false;
          if (!sameKey) {
            try {
              await subscription.unsubscribe();
            } catch {
              /* noop */
            }
            subscription = null;
          }
        }

        if (!subscription) {
          subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: base64ToUint8Array(vapidKey),
          });
        }

        if (cancelled) return;

        const json = subscription.toJSON();
        await axios.post('/messaging/internal/push/subscribe', {
          endpoint: json.endpoint,
          keys: json.keys,
          user_agent: navigator.userAgent,
        });
      } catch (error) {
        console.warn('[Push] subscription skipped', error?.message || error);
      }
    };

    enablePush();

    return () => {
      cancelled = true;
    };
  }, [user?.id, user?.role]);
}
