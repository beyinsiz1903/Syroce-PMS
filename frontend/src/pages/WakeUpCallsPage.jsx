import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import {
  AlarmClock, Plus, CheckCircle, XCircle, Clock,
  Trash2, RefreshCw, PhoneCall, PhoneOff, Repeat, Bell, BellOff, Volume2, TimerReset
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  getWakeUpAlarmSettings,
  playWakeUpChime,
  saveWakeUpAlarmSettings,
  snoozeWakeUpTime,
  todayInIstanbul,
  unlockWakeUpAudio,
  WAKEUP_VOLUME_OPTIONS,
} from '@/lib/wakeUpAlarm';

const STATUS_COLORS = {
  pending: 'bg-amber-100 text-amber-700 border-amber-200',
  completed: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  missed: 'bg-red-100 text-red-700 border-red-200',
  cancelled: 'bg-gray-100 text-gray-500 border-gray-200',
};
const STATUS_LABELS = {
  pending: 'Bekliyor', completed: 'Tamamlandı', missed: 'Cevapsız', cancelled: 'İptal',
};
const RESPONSE_LABELS = {
  answered: 'Cevapladı', no_answer: 'Cevaplanmadı', busy: 'Meşgul',
};
const METHOD_LABELS = { phone: 'Telefon', system: 'Sistem', both: 'Her İkisi' };

