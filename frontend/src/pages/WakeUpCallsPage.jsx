import { useState, useEffect, useCallback } from 'react';
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
  Trash2, Edit2, RefreshCw, PhoneCall, PhoneOff, Repeat
} from 'lucide-react';

const API = "";

const STATUS_COLORS = {
  pending: 'bg-amber-100 text-amber-700 border-amber-200',
  completed: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  missed: 'bg-red-100 text-red-700 border-red-200',
  cancelled: 'bg-gray-100 text-gray-500 border-gray-200',
};
const STATUS_LABELS = {
  pending: 'Bekliyor', completed: 'Tamamlandi', missed: 'Cevapsiz', cancelled: 'Iptal',
};
const RESPONSE_LABELS = {
  answered: 'Cevapladi', no_answer: 'Cevaplanmadi', busy: 'Mesgul',
};
const METHOD_LABELS = { phone: 'Telefon', system: 'Sistem', both: 'Her Ikisi' };

const WakeUpCallsPage = ({ user, tenant, onLogout }) => {
  const [calls, setCalls] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filterDate, setFilterDate] = useState(new Date().toISOString().split('T')[0]);
  const [filterStatus, setFilterStatus] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showUpdate, setShowUpdate] = useState(null);
  const [form, setForm] = useState({
    room_number: '', guest_name: '', wake_time: '07:00', wake_date: '',
    recurring: false, recurrence_end_date: '', notes: '', method: 'phone',
  });

  const loadCalls = useCallback(async () => {
    try {
      const params = {};
      if (filterDate) params.date = filterDate;
      if (filterStatus) params.status = filterStatus;
      const res = await axios.get(`/pms/wake-up-calls`, { params });
      setCalls(res.data?.calls || []);
      setStats(res.data?.stats || {});
    } catch (e) {
      console.error('Load calls error', e);
    } finally {
      setLoading(false);
    }
  }, [filterDate, filterStatus]);

  useEffect(() => { loadCalls(); }, [loadCalls]);

  const handleCreate = async () => {
    if (!form.room_number || !form.wake_time || !form.wake_date) {
      toast.error('Oda no, saat ve tarih zorunlu'); return;
    }
    try {
      await axios.post(`/pms/wake-up-calls`, form);
      toast.success('Uyandirma cagrisi olusturuldu');
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
      toast.success(`Durum "${STATUS_LABELS[status]}" olarak guncellendi`);
      loadCalls();
    } catch (e) {
      toast.error('Guncelleme hatasi');
    }
  };

  const handleDelete = async (callId) => {
    if (!window.confirm('Bu uyandirma cagrisini silmek istediginize emin misiniz?')) return;
    try {
      await axios.delete(`/pms/wake-up-calls/${callId}`);
      toast.success('Silindi');
      loadCalls();
    } catch (e) {
      toast.error('Silme hatasi');
    }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
      <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto" data-testid="wake-up-calls-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <AlarmClock className="w-6 h-6 text-indigo-600" />
              Uyandirma Cagrisi Yonetimi
            </h1>
            <p className="text-sm text-gray-500 mt-1">Misafir uyandirma cagrilarini planlayip takip edin</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadCalls(); }}>
              <RefreshCw className="w-4 h-4 mr-1" /> Yenile
            </Button>
            <Button size="sm" onClick={() => { setForm(f => ({ ...f, wake_date: filterDate })); setShowCreate(true); }} data-testid="create-wakeup-btn">
              <Plus className="w-4 h-4 mr-1" /> Yeni Cagri
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="p-3">
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-blue-500" />
              <div>
                <div className="text-2xl font-bold">{stats.total_today || 0}</div>
                <div className="text-xs text-gray-500">Bugun Toplam</div>
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
                <div className="text-xs text-gray-500">Tamamlandi</div>
              </div>
            </div>
          </Card>
          <Card className="p-3">
            <div className="flex items-center gap-2">
              <XCircle className="w-5 h-5 text-red-500" />
              <div>
                <div className="text-2xl font-bold">{stats.missed || 0}</div>
                <div className="text-xs text-gray-500">Cevapsiz</div>
              </div>
            </div>
          </Card>
        </div>

        {/* Filters */}
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
              <option value="">Tumu</option>
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Calls List */}
        {loading ? (
          <div className="text-center py-12 text-gray-400">Yukleniyor...</div>
        ) : calls.length === 0 ? (
          <Card className="p-12 text-center">
            <AlarmClock className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">Bu tarih icin uyandirma cagrisi yok</p>
            <Button size="sm" className="mt-3" onClick={() => { setForm(f => ({ ...f, wake_date: filterDate })); setShowCreate(true); }}>
              <Plus className="w-4 h-4 mr-1" /> Yeni Olustur
            </Button>
          </Card>
        ) : (
          <div className="space-y-2">
            {calls.map(call => (
              <Card key={call.id} className="hover:shadow-sm transition-shadow" data-testid={`call-card-${call.id}`}>
                <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-4">
                    {/* Time */}
                    <div className="text-center min-w-[60px]">
                      <div className="text-2xl font-bold text-indigo-600">{call.wake_time}</div>
                      <div className="text-[10px] text-gray-400">{call.wake_date}</div>
                    </div>

                    {/* Info */}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">Oda {call.room_number}</span>
                        {call.guest_name && <span className="text-sm text-gray-500">- {call.guest_name}</span>}
                        {call.recurring && <Badge variant="outline" className="text-[10px] gap-1"><Repeat className="w-3 h-3" />Tekrar</Badge>}
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

                  {/* Actions */}
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
                          <PhoneOff className="w-3 h-3 mr-1" /> Cevapsiz
                        </Button>
                        <Button size="sm" variant="ghost" className="h-8 text-xs text-gray-500"
                          onClick={() => handleStatus(call.id, 'cancelled')}
                        >
                          <XCircle className="w-3 h-3" />
                        </Button>
                      </>
                    )}
                    <Button size="sm" variant="ghost" className="h-8 text-xs text-red-400 hover:text-red-600"
                      onClick={() => handleDelete(call.id)}
                    >
                      <Trash2 className="w-3 h-3" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Create Dialog */}
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <AlarmClock className="w-5 h-5 text-indigo-600" /> Yeni Uyandirma Cagrisi
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Oda No *</Label>
                  <Input value={form.room_number} onChange={e => setForm(f => ({ ...f, room_number: e.target.value }))} placeholder="101" data-testid="wakeup-room-input" />
                </div>
                <div>
                  <Label>Misafir Adi</Label>
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
                <Label>Yontem</Label>
                <select value={form.method} onChange={e => setForm(f => ({ ...f, method: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm">
                  <option value="phone">Telefon</option>
                  <option value="system">Sistem</option>
                  <option value="both">Her Ikisi</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={form.recurring} onChange={e => setForm(f => ({ ...f, recurring: e.target.checked }))} className="w-4 h-4 rounded" id="recurring" />
                <Label htmlFor="recurring" className="cursor-pointer">Tekrar Eden</Label>
                {form.recurring && (
                  <Input type="date" value={form.recurrence_end_date} onChange={e => setForm(f => ({ ...f, recurrence_end_date: e.target.value }))} placeholder="Bitis tarihi" className="ml-2 h-8 w-36 text-sm" />
                )}
              </div>
              <div>
                <Label>Notlar</Label>
                <Input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Ek bilgi..." />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowCreate(false)}>Iptal</Button>
                <Button onClick={handleCreate} data-testid="save-wakeup-btn">Olustur</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default WakeUpCallsPage;
