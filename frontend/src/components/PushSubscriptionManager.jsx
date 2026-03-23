import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Popover,
  PopoverTrigger,
  PopoverContent
} from '@/components/ui/popover';
import { BellRing, ShieldCheck, WifiOff } from 'lucide-react';

const CHANNEL_OPTIONS = [
  { id: 'arrivals', label: 'Front Desk & Arrivals' },
  { id: 'housekeeping', label: 'Housekeeping Tasks' },
  { id: 'maintenance', label: 'Maintenance / Engineering' },
  { id: 'finance', label: 'Finance & Payments' },
  { id: 'executive', label: 'Executive Briefings' },
];

const DEVICE_ID_STORAGE_KEY = 'syroce_push_device_id';

const getDeviceId = () => {
  if (typeof window === 'undefined') return 'server';
  let existing = localStorage.getItem(DEVICE_ID_STORAGE_KEY);
  if (!existing) {
    existing = crypto.randomUUID
      ? crypto.randomUUID()
      : `device_${Date.now().toString(36)}`;
    localStorage.setItem(DEVICE_ID_STORAGE_KEY, existing);
  }
  return existing;
};

const PushSubscriptionManager = () => {
  const [status, setStatus] = useState('loading'); // loading | enabled | disabled | unsupported
  const [subscriptions, setSubscriptions] = useState(CHANNEL_OPTIONS.map((c) => c.id));
  const [devices, setDevices] = useState([]);
  const [saving, setSaving] = useState(false);
  const [registering, setRegistering] = useState(false);

  const supportPush = useMemo(() => {
    if (typeof window === 'undefined') return false;
    return 'Notification' in window && 'serviceWorker' in navigator;
  }, []);

  const loadStatus = useCallback(async () => {
    if (!supportPush) {
      setStatus('unsupported');
      return;
    }
    try {
      const res = await axios.get('/notifications/push-status');
      setDevices(res.data.devices || []);
      setSubscriptions(res.data.subscriptions || CHANNEL_OPTIONS.map((c) => c.id));
      setStatus(res.data.enabled ? 'enabled' : 'disabled');
    } catch (error) {
      console.error('Push status load failed', error);
      setStatus('error');
    }
  }, [supportPush]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleRequestPermission = async () => {
    if (!supportPush) {
      toast.error('Tarayıcı push bildirimlerini desteklemiyor');
      return;
    }

    try {
      setRegistering(true);
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        toast.error('Bildirim izni verilmedi');
        setRegistering(false);
        return;
      }

      const deviceId = getDeviceId();
      const tokenSource = btoa(`${deviceId}:${Date.now()}:${navigator.userAgent}`);
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

      await axios.post('/notifications/push/register', {
        device_id: deviceId,
        device_name: navigator.userAgent,
        platform: 'web',
        push_token: tokenSource,
        user_agent: navigator.userAgent,
        timezone,
        subscriptions,
        capabilities: {
          notification_permission: permission,
          service_worker: true
        }
      });

      toast.success('Push bildirimleri aktif edildi');
      await loadStatus();
    } catch (error) {
      console.error('Push registration failed', error);
      toast.error('Push kaydı başarısız');
    } finally {
      setRegistering(false);
    }
  };

  const handleToggleChannel = async (channelId) => {
    const next = subscriptions.includes(channelId)
      ? subscriptions.filter((c) => c !== channelId)
      : [...subscriptions, channelId];

    setSubscriptions(next);
    try {
      setSaving(true);
      await axios.post('/notifications/push/subscriptions', { channels: next });
      toast.success('Bildirim tercihleri güncellendi');
    } catch (error) {
      console.error('Subscription update failed', error);
      toast.error('Tercihler güncellenemedi');
    } finally {
      setSaving(false);
    }
  };

  const statusLabel = useMemo(() => {
    switch (status) {
      case 'enabled':
        return 'Push aktif';
      case 'disabled':
        return 'Push kapalı';
      case 'unsupported':
        return 'Desteklenmiyor';
      case 'error':
        return 'Hata';
      default:
        return 'Kontrol ediliyor';
    }
  }, [status]);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={`hidden md:flex items-center gap-2 ${
            status === 'enabled' ? 'text-green-600' : 'text-gray-500'
          }`}
        >
          {supportPush ? (
            <BellRing className="w-4 h-4" />
          ) : (
            <WifiOff className="w-4 h-4" />
          )}
          <span className="text-xs font-medium">{statusLabel}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold">Push Notifications</p>
            <p className="text-xs text-gray-500">
              Mobil ekipler için gerçek zamanlı uyarılar
            </p>
          </div>
          <Badge variant={status === 'enabled' ? 'default' : 'secondary'}>
            {status === 'enabled' ? 'AKTİF' : 'PASİF'}
          </Badge>
        </div>

        {devices.length > 0 && (
          <div className="rounded-md border bg-gray-50 p-3 text-xs space-y-1">
            <p className="font-medium text-gray-700">Kayıtlı Cihazlar</p>
            {devices.map((device) => (
              <div key={device.device_id} className="flex items-center justify-between">
                <span>{device.platform || 'web'}</span>
                <span className="text-gray-500">
                  {new Date(device.updated_at).toLocaleTimeString('tr-TR', {
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-2">
          <p className="text-xs font-semibold text-gray-600">Kanal Tercihleri</p>
          <div className="space-y-2">
            {CHANNEL_OPTIONS.map((channel) => (
              <div
                key={channel.id}
                className="flex items-center justify-between text-xs py-1"
              >
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-3.5 h-3.5 text-blue-500" />
                  <span>{channel.label}</span>
                </div>
                <Switch
                  checked={subscriptions.includes(channel.id)}
                  onCheckedChange={() => handleToggleChannel(channel.id)}
                  disabled={saving}
                />
              </div>
            ))}
          </div>
        </div>

        <Button
          className="w-full"
          onClick={handleRequestPermission}
          disabled={!supportPush || registering}
        >
          {status === 'enabled' ? 'Cihazı Yenile' : 'Push Bildirimlerini Aç'}
        </Button>
        {!supportPush && (
          <p className="text-[11px] text-red-500">
            Tarayıcı push bildirimlerini desteklemiyor veya servis worker aktif değil.
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
};

export default PushSubscriptionManager;
