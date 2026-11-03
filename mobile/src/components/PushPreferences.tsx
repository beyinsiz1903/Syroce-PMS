import React, { useEffect, useState } from 'react';
import { Platform } from 'react-native';
import { Button, Card, H2, Muted } from './ui';
import { getLastPushStatus, registerForPush, subscribePushStatus } from '../notifications/push';

export function PushPreferences() {
  const [status, setStatus] = useState(getLastPushStatus());
  const [busy, setBusy] = useState(false);
  useEffect(() => subscribePushStatus(setStatus), []);
  const labels = {
    registered: 'Bildirimler bu hesap için etkin.', denied: 'Bildirim izni kapalı. Cihaz ayarlarından Syroce bildirimlerine izin verebilirsiniz.',
    unavailable: 'Bu ortamda cihaz bildirimi desteklenmiyor.', error: 'Bildirim kaydı tamamlanamadı. Yeniden deneyebilirsiniz.',
    unknown: 'Bildirimler henüz etkinleştirilmedi.',
  };
  return <Card>
    <H2>Bildirimler</H2>
    <Muted accessibilityLiveRegion="polite">{labels[status]}</Muted>
    {Platform.OS !== 'web' && status !== 'registered' ? <Button title="Bildirimleri etkinleştir" loading={busy} onPress={async () => {
      setBusy(true);
      try { await registerForPush(); } finally { setBusy(false); }
    }} /> : null}
  </Card>;
}
