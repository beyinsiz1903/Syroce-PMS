import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { policeAgentCommand } from '@/lib/kbsExtensionBridge';
import { Button } from '@/components/ui/button';

const reasons = {
  not_enabled: 'Bu tarayıcı oturumu için kapalı.',
  stopped: 'Gönderici durduruldu.',
  pms_login_or_context_required: 'PMS oturumu veya kullanıcı/otel değişti. Doğru hesapla giriş yapıp yeniden etkinleştirin.',
  egm_login_required: 'EGM oturumu sona erdi. EGMSEC ile normal giriş yapıp yeniden etkinleştirin.',
  egm_session_mode_required: 'Eklentinin Polis profilinde EGM oturumu seçilmeli.',
  server_managed: 'Bu tesis sunucu göndericisi tarafından yönetiliyor; tarayıcı gönderimi durduruldu.',
  server_test_mode: 'PMS sunucusu KBS test modunda; kuruma canlı bildirim gönderimi kapalı.',
  alarm_unavailable: 'Tarayıcı arka plan alarmı kurulamadı. Eklenti izinlerini kontrol edip yeniden etkinleştirin.',
  pms_unavailable: 'PMS bağlantısı doğrulanamadı. Kabul alınmamış kayıtlar gönderilmiş sayılmaz.',
};

export default function KBSBackgroundSender({ tenantId, onOwnershipChange, allowStart = true }) {
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const requestVersion = useRef(0);
  const commandRunning = useRef(false);
  const reconcile = useCallback(async () => {
    if (commandRunning.current) return;
    const gen = generation.current;
    const version = ++requestVersion.current;
    try {
      const result = await policeAgentCommand('STATUS');
      if (gen !== generation.current || version !== requestVersion.current) return;
      if (!result.ok) throw new Error('unknown');
      setState(result.state); setError('');
      onOwnershipChange(result.state?.enabled === true);
    } catch {
      if (gen !== generation.current || version !== requestVersion.current) return;
      setError('Arka plan durumu doğrulanamadı. Eklentiyi 1.5.0 veya üstüne güncelleyin. Sonucu belirsiz etkinleştirmeyi tekrarlamadan önce durumu yenileyin.');
      onOwnershipChange(true); // Unknown ownership must not start a second foreground worker.
    }
  }, [onOwnershipChange]);
  useEffect(() => {
    const gen = ++generation.current;
    setState(null); setConsent(false); onOwnershipChange(true);
    reconcile();
    const timer = setInterval(reconcile, 30000);
    return () => { generation.current = gen + 1; clearInterval(timer); };
  }, [tenantId, onOwnershipChange, reconcile]);

  const change = async (start) => {
    if (commandRunning.current) return;
    commandRunning.current = true;
    requestVersion.current++;
    onOwnershipChange(true);
    const gen = generation.current;
    setBusy(true);
    try {
      let binding;
      if (start) {
        const { data: user } = await axios.get('/auth/me');
        if (gen !== generation.current) return;
        if (!consent || !user?.id || !user?.tenant_id || (tenantId && String(user.tenant_id) !== String(tenantId))) throw new Error('context');
        binding = { tenantId: String(user.tenant_id), userId: String(user.id), consent: true };
      }
      const result = await policeAgentCommand(start ? 'START' : 'STOP', binding);
      if (gen !== generation.current) return;
      if (!result.ok) throw new Error(result.error);
      setConsent(false);
      // Always reconcile the real state; never infer activation from a click.
      commandRunning.current = false;
      await reconcile();
    } catch {
      if (gen !== generation.current) return;
      commandRunning.current = false;
      await reconcile();
      setError('İşlem tamamlandığı doğrulanamadı. PMS girişini ve eklenti ayarını kontrol edip durumu yenileyin.');
      onOwnershipChange(true);
    } finally {
      commandRunning.current = false;
      if (gen === generation.current) setBusy(false);
    }
  };
  const otherHotel = state?.enabled && tenantId && state.tenantId !== String(tenantId);
  return <div className="mt-3 space-y-2 rounded border p-3 text-sm">
    <p className="font-medium">Polis — arka plan göndericisi: {state?.enabled ? 'Açık' : state ? 'Kapalı' : 'Doğrulanıyor'}</p>
    <p>PMS sayfası kapalıyken de çalışır. Chrome/Edge ve bilgisayar açık, bu tesisin PMS ve EGM oturumları geçerli olmalıdır. Tarayıcı yeniden açılınca tekrar etkinleştirilir. Şifre veya PMS token’ı eklentiye kaydedilmez.</p>
    {otherHotel && <p role="alert">Başka bir otel için etkin. Mevcut göndericiyi durdurmadan bu tesise geçilemez.</p>}
    {state?.reason && <p>{reasons[state.reason] || 'Gönderici durumu kontrol edilmeli.'}</p>}
    {error && <p role="alert" className="text-amber-800">{error}</p>}
    {!state?.enabled && allowStart && <label className="flex items-start gap-2">
      <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} disabled={busy || !state} />
      EGM’de açık tesisin bu otel olduğunu kontrol ettim; bu tarayıcı oturumunda otomatik giriş/çıkış bildirimini etkinleştir.
    </label>}
    <div className="flex flex-wrap gap-2">
      {state?.enabled
        ? <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => change(false)}>Arka plan gönderimini durdur</Button>
        : allowStart && <Button type="button" size="sm" disabled={busy || !consent || !state || !!error} onClick={() => change(true)}>Arka plan gönderimini etkinleştir</Button>}
      <Button type="button" size="sm" variant="outline" disabled={busy} onClick={reconcile}>Gönderici durumunu yenile</Button>
    </div>
    {state?.lastRunAt && <p>Son kontrol: {new Date(state.lastRunAt).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul' })}. Bu oturumda kabulü kaydedilen: {state.sent || 0}; gönderilemeyen: {state.failed || 0}.</p>}
  </div>;
}
