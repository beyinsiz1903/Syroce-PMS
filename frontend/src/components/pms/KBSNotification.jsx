import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { pingExtension, sendViaExtension, buildKbsBody } from '@/lib/kbsExtensionBridge';
import KBSCloudSettings from './KBSCloudSettings';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import KBSGuestFields from './KBSGuestFields';
import { emptyKbsIdentity } from '@/lib/kbsIdentity';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Shield, Send, CheckCircle,
  Search, UserCog, Loader2, RefreshCw, Download
} from 'lucide-react';



const getApiErrorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) return detail.message;
    if (typeof detail.msg === 'string' && detail.msg.trim()) return detail.msg;
    if (typeof detail.error === 'string' && detail.error.trim()) return detail.error;
  }
  if (typeof error?.message === 'string' && error.message.trim()) return error.message;
  return fallback;
};

const cleanKbsError = (error, fallback = 'KBS gönderimi doğrulanamadı') => {
  const value = String(error || '').trim();
  if (!value) return fallback;
  if (value === 'delivery_unknown_check_authority') return 'Teslim sonucu belirsiz. Mükerrer bildirim oluşturmamak için kurum kaydı kontrol edilene kadar tekrar gönderim durduruldu.';
  const cleaned = value
    .replace(/(?:&lt;|<)br\s*\/?(?:&gt;|>)/gi, ' ')
    .replace(/^jandarma_girdihatasi\s*:\s*/i, 'Jandarma veri hatası: ')
    .replace(/^jandarma_yetkihatasi\s*:\s*/i, 'Jandarma yetki hatası: ')
    .replace(/^jandarma_kullanicihatasi\s*:\s*/i, 'Jandarma kullanıcı hatası: ')
    .replace(/\s+/g, ' ')
    .trim();
  const normalized = cleaned.toLocaleLowerCase('tr-TR');
  if (normalized.includes('müşteri tesiste zaten kayıtlı') || normalized.includes('musteri tesiste zaten kayitli')) {
    return 'Jandarma KBS aynı misafir için tesiste açık kayıt olduğunu bildirdi; tekrar gönderim durduruldu.';
  }
  if (normalized.includes('string or binary data would be truncated')) {
    return 'Jandarma KBS bir alanı kabul ettiği uzunluğun üzerinde buldu. Misafir bilgisini yenileyip tekrar deneyin.';
  }
  return cleaned;
};

const isRemoteAlreadyRegisteredKbsError = (error) => {
  const value = String(error || '').toLocaleLowerCase('tr-TR');
  return value.includes('müşteri tesiste zaten kayıtlı') || value.includes('musteri tesiste zaten kayitli');
};

const isPayloadRefreshKbsError = (error) => (
  String(error || '').toLowerCase().includes('string or binary data would be truncated')
);

const isPermanentKbsError = (error) => {
  const value = String(error || '').trim().toLowerCase();
  if (!value) return false;
  if (isRemoteAlreadyRegisteredKbsError(error) || isPayloadRefreshKbsError(error)) return true;
  return [
    'jandarma_girdihatasi',
    'jandarma_yetkihatasi',
    'jandarma_kullanicihatasi',
    'payload_incomplete',
    'unconfigured',
    'password_required',
    'confirmation_required',
    'endpoint_invalid',
    'endpoint_not_allowed',
    'bad_body',
    'invalid_',
    'missing_',
    'unsupported_',
    'foreign_guest_name_requires_surname',
    'http 4',
  ].some((prefix) => value.startsWith(prefix));
};

const isTurkishGuest = (guest) => {
  const nationality = String(guest?.nationality || '').trim().toUpperCase()
    .replaceAll('Ç', 'C').replaceAll('Ğ', 'G').replaceAll('İ', 'I')
    .replaceAll('Ö', 'O').replaceAll('Ş', 'S').replaceAll('Ü', 'U');
  return ['', 'TC', 'TR', 'TUR', 'TURKIYE'].includes(nationality);
};

const hasMissingKbsData = (guest) => Array.isArray(guest?.missing_fields)
  ? guest.missing_fields.length > 0
  : !guest?.id_number || (!isTurkishGuest(guest) && !guest?.birth_date);

