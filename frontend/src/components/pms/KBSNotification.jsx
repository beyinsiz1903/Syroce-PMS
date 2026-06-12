import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { pingExtension, sendViaExtension, buildKbsBody } from '@/lib/kbsExtensionBridge';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Shield, Send, CheckCircle, AlertTriangle, Clock,
  Download, Search, UserCog, Loader2, RefreshCw, Skull, ListPlus
} from 'lucide-react';

const escapeXml = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');

const KBSNotification = ({ bookings = [], guests = [] }) => {
  const { t } = useTranslation();
  const tk = (k) => t(`pmsComponents.kbs.${k}`);

  const [pendingGuests, setPendingGuests] = useState([]);
  const [sentHistory, setSentHistory] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState('pending');
  const [sending, setSending] = useState(false);
  const [editDialog, setEditDialog] = useState(null);
  const [editForm, setEditForm] = useState({ id_number: '', birth_date: '' });

  // Faz 1 kuyruk altyapısı entegrasyonu
  const [queueJobs, setQueueJobs] = useState([]);
  const [queueStats, setQueueStats] = useState({
    pending: 0, in_progress: 0, done: 0, failed: 0, dead: 0,
  });
  const [queueLoading, setQueueLoading] = useState(false);
  const [enqueuingId, setEnqueuingId] = useState(null);

  // KBS tarayici eklentisi (otel IP'sinden gonderim) entegrasyonu
  const [extInfo, setExtInfo] = useState({ present: false, state: 'absent', version: '', installId: '' });
  const [autoSend, setAutoSend] = useState(() => {
    try { return localStorage.getItem('kbs_ext_autosend') === '1'; } catch { return false; }
  });
  const [draining, setDraining] = useState(false);
  const [lastDrain, setLastDrain] = useState(null);
  const drainingRef = useRef(false);

  const fetchQueue = useCallback(async () => {
    setQueueLoading(true);
    try {
      const res = await axios.get('/kbs/queue', { params: { limit: 200 } });
      setQueueJobs(res.data?.jobs || []);
      setQueueStats(res.data?.stats || {
        pending: 0, in_progress: 0, done: 0, failed: 0, dead: 0,
      });
    } catch {
      // Sessiz: ilk yüklemede backend kuyruk dolmamış olabilir
    } finally {
      setQueueLoading(false);
    }
  }, []);

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

  const enqueueBooking = async (bookingId, action = 'checkin') => {
    if (!bookingId) return;
    setEnqueuingId(bookingId);
    try {
      const res = await axios.post('/kbs/queue', {
        booking_id: bookingId, action,
      });
      toast.success(res.data?.created ? tk('addedToQueue') : tk('alreadyQueued'));
      fetchQueue();
    } catch (err) {
      toast.error(err?.response?.data?.detail || tk('addToQueueError'));
    } finally {
      setEnqueuingId(null);
    }
  };

  const retryDeadJob = async (job) => {
    // dead ya da legacy başarısız iş için: aynı booking + action ile force=true
    try {
      await axios.post('/kbs/queue', {
        booking_id: job.booking_id,
        action: job.action || 'checkin',
        force: true,
      });
      toast.success(tk('retryQueued'));
      fetchQueue();
    } catch (err) {
      toast.error(err?.response?.data?.detail || tk('retryError'));
    }
  };

  // --- KBS tarayici eklentisi: kuyrugu otel IP'sinden gonderme ---
  const refreshExt = useCallback(async () => {
    try {
      const info = await pingExtension();
      setExtInfo(info);
    } catch {
      setExtInfo({ present: false, state: 'absent', version: '', installId: '' });
    }
  }, []);

  useEffect(() => { refreshExt(); }, [refreshExt]);

  const extReady = extInfo.present && (extInfo.state === 'test' || extInfo.state === 'configured');

  const newIdemKey = () => (
    (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : String(Date.now()) + '-' + Math.random().toString(16).slice(2)
  );

  // Tek isi: claim -> eklenti ile EGM'ye gonder -> complete/fail.
  const processJobViaExtension = useCallback(async (job, workerId) => {
    let claimed = null;
    try {
      const c = await axios.post(`/kbs/queue/${job.id}/claim`, {
        worker_id: workerId, lease_seconds: 300,
      });
      claimed = c.data?.job;
    } catch {
      return 'skipped'; // 409 (baska worker / backoff / kapali) -> atla
    }
    if (!claimed) return 'skipped';

    const body = buildKbsBody(claimed.payload, claimed.action || 'checkin');
    const sent = await sendViaExtension(body);
    const idem = newIdemKey();

    if (sent.ok && sent.reference) {
      try {
        await axios.post(`/kbs/queue/${job.id}/complete`,
          { worker_id: workerId, kbs_reference: sent.reference },
          { headers: { 'Idempotency-Key': idem } });
        return 'ok';
      } catch {
        return 'fail';
      }
    }
    try {
      await axios.post(`/kbs/queue/${job.id}/fail`,
        { worker_id: workerId, error: sent.error || 'extension_send_failed', retry: true },
        { headers: { 'Idempotency-Key': idem } });
    } catch {
      // fail kaydi yazilamadi: lease suresi dolunca tekrar denenir
    }
    return 'fail';
  }, []);

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
        if (r === 'ok') ok++;
        else if (r === 'fail') fail++;
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

  const sendJobViaExtension = useCallback(async (job) => {
    if (!extReady || !extInfo.installId) {
      toast.error('KBS eklentisi kurulu/yapilandirilmis degil');
      return;
    }
    const workerId = `ext:${extInfo.installId}`;
    const r = await processJobViaExtension(job, workerId);
    if (r === 'ok') toast.success('KBS gonderimi tamamlandi');
    else if (r === 'fail') toast.error('KBS gonderimi basarisiz');
    else toast.error('Is su anda claim edilemedi (baska worker / bekleme)');
    fetchQueue();
  }, [extReady, extInfo.installId, processJobViaExtension, fetchQueue]);

  const toggleAutoSend = () => {
    setAutoSend((prev) => {
      const next = !prev;
      try { localStorage.setItem('kbs_ext_autosend', next ? '1' : '0'); } catch { /* yoksay */ }
      return next;
    });
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

  useEffect(() => {
    const checkedIn = bookings.filter(b => b.status === 'checked_in');
    const pending = checkedIn.map(b => ({
      id: b.id,
      guest_id: b.guest_id || b.guestId || b.id,
      guest_name: b.guest_name || b.guestName || tk('unknown'),
      room_number: b.room_number || b.roomNumber || '-',
      check_in: b.check_in || b.checkIn,
      check_out: b.check_out || b.checkOut,
      nationality: b.guest_nationality || b.nationality || 'TC',
      id_type: b.id_type || 'tc_kimlik',
      id_number: b.id_number || '',
      birth_date: b.birth_date || '',
      kbs_status: b.kbs_status || 'pending',
      kbs_sent_at: b.kbs_sent_at || null,
    }));
    setPendingGuests(pending.filter(p => p.kbs_status === 'pending'));
    setSentHistory(pending.filter(p => p.kbs_status !== 'pending'));
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [bookings]);

  const sendToKBS = async (guest) => {
    setSending(true);
    try {
      const res = await axios.post('/kbs/send', {
        booking_id: guest.id,
        guest_data: {
          guest_name: guest.guest_name,
          nationality: guest.nationality,
          id_number: guest.id_number,
        }
      });
      toast.success(t('pmsComponents.kbs.guestSent', { name: guest.guest_name, ref: res.data.kbs_reference }));
      setPendingGuests(prev => prev.filter(p => p.id !== guest.id));
      setSentHistory(prev => [{
        ...guest,
        kbs_status: 'sent',
        kbs_sent_at: res.data.sent_at,
        kbs_reference: res.data.kbs_reference,
      }, ...prev]);
    } catch {
      toast.error(tk('sendError'));
    } finally {
      setSending(false);
    }
  };

  const sendAllToKBS = async () => {
    const toSend = pendingGuests.filter(p => p.id_number);
    if (toSend.length === 0) {
      toast.error(tk('noValidRecords'));
      return;
    }
    setSending(true);
    try {
      const res = await axios.post('/kbs/send-batch', { booking_ids: toSend.map(p => p.id) });
      toast.success(t('pmsComponents.kbs.guestsSent', { count: res.data.count }));
      const sentIds = new Set(toSend.map(p => p.id));
      const sentResults = res.data.results || [];
      setPendingGuests(prev => prev.filter(p => !sentIds.has(p.id)));
      setSentHistory(prev => [
        ...toSend.map(g => {
          const r = sentResults.find(sr => sr.booking_id === g.id);
          return { ...g, kbs_status: 'sent', kbs_sent_at: res.data.sent_at, kbs_reference: r?.kbs_reference || '' };
        }),
        ...prev
      ]);
    } catch {
      toast.error(tk('batchError'));
    } finally {
      setSending(false);
    }
  };

  const downloadXML = () => {
    const xmlLines = ['<?xml version="1.0" encoding="UTF-8"?>', '<KBSBildirimler>'];
    pendingGuests.filter(g => g.id_number).forEach(g => {
      xmlLines.push('  <Misafir>');
      xmlLines.push(`    <AdSoyad>${escapeXml(g.guest_name)}</AdSoyad>`);
      xmlLines.push(`    <KimlikNo>${escapeXml(g.id_number)}</KimlikNo>`);
      xmlLines.push(`    <Uyruk>${escapeXml(g.nationality)}</Uyruk>`);
      xmlLines.push(`    <OdaNo>${escapeXml(g.room_number)}</OdaNo>`);
      xmlLines.push(`    <GirisTarihi>${escapeXml(g.check_in)}</GirisTarihi>`);
      xmlLines.push(`    <CikisTarihi>${escapeXml(g.check_out)}</CikisTarihi>`);
      xmlLines.push('  </Misafir>');
    });
    xmlLines.push('</KBSBildirimler>');
    const blob = new Blob([xmlLines.join('\n')], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kbs_notification_${new Date().toISOString().split('T')[0]}.xml`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(tk('xmlDownloaded'));
  };

  const openEditDialog = (guest) => {
    setEditForm({ id_number: guest.id_number || '', birth_date: guest.birth_date || '' });
    setEditDialog(guest);
  };

  const saveGuestInfo = async () => {
    if (!editDialog) return;
    try {
      await axios.patch(`/pms/guests/${editDialog.guest_id}/preferences`, {
        id_number: editForm.id_number,
        birth_date: editForm.birth_date,
      });
      setPendingGuests(prev => prev.map(p =>
        p.id === editDialog.id ? { ...p, id_number: editForm.id_number, birth_date: editForm.birth_date } : p
      ));
      toast.success(tk('updateSuccess'));
      setEditDialog(null);
    } catch {
      toast.error(tk('updateError'));
    }
  };

  const filteredPending = pendingGuests.filter(g =>
    !searchTerm || g.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) || String(g.room_number).includes(searchTerm)
  );
  const filteredSent = sentHistory.filter(g =>
    !searchTerm || g.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) || String(g.room_number).includes(searchTerm)
  );
  const missingData = pendingGuests.filter(g => !g.id_number || !g.birth_date);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Shield className="h-5 w-5" /> {tk('title')}
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={downloadXML} disabled={pendingGuests.filter(p => p.id_number).length === 0}>
            <Download className="h-4 w-4 mr-1" /> {tk('downloadXml')}
          </Button>
          <Button onClick={sendAllToKBS} disabled={pendingGuests.length === 0 || sending}>
            <Send className="h-4 w-4 mr-1" /> {tk('sendAll')} ({pendingGuests.filter(p => p.id_number).length})
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-yellow-50 border-yellow-200">
          <CardContent className="p-3 text-center">
            <Clock className="w-5 h-5 mx-auto mb-1 text-yellow-600" />
            <p className="text-2xl font-bold text-yellow-700">{pendingGuests.length}</p>
            <p className="text-xs text-yellow-600">{tk('pendingNotif')}</p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200">
          <CardContent className="p-3 text-center">
            <CheckCircle className="w-5 h-5 mx-auto mb-1 text-green-600" />
            <p className="text-2xl font-bold text-green-700">{sentHistory.length}</p>
            <p className="text-xs text-green-600">{tk('sentNotif')}</p>
          </CardContent>
        </Card>
        <Card className="bg-red-50 border-red-200">
          <CardContent className="p-3 text-center">
            <AlertTriangle className="w-5 h-5 mx-auto mb-1 text-red-600" />
            <p className="text-2xl font-bold text-red-700">{missingData.length}</p>
            <p className="text-xs text-red-600">{tk('missingInfo')}</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-3 text-center">
            <Shield className="w-5 h-5 mx-auto mb-1 text-blue-600" />
            <p className="text-2xl font-bold text-blue-700">{pendingGuests.filter(g => g.nationality !== 'TC').length}</p>
            <p className="text-xs text-blue-600">{tk('foreignNational')}</p>
          </CardContent>
        </Card>
      </div>

      {/* Faz 3: Agent Kuyruğu Durum Çubuğu */}
      <div className="rounded-lg border bg-gray-50 p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-semibold text-gray-700 flex items-center gap-2">
            <ListPlus className="w-4 h-4 text-gray-500" />
            {tk('queueStatusBar')}
          </div>
          <Button variant="ghost" size="sm" onClick={fetchQueue} disabled={queueLoading}
            className="h-7 px-2 text-xs">
            <RefreshCw className={`w-3 h-3 mr-1 ${queueLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
        <div className="grid grid-cols-5 gap-2">
          <div className="text-center bg-white rounded border-yellow-200 border p-2">
            <Clock className="w-4 h-4 mx-auto text-yellow-600" />
            <p className="text-lg font-bold text-yellow-700">{queueStats.pending || 0}</p>
            <p className="text-[10px] text-yellow-700">{tk('qPending')}</p>
          </div>
          <div className="text-center bg-white rounded border-blue-200 border p-2">
            <Loader2 className="w-4 h-4 mx-auto text-blue-600" />
            <p className="text-lg font-bold text-blue-700">{queueStats.in_progress || 0}</p>
            <p className="text-[10px] text-blue-700">{tk('qInProgress')}</p>
          </div>
          <div className="text-center bg-white rounded border-green-200 border p-2">
            <CheckCircle className="w-4 h-4 mx-auto text-green-600" />
            <p className="text-lg font-bold text-green-700">{queueStats.done || 0}</p>
            <p className="text-[10px] text-green-700">{tk('qDone')}</p>
          </div>
          <div className="text-center bg-white rounded border-amber-200 border p-2">
            <AlertTriangle className="w-4 h-4 mx-auto text-amber-600" />
            <p className="text-lg font-bold text-amber-700">{queueStats.failed || 0}</p>
            <p className="text-[10px] text-amber-700">{tk('qFailed')}</p>
          </div>
          <div className="text-center bg-white rounded border-red-200 border p-2">
            <Skull className="w-4 h-4 mx-auto text-red-600" />
            <p className="text-lg font-bold text-red-700">{queueStats.dead || 0}</p>
            <p className="text-[10px] text-red-700">{tk('qDead')}</p>
          </div>
        </div>
      </div>

      {/* KBS tarayici eklentisi: otelin IP adresinden gonderim */}
      <div className="rounded-lg border bg-gray-50 p-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="text-xs font-semibold text-gray-700 flex items-center gap-2">
            <Shield className="w-4 h-4 text-gray-500" />
            KBS Tarayici Eklentisi
            {extInfo.present ? (
              <Badge className={
                extInfo.state === 'configured' ? 'bg-green-100 text-green-800'
                  : extInfo.state === 'test' ? 'bg-blue-100 text-blue-800'
                    : 'bg-amber-100 text-amber-800'
              }>
                {extInfo.state === 'configured' ? `Bagli v${extInfo.version}`
                  : extInfo.state === 'test' ? `Test modu v${extInfo.version}`
                    : 'Yapilandirilmamis'}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-gray-500">Kurulu degil</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
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
            ? 'Bildirimler resepsiyon bilgisayarinin tarayicisindan (otelin IP adresi) Emniyet KBS sistemine iletilir.'
            : 'Eklenti kurulu degil. Kuyruktaki bildirimler eklenti kurulup acilana kadar bekler (kurulum: extension/ klasoru).'}
          {lastDrain && ` Son gonderim: ${new Date(lastDrain.at).toLocaleTimeString()} - basarili ${lastDrain.ok}, hata ${lastDrain.fail}.`}
        </p>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <Input className="pl-9" placeholder={tk('searchPlaceholder')} value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="pending">{tk('pendingTab')} ({pendingGuests.length})</TabsTrigger>
          <TabsTrigger value="sent">{tk('sentTab')} ({sentHistory.length})</TabsTrigger>
          <TabsTrigger value="missing">{tk('missingTab')} ({missingData.length})</TabsTrigger>
          <TabsTrigger value="queue">{tk('queueTab')} ({queueJobs.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="space-y-2">
          {filteredPending.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <Shield className="w-10 h-10 mx-auto mb-2 text-gray-300" />
              <p>{tk('noPending')}</p>
            </div>
          ) : filteredPending.map(guest => (
            <Card key={guest.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">{tk('room')} {guest.room_number}</Badge>
                    <Badge variant="secondary">{guest.nationality}</Badge>
                    {!guest.id_number && <Badge variant="destructive">{tk('idMissing')}</Badge>}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {tk('checkinDate')} {guest.check_in ? new Date(guest.check_in).toLocaleDateString() : '-'} |
                    {tk('checkoutDate')} {guest.check_out ? new Date(guest.check_out).toLocaleDateString() : '-'}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="outline"
                    onClick={() => enqueueBooking(guest.id, 'checkin')}
                    disabled={enqueuingId === guest.id}>
                    <ListPlus className="h-3 w-3 mr-1" /> {tk('addToQueue')}
                  </Button>
                  <Button size="sm" onClick={() => sendToKBS(guest)} disabled={!guest.id_number || sending}>
                    <Send className="h-3 w-3 mr-1" /> {tk('send')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="sent" className="space-y-2">
          {filteredSent.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <CheckCircle className="w-10 h-10 mx-auto mb-2 text-gray-300" />
              <p>{tk('noSent')}</p>
            </div>
          ) : filteredSent.map(guest => (
            <Card key={guest.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">{tk('room')} {guest.room_number}</Badge>
                    {guest.kbs_reference && <Badge variant="secondary">{tk('ref')} {guest.kbs_reference}</Badge>}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {tk('sentAt')} {guest.kbs_sent_at ? new Date(guest.kbs_sent_at).toLocaleString() : '-'}
                  </div>
                </div>
                <Badge className="bg-green-100 text-green-800">{tk('sent')}</Badge>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="missing" className="space-y-2">
          {missingData.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <CheckCircle className="w-10 h-10 mx-auto mb-2 text-gray-300" />
              <p>{tk('allComplete')}</p>
            </div>
          ) : missingData.map(guest => (
            <Card key={guest.id} className="border-red-200">
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">{tk('room')} {guest.room_number}</Badge>
                  </div>
                  <div className="text-xs text-red-600 mt-1">
                    {tk('missing')} {!guest.id_number ? tk('idNumber') + ' ' : ''}{!guest.birth_date ? tk('birthDate') : ''}
                  </div>
                </div>
                <Button size="sm" variant="outline" onClick={() => openEditDialog(guest)}>
                  <UserCog className="w-3.5 h-3.5 mr-1" /> {tk('updateInfo')}
                </Button>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        {/* Faz 3: Kuyruk sekmesi — agent app'in çalıştığı işler */}
        <TabsContent value="queue" className="space-y-2">
          {queueJobs.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <ListPlus className="w-10 h-10 mx-auto mb-2 text-gray-300" />
              <p>{tk('noQueueJobs')}</p>
            </div>
          ) : queueJobs.map(job => {
            const statusColors = {
              pending: 'bg-yellow-100 text-yellow-800',
              in_progress: 'bg-blue-100 text-blue-800',
              done: 'bg-green-100 text-green-800',
              failed: 'bg-amber-100 text-amber-800',
              dead: 'bg-red-100 text-red-800',
            };
            const statusLabel = {
              pending: tk('qPending'), in_progress: tk('qInProgress'),
              done: tk('qDone'), failed: tk('qFailed'), dead: tk('qDead'),
            }[job.status] || job.status;
            const guestName = job.payload?.guest_name || tk('unknown');
            const room = job.payload?.room_number || '-';
            const isRetryable = job.status === 'dead' || job.status === 'failed';
            return (
              <Card key={job.id}>
                <CardContent className="p-3 flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{guestName}</span>
                      <Badge variant="outline">{tk('room')} {room}</Badge>
                      <Badge className={statusColors[job.status] || ''}>
                        {statusLabel}
                      </Badge>
                      <Badge variant="secondary" className="text-[10px]">
                        {tk('qAttempts')}: {job.attempts || 0}/{job.max_attempts || 5}
                      </Badge>
                      {job.action && (
                        <Badge variant="outline" className="text-[10px]">
                          {job.action}
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 mt-1 space-y-0.5">
                      {job.kbs_reference && (
                        <div className="text-green-600">
                          {tk('qKbsRef')}: <span className="font-mono">{job.kbs_reference}</span>
                        </div>
                      )}
                      {job.worker_id && (
                        <div>{tk('qWorker')}: <span className="font-mono">{job.worker_id}</span></div>
                      )}
                      {job.last_error && (
                        <div className="text-red-600 truncate" title={job.last_error}>
                          {tk('qLastError')}: {job.last_error}
                        </div>
                      )}
                      {job.next_retry_at && job.status === 'pending' && (
                        <div>{tk('qNextRetry')}: {new Date(job.next_retry_at).toLocaleString()}</div>
                      )}
                      <div className="text-gray-400">
                        {tk('qCreatedAt')}: {job.created_at ? new Date(job.created_at).toLocaleString() : '-'}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {extReady && job.status === 'pending' && (
                      <Button size="sm" variant="outline" onClick={() => sendJobViaExtension(job)}>
                        <Send className="h-3 w-3 mr-1" /> Eklenti ile gonder
                      </Button>
                    )}
                    {isRetryable && (
                      <Button size="sm" variant="outline" onClick={() => retryDeadJob(job)}>
                        <RefreshCw className="h-3 w-3 mr-1" /> {tk('retry')}
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </TabsContent>
      </Tabs>

      <Dialog open={!!editDialog} onOpenChange={o => { if (!o) setEditDialog(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tk('updateTitle')}</DialogTitle>
          </DialogHeader>
          {editDialog && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">{editDialog.guest_name} - {tk('room')} {editDialog.room_number}</p>
              <div>
                <Label>{tk('idLabel')}</Label>
                <Input
                  value={editForm.id_number}
                  onChange={e => setEditForm({ ...editForm, id_number: e.target.value })}
                  placeholder={tk('idPlaceholder')}
                />
              </div>
              <div>
                <Label>{tk('birthDateLabel')}</Label>
                <Input
                  type="date"
                  value={editForm.birth_date}
                  onChange={e => setEditForm({ ...editForm, birth_date: e.target.value })}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setEditDialog(null)}>{tk('cancel')}</Button>
                <Button onClick={saveGuestInfo}>{tk('save')}</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KBSNotification;
