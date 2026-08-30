import { useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  getAlertedWakeUpIds,
  getWakeUpAlarmSettings,
  playWakeUpChime,
  rememberWakeUpAlerts,
  todayInIstanbul,
  WAKEUP_ALARM_EVENT,
  wakeUpAlertIdentity,
} from '@/lib/wakeUpAlarm';

const POLL_INTERVAL_MS = 30000;

export default function WakeUpAlarmMonitor({ tenant }) {
  const navigate = useNavigate();
  const pollingRef = useRef(false);

  const fireAlerts = useCallback(async (calls) => {
    const alerted = getAlertedWakeUpIds();
    const fresh = calls.filter((call) => call.is_due && !alerted.has(wakeUpAlertIdentity(call)));
    if (fresh.length === 0) return;

    const settings = getWakeUpAlarmSettings();
    if (settings.enabled) {
      await playWakeUpChime(settings.volume).catch(() => false);
    }

    fresh.forEach((call) => {
      const details = `Oda ${call.room_number}${call.guest_name ? ` — ${call.guest_name}` : ''} • ${call.wake_time}`;
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        try {
          const notification = new Notification('Uyandırma çağrısı zamanı', {
            body: details,
            tag: `wakeup-${wakeUpAlertIdentity(call)}`,
            requireInteraction: true,
          });
          notification.onclick = () => {
            window.focus();
            navigate('/wake-up-calls');
            notification.close();
          };
        } catch {
          // Tarayıcı bildirimi desteklenmiyorsa uygulama içi uyarı yeterlidir.
        }
      }
      toast.warning(`Uyandırma çağrısı: ${details}`, {
        duration: 30000,
        action: { label: 'Aç', onClick: () => navigate('/wake-up-calls') },
      });
    });
    rememberWakeUpAlerts(fresh);
  }, [navigate]);

  const poll = useCallback(async () => {
    if (!tenant) return;
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      const response = await axios.get('/pms/wake-up-calls', {
        params: { date: todayInIstanbul(), status: 'pending' },
      });
      await fireAlerts(response.data?.calls || []);
    } catch {
      // Ağ kesintisinde kullanıcıyı her 30 saniyede bir uyarmayın; sonraki tur yeniden dener.
    } finally {
      pollingRef.current = false;
    }
  }, [fireAlerts, tenant]);

  useEffect(() => {
    poll();
    const interval = window.setInterval(poll, POLL_INTERVAL_MS);
    const onVisibility = () => { if (!document.hidden) poll(); };
    const onSettings = () => poll();
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener(WAKEUP_ALARM_EVENT, onSettings);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener(WAKEUP_ALARM_EVENT, onSettings);
    };
  }, [poll]);

  return null;
}