const kbsDeliveryKey = (row) => {
  const bookingId = String(row?.booking_id || row?.id || '');
  const guestId = String(row?.guest_id || '');
  const action = String(row?.kbs_action || row?.action || 'checkin');
  return bookingId ? `${bookingId}:${guestId}:${action}` : '';
};

const reasonText = (row) => ({
  missing_data: 'Eksik veya geçersiz misafir bilgisi — tamamlanmalı.',
  already_registered: 'Kurum aynı kimlik için tesiste açık kayıt bildirdi. Yeni gönderimden önce kurum kaydı uzlaştırılmalı.',
  delivery_uncertain: 'Teslim sonucu belirsiz — mükerrer kayıt oluşturmamak için kurumdan kontrol edilmeli.',
  awaiting_checkin: 'Bu misafirin giriş kabulü alınmadan çıkış gönderilemez.',
  authority_rejected: 'Kurum veya gönderici bildirimi reddetti — kayıt ve bağlantı bilgileri kontrol edilmeli.',
  processing: 'Gönderim sürüyor; kurum kabulü henüz alınmadı.',
  test_only: 'Test sonucu resmî bildirim değildir.',
  awaiting_delivery: 'Kurum kabulü henüz alınmadı. Gönderim bağlantısı ve otomatik gönderici kontrol edilmeli.',
}[row.status_reason] || 'Gönderim sonucu doğrulanamadı.');

const readTenantKbsSetting = (name, tenantId) => {
  const scoped = localStorage.getItem(`${name}:${tenantId || 'default'}`);
  // Eski surumlerde ayar otel baglamindan bagimsiz tutuluyordu. Ilk okumada
  // geriye donuk uyumluluk sagla; bundan sonraki yazmalar tenant'a ozeldir.
  return scoped ?? localStorage.getItem(name);
};

