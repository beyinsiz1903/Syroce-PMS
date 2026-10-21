import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const errors = {
  secure_storage_unavailable: 'Sunucunun güvenli anahtar saklaması yapılandırılmalı. Bilgiler açık metinle kaydedilmedi.',
  fixed_egress_ip_required: 'Önce sunucunun sabit çıkış IP’si yapılandırılmalı ve Jandarma hesabında tanımlanmalı.',
  connection_verification_required: 'Değişen bağlantı bilgilerini önce doğrulayın.',
  live_confirmation_required: 'Canlı bildirim onayı gerekli.',
  sender_busy_retry_later: 'Devam eden gönderim var; tamamlanmasını bekleyin.',
  configuration_changed_retry_verification: 'Ayarlar değişti; bağlantıyı yeniden doğrulayın.',
  delivery_unknown_check_authority: 'Bağlantı tamamlanamadı. IP yetkisini ve sunucunun erişimini kontrol edin.',
};

export default function KBSCloudSettings({ tenantId, onStatusChange }) {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ user_tc: '', facility_code: '', password: '' });
  const [open, setOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const active = useRef(true);
  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get('/kbs/cloud/status');
      if (!active.current) return;
      setStatus(data);
      onStatusChange(data);
      setLoadError(false);
    } catch {
      if (!active.current) return;
      setLoadError(true);
      onStatusChange(null);
    }
  }, [onStatusChange]);
  useEffect(() => {
    active.current = true;
    setStatus(null);
    setForm({ user_tc: '', facility_code: '', password: '' });
    setConfirmed(false);
    setOpen(false);
    refresh();
    const timer = setInterval(() => { if (!document.hidden) refresh(); }, 30000);
    return () => { active.current = false; clearInterval(timer); };
  }, [tenantId, refresh]);

  const mutate = async (path, data) => {
    setBusy(true);
    try {
      if (path === 'verify') {
        await axios.post('/kbs/cloud/verify');
        toast.success('Jandarma bağlantısı doğrulandı. Misafir bildirimi gönderilmedi.');
      } else {
        await axios.put('/kbs/cloud/settings', data);
        setForm({ user_tc: '', facility_code: '', password: '' });
        toast.success(data.enabled ? 'Sunucu gönderimi etkin. Kuyruk arka planda işlenecek.' : 'Ayarlar kaydedildi; sunucu gönderimi duraklatıldı.');
      }
      await refresh();
    } catch (error) {
      const code = error?.response?.data?.detail;
      toast.error(errors[code] || (typeof code === 'string' && code.startsWith('jandarma_')
        ? 'Jandarma bağlantıyı reddetti. Kullanıcı, tesis kodu, web servis şifresi ve kayıtlı IP’yi kontrol edin.'
        : 'KBS sunucu ayarı tamamlanamadı; gönderim etkinleştirilmedi.'));
    } finally {
      setBusy(false);
    }
  };
  const workerStale = status?.enabled && (!status.last_worker_at || Date.now() - Date.parse(status.last_worker_at) > 180000);

  return (
    <section className="rounded-lg border bg-white p-4 space-y-3" aria-label="KBS sunucu bağlantısı">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">Jandarma — bilgisayarsız sunucu gönderimi</h3>
        {status?.can_manage && <Button variant="outline" onClick={() => setOpen(!open)}>Bağlantı ayarları</Button>}
      </div>
      <p className="text-sm text-muted-foreground">
        {loadError ? 'Sunucu bağlantı durumu okunamadı. Bildirimin ulaştığını varsaymayın.'
          : !status ? 'Bağlantı durumu kontrol ediliyor…'
            : status.enabled ? 'Sunucu gönderimi etkin. Telefonda bu sayfanın açık kalması gerekmez.'
              : status.verified ? 'Bağlantı doğrulandı; canlı gönderim duraklatılmış.'
                : status.configured ? 'Ayarlar kayıtlı; bağlantı henüz doğrulanmadı. Kuyruk bekler.'
                  : 'Sunucu bağlantısı henüz kurulmadı. Mevcut eklenti bağlantısı değiştirilmedi.'}
      </p>
      {workerStale && <p role="alert" className="text-sm text-amber-700">Arka plan göndericisinden güncel çalışma bilgisi yok. Kuyruk teslimatını kontrol edin.</p>}
      {status?.last_error && <p role="alert" className="text-sm text-destructive">Bağlantı hatası: {errors[status.last_error] || 'Kurum bağlantısını doğrulayın.'}</p>}
      {open && status?.can_manage && (
        <div className="space-y-3">
          <p className="text-sm">Yalnız Jandarma bölgesindeki tesisler içindir. E-Devlet şifrenizi girmeyin. Sunucu çıkış IP’si Jandarma KBS → Web Servis İşlemleri’nde yetkilendirilmelidir.</p>
          <p className="text-sm">Yönetici tarafından tanımlanan sunucu çıkış IP’si: <strong>{status.egress_ip || 'Henüz yapılandırılmadı'}</strong></p>
          <form className="grid gap-3 sm:grid-cols-3" autoComplete="off" onSubmit={(e) => { e.preventDefault(); mutate('settings', { ...form, enabled: false }); }}>
            <div><Label htmlFor="kbs-cloud-user">Yetkili kullanıcı T.C.</Label><Input id="kbs-cloud-user" type="password" inputMode="numeric" maxLength={11} value={form.user_tc} onChange={(e) => setForm({ ...form, user_tc: e.target.value })} /></div>
            <div><Label htmlFor="kbs-cloud-facility">Tesis kodu</Label><Input id="kbs-cloud-facility" inputMode="numeric" maxLength={19} value={form.facility_code} onChange={(e) => setForm({ ...form, facility_code: e.target.value })} /></div>
            <div><Label htmlFor="kbs-cloud-password">Web servis şifresi</Label><Input id="kbs-cloud-password" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
            <p className="text-xs text-muted-foreground sm:col-span-3">Kayıtlı bilgileri korumak için boş bırakabilirsiniz. Bilgileri değiştirmek doğrulamayı ve canlı gönderimi kapatır.</p>
            <Button type="submit" disabled={busy}>Bilgileri güvenle kaydet</Button>
          </form>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={busy || !status.configured} onClick={() => mutate('verify')}>Bağlantıyı doğrula (bildirim göndermez)</Button>
            {status.enabled && <Button variant="outline" disabled={busy} onClick={() => mutate('settings', { enabled: false })}>Sunucu gönderimini duraklat</Button>}
          </div>
          {!status.enabled && <>
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> Sunucunun çıkış IP’sini Jandarma hesabında yetkilendirdim; bu tesisin gerçek giriş/çıkış bildirimlerinin gönderilmesini onaylıyorum.</label>
            <Button disabled={busy || !status.verified || !confirmed} onClick={() => mutate('settings', { enabled: true, live_confirmed: true })}>Canlı sunucu gönderimini etkinleştir</Button>
          </>}
        </div>
      )}
    </section>
  );
}
