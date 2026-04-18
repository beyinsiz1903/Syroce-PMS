import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  AlarmClock, Plus, Phone, CheckCircle, XCircle, Clock,
  Trash2, Edit2, RefreshCw, PhoneCall, PhoneOff, Repeat, Bell, BellOff
} from 'lucide-react';

// Tek, uzun ömürlü AudioContext — kullanıcı etkileşimiyle bir kez
// resume edildikten sonra timer-tabanlı sonraki alarmlar da çalar
// (autoplay policy bypass'ı için kritik).
let _alarmCtx = null;
function getAlarmCtx() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  if (!_alarmCtx) {
    try { _alarmCtx = new Ctx(); } catch { return null; }
  }
  return _alarmCtx;
}

function playAlarmBeep() {
  const ctx = getAlarmCtx();
  if (!ctx) return;
  if (ctx.state === 'suspended') {
    ctx.resume().catch(() => {});
  }
  const beep = (start, freq = 880) => {
    try {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      osc.connect(gain).connect(ctx.destination);
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + start);
      gain.gain.exponentialRampToValueAtTime(0.5, ctx.currentTime + start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + 0.35);
      osc.start(ctx.currentTime + start);
      osc.stop(ctx.currentTime + start + 0.4);
    } catch { /* noop */ }
  };
  beep(0, 880);
  beep(0.45, 880);
  beep(0.9, 1100);
}

// Hotel-local (Istanbul) tarihi — UTC ISO yerine. Saat dilimi farkı
// gece yarısı sınırında is_due/filterDate uyumsuzluğu yapmasın diye.
function todayInIstanbul() {
  try {
    const fmt = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit',
    });
    return fmt.format(new Date()); // YYYY-MM-DD
  } catch {
    const d = new Date(Date.now() + 3 * 3600 * 1000);
    return d.toISOString().split('T')[0];
  }
}

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

