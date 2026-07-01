import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Smile, Meh, Frown, Home, Plus, Trash2, RefreshCw,
  MessageSquare, DoorClosed,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { confirmDialog } from '@/lib/dialogs';

const CATEGORY_BADGE = {
  promoter:  { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200', label: 'Destekçi (9-10)', Icon: Smile },
  passive:   { cls: 'bg-amber-100 text-amber-700 border-amber-200',       label: 'Nötr (7-8)',      Icon: Meh   },
  detractor: { cls: 'bg-red-100 text-red-700 border-red-200',             label: 'Eleştirmen (0-6)', Icon: Frown },
};

const PERIOD_OPTIONS = [
  { v: 7,   l: 'Son 7 gün' },
  { v: 30,  l: 'Son 30 gün' },
  { v: 90,  l: 'Son 90 gün' },
  { v: 365, l: 'Son 1 yıl' },
];

const fmtDate = (iso) => {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' });
  } catch { return iso.slice(0, 16).replace('T', ' '); }
};

const GuestJourney = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [npsData, setNpsData] = useState(null);
  const [recent, setRecent]   = useState([]);
  const [byRoom, setByRoom]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays]       = useState(30);
  const [filterCat, setFilterCat] = useState('');
  const [filterRoom, setFilterRoom] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    room_number: '', guest_name: '', nps_score: 9, feedback: '',
  });

  const loadAll = useCallback(async () => {
    try {
      const [scoreRes, recentRes, roomRes] = await Promise.all([
        axios.get(`/nps/score?days=${days}`),
        axios.get(`/nps/recent?days=${days}&limit=50` +
          (filterCat ? `&category=${filterCat}` : '') +
          (filterRoom ? `&room_number=${encodeURIComponent(filterRoom)}` : '')),
        axios.get(`/nps/by-room?days=${days}`),
      ]);
      setNpsData(scoreRes.data);
      setRecent(recentRes.data?.items || []);
      setByRoom(roomRes.data?.rooms || []);
    } catch (err) {
      console.error('NPS yüklenemedi', err);
      toast.error('Veriler yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [days, filterCat, filterRoom]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleCreate = async () => {
    const score = Number(form.nps_score);
    if (Number.isNaN(score) || score < 0 || score > 10) {
      toast.error('Puan 0-10 arası olmalı'); return;
    }
    try {
      await axios.post('/nps/survey', {
        room_number: form.room_number.trim() || null,
        guest_name:  form.guest_name.trim() || null,
        nps_score:   score,
        feedback:    form.feedback.trim() || null,
        source:      'manual',
      });
      toast.success('Yorum kaydedildi');
      setShowCreate(false);
      setForm({ room_number: '', guest_name: '', nps_score: 9, feedback: '' });
      setLoading(true);
      await loadAll();
    } catch (err) {
      toast.error('Kaydedilemedi: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDelete = async (id) => {
    if (!await confirmDialog({ message: 'Bu yorum silinsin mi?' })) return;
    try {
      await axios.delete(`/nps/survey/${id}`);
      // Optimistik UI: listeden hemen kaldır, sonra reload (out-of-order
      // yanıtlar gelse bile silinen kayıt geri görünmesin).
      setRecent(prev => prev.filter(x => x.id !== id));
      toast.success('Silindi');
      await loadAll();
    } catch (err) {
      toast.error('Silinemedi');
    }
  };

  const npsColor = (score) =>
    score >= 50 ? 'text-emerald-600' :
    score >= 0  ? 'text-amber-600'   :
                  'text-red-600';

  return (
    <>
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button variant="outline" size="icon" onClick={() => navigate('/')} className="hover:bg-indigo-50">
              <Home className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold">{t('guestJourney.title', 'Misafir Yolculuğu & NPS')}</h1>
              <p className="text-sm text-gray-500">Müşteri ilişkileri yorum & puan girişi, oda bazlı raporlama</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={days}
              onChange={e => setDays(Number(e.target.value))}
              className="h-9 border rounded-md px-3 text-sm bg-white"
              data-testid="period-select"
            >
              {PERIOD_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
            <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadAll(); }}>
              <RefreshCw className="w-4 h-4 mr-1" /> Yenile
            </Button>
            <Button size="sm" onClick={() => setShowCreate(true)} data-testid="add-feedback-btn">
              <Plus className="w-4 h-4 mr-1" /> Yeni Yorum
            </Button>
          </div>
        </div>

        {/* NPS Skor kartı */}
        <Card className="bg-gradient-to-r from-emerald-50 via-blue-50 to-indigo-50">
          <CardContent className="pt-6 pb-5 text-center">
            <p className="text-xs uppercase tracking-wider text-gray-500 mb-1">Net Tavsiye Skoru</p>
            <p className={`text-6xl font-bold ${npsData ? npsColor(npsData.nps_score) : 'text-gray-300'}`}>
              {npsData ? npsData.nps_score : '—'}
            </p>
            <p className="text-sm text-gray-500 mt-1">
              {npsData ? `${npsData.total_responses} yanıt` : 'Yükleniyor…'} • Son {days} gün
            </p>
          </CardContent>
        </Card>

        {/* Kategori dağılımı */}
        <div className="grid grid-cols-3 gap-3">
          {['promoter', 'passive', 'detractor'].map(cat => {
            const meta = CATEGORY_BADGE[cat];
            const value = npsData?.[cat === 'promoter' ? 'promoters' : cat === 'passive' ? 'passives' : 'detractors'] ?? 0;
            return (
              <Card
                key={cat}
                className={`cursor-pointer transition-all ${filterCat === cat ? 'ring-2 ring-indigo-400' : 'hover:shadow-md'}`}
                onClick={() => setFilterCat(filterCat === cat ? '' : cat)}
                data-testid={`cat-card-${cat}`}
              >
                <CardContent className="pt-5 pb-4 text-center">
                  <meta.Icon className={`w-9 h-9 mx-auto mb-1 ${cat === 'promoter' ? 'text-emerald-500' : cat === 'passive' ? 'text-amber-500' : 'text-red-500'}`} />
                  <div className="text-2xl font-bold">{value}</div>
                  <div className="text-xs text-gray-500">{meta.label}</div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Oda bazlı tablo */}
        <Card>
          <CardContent className="p-0">
            <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <DoorClosed className="w-4 h-4 text-indigo-600" />
                <h2 className="font-semibold text-sm">Oda Bazlı Performans</h2>
                <span className="text-xs text-gray-500">({byRoom.length} oda)</span>
              </div>
              <p className="text-xs text-gray-400">En düşük ortalamadan başlar — şikayet odaklı</p>
            </div>
            {byRoom.length === 0 ? (
              <div className="p-8 text-center text-sm text-gray-400">
                Bu dönem için oda bazlı veri yok
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                    <tr>
                      <th className="px-4 py-2 text-left">Oda</th>
                      <th className="px-4 py-2 text-left">Ort. Puan</th>
                      <th className="px-4 py-2 text-left">Yanıt</th>
                      <th className="px-4 py-2 text-left">Dağılım</th>
                      <th className="px-4 py-2 text-left">Son Yanıt</th>
                      <th className="px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {byRoom.map(r => (
                      <tr key={r.room_number} className="border-t hover:bg-gray-50">
                        <td className="px-4 py-2 font-semibold">{r.room_number}</td>
                        <td className="px-4 py-2">
                          <span className={`font-bold ${r.avg_score >= 9 ? 'text-emerald-600' : r.avg_score >= 7 ? 'text-amber-600' : 'text-red-600'}`}>
                            {r.avg_score?.toFixed(1)}
                          </span>
                          <span className="text-gray-400"> / 10</span>
                        </td>
                        <td className="px-4 py-2">{r.response_count}</td>
                        <td className="px-4 py-2">
                          <div className="flex gap-1 text-xs">
                            <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700">{r.promoters}</span>
                            <span className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700">{r.passives}</span>
                            <span className="px-1.5 py-0.5 rounded bg-red-50 text-red-700">{r.detractors}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2 text-xs text-gray-500">{fmtDate(r.last_responded_at)}</td>
                        <td className="px-4 py-2 text-right">
                          <Button
                            variant="ghost" size="sm" className="h-7 text-xs"
                            onClick={() => setFilterRoom(filterRoom === r.room_number ? '' : r.room_number)}
                          >
                            {filterRoom === r.room_number ? 'Filtreyi Kaldır' : 'Yorumları Gör'}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Son yorumlar */}
        <Card>
          <CardContent className="p-0">
            <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-indigo-600" />
                <h2 className="font-semibold text-sm">Son Yorumlar</h2>
                <span className="text-xs text-gray-500">({recent.length})</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                {filterCat && (
                  <Badge className={`${CATEGORY_BADGE[filterCat].cls} cursor-pointer`} onClick={() => setFilterCat('')}>
                    {CATEGORY_BADGE[filterCat].label} 
                  </Badge>
                )}
                {filterRoom && (
                  <Badge className="bg-blue-100 text-blue-700 border-blue-200 cursor-pointer" onClick={() => setFilterRoom('')}>
                    Oda {filterRoom} 
                  </Badge>
                )}
              </div>
            </div>
            {loading ? (
              <div className="p-8 text-center text-sm text-gray-400">Yükleniyor…</div>
            ) : recent.length === 0 ? (
              <div className="p-8 text-center text-sm text-gray-400">
                Bu dönem/filtre için yorum yok. Sağ üstten <strong>Yeni Yorum</strong> ekleyebilirsin.
              </div>
            ) : (
              <ul className="divide-y">
                {recent.map(s => {
                  const meta = CATEGORY_BADGE[s.category] || CATEGORY_BADGE.passive;
                  return (
                    <li key={s.id} className="p-4 flex gap-3 hover:bg-gray-50" data-testid={`feedback-${s.id}`}>
                      <div className="text-center min-w-[48px]">
                        <div className={`text-2xl font-bold ${s.nps_score >= 9 ? 'text-emerald-600' : s.nps_score >= 7 ? 'text-amber-600' : 'text-red-600'}`}>
                          {s.nps_score}
                        </div>
                        <div className="text-[10px] text-gray-400">/ 10</div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge className={`text-[10px] ${meta.cls}`}>{meta.label}</Badge>
                          {s.room_number && (
                            <span className="text-xs font-semibold text-gray-700">Oda {s.room_number}</span>
                          )}
                          {s.guest_name && (
                            <span className="text-xs text-gray-500">— {s.guest_name}</span>
                          )}
                          <span className="text-[10px] text-gray-400 ml-auto">
                            {fmtDate(s.responded_at)}
                            {s.recorded_by && ` • ${s.recorded_by}`}
                          </span>
                        </div>
                        {s.feedback && (
                          <p className="text-sm text-gray-700 mt-1 whitespace-pre-wrap break-words">
                            {s.feedback}
                          </p>
                        )}
                      </div>
                      <Button
                        variant="ghost" size="icon" className="h-8 w-8 text-gray-400 hover:text-red-600"
                        onClick={() => handleDelete(s.id)}
                        data-testid={`delete-${s.id}`}
                        title="Yorumu sil"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Yeni yorum dialog */}
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Yeni Misafir Yorumu</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Oda No</Label>
                  <Input
                    value={form.room_number}
                    onChange={e => setForm(f => ({ ...f, room_number: e.target.value }))}
                    placeholder="örn. 305"
                    data-testid="form-room"
                  />
                </div>
                <div>
                  <Label className="text-xs">Misafir Adı (opsiyonel)</Label>
                  <Input
                    value={form.guest_name}
                    onChange={e => setForm(f => ({ ...f, guest_name: e.target.value }))}
                    placeholder="Ad Soyad"
                    data-testid="form-guest"
                  />
                </div>
              </div>

              <div>
                <Label className="text-xs flex justify-between">
                  <span>Puan (0–10)</span>
                  <span className={`font-bold ${form.nps_score >= 9 ? 'text-emerald-600' : form.nps_score >= 7 ? 'text-amber-600' : 'text-red-600'}`}>
                    {form.nps_score} — {CATEGORY_BADGE[_npsCategory(form.nps_score)].label}
                  </span>
                </Label>
                <input
                  type="range" min="0" max="10" step="1"
                  value={form.nps_score}
                  onChange={e => setForm(f => ({ ...f, nps_score: Number(e.target.value) }))}
                  className="w-full mt-1"
                  data-testid="form-score"
                />
                <div className="flex justify-between text-[10px] text-gray-400 mt-1">
                  <span>0</span><span>5</span><span>10</span>
                </div>
              </div>

              <div>
                <Label className="text-xs">Yorum</Label>
                <textarea
                  rows={4}
                  value={form.feedback}
                  onChange={e => setForm(f => ({ ...f, feedback: e.target.value }))}
                  placeholder="Misafirin söylediği — şikayet, övgü, öneri…"
                  className="w-full border rounded-md px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-200"
                  data-testid="form-feedback"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowCreate(false)}>İptal</Button>
              <Button onClick={handleCreate} data-testid="form-submit">Kaydet</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

// Backend'le aynı kategori kuralı — client-side preview için
function _npsCategory(score) {
  return score <= 6 ? 'detractor' : score <= 8 ? 'passive' : 'promoter';
}

export default GuestJourney;