const WakeUpCallsPage = () => {
  const { t } = useTranslation();
  const [calls, setCalls] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filterDate, setFilterDate] = useState(todayInIstanbul());
  const [filterStatus, setFilterStatus] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    room_number: '', guest_name: '', wake_time: '07:00', wake_date: '',
    recurring: false, recurrence_end_date: '', notes: '', method: 'phone',
  });
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const initialAlarmSettings = getWakeUpAlarmSettings();
  const [alertsArmed, setAlertsArmed] = useState(initialAlarmSettings.enabled);
  const [alarmVolume, setAlarmVolume] = useState(initialAlarmSettings.volume);
  const today = todayInIstanbul();

  const loadCalls = useCallback(async () => {
    try {
      const params = {};
      if (filterDate) params.date = filterDate;
      if (filterStatus) params.status = filterStatus;
      const res = await axios.get(`/pms/wake-up-calls`, { params });
      const list = res.data?.calls || [];
      setCalls(list);
      setStats(res.data?.stats || {});
    } catch (e) {
      console.error('Load calls error', e);
    } finally {
      setLoading(false);
    }
  }, [filterDate, filterStatus]);

  useEffect(() => { loadCalls(); }, [loadCalls]);

  // Listeyi güncel tutar; sesli ve masaüstü alarmı uygulama kabuğundaki
  // WakeUpAlarmMonitor tüm PMS sayfalarında ayrıca izler.
  useEffect(() => {
    if (filterDate !== today) return;
    const tick = () => { if (!document.hidden) loadCalls(); };
    const interval = setInterval(tick, 60000);
    const onVis = () => { if (!document.hidden) loadCalls(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [loadCalls, filterDate, today]);

  const armAlerts = async () => {
    try {
      if (typeof Notification !== 'undefined' && Notification.permission !== 'granted') {
        const perm = await Notification.requestPermission();
        if (perm !== 'granted') {
          toast.warning('Masaüstü bildirimi kapalı; uygulama içi uyarı ve seçtiğiniz ses kullanılacak.');
        }
      }
      await unlockWakeUpAudio();
      saveWakeUpAlarmSettings({ enabled: true, volume: alarmVolume });
      await playWakeUpChime(alarmVolume);
      setAlertsArmed(true);
      toast.success('Resepsiyon alarmı açık; PMS içinde çalışırken çağrılar izlenecek.');
    } catch (e) {
      toast.error('Alarm açılamadı: ' + e.message);
    }
  };

  const changeAlarmVolume = async (volume) => {
    setAlarmVolume(volume);
    saveWakeUpAlarmSettings({ enabled: alertsArmed, volume });
    if (alertsArmed && volume !== 'silent') await playWakeUpChime(volume);
  };

  const disarmAlerts = () => {
    saveWakeUpAlarmSettings({ enabled: false, volume: alarmVolume });
    setAlertsArmed(false);
    toast.success('Bu bilgisayardaki sesli uyandırma alarmı kapatıldı.');
  };

  const testAlarm = async () => {
    try {
      await unlockWakeUpAudio();
      await playWakeUpChime(alarmVolume);
      toast.success(alarmVolume === 'silent' ? 'Yalnız görsel uyarı seçili.' : 'Kısa alarm sesi oynatıldı.');
    } catch {
      toast.error('Ses oynatılamadı. Tarayıcının ses iznini kontrol edin.');
    }
  };

  const handleCreate = async () => {
    if (!form.room_number || !form.wake_time || !form.wake_date) {
      toast.error('Oda no, saat ve tarih zorunlu'); return;
    }
    try {
      await axios.post(`/pms/wake-up-calls`, form);
      toast.success('Uyandırma çağrısı oluşturuldu');
      setShowCreate(false);
      setForm({ room_number: '', guest_name: '', wake_time: '07:00', wake_date: filterDate || '', recurring: false, recurrence_end_date: '', notes: '', method: 'phone' });
      loadCalls();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleStatus = async (callId, status, response) => {
    try {
      const payload = { status };
      if (response) payload.response = response;
      await axios.put(`/pms/wake-up-calls/${callId}`, payload);
      toast.success(`Durum "${STATUS_LABELS[status]}" olarak güncellendi`);
      loadCalls();
    } catch (e) {
      toast.error('Güncelleme hatası');
    }
  };

  const handleSnooze = async (call) => {
    try {
      const nextSchedule = snoozeWakeUpTime(call, 5);
      await axios.put(`/pms/wake-up-calls/${call.id}`, {
        ...nextSchedule,
        status: 'pending',
        attempt_count: (call.attempt_count || 0) + 1,
      });
      toast.success(`Oda ${call.room_number} çağrısı 5 dakika ertelendi.`);
      loadCalls();
    } catch {
      toast.error('Uyandırma çağrısı ertelenemedi.');
    }
  };

  const handleDelete = async (callId) => {
    try {
      await axios.delete(`/pms/wake-up-calls/${callId}`);
      toast.success('Silindi');
      setDeleteConfirm(null);
      loadCalls();
    } catch (e) {
      toast.error('Silme hatası');
    }
  };

  return (
    <>
      <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto" data-testid="wake-up-calls-page">
        <PageHeader
          icon={AlarmClock}
          iconClassName="text-indigo-600"
          title={t('cm.pages_WakeUpCallsPage.uyandirma_cagrisi_yonetimi')}
          subtitle={t('cm.pages_WakeUpCallsPage.misafir_uyandirma_cagrilarini_planlayip_')}
          actions={
            <>
              {alertsArmed && (
                <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 gap-1 self-center">
                  <Bell className="w-3 h-3" /> {t('cm.pages_WakeUpCallsPage.alarm_aktif')}
                </Badge>
              )}
              <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadCalls(); }}>
                <RefreshCw className="w-4 h-4 mr-1.5" /> {t('cm.pages_WakeUpCallsPage.yenile')}
              </Button>
              <Button size="sm" onClick={() => { setForm(f => ({ ...f, wake_date: filterDate })); setShowCreate(true); }} data-testid="create-wakeup-btn">
                <Plus className="w-4 h-4 mr-1.5" /> {t('cm.pages_WakeUpCallsPage.yeni_cagri')}
              </Button>
            </>
          }
        />

        <Card className={alertsArmed ? 'border-emerald-200 bg-emerald-50/50' : 'border-amber-200 bg-amber-50/50'}>
          <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className={`mt-0.5 rounded-full p-2 ${alertsArmed ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                {alertsArmed ? <Bell className="h-5 w-5" /> : <BellOff className="h-5 w-5" />}
              </div>
              <div>
                <p className="font-semibold">{alertsArmed ? 'Resepsiyon alarmı açık' : 'Resepsiyon alarmını etkinleştirin'}</p>
                <p className="mt-0.5 max-w-2xl text-sm text-muted-foreground">
                  {alertsArmed
                    ? 'PMS içinde hangi ekranda olursanız olun zamanı gelen çağrı düşük ses, masaüstü bildirimi ve uygulama içi uyarıyla gösterilir.'
                    : 'Tarayıcı ses izni için bu bilgisayarda bir kez alarmı açın. Varsayılan ses kısa ve düşük seviyededir.'}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label htmlFor="alarm-volume" className="text-xs text-muted-foreground">Uyarı seviyesi</Label>
                <select
                  id="alarm-volume"
                  value={alarmVolume}
                  onChange={(event) => changeAlarmVolume(event.target.value)}
                  className="h-9 rounded-md border bg-background px-3 text-sm"
                  data-testid="alarm-volume"
                >
                  {Object.entries(WAKEUP_VOLUME_OPTIONS).map(([value, option]) => (
                    <option key={value} value={value}>{option.label}</option>
                  ))}
                </select>
              </div>
              <Button type="button" variant="outline" size="sm" onClick={testAlarm} disabled={alarmVolume === 'silent'}>
                <Volume2 className="mr-1.5 h-4 w-4" /> Sesi dene
              </Button>
              {!alertsArmed && (
                <Button type="button" size="sm" onClick={armAlerts} data-testid="arm-alerts-primary">
                  <Bell className="mr-1.5 h-4 w-4" /> Alarmı aç
                </Button>
              )}
              {alertsArmed && (
                <Button type="button" variant="ghost" size="sm" onClick={disarmAlerts}>
                  <BellOff className="mr-1.5 h-4 w-4" /> Alarmı kapat
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard icon={Clock} label={t('cm.pages_WakeUpCallsPage.bugun_toplam')} value={stats.total_today || 0} intent="info" />
          <KpiCard icon={AlarmClock} label="Bekliyor" value={stats.pending || 0} intent="warning" />
          <KpiCard icon={CheckCircle} label={t('cm.pages_WakeUpCallsPage.tamamlandi')} value={stats.completed || 0} intent="success" />
          <KpiCard icon={XCircle} label={t('cm.pages_WakeUpCallsPage.cevapsiz')} value={stats.missed || 0} intent="danger" highlight={(stats.missed || 0) > 0} />
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <div>
            <Label className="text-xs text-gray-500">{t('cm.pages_WakeUpCallsPage.tarih')}</Label>
            <Input
              type="date"
              value={filterDate}
              onChange={e => setFilterDate(e.target.value)}
              className="h-9 w-40"
              data-testid="filter-date"
            />
          </div>
          <div>
            <Label className="text-xs text-gray-500">{t('cm.pages_WakeUpCallsPage.durum')}</Label>
            <select
              value={filterStatus}
              onChange={e => setFilterStatus(e.target.value)}
              className="h-9 border rounded-md px-3 text-sm"
              data-testid="filter-status"
            >
              <option value="">{t('cm.pages_WakeUpCallsPage.tumu')}</option>
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">{t('cm.pages_WakeUpCallsPage.yukleniyor')}</div>
        ) : calls.length === 0 ? (
          <Card className="p-12 text-center">
            <AlarmClock className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">{t('cm.pages_WakeUpCallsPage.bu_tarih_icin_uyandirma_cagrisi_yok')}</p>
            <Button size="sm" className="mt-3" onClick={() => { setForm(f => ({ ...f, wake_date: filterDate })); setShowCreate(true); }}>
              <Plus className="w-4 h-4 mr-1" /> {t('cm.pages_WakeUpCallsPage.yeni_olustur')}
            </Button>
          </Card>
        ) : (
          <div className="space-y-2">
            {calls.map(call => (
              <Card
                key={call.id}
                className={`transition-shadow ${call.is_due ? 'ring-2 ring-red-400 bg-red-50/40 animate-pulse' : 'hover:shadow-sm'}`}
                data-testid={`call-card-${call.id}`}
              >
                <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-4">
                    <div className="text-center min-w-[60px]">
                      <div className={`text-2xl font-bold ${call.is_due ? 'text-red-600' : 'text-indigo-600'}`}>{call.wake_time}</div>
                      <div className="text-[10px] text-gray-400">{call.wake_date}</div>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{t('cm.pages_WakeUpCallsPage.oda')} {call.room_number}</span>
                        {call.guest_name && <span className="text-sm text-gray-500">- {call.guest_name}</span>}
                        {call.recurring && <Badge variant="outline" className="text-[10px] gap-1"><Repeat className="w-3 h-3" />Tekrar</Badge>}
                        {call.is_due && (
                          <Badge className="bg-red-600 text-white text-[10px] gap-1">
                            <AlarmClock className="w-3 h-3" /> {t('cm.pages_WakeUpCallsPage.simdi_ara')}
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge className={`text-[10px] ${STATUS_COLORS[call.status] || ''}`}>
                          {STATUS_LABELS[call.status] || call.status}
                        </Badge>
                        <span className="text-xs text-gray-400">{METHOD_LABELS[call.method] || call.method}</span>
                        {call.response && <span className="text-xs text-gray-500">({RESPONSE_LABELS[call.response] || call.response})</span>}
                        {call.attempt_count > 0 && <span className="text-xs text-gray-400">{call.attempt_count} deneme</span>}
                      </div>
                      {call.notes && <div className="text-xs text-gray-500 mt-1">{call.notes}</div>}
                    </div>
                  </div>

                  <div className="flex items-center gap-1 flex-shrink-0">
                    {call.status === 'pending' && (
                      <>
                        <Button size="sm" variant="outline" className="h-8 text-xs text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                          onClick={() => handleStatus(call.id, 'completed', 'answered')}
                          data-testid={`complete-btn-${call.id}`}
                        >
                          <PhoneCall className="w-3 h-3 mr-1" /> Arandı
                        </Button>
                        <Button size="sm" variant="outline" className="h-8 text-xs text-indigo-600 border-indigo-200 hover:bg-indigo-50"
                          onClick={() => handleSnooze(call)}
                          data-testid={`snooze-btn-${call.id}`}
                        >
                          <TimerReset className="w-3 h-3 mr-1" /> 5 dk ertele
                        </Button>
                        <Button size="sm" variant="outline" className="h-8 text-xs text-red-600 border-red-200 hover:bg-red-50"
                          onClick={() => handleStatus(call.id, 'missed', 'no_answer')}
                          data-testid={`missed-btn-${call.id}`}
                        >
                          <PhoneOff className="w-3 h-3 mr-1" /> {t('cm.pages_WakeUpCallsPage.cevapsiz_ff6c6')}
                        </Button>
                        <Button size="sm" variant="ghost" className="h-8 text-xs text-gray-500"
                          onClick={() => handleStatus(call.id, 'cancelled')}
                        >
                          <XCircle className="w-3 h-3" />
                        </Button>
                      </>
                    )}
                    <Button size="sm" variant="ghost" className="h-8 text-xs text-red-400 hover:text-red-600"
                      onClick={() => setDeleteConfirm(call)}
                    >
                      <Trash2 className="w-3 h-3" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <AlarmClock className="w-5 h-5 text-indigo-600" /> {t('cm.pages_WakeUpCallsPage.yeni_uyandirma_cagrisi')}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>{t('cm.pages_WakeUpCallsPage.oda_no')}</Label>
                  <Input value={form.room_number} onChange={e => setForm(f => ({ ...f, room_number: e.target.value }))} placeholder="101" data-testid="wakeup-room-input" />
                </div>
                <div>
                  <Label>{t('cm.pages_WakeUpCallsPage.misafir_adi')}</Label>
                  <Input value={form.guest_name} onChange={e => setForm(f => ({ ...f, guest_name: e.target.value }))} placeholder="Ad Soyad" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>{t('cm.pages_WakeUpCallsPage.saat')}</Label>
                  <Input type="time" value={form.wake_time} onChange={e => setForm(f => ({ ...f, wake_time: e.target.value }))} data-testid="wakeup-time-input" />
                </div>
                <div>
                  <Label>{t('cm.pages_WakeUpCallsPage.tarih_fabdd')}</Label>
                  <Input type="date" value={form.wake_date} onChange={e => setForm(f => ({ ...f, wake_date: e.target.value }))} data-testid="wakeup-date-input" />
                </div>
              </div>
              <div>
                <Label>{t('cm.pages_WakeUpCallsPage.yontem')}</Label>
                <select value={form.method} onChange={e => setForm(f => ({ ...f, method: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm">
                  <option value="phone">Telefon</option>
                  <option value="system">Sistem</option>
                  <option value="both">{t('cm.pages_WakeUpCallsPage.her_ikisi')}</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={form.recurring} onChange={e => setForm(f => ({ ...f, recurring: e.target.checked }))} className="w-4 h-4 rounded" id="recurring" />
                <Label htmlFor="recurring" className="cursor-pointer">Tekrar Eden</Label>
                {form.recurring && (
                  <Input type="date" value={form.recurrence_end_date} onChange={e => setForm(f => ({ ...f, recurrence_end_date: e.target.value }))} placeholder={t('cm.pages_WakeUpCallsPage.bitis_tarihi')} className="ml-2 h-8 w-36 text-sm" />
                )}
              </div>
              <div>
                <Label>Notlar</Label>
                <Input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Ek bilgi..." />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowCreate(false)}>{t('cm.pages_WakeUpCallsPage.iptal')}</Button>
                <Button onClick={handleCreate} data-testid="save-wakeup-btn">{t('cm.pages_WakeUpCallsPage.olustur')}</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        <Dialog open={!!deleteConfirm} onOpenChange={o => { if (!o) setDeleteConfirm(null); }}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>{t('cm.pages_WakeUpCallsPage.silme_onayi')}</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-gray-600">
              {t('cm.pages_WakeUpCallsPage.bu_uyandirma_cagrisini_silmek_istedigini')}
              {deleteConfirm && <span className="font-medium"> {t('cm.pages_WakeUpCallsPage.oda_68a89')} {deleteConfirm.room_number} - {deleteConfirm.wake_time})</span>}
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)}>{t('cm.pages_WakeUpCallsPage.iptal_25174')}</Button>
              <Button variant="destructive" onClick={() => handleDelete(deleteConfirm?.id)}>{t('cm.pages_WakeUpCallsPage.sil')}</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

export default WakeUpCallsPage;