const WakeUpCallsPage = ({ user, tenant, onLogout }) => {
  const [calls, setCalls] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filterDate, setFilterDate] = useState(todayInIstanbul());
  const [filterStatus, setFilterStatus] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showUpdate, setShowUpdate] = useState(null);
  const [form, setForm] = useState({
    room_number: '', guest_name: '', wake_time: '07:00', wake_date: '',
    recurring: false, recurrence_end_date: '', notes: '', method: 'phone',
  });
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [alertsArmed, setAlertsArmed] = useState(false);
  const alertedIdsRef = useRef(new Set());
  const armedRef = useRef(false);

  // Bugün için zaten alarm çalmış çağrıları sessionStorage'da tutuyoruz
  // ki sayfa kapanıp açıldığında aynı alarm tekrar çalmasın.
  const today = todayInIstanbul();
  const alertKey = `wakeup-alerted-${today}`;

  useEffect(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(alertKey) || '[]');
      alertedIdsRef.current = new Set(saved);
    } catch { alertedIdsRef.current = new Set(); }
  }, [alertKey]);

  const fireAlertsFor = useCallback((dueCalls) => {
    const fresh = dueCalls.filter(c => !alertedIdsRef.current.has(c.id));
    if (fresh.length === 0) return;

    // Alarm henüz "armed" değilse: visual + toast tetikle, ama ses/desktop
    // bildirim için izin/etkileşim gerekir. Ref kullanıyoruz ki callback
    // her arm değişiminde yeniden oluşmasın (poller'ın yeniden kurulumunu
    // tetikleyip duplicate fetch yapmaz).
    if (armedRef.current) {
      playAlarmBeep();
    }

    // Tarayıcı bildirimi — izin verildiyse her çağrı için ayrı bildirim
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      fresh.forEach(c => {
        try {
          const n = new Notification('⏰ Uyandırma Çağrısı Zamanı', {
            body: `Oda ${c.room_number}${c.guest_name ? ` — ${c.guest_name}` : ''} • ${c.wake_time}`,
            tag: `wakeup-${c.id}`,
            requireInteraction: true,
          });
          n.onclick = () => { window.focus(); n.close(); };
        } catch { /* noop */ }
      });
    }

    // Toast (her zaman gösterilir, izin gerekmez)
    fresh.forEach(c => {
      toast.warning(`⏰ Oda ${c.room_number} — uyandırma saati (${c.wake_time})`, {
        duration: 15000,
      });
    });

    // Hatırla
    fresh.forEach(c => alertedIdsRef.current.add(c.id));
    try {
      sessionStorage.setItem(alertKey, JSON.stringify([...alertedIdsRef.current]));
    } catch { /* noop */ }
  }, [alertKey]);

  const loadCalls = useCallback(async () => {
    try {
      const params = {};
      if (filterDate) params.date = filterDate;
      if (filterStatus) params.status = filterStatus;
      const res = await axios.get(`/pms/wake-up-calls`, { params });
      const list = res.data?.calls || [];
      setCalls(list);
      setStats(res.data?.stats || {});
      // Backend `is_due` damgaladıysa alarmı tetikle
      const due = list.filter(c => c.is_due);
      if (due.length > 0) fireAlertsFor(due);
    } catch (e) {
      console.error('Load calls error', e);
    } finally {
      setLoading(false);
    }
  }, [filterDate, filterStatus, fireAlertsFor]);

  useEffect(() => { loadCalls(); }, [loadCalls]);

  // 30 sn'de bir poll — sadece bugün filtreliyken çalsın (mantıklı)
  useEffect(() => {
    if (filterDate !== today) return;
    const interval = setInterval(() => { loadCalls(); }, 30000);
    return () => clearInterval(interval);
  }, [loadCalls, filterDate, today]);

  // Alarm sistemini etkinleştir: izin iste + AudioContext'i kullanıcı
  // etkileşimiyle "uyandır" (autoplay policy gereği).
  const armAlerts = async () => {
    try {
      if (typeof Notification !== 'undefined' && Notification.permission !== 'granted') {
        const perm = await Notification.requestPermission();
        if (perm !== 'granted') {
          toast.error('Tarayıcı bildirim izni reddedildi — sadece sesli alarm çalacak');
        }
      }
      // Tek AudioContext'i bu kullanıcı gesture'ında resume et —
      // sonraki timer-tetikli alarmlarda autoplay policy'yi bypass eder.
      const ctx = getAlarmCtx();
      if (ctx && ctx.state === 'suspended') {
        await ctx.resume();
      }
      playAlarmBeep();
      armedRef.current = true;
      setAlertsArmed(true);
      toast.success('Sesli alarm + bildirimler aktif');
    } catch (e) {
      toast.error('Alarm açılamadı: ' + e.message);
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
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
      <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto" data-testid="wake-up-calls-page">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <AlarmClock className="w-6 h-6 text-indigo-600" />
              Uyandırma Çağrısı Yönetimi
            </h1>
            <p className="text-sm text-gray-500 mt-1">Misafir uyandırma çağrılarını planlayıp takip edin</p>
          </div>
          <div className="flex gap-2">
            {!alertsArmed ? (
              <Button
                variant="outline" size="sm"
                onClick={armAlerts}
                className="border-amber-300 text-amber-700 hover:bg-amber-50"
                data-testid="arm-alerts-btn"
              >
                <BellOff className="w-4 h-4 mr-1" /> Sesli Alarmı Aç
              </Button>
            ) : (
              <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 gap-1 self-center">
                <Bell className="w-3 h-3" /> Alarm Aktif
              </Badge>
            )}
            <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadCalls(); }}>
              <RefreshCw className="w-4 h-4 mr-1" /> Yenile
            </Button>
            <Button size="sm" onClick={() => { setForm(f => ({ ...f, wake_date: filterDate })); setShowCreate(true); }} data-testid="create-wakeup-btn">
              <Plus className="w-4 h-4 mr-1" /> Yeni Çağrı
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="p-3">
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-blue-500" />
              <div>
                <div className="text-2xl font-bold">{stats.total_today || 0}</div>
                <div className="text-xs text-gray-500">Bugün Toplam</div>
              </div>
            </div>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-2">
              <AlarmClock className="w-5 h-5 text-amber-500" />
              <div>
                <div className="text-2xl font-bold">{stats.pending || 0}</div>
                <div className="text-xs text-gray-500">Bekliyor</div>
              </div>
            </div>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-emerald-500" />
              <div>
                <div className="text-2xl font-bold">{stats.completed || 0}</div>
                <div className="text-xs text-gray-500">Tamamlandı</div>
              </div>
            </div>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-2">
              <XCircle className="w-5 h-5 text-red-500" />
              <div>
                <div className="text-2xl font-bold">{stats.missed || 0}</div>
                <div className="text-xs text-gray-500">Cevapsız</div>
              </div>
            </div>
          </Card>
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <div>
            <Label className="text-xs text-gray-500">Tarih</Label>
            <Input
              type="date"
              value={filterDate}
              onChange={e => setFilterDate(e.target.value)}
              className="h-9 w-40"
              data-testid="filter-date"
            />
          </div>
          <div>
            <Label className="text-xs text-gray-500">Durum</Label>
            <select
              value={filterStatus}
              onChange={e => setFilterStatus(e.target.value)}
              className="h-9 border rounded-md px-3 text-sm"
              data-testid="filter-status"
            >
              <option value="">Tümü</option>
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">Yükleniyor...</div>
        ) : calls.length === 0 ? (
          <Card className="p-12 text-center">
            <AlarmClock className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">Bu tarih için uyandırma çağrısı yok</p>
            <Button size="sm" className="mt-3" onClick={() => { setForm(f => ({ ...f, wake_date: filterDate })); setShowCreate(true); }}>
              <Plus className="w-4 h-4 mr-1" /> Yeni Oluştur
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
                        <span className="font-semibold">Oda {call.room_number}</span>
                        {call.guest_name && <span className="text-sm text-gray-500">- {call.guest_name}</span>}
                        {call.recurring && <Badge variant="outline" className="text-[10px] gap-1"><Repeat className="w-3 h-3" />Tekrar</Badge>}
                        {call.is_due && (
                          <Badge className="bg-red-600 text-white text-[10px] gap-1">
                            <AlarmClock className="w-3 h-3" /> ŞİMDİ ARA!
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
                          <PhoneCall className="w-3 h-3 mr-1" /> Tamamla
                        </Button>
                        <Button size="sm" variant="outline" className="h-8 text-xs text-red-600 border-red-200 hover:bg-red-50"
                          onClick={() => handleStatus(call.id, 'missed', 'no_answer')}
                          data-testid={`missed-btn-${call.id}`}
                        >
                          <PhoneOff className="w-3 h-3 mr-1" /> Cevapsız
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
                <AlarmClock className="w-5 h-5 text-indigo-600" /> Yeni Uyandırma Çağrısı
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Oda No *</Label>
                  <Input value={form.room_number} onChange={e => setForm(f => ({ ...f, room_number: e.target.value }))} placeholder="101" data-testid="wakeup-room-input" />
                </div>
                <div>
                  <Label>Misafir Adı</Label>
                  <Input value={form.guest_name} onChange={e => setForm(f => ({ ...f, guest_name: e.target.value }))} placeholder="Ad Soyad" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Saat *</Label>
                  <Input type="time" value={form.wake_time} onChange={e => setForm(f => ({ ...f, wake_time: e.target.value }))} data-testid="wakeup-time-input" />
                </div>
                <div>
                  <Label>Tarih *</Label>
                  <Input type="date" value={form.wake_date} onChange={e => setForm(f => ({ ...f, wake_date: e.target.value }))} data-testid="wakeup-date-input" />
                </div>
              </div>
              <div>
                <Label>Yöntem</Label>
                <select value={form.method} onChange={e => setForm(f => ({ ...f, method: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm">
                  <option value="phone">Telefon</option>
                  <option value="system">Sistem</option>
                  <option value="both">Her İkisi</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={form.recurring} onChange={e => setForm(f => ({ ...f, recurring: e.target.checked }))} className="w-4 h-4 rounded" id="recurring" />
                <Label htmlFor="recurring" className="cursor-pointer">Tekrar Eden</Label>
                {form.recurring && (
                  <Input type="date" value={form.recurrence_end_date} onChange={e => setForm(f => ({ ...f, recurrence_end_date: e.target.value }))} placeholder="Bitiş tarihi" className="ml-2 h-8 w-36 text-sm" />
                )}
              </div>
              <div>
                <Label>Notlar</Label>
                <Input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Ek bilgi..." />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowCreate(false)}>İptal</Button>
                <Button onClick={handleCreate} data-testid="save-wakeup-btn">Oluştur</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        <Dialog open={!!deleteConfirm} onOpenChange={o => { if (!o) setDeleteConfirm(null); }}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>Silme Onayı</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-gray-600">
              Bu uyandırma çağrısını silmek istediğinize emin misiniz?
              {deleteConfirm && <span className="font-medium"> (Oda {deleteConfirm.room_number} - {deleteConfirm.wake_time})</span>}
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)}>İptal</Button>
              <Button variant="destructive" onClick={() => handleDelete(deleteConfirm?.id)}>Sil</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default WakeUpCallsPage;
