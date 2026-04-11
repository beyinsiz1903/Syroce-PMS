import { useEffect } from 'react';
import axios from 'axios';

const VAPID_KEY = import.meta.env.VITE_VAPID_PUBLIC_KEY || 'BHVV1Bv0roomOpsFallbackKeyExample1234567890';

const isPushSupported = () =>
  typeof window !== 'undefined' &&
  'serviceWorker' in navigator &&
  'PushManager' in window &&
  window.Notification;

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

const bufferToBase64 = (buffer) => {
  if (!buffer) return null;
  const bytes = new Uint8Array(buffer);
  let binary = '';
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return window.btoa(binary);
};

const registerSubscription = async (subscription, role = 'unknown') => {
  const payload = {
    endpoint: subscription.endpoint,
    public_key: bufferToBase64(subscription.getKey('p256dh')),
    auth_key: bufferToBase64(subscription.getKey('auth')),
    platform: 'web',
    role,
    device_info: {
      userAgent: navigator.userAgent,
      language: navigator.language
    }
  };
  return axios.post('/notifications/subscribe', payload);
};

export default function usePushNotifications(user) {
  useEffect(() => {
    if (!user || !isPushSupported()) {
      return;
    }

    let cancelled = false;

    const enablePush = async () => {
      try {
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
          console.warn('[Push] Permission denied');
          return;
        }

        const registration = await navigator.serviceWorker.ready;
        let subscription = await registration.pushManager.getSubscription();

        if (!subscription) {
          subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: base64ToUint8Array(VAPID_KEY)
          });
        }

        if (!cancelled) {
          await registerSubscription(subscription, user?.role);
        }
      } catch (error) {
        console.error('[Push] Failed to register', error);
      }
    };

    enablePush();

    return () => {
      cancelled = true;
    };
  }, [user?.id, user?.role]);
}
