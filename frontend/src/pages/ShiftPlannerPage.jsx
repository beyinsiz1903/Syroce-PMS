import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Calendar, ChevronLeft, ChevronRight, Plus, RefreshCw,
  Trash2, Users, ArrowLeft,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { confirmDialog } from '@/lib/dialogs';

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
  const [saving, setSaving] = useState(false);

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart); d.setDate(d.getDate() + i); return d;
  }), [weekStart]);

  const startStr = fmtDate(days[0]);
  const endStr = fmtDate(days[6]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [shRes, stRes] = await Promise.all([
        axios.get('/hr/shifts', { params: { start: startStr, end: endStr } }),
        axios.get('/hr/staff'),
      ]);
      setShifts(shRes.data?.items || []);
      setStaff(stRes.data?.staff || []);
    } catch (err) {
      toast.error('Vardiyalar yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [startStr, endStr]);

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
                                  <button
                                    type="button"
                                    onClick={() => deleteShift(sh)}
                                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-600"
                                    title="Sil"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </button>
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