const KBSNotification = ({ tenantId = '' }) => {
  const { t } = useTranslation();
  const tk = (k) => t(`pmsComponents.kbs.${k}`);

  const [pendingGuests, setPendingGuests] = useState([]);
  const pendingGuestsRef = useRef([]);
  const [sentHistory, setSentHistory] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState('pending');
  const [sending, setSending] = useState(false);
  const [editDialog, setEditDialog] = useState(null);
  const [editForm, setEditForm] = useState(emptyKbsIdentity);
  const [savingGuestInfo, setSavingGuestInfo] = useState(false);

  // Faz 1 kuyruk altyapısı entegrasyonu
  const [queueLoading, setQueueLoading] = useState(false);
  const [listError, setListError] = useState(false);
  const [page, setPage] = useState(0);
  const [listMeta, setListMeta] = useState({ counts: { sent: 0, not_sent: 0 }, has_more: false, hidden_unresolved_count: 0 });
  const [cloudStatus, setCloudStatus] = useState(null);
  const listRequestRef = useRef(0);
  const listTenantRef = useRef(tenantId);

  // KBS tarayici eklentisi (otel IP'sinden gonderim) entegrasyonu
  const [extInfo, setExtInfo] = useState({ present: false, state: 'absent', states: {}, version: '', installId: '' });
  // Secili makam: 'polis' (Emniyet/EGM) | 'jandarma'. Otel adresine gore secilir.
  const [authority, setAuthority] = useState(() => {
    try {
      return readTenantKbsSetting('kbs_ext_authority', tenantId) === 'jandarma' ? 'jandarma' : 'polis';
    } catch { return 'polis'; }
  });
  const [downloadingExt, setDownloadingExt] = useState(false);
  const [autoSend, setAutoSend] = useState(() => {
    try { return readTenantKbsSetting('kbs_ext_autosend', tenantId) === '1'; } catch { return false; }
  });
  const [draining, setDraining] = useState(false);
  const [lastDrain, setLastDrain] = useState(null);
  const drainingRef = useRef(false);

  useEffect(() => {
    listTenantRef.current = tenantId;
    listRequestRef.current += 1;
    setCloudStatus(null);
    setPendingGuests([]); setSentHistory([]); setEditDialog(null); setEditForm(emptyKbsIdentity()); setPage(0);
    try {
      setAuthority(readTenantKbsSetting('kbs_ext_authority', tenantId) === 'jandarma' ? 'jandarma' : 'polis');
      setAutoSend(readTenantKbsSetting('kbs_ext_autosend', tenantId) === '1');
    } catch {
      setAuthority('polis');
      setAutoSend(false);
    }
  }, [tenantId]);

  const fetchQueue = useCallback(async () => {
    const requestId = ++listRequestRef.current;
    setQueueLoading(true);
    try {
      const res = await axios.get('/kbs/notifications', {
        params: { group: activeTab === 'sent' ? 'sent' : 'not_sent', skip: page * 50, limit: 50 },
      });
      if (requestId !== listRequestRef.current || tenantId !== listTenantRef.current) return;
      if (!Array.isArray(res.data?.items)) throw new Error('invalid_notification_list');
      const rows = res.data.items.map(item => ({
        ...item, kbs_action: item.action, kbs_status: item.delivery_group === 'sent' ? 'sent' : 'pending',
        kbs_sent_at: item.completed_at,
      }));
      setPendingGuests(rows.filter(row => row.delivery_group === 'not_sent'));
      setSentHistory(rows.filter(row => row.delivery_group === 'sent'));
      setListMeta(res.data);
      setListError(false);
    } catch {
      if (requestId === listRequestRef.current) setListError(true); // Never show failure as empty/successful.
    } finally { if (requestId === listRequestRef.current) setQueueLoading(false); }
  }, [activeTab, page, tenantId]);

  useEffect(() => {
    fetchQueue();
    let id = null;
    const start = () => {
      if (id !== null) return;
      id = setInterval(fetchQueue, 30000);
    };
    const stop = () => {
      if (id !== null) {
        clearInterval(id);
        id = null;
      }
    };
    const onVisibility = () => {
      if (document.hidden) {
        stop();
      } else {
        fetchQueue();
        start();
      }
    };
    if (!document.hidden) start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [fetchQueue]);

  const refreshExt = useCallback(async () => {
    try {
      const info = await pingExtension();
      setExtInfo(info);
    } catch {
      setExtInfo({ present: false, state: 'absent', states: {}, version: '', installId: '' });
    }
  }, []);

  useEffect(() => { refreshExt(); }, [refreshExt]);

  // Secili makamin durumu. Eski (v1.0) eklenti yalnizca tekil 'state' dondurur ->
  // bu Polis profiline esittir (geriye uyumluluk).
  const authorityState = (extInfo.states && extInfo.states[authority])
    || (authority === 'polis' ? extInfo.state : 'absent')
    || 'absent';
  // Test modu hiçbir zaman operasyonel gönderim olarak kabul edilmez.
  const extReady = !cloudStatus?.managed && extInfo.present && authorityState === 'configured';

  const newIdemKey = () => (
    (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : String(Date.now()) + '-' + Math.random().toString(16).slice(2)
  );

  useEffect(() => {
    pendingGuestsRef.current = pendingGuests;
  }, [pendingGuests]);

  const markBookingSent = useCallback((job, reference) => {
    const bookingId = String(job?.booking_id || '');
    if (!bookingId) return;
    const existingPending = pendingGuestsRef.current.find(row => (
      kbsDeliveryKey(row) === kbsDeliveryKey(job)
      || (!job?.guest_id
        && String(row?.booking_id || row?.id || '') === bookingId
        && String(row?.kbs_action || 'checkin') === String(job?.action || 'checkin'))
    ));
    const deliveryKey = kbsDeliveryKey(existingPending || job);
    const sentAt = new Date().toISOString();
    const sentGuest = {
      id: job.booking_id,
      booking_id: job.booking_id,
      guest_id: job.guest_id || existingPending?.guest_id,
      guest_name: job.payload?.guest_name || existingPending?.guest_name || tk('unknown'),
      room_number: job.payload?.room_number || existingPending?.room_number || '-',
      check_in: job.payload?.check_in || existingPending?.check_in,
      check_out: job.payload?.check_out || existingPending?.check_out,
      nationality: job.payload?.nationality || existingPending?.nationality || 'TR',
      id_number: job.payload?.id_number || existingPending?.id_number || '',
      birth_date: job.payload?.birth_date || existingPending?.birth_date || '',
      kbs_status: 'sent',
      kbs_sent_at: sentAt,
      kbs_reference: reference,
      kbs_action: job.action || 'checkin',
    };

    setPendingGuests(prev => prev.filter(row => kbsDeliveryKey(row) !== deliveryKey));
    setSentHistory(prev => {
      const existing = prev.find(row => kbsDeliveryKey(row) === deliveryKey);
      return [
        { ...sentGuest, ...(existing || {}), kbs_status: 'sent', kbs_sent_at: sentAt, kbs_reference: reference },
        ...prev.filter(row => kbsDeliveryKey(row) !== deliveryKey),
      ];
    });
  // tk is used only for a defensive fallback label and does not affect identity.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Tek isi: claim -> eklenti ile EGM'ye gonder -> complete/fail.
  const processJobViaExtension = useCallback(async (job, workerId) => {
    let claimed = null;
    try {
      const c = await axios.post(`/kbs/queue/${job.id}/claim`, {
        worker_id: workerId, lease_seconds: 300,
      });
      claimed = c.data?.job;
    } catch (error) {
      if (error?.response?.status === 409) {
        return { status: 'skipped', reference: '', error: '' }; // baska worker / backoff / kapali
      }
      return {
        status: 'fail',
        reference: '',
        error: getApiErrorMessage(error, 'KBS işi gönderim için hazırlanamadı'),
      };
    }
    if (!claimed) return { status: 'skipped', reference: '', error: '' };

    const body = buildKbsBody(claimed.payload, claimed.action || 'checkin');
    const idem = newIdemKey();
    let sent;
    try {
      sent = await sendViaExtension(body, authority);
    } catch (error) {
      const extensionError = error?.message || 'extension_send_failed';
      try {
        await axios.post(`/kbs/queue/${job.id}/fail`,
          { worker_id: workerId, error: 'delivery_unknown_check_authority', retry: false, delivery_uncertain: true },
          { headers: { 'Idempotency-Key': idem } });
      } catch {
        // Sunucu fail kaydi da ulasilamazsa lease bitiminde is yeniden alinabilir.
      }
      return {
        status: 'fail',
        reference: '',
        error: cleanKbsError(extensionError, 'KBS eklentisi bildirimi tamamlayamadi'),
      };
    }

    if (sent.test || sent.reference?.startsWith('TEST-')) {
      try {
        await axios.post(`/kbs/queue/${job.id}/fail`,
          { worker_id: workerId, error: 'Test modu sonucu production bildirimi değildir', retry: false },
          { headers: { 'Idempotency-Key': idem } });
      } catch {
        // lease süresi dolunca sunucu işi tekrar görünür yapar
      }
      return { status: 'test', reference: sent.reference || '', error: 'Test modu sonucu production bildirimi değildir' };
    }

    if (sent.ok && sent.reference) {
      try {
        await axios.post(`/kbs/queue/${job.id}/complete`,
          {
            worker_id: workerId,
            kbs_reference: sent.reference,
            authority,
            official_reference: sent.officialReference,
            authority_response_code: (sent.responseCode || '').slice(0, 100),
            authority_response_message: (sent.responseMessage || '').slice(0, 500),
          },
          { headers: { 'Idempotency-Key': idem } });
        markBookingSent(claimed, sent.reference);
        return { status: 'ok', reference: sent.reference, error: '' };
      } catch (error) {
        try {
          await axios.post(`/kbs/queue/${job.id}/fail`,
            { worker_id: workerId, error: 'delivery_unknown_check_authority', retry: false, delivery_uncertain: true },
            { headers: { 'Idempotency-Key': newIdemKey() } });
        } catch { /* Already completed or offline: never resend this uncertain lease. */ }
        return {
          status: 'fail',
          reference: '',
          error: getApiErrorMessage(error, 'KBS kabulü kaydedilemedi'),
        };
      }
    }
    const sendError = cleanKbsError(sent.error, 'KBS kurumu gönderimi reddetti');
    try {
      await axios.post(`/kbs/queue/${job.id}/fail`,
        {
          worker_id: workerId,
          error: sent.error || 'extension_send_failed',
          retry: !isPermanentKbsError(sent.error),
        },
        { headers: { 'Idempotency-Key': idem } });
    } catch {
      // fail kaydi yazilamadi: lease suresi dolunca tekrar denenir
    }
    return { status: 'fail', reference: '', error: sendError };
  }, [authority, markBookingSent]);

  const drainViaExtension = useCallback(async () => {
    if (!extReady || !extInfo.installId) return;
    if (drainingRef.current) return;
    drainingRef.current = true;
    setDraining(true);
    const workerId = `ext:${extInfo.installId}`;
    let ok = 0, fail = 0;
    try {
      const res = await axios.get('/kbs/queue', { params: { status: 'pending', limit: 20 } });
      const jobs = res.data?.jobs || [];
      for (const job of jobs) {
        const r = await processJobViaExtension(job, workerId);
        if (r?.status === 'ok') ok++;
        else if (r?.status === 'fail' || r?.status === 'test') fail++;
      }
    } catch {
      // listeleme hatasi -> sessiz, sonraki turda tekrar denenir
    } finally {
      drainingRef.current = false;
      setDraining(false);
      setLastDrain({ ok, fail, at: new Date().toISOString() });
      fetchQueue();
    }
  }, [extReady, extInfo.installId, processJobViaExtension, fetchQueue]);

  const toggleAutoSend = () => {
    setAutoSend((prev) => {
      const next = !prev;
      try { localStorage.setItem(`kbs_ext_autosend:${tenantId || 'default'}`, next ? '1' : '0'); } catch { /* yoksay */ }
      return next;
    });
  };

  const changeAuthority = (a) => {
    const next = a === 'jandarma' ? 'jandarma' : 'polis';
    setAuthority(next);
    try { localStorage.setItem(`kbs_ext_authority:${tenantId || 'default'}`, next); } catch { /* yoksay */ }
  };

  // KBS tarayici eklenti paketini (ZIP) backend'den indir.
  const downloadExtension = async () => {
    setDownloadingExt(true);
    try {
      const res = await axios.get('/kbs/extension/download', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'syroce-kbs-eklentisi.zip';
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Safari indirme islemini asenkron baslatabildigi icin object URL'yi
      // ayni tick'te iptal etmek indirmeyi aralikli olarak bozabiliyor.
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success('Eklenti paketi indirildi');
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Eklenti paketi indirilemedi');
    } finally {
      setDownloadingExt(false);
    }
  };

  // Eklenti durumunu periyodik tazele + otomatik gonderim acikken kuyrugu boalt.
  useEffect(() => {
    const id = setInterval(() => {
      if (document.hidden) return;
      refreshExt();
      if (autoSend) drainViaExtension();
    }, 30000);
    if (!document.hidden && autoSend) drainViaExtension();
    return () => clearInterval(id);
  }, [autoSend, refreshExt, drainViaExtension]);

  const sendToKBS = async (guest) => {
    setSending(true);
    try {
      const res = await axios.post('/kbs/queue', {
        booking_id: guest.booking_id || guest.id,
        action: guest.kbs_action || 'checkin',
        guest_id: guest.guest_id || undefined,
      });
      const job = res.data?.job;
      if (cloudStatus?.managed) {
        toast.info(cloudStatus.enabled ? 'Bildirim sunucu kuyruğunda; kurum kabulünü kuyruktan takip edin.' : 'Bildirim kuyrukta bekliyor. Sunucu bağlantısı doğrulanıp etkinleştirilmeli.');
        return;
      }
      if (!extReady || !extInfo.installId) {
        toast.info('Bildirim kuyruğa eklendi; henüz kuruma gönderilmedi. Canlı moddaki resepsiyon eklentisi gönderecek.');
        return;
      }
      const result = job
        ? await processJobViaExtension(job, `ext:${extInfo.installId}`)
        : { status: 'fail' };
      if (result?.status === 'ok') {
        toast.success(`${guest.guest_name} için KBS kabulü doğrulandı. Yerel teslim kaydı: ${result.reference}`);
      } else if (result?.status === 'test') {
        toast.error('Test modu sonucu gönderilmiş sayılmadı. Eklentiyi canlı moda alın.');
      } else {
        toast.error(cleanKbsError(result?.error, 'KBS gönderimi doğrulanamadı; kayıt başarılı olarak işaretlenmedi.'));
      }
    } catch (error) {
      toast.error(getApiErrorMessage(error, tk('sendError')));
    } finally {
      fetchQueue();
      setSending(false);
    }
  };

  const openEditDialog = (guest) => {
    setEditForm({ ...emptyKbsIdentity(), nationality: guest.nationality || 'TR',
      id_type: guest.id_type || (isTurkishGuest(guest) ? 'tc_kimlik' : 'passport') });
    setEditDialog(guest);
  };

  const saveGuestInfo = async () => {
    if (!editDialog) return;
    setSavingGuestInfo(true);
    try {
      const { birth_date, ...fields } = editForm;
      const body = Object.fromEntries(Object.entries({ ...fields, date_of_birth: birth_date })
        .map(([key, value]) => [key, String(value || '').trim()]).filter(([, value]) => value));
      await axios.put(`/kbs/booking/${encodeURIComponent(editDialog.booking_id)}/guests/${encodeURIComponent(editDialog.guest_id)}/identity`, body);
      setEditDialog(null);
      setEditForm(emptyKbsIdentity());
      toast.success(tk('updateSuccess'));
      await fetchQueue();
    } catch (error) {
      toast.error(getApiErrorMessage(error, tk('updateError')));
    } finally { setSavingGuestInfo(false); }
  };

  const filteredPending = pendingGuests.filter(g =>
    !searchTerm || g.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) || String(g.room_number).includes(searchTerm)
  );
  const filteredSent = sentHistory.filter(g =>
    !searchTerm || g.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) || String(g.room_number).includes(searchTerm)
  );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold flex items-center gap-2"><Shield className="h-5 w-5" /> {tk('title')}</h2>
        <Button type="button" variant="outline" onClick={fetchQueue} disabled={queueLoading} aria-label="KBS bildirimlerini yenile">
          <RefreshCw className={queueLoading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} /> Yenile
        </Button>
      </div>
      <p className="text-sm text-gray-600">Giriş ve çıkış bildirimleri otomatik hazırlanır. Yalnız kurum kabulü alınanlar gönderilmiş sayılır. Misafirler gerçek çıkışlarından 24 saat sonra bu listeden kalkar; teslim ve denetim kayıtları silinmez.</p>
      {!!listMeta.hidden_unresolved_count && <p role="status" className="text-sm text-amber-700">
        Görünürlük süresi dolmuş {listMeta.hidden_unresolved_count} bildirim hâlâ sonuçlanmamış. Kişi bilgileri ana listede gösterilmez; yönetici denetim kayıtlarından takip etmelidir.
      </p>}
      <details className="rounded border p-3">
        <summary className="cursor-pointer text-sm font-medium">Bağlantı ve gönderim ayarları</summary>
      <KBSCloudSettings key={tenantId} tenantId={tenantId} onStatusChange={setCloudStatus} />
      {!cloudStatus?.managed && <div className="rounded-lg border bg-gray-50 p-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="text-xs font-semibold text-gray-700 flex items-center gap-2">
            <Shield className="w-4 h-4 text-gray-500" />
            KBS Tarayici Eklentisi
            {extInfo.present ? (
              <Badge className={
                authorityState === 'configured' ? 'bg-green-100 text-green-800'
                  : authorityState === 'test' ? 'bg-blue-100 text-blue-800'
                    : 'bg-amber-100 text-amber-800'
              }>
                {authorityState === 'configured' ? `Bagli v${extInfo.version}`
                  : authorityState === 'test' ? `Test modu v${extInfo.version}`
                    : authorityState === 'password_required' ? 'Web servis sifresi gerekli'
                      : authorityState === 'confirmation_required' ? 'Canli gonderim onayi gerekli'
                        : 'Yapilandirilmamis'}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-gray-500">Kurulu degil</Badge>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1">
              <span className="text-[11px] text-gray-500">Makam:</span>
              <Button variant={authority === 'polis' ? 'default' : 'outline'} size="sm"
                className="h-7 px-2 text-xs" onClick={() => changeAuthority('polis')}>
                Polis
              </Button>
              <Button variant={authority === 'jandarma' ? 'default' : 'outline'} size="sm"
                className="h-7 px-2 text-xs" onClick={() => changeAuthority('jandarma')}>
                Jandarma
              </Button>
            </div>
            <Button variant="outline" size="sm" className="h-7 px-2 text-xs"
              onClick={downloadExtension} disabled={downloadingExt}>
              <Download className={`w-3 h-3 mr-1 ${downloadingExt ? 'animate-pulse' : ''}`} />
              Eklentiyi indir
            </Button>
            {authority === 'polis' && (
              <Button variant="outline" size="sm" className="h-7 px-2 text-xs"
                onClick={() => window.open('https://kbs.egm.gov.tr/', '_blank', 'noopener,noreferrer')}>
                EGM KBS girisini ac
              </Button>
            )}
            {extReady && (
              <>
                <Button variant={autoSend ? 'default' : 'outline'} size="sm"
                  className="h-7 px-2 text-xs" onClick={toggleAutoSend}>
                  {autoSend ? 'Otomatik gonderim: Acik' : 'Otomatik gonderim: Kapali'}
                </Button>
                <Button variant="outline" size="sm" className="h-7 px-2 text-xs"
                  onClick={drainViaExtension} disabled={draining}>
                  <Send className={`w-3 h-3 mr-1 ${draining ? 'animate-pulse' : ''}`} />
                  Simdi gonder
                </Button>
              </>
            )}
          </div>
        </div>
        <p className="text-[11px] text-gray-500 mt-1">
          {extInfo.present
            ? authority === 'polis'
              ? 'Polis bildirimleri bu tarayicidaki EGM KBS oturumuyla iletilir. KBS sekmesinin acik kalmasi gerekmez; oturum sona ererse EGMSEC ile yeniden giris yapin. E-Devlet ve EGMSEC bilgileri Syroce tarafindan saklanmaz.'
              : 'Bildirimler resepsiyon bilgisayarinin tarayicisindan Jandarma KBS sistemine iletilir. Web servis sifresi tarayici kapaninca silinir ve yeniden girilmelidir.'
            : 'Eklenti kurulu degil. "Eklentiyi indir" ile paketi alip Chrome/Edge > Eklentiler > Gelistirici modu > Paketlenmemis yukle ile kurun. Kuyruktaki bildirimler eklenti kurulup acilana kadar bekler.'}
          {lastDrain && ` Son gonderim: ${new Date(lastDrain.at).toLocaleTimeString()} - basarili ${lastDrain.ok}, hata ${lastDrain.fail}.`}
        </p>
      </div>}


      </details>
      <div className="relative">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
        <Input aria-label="Misafir veya oda ara" value={searchTerm} onChange={e => setSearchTerm(e.target.value)} placeholder="Misafir veya oda ara" className="pl-9" />
      </div>
      {listError && <div role="alert" className="rounded border border-red-300 p-3 text-red-700">Bildirim listesi yenilenemedi. Görünen bilgiler eski olabilir; gönderilmiş varsaymayın.</div>}
      <Tabs value={activeTab} onValueChange={tab => { setActiveTab(tab); setPage(0); }}>
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="sent">Gönderilen ({listMeta.counts?.sent || 0})</TabsTrigger>
          <TabsTrigger value="pending">Gönderilmeyen ({listMeta.counts?.not_sent || 0})</TabsTrigger>
        </TabsList>
        <TabsContent value="pending" className="space-y-2">
          {!listError && !queueLoading && !filteredPending.length && <p className="py-6 text-center text-gray-500">Bu görünümde gönderilmeyen bildirim yok.</p>}
          {filteredPending.map(guest => {
            const reason = reasonText(guest);
            const blocked = ['already_registered', 'delivery_uncertain', 'awaiting_checkin', 'test_only'].includes(guest.status_reason);
            return <Card key={kbsDeliveryKey(guest)}>
              <CardContent className="flex flex-wrap items-start justify-between gap-3 p-3">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">Oda {guest.room_number || '—'}</Badge>
                    <Badge variant="outline">{guest.kbs_action === 'checkout' ? 'Çıkış bildirimi' : 'Giriş bildirimi'}</Badge>
                  </div>
                  <p className="text-sm text-amber-800">{reason}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {guest.guest_id && listMeta.can_edit && hasMissingKbsData(guest) && <Button type="button" variant="outline" size="sm" onClick={() => openEditDialog(guest)} aria-label={`${tk('idMissing')}: ${guest.guest_name}`}>
                    <UserCog className="mr-1 h-3 w-3" /> {tk('updateInfo')}
                  </Button>}
                  {!guest.guest_id && <a className="text-sm underline" href={`/app/pms#reservations`}>Konaklayan bilgilerini tamamla</a>}
                  {!hasMissingKbsData(guest) && !blocked && guest.guest_id && <Button type="button" size="sm" onClick={() => sendToKBS(guest)} disabled={sending || guest.status === 'in_progress'}>
                    <Send className="mr-1 h-3 w-3" /> {tk('send')}
                  </Button>}
                </div>
              </CardContent>
            </Card>;
          })}
        </TabsContent>
        <TabsContent value="sent" className="space-y-2">
          {!listError && !queueLoading && !filteredSent.length && <p className="py-6 text-center text-gray-500">Bu görünümde gönderilen bildirim yok.</p>}
          {filteredSent.map(guest => <Card key={kbsDeliveryKey(guest)}>
            <CardContent className="space-y-1 p-3">
              <div className="flex flex-wrap items-center gap-2"><CheckCircle className="h-4 w-4 text-green-600" /><span className="font-medium">{guest.guest_name}</span>
                <Badge variant="outline">Oda {guest.room_number || '—'}</Badge><Badge variant="outline">{guest.kbs_action === 'checkout' ? 'Çıkış bildirimi' : 'Giriş bildirimi'}</Badge></div>
              <p className="text-sm text-green-700">Kurum kabulü alındı · {guest.kbs_sent_at ? new Date(guest.kbs_sent_at).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul' }) : 'Teslim kaydı mevcut'}</p>
            </CardContent>
          </Card>)}
        </TabsContent>
      </Tabs>
      <div className="flex justify-between gap-2">
        <Button type="button" variant="outline" disabled={!page || queueLoading} onClick={() => setPage(p => Math.max(0, p - 1))}>Önceki</Button>
        <Button type="button" variant="outline" disabled={!listMeta.has_more || queueLoading} onClick={() => setPage(p => p + 1)}>Sonraki</Button>
      </div>
      <Dialog open={!!editDialog} onOpenChange={open => { if (!open) { setEditDialog(null); setEditForm(emptyKbsIdentity()); } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{tk('updateTitle')}</DialogTitle></DialogHeader>
          {editDialog && <div className="space-y-3">
            <p>{editDialog.guest_name} · Oda {editDialog.room_number || '—'}</p>
            <p className="text-sm text-gray-600">Yalnız tamamlayacağınız alanları girin. Mevcut kimlik numaraları bu ekranda gösterilmez.</p>
            <KBSGuestFields value={editForm} onChange={setEditForm} />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => { setEditDialog(null); setEditForm(emptyKbsIdentity()); }} disabled={savingGuestInfo}>{tk('cancel')}</Button>
              <Button type="button" onClick={saveGuestInfo} disabled={savingGuestInfo}>{savingGuestInfo && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}{tk('save')}</Button>
            </div>
          </div>}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KBSNotification;
