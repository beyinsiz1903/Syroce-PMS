import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Calendar, ChevronLeft, ChevronRight, Plus, RefreshCw,
  Trash2, Users, ArrowLeft, Repeat, Check, X,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { confirmDialog, promptDialog } from '@/lib/dialogs';

const SHIFT_TYPES = {
  morning:   { label: 'Sabah',     intent: 'info',    times: ['07:00', '15:00'] },
  afternoon: { label: 'Öğle',      intent: 'warning', times: ['11:00', '19:00'] },
  evening:   { label: 'Akşam',     intent: 'warning', times: ['15:00', '23:00'] },
  night:     { label: 'Gece',      intent: 'neutral', times: ['23:00', '07:00'] },
  split:     { label: 'Bölünmüş',  intent: 'info',    times: ['09:00', '17:00'] },
};

const fmtDate = (d) => d.toISOString().slice(0, 10);
const startOfWeek = (date) => {
  const d = new Date(date);
  const day = d.getDay() || 7;
  if (day !== 1) d.setDate(d.getDate() - (day - 1));
  d.setHours(0, 0, 0, 0);
  return d;
};

const ShiftPlannerPage = () => {
  const navigate = useNavigate();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [shifts, setShifts] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dialog, setDialog] = useState({ open: false, form: null });
  const [swapDialog, setSwapDialog] = useState({ open: false, shift: null, target_staff_id: '', reason: '' });
  const [swapRequests, setSwapRequests] = useState([]);
  const [saving, setSaving] = useState(false);

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart); d.setDate(d.getDate() + i); return d;
  }), [weekStart]);

  const startStr = fmtDate(days[0]);
  const endStr = fmtDate(days[6]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [shRes, stRes, swRes] = await Promise.all([
        axios.get('/hr/shifts', { params: { start: startStr, end: endStr } }),
        axios.get('/hr/staff'),
        axios.get('/hr/shift-swap-requests').catch(() => ({ data: { items: [] } })),
      ]);
      setShifts(shRes.data?.items || []);
      setStaff(stRes.data?.staff || []);
      setSwapRequests(swRes.data?.items || []);
    } catch (err) {
      toast.error('Vardiyalar yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [startStr, endStr]);

  const openSwap = (shift) => setSwapDialog({
    open: true, shift, target_staff_id: '', reason: '',
  });

  const submitSwap = async (e) => {
    e.preventDefault();
    if (!swapDialog.target_staff_id) { toast.error('Hedef personel seçin'); return; }
    setSaving(true);
    try {
      await axios.post('/hr/shift-swap-request', {
        shift_id: swapDialog.shift.id,
        target_staff_id: swapDialog.target_staff_id,
        reason: swapDialog.reason,
      });
      toast.success('Değişim talebi gönderildi — İK onayını bekliyor');
      setSwapDialog({ open: false, shift: null, target_staff_id: '', reason: '' });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Talep gönderilemedi');
    } finally { setSaving(false); }
  };

  const decideSwap = async (req, action) => {
    let note = '';
    if (action === 'reject') {
      note = await promptDialog({ message: 'Red sebebi (opsiyonel):', defaultValue: '' });
      if (note === null) return;
    }
    try {
      await axios.post(`/hr/shift-swap-request/${req.id}/decision`, { action, note });
      toast.success(action === 'approve' ? 'Değişim onaylandı' : 'Değişim reddedildi');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem başarısız');
    }
  };

  const consentSwap = async (req, action) => {
    let note = '';
    if (action === 'reject') {
      note = await promptDialog({ message: 'Red sebebi (opsiyonel):', defaultValue: '' });
      if (note === null) return;
    } else if (!await confirmDialog({
      message: `${req.shift_date} ${req.shift_type} vardiyasını devralmayı kabul ediyor musunuz?`,
    })) return;
    try {
      await axios.post(`/hr/shift-swap-request/${req.id}/consent`, { action, note });
      toast.success(action === 'approve' ? 'Onay verildi — İK kararını bekliyor' : 'Reddettiniz');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem başarısız');
    }
  };

  const currentUserEmail = useMemo(() => {
    try { return (JSON.parse(localStorage.getItem('user') || '{}').email || '').toLowerCase(); }
    catch { return ''; }
  }, []);

  const incomingConsentRequests = useMemo(() => {
    if (!currentUserEmail) return [];
    return swapRequests.filter((r) => {
      if (r.target_consent_status !== 'pending' || r.status !== 'pending') return false;
      const target = staff.find((s) => s.id === r.target_staff_id);
      return target && (target.email || '').toLowerCase() === currentUserEmail;
    });
  }, [swapRequests, staff, currentUserEmail]);

  // Yöneticiler için bekleyen swaplar — sadece hedef rıza vermiş olanlar onaylanabilir,
  // diğerleri "rıza bekleniyor" olarak gösterilir.
  const pendingSwaps = useMemo(() => swapRequests.filter((r) => r.status === 'pending'), [swapRequests]);

  useEffect(() => { load(); }, [load]);

  const shiftsByStaffDay = useMemo(() => {
    const map = {};
    shifts.forEach((s) => {
      const key = `${s.staff_id}__${s.shift_date}`;
      (map[key] = map[key] || []).push(s);
    });
    return map;
  }, [shifts]);

  const allStaffShown = useMemo(() => {
    const merged = [...staff];
    const seen = new Set(staff.map((s) => s.id));
    shifts.forEach((s) => {
      if (!seen.has(s.staff_id)) {
        seen.add(s.staff_id);
        merged.push({ id: s.staff_id, name: s.staff_name || s.staff_id });
      }
    });
    return merged;
  }, [staff, shifts]);

  const openAdd = (staffId, date) => {
    setDialog({
      open: true,
      form: {
        staff_id: staffId || (staff[0]?.id ?? ''),
        shift_date: fmtDate(date || days[0]),
        shift_type: 'morning',
        start_time: '07:00',
        end_time: '15:00',
        notes: '',
      },
    });
  };

  const onTypeChange = (t) => {
    const def = SHIFT_TYPES[t];
    setDialog((d) => ({
      ...d, form: { ...d.form, shift_type: t, start_time: def.times[0], end_time: def.times[1] },
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    const f = dialog.form;
    if (!f.staff_id) { toast.error('Personel seçin'); return; }
    try {
      setSaving(true);
      await axios.post('/hr/shifts', f);
      toast.success('Vardiya planlandı');
      setDialog({ open: false, form: null });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    } finally {
      setSaving(false);
    }
  };

  const deleteShift = async (sh) => {
    if (!await confirmDialog({
      message: `${sh.staff_name} • ${sh.shift_date} ${sh.start_time} vardiyası silinsin mi?`,
    })) return;
    try {
      await axios.delete(`/hr/shifts/${sh.id}`);
      toast.success('Silindi');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  const headerActions = (
    <>
      <Button variant="outline" size="sm" onClick={() => navigate('/hr')}>
        <ArrowLeft className="w-4 h-4 mr-1.5" />İK Paneli
      </Button>
      <Button variant="outline" size="sm" onClick={load} disabled={loading}>
        <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Yenile
      </Button>
      <Button size="sm" onClick={() => openAdd()}>
        <Plus className="w-4 h-4 mr-1.5" />Vardiya Ekle
      </Button>
    </>
  );

  const moveWeek = (delta) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + delta * 7);
    setWeekStart(d);
  };

  return (
    <div className="p-2">
      <PageHeader
        icon={Calendar}
        title="Vardiya Planlayıcı"
        subtitle="Haftalık personel vardiya planı — hücreye tıklayarak ekle/kaldır"
        actions={headerActions}
      />

      <div className="grid gap-3 md:grid-cols-4 mb-4">
        <KpiCard intent="info" icon={Users} label="Aktif Personel" value={allStaffShown.length} />
        <KpiCard intent="success" icon={Calendar} label="Bu Hafta Vardiya" value={shifts.length} />
        <KpiCard intent="warning" label="Boş Personel-Gün"
          value={Math.max(0, allStaffShown.length * 7 - shifts.length)}
          sub="planlanmamış" />
        <KpiCard intent="neutral" label="Hafta"
          value={`${days[0].toLocaleDateString('tr-TR', { day: '2-digit', month: 'short' })} – ${days[6].toLocaleDateString('tr-TR', { day: '2-digit', month: 'short' })}`} />
      </div>

      {incomingConsentRequests.length > 0 && (
        <Card className="mb-4 border-sky-200 bg-sky-50/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sky-900">
              <Repeat className="w-4 h-4" />Bana Gelen Devralma Talepleri ({incomingConsentRequests.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {incomingConsentRequests.map((r) => (
                <div key={r.id} className="flex items-center gap-3 text-sm rounded border border-sky-200 bg-white p-2">
                  <div className="flex-1">
                    <div className="font-medium">
                      <span className="text-slate-700">{r.from_staff_name}</span> sizden devralmanızı istiyor
                    </div>
                    <div className="text-xs text-slate-500">
                      {r.shift_date} • {r.shift_type}
                      {r.reason && ` • Sebep: ${r.reason}`}
                    </div>
                  </div>
                  <Button size="sm" onClick={() => consentSwap(r, 'approve')}>
                    <Check className="w-3.5 h-3.5 mr-1" />Kabul Et
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => consentSwap(r, 'reject')}>
                    <X className="w-3.5 h-3.5 mr-1 text-rose-600" />Reddet
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {pendingSwaps.length > 0 && (
        <Card className="mb-4 border-amber-200 bg-amber-50/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-amber-900">
              <Repeat className="w-4 h-4" />Bekleyen Vardiya Değişim Talepleri ({pendingSwaps.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {pendingSwaps.map((r) => {
                const consentApproved = r.target_consent_status === 'approved';
                return (
                  <div key={r.id} className="flex items-center gap-3 text-sm rounded border border-amber-200 bg-white p-2">
                    <div className="flex-1">
                      <div className="font-medium">
                        {r.from_staff_name} → <span className="text-sky-700">{r.target_staff_name}</span>
                      </div>
                      <div className="text-xs text-slate-500">
                        {r.shift_date} • {r.shift_type}
                        {r.reason && ` • Sebep: ${r.reason}`}
                      </div>
                    </div>
                    <StatusBadge intent={consentApproved ? 'success' : 'warning'}>
                      {consentApproved ? 'Hedef onayladı' : 'Hedef rızası bekleniyor'}
                    </StatusBadge>
                    <Button size="sm" variant="outline" disabled={!consentApproved}
                      title={consentApproved ? 'Onayla' : 'Hedef personelin rızası alınmadan onaylanamaz'}
                      onClick={() => decideSwap(r, 'approve')}>
                      <Check className="w-3.5 h-3.5 mr-1 text-emerald-600" />Onayla
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => decideSwap(r, 'reject')}>
                      <X className="w-3.5 h-3.5 mr-1 text-rose-600" />Reddet
                    </Button>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => moveWeek(-1)}><ChevronLeft className="w-4 h-4" /></Button>
            <span className="px-2">
              {days[0].toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })}
              {' – '}
              {days[6].toLocaleDateString('tr-TR', { day: '2-digit', month: 'long' })}
            </span>
            <Button variant="outline" size="sm" onClick={() => moveWeek(1)}><ChevronRight className="w-4 h-4" /></Button>
            <Button variant="outline" size="sm" onClick={() => setWeekStart(startOfWeek(new Date()))}>Bu Hafta</Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr>
                  <th className="text-left py-2 px-2 border-b w-44">Personel</th>
                  {days.map((d) => (
                    <th key={fmtDate(d)} className="text-left py-2 px-2 border-b">
                      <div className="font-medium">
                        {d.toLocaleDateString('tr-TR', { weekday: 'short' })}
                      </div>
                      <div className="text-slate-400 text-[11px]">
                        {d.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit' })}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allStaffShown.map((p) => (
                  <tr key={p.id} className="border-b border-slate-50">
                    <td className="py-2 px-2 align-top">
                      <button
                        type="button"
                        onClick={() => navigate(`/staff/${p.id}`)}
                        className="font-medium text-slate-900 hover:text-sky-700 hover:underline text-left"
                      >
                        {p.name}
                      </button>
                      {p.department && (
                        <div className="text-[11px] text-slate-400 capitalize">{p.department}</div>
                      )}
                    </td>
                    {days.map((d) => {
                      const ds = fmtDate(d);
                      const list = shiftsByStaffDay[`${p.id}__${ds}`] || [];
                      return (
                        <td key={ds} className="align-top py-1 px-1 border-l border-slate-50">
                          <div className="space-y-1">
                            {list.map((sh) => {
                              const meta = SHIFT_TYPES[sh.shift_type] || SHIFT_TYPES.morning;
                              return (
                                <div key={sh.id} className="group flex items-center justify-between rounded border border-slate-200 px-1.5 py-1">
                                  <div className="flex flex-col">
                                    <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                                    <span className="text-[10px] text-slate-500 mt-0.5">
                                      {sh.start_time}–{sh.end_time}
                                    </span>
                                  </div>
                                  <div className="opacity-0 group-hover:opacity-100 flex gap-0.5">
                                    <button
                                      type="button"
                                      onClick={() => openSwap(sh)}
                                      className="text-slate-400 hover:text-sky-600"
                                      title="Değişim İste"
                                    >
                                      <Repeat className="w-3 h-3" />
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => deleteShift(sh)}
                                      className="text-slate-400 hover:text-rose-600"
                                      title="Sil"
                                    >
                                      <Trash2 className="w-3 h-3" />
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
                            <button
                              type="button"
                              onClick={() => openAdd(p.id, d)}
                              className="w-full text-[10px] text-slate-400 hover:text-slate-700 hover:bg-slate-50 rounded py-0.5 border border-dashed border-slate-200"
                            >
                              + ekle
                            </button>
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {allStaffShown.length === 0 && (
                  <tr><td colSpan={8} className="py-10 text-center text-slate-500">
                    Henüz personel yok — önce <button className="underline" onClick={() => navigate('/staff-management')}>Personel Yönetimi</button>'nden ekleyin.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Vardiya Değişim Talebi Dialog */}
      <Dialog open={swapDialog.open} onOpenChange={(o) => !o && setSwapDialog({ open: false, shift: null, target_staff_id: '', reason: '' })}>
        <DialogContent>
          <DialogHeader><DialogTitle className="flex items-center gap-2">
            <Repeat className="w-5 h-5 text-sky-600" />Vardiya Değişim Talebi
          </DialogTitle></DialogHeader>
          {swapDialog.shift && (
            <form onSubmit={submitSwap} className="grid gap-3">
              <div className="rounded bg-slate-50 border border-slate-200 p-3 text-sm">
                <div className="font-medium">{swapDialog.shift.staff_name}</div>
                <div className="text-xs text-slate-600">
                  {swapDialog.shift.shift_date} • {swapDialog.shift.shift_type}
                  {' • '}{swapDialog.shift.start_time}–{swapDialog.shift.end_time}
                </div>
              </div>
              <div>
                <Label className="text-xs">Vardiyayı Devralacak Personel *</Label>
                <select required value={swapDialog.target_staff_id}
                  onChange={(e) => setSwapDialog({ ...swapDialog, target_staff_id: e.target.value })}
                  className="w-full rounded-md border border-input px-3 py-2 text-sm">
                  <option value="">— Seçin —</option>
                  {allStaffShown.filter((p) => p.id !== swapDialog.shift.staff_id).map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs">Sebep / Not</Label>
                <Textarea rows={3} value={swapDialog.reason}
                  onChange={(e) => setSwapDialog({ ...swapDialog, reason: e.target.value })}
                  placeholder="Örn: Doktor randevusu nedeniyle değişiklik istiyorum" />
              </div>
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                Talep İK onayını bekleyecek. Onaylanırsa vardiya hedef personele otomatik aktarılır.
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setSwapDialog({ open: false, shift: null, target_staff_id: '', reason: '' })}>Vazgeç</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Gönderiliyor...' : 'Talep Gönder'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={dialog.open} onOpenChange={(o) => !o && setDialog({ open: false, form: null })}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Vardiya Ekle</DialogTitle>
          </DialogHeader>
          {dialog.form && (
            <form onSubmit={submit} className="grid gap-3">
              <div>
                <Label className="text-xs">Personel</Label>
                <select
                  value={dialog.form.staff_id}
                  onChange={(e) => setDialog({ ...dialog, form: { ...dialog.form, staff_id: e.target.value } })}
                  className="w-full rounded-md border border-input px-3 py-2 text-sm"
                >
                  <option value="">— Seçin —</option>
                  {allStaffShown.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">Tarih</Label>
                  <Input type="date" value={dialog.form.shift_date}
                    onChange={(e) => setDialog({ ...dialog, form: { ...dialog.form, shift_date: e.target.value } })} />
                </div>
                <div>
                  <Label className="text-xs">Vardiya Tipi</Label>
                  <select value={dialog.form.shift_type} onChange={(e) => onTypeChange(e.target.value)}
                    className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    {Object.entries(SHIFT_TYPES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">Başlangıç</Label>
                  <Input type="time" value={dialog.form.start_time}
                    onChange={(e) => setDialog({ ...dialog, form: { ...dialog.form, start_time: e.target.value } })} />
                </div>
                <div>
                  <Label className="text-xs">Bitiş</Label>
                  <Input type="time" value={dialog.form.end_time}
                    onChange={(e) => setDialog({ ...dialog, form: { ...dialog.form, end_time: e.target.value } })} />
                </div>
              </div>
              <div>
                <Label className="text-xs">Not</Label>
                <Input value={dialog.form.notes}
                  onChange={(e) => setDialog({ ...dialog, form: { ...dialog.form, notes: e.target.value } })}
                  placeholder="Opsiyonel" />
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setDialog({ open: false, form: null })}>Vazgeç</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ekle'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ShiftPlannerPage;
