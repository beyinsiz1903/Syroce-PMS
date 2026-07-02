import { useTranslation } from "react-i18next";
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Calendar, ChevronLeft, ChevronRight, Plus, RefreshCw, Trash2, Users, ArrowLeft, Repeat, Check, X, Copy, AlertTriangle, Download, Filter } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { confirmDialog, promptDialog } from '@/lib/dialogs';
const SHIFT_TYPES = {
  morning: {
    label: 'Sabah',
    intent: 'info',
    times: ['07:00', '15:00'],
    crossesMidnight: false
  },
  afternoon: {
    label: 'Öğle',
    intent: 'warning',
    times: ['11:00', '19:00'],
    crossesMidnight: false
  },
  evening: {
    label: 'Akşam',
    intent: 'warning',
    times: ['15:00', '23:00'],
    crossesMidnight: false
  },
  night: {
    label: 'Gece',
    intent: 'neutral',
    times: ['22:00', '06:00'],
    crossesMidnight: true
  },
  split: {
    label: 'Bölünmüş',
    intent: 'info',
    times: ['09:00', '17:00'],
    crossesMidnight: false
  }
};
const fmtDate = d => d.toISOString().slice(0, 10);
const startOfWeek = date => {
  const d = new Date(date);
  const day = d.getDay() || 7;
  if (day !== 1) d.setDate(d.getDate() - (day - 1));
  d.setHours(0, 0, 0, 0);
  return d;
};
const ShiftPlannerPage = () => {
  const {
    t
  } = useTranslation();
  const navigate = useNavigate();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [shifts, setShifts] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dialog, setDialog] = useState({
    open: false,
    form: null
  });
  const [swapDialog, setSwapDialog] = useState({
    open: false,
    shift: null,
    target_staff_id: '',
    reason: ''
  });
  const [swapRequests, setSwapRequests] = useState([]);
  const [saving, setSaving] = useState(false);
  // Task #263: department filter + coverage + bulk
  const [deptFilter, setDeptFilter] = useState('');
  const [coverage, setCoverage] = useState({
    gaps: [],
    rules_count: 0
  });
  const [bulkDialog, setBulkDialog] = useState({
    open: false
  });
  const [bulkForm, setBulkForm] = useState({
    staff_ids: [],
    dates: [],
    shift_type: 'morning',
    start_time: '07:00',
    end_time: '15:00',
    crosses_midnight: false,
    notes: ''
  });
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [weeklyHours, setWeeklyHours] = useState([]);
  const days = useMemo(() => Array.from({
    length: 7
  }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    return d;
  }), [weekStart]);
  const startStr = fmtDate(days[0]);
  const endStr = fmtDate(days[6]);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const shParams = {
        start: startStr,
        end: endStr
      };
      if (deptFilter) shParams.department = deptFilter;
      const [shRes, stRes, swRes, covRes, whRes] = await Promise.all([axios.get('/hr/shifts', {
        params: shParams
      }), axios.get('/hr/staff'), axios.get('/hr/shift-swap-requests').catch(() => ({
        data: {
          items: []
        }
      })), axios.get('/hr/coverage/check', {
        params: {
          start: startStr,
          end: endStr
        }
      }).catch(() => ({
        data: {
          gaps: [],
          rules_count: 0
        }
      })), axios.get('/hr/shifts/weekly-hours', {
        params: {
          week_start: startStr
        }
      }).catch(() => ({
        data: {
          items: []
        }
      }))]);
      setShifts(shRes.data?.items || []);
      setStaff(stRes.data?.staff || []);
      setSwapRequests(swRes.data?.items || []);
      setCoverage({
        gaps: covRes.data?.gaps || [],
        rules_count: covRes.data?.rules_count || 0
      });
      setWeeklyHours(whRes.data?.items || []);
    } catch (err) {
      toast.error('Vardiyalar yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [startStr, endStr, deptFilter]);
  const departments = useMemo(() => {
    const set = new Set();
    staff.forEach(s => {
      if (s.department) set.add(s.department);
    });
    return Array.from(set).sort();
  }, [staff]);
  const hoursByStaff = useMemo(() => {
    const m = {};
    weeklyHours.forEach(w => {
      m[w.staff_id] = w;
    });
    return m;
  }, [weeklyHours]);
  const openBulk = () => {
    setBulkForm({
      staff_ids: [],
      dates: days.map(fmtDate),
      shift_type: 'morning',
      start_time: '07:00',
      end_time: '15:00',
      crosses_midnight: false,
      notes: ''
    });
    setBulkDialog({
      open: true
    });
  };
  const onBulkTypeChange = t => {
    const def = SHIFT_TYPES[t];
    setBulkForm(f => ({
      ...f,
      shift_type: t,
      start_time: def.times[0],
      end_time: def.times[1],
      crosses_midnight: !!def.crossesMidnight
    }));
  };
  const toggleBulkStaff = sid => {
    setBulkForm(f => ({
      ...f,
      staff_ids: f.staff_ids.includes(sid) ? f.staff_ids.filter(x => x !== sid) : [...f.staff_ids, sid]
    }));
  };
  const toggleBulkDate = d => {
    setBulkForm(f => ({
      ...f,
      dates: f.dates.includes(d) ? f.dates.filter(x => x !== d) : [...f.dates, d]
    }));
  };
  const submitBulk = async e => {
    e.preventDefault();
    if (!bulkForm.staff_ids.length || !bulkForm.dates.length) {
      toast.error('En az 1 personel ve 1 gün seçin');
      return;
    }
    try {
      setBulkSubmitting(true);
      const res = await axios.post('/hr/shifts/bulk', bulkForm);
      const created = res.data?.created_count || 0;
      const skipped = res.data?.skipped_count || 0;
      toast.success(`${created} vardiya planlandı${skipped ? ` • ${skipped} atlandı (izin/çakışma)` : ''}`);
      setBulkDialog({
        open: false
      });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Toplu oluşturma başarısız');
    } finally {
      setBulkSubmitting(false);
    }
  };
  const downloadShiftsXlsx = async () => {
    try {
      const res = await axios.get('/hr/shifts/export/xlsx', {
        params: {
          start: startStr,
          end: endStr
        },
        responseType: 'blob'
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `vardiyalar_${startStr}_${endStr}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error('Excel indirilemedi');
    }
  };
  const openSwap = shift => setSwapDialog({
    open: true,
    shift,
    target_staff_id: '',
    reason: ''
  });
  const submitSwap = async e => {
    e.preventDefault();
    if (!swapDialog.target_staff_id) {
      toast.error('Hedef personel seçin');
      return;
    }
    setSaving(true);
    try {
      await axios.post('/hr/shift-swap-request', {
        shift_id: swapDialog.shift.id,
        target_staff_id: swapDialog.target_staff_id,
        reason: swapDialog.reason
      });
      toast.success('Değişim talebi gönderildi — İK onayını bekliyor');
      setSwapDialog({
        open: false,
        shift: null,
        target_staff_id: '',
        reason: ''
      });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Talep gönderilemedi');
    } finally {
      setSaving(false);
    }
  };
  const decideSwap = async (req, action) => {
    let note = '';
    if (action === 'reject') {
      note = await promptDialog({
        message: 'Red sebebi (opsiyonel):',
        defaultValue: ''
      });
      if (note === null) return;
    }
    try {
      await axios.post(`/hr/shift-swap-request/${req.id}/decision`, {
        action,
        note
      });
      toast.success(action === 'approve' ? 'Değişim onaylandı' : 'Değişim reddedildi');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem başarısız');
    }
  };
  const consentSwap = async (req, action) => {
    let note = '';
    if (action === 'reject') {
      note = await promptDialog({
        message: 'Red sebebi (opsiyonel):',
        defaultValue: ''
      });
      if (note === null) return;
    } else if (!(await confirmDialog({
      message: `${req.shift_date} ${req.shift_type} vardiyasını devralmayı kabul ediyor musunuz?`
    }))) return;
    try {
      await axios.post(`/hr/shift-swap-request/${req.id}/consent`, {
        action,
        note
      });
      toast.success(action === 'approve' ? 'Onay verildi — İK kararını bekliyor' : 'Reddettiniz');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem başarısız');
    }
  };
  const currentUserEmail = useMemo(() => {
    try {
      return (JSON.parse(localStorage.getItem('user') || '{}').email || '').toLowerCase();
    } catch {
      return '';
    }
  }, []);
  const incomingConsentRequests = useMemo(() => {
    if (!currentUserEmail) return [];
    return swapRequests.filter(r => {
      if (r.target_consent_status !== 'pending' || r.status !== 'pending') return false;
      const target = staff.find(s => s.id === r.target_staff_id);
      return target && (target.email || '').toLowerCase() === currentUserEmail;
    });
  }, [swapRequests, staff, currentUserEmail]);

  // Yöneticiler için bekleyen swaplar — sadece hedef rıza vermiş olanlar onaylanabilir,
  // diğerleri "rıza bekleniyor" olarak gösterilir.
  const pendingSwaps = useMemo(() => swapRequests.filter(r => r.status === 'pending'), [swapRequests]);
  useEffect(() => {
    load();
  }, [load]);
  const shiftsByStaffDay = useMemo(() => {
    const map = {};
    shifts.forEach(s => {
      const key = `${s.staff_id}__${s.shift_date}`;
      (map[key] = map[key] || []).push(s);
    });
    return map;
  }, [shifts]);

  // Task #257: gece vardiyaları ertesi gün hücresinde de "← 06:00 (önceki gün)"
  // şeklinde görünmeli. Ayrı bir overflow map tutuyoruz; ana liste değişmez
  // (KPI sayımı çift sayım yapmaz, "Bu Hafta Vardiya" hâlâ shifts.length).
  const overnightByStaffDay = useMemo(() => {
    const map = {};
    shifts.forEach(s => {
      if (!s.crosses_midnight || !s.shift_date) return;
      const start = new Date(`${s.shift_date}T00:00:00`);
      if (Number.isNaN(start.getTime())) return;
      const next = new Date(start);
      next.setDate(next.getDate() + 1);
      const nextStr = fmtDate(next);
      const key = `${s.staff_id}__${nextStr}`;
      (map[key] = map[key] || []).push(s);
    });
    return map;
  }, [shifts]);
  const allStaffShown = useMemo(() => {
    const merged = [...staff];
    const seen = new Set(staff.map(s => s.id));
    shifts.forEach(s => {
      if (!seen.has(s.staff_id)) {
        seen.add(s.staff_id);
        merged.push({
          id: s.staff_id,
          name: s.staff_name || s.staff_id
        });
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
        crosses_midnight: false,
        notes: ''
      }
    });
  };
  const onTypeChange = t => {
    const def = SHIFT_TYPES[t];
    setDialog(d => ({
      ...d,
      form: {
        ...d.form,
        shift_type: t,
        start_time: def.times[0],
        end_time: def.times[1],
        crosses_midnight: !!def.crossesMidnight
      }
    }));
  };
  const submit = async e => {
    e.preventDefault();
    const f = dialog.form;
    if (!f.staff_id) {
      toast.error('Personel seçin');
      return;
    }
    try {
      setSaving(true);
      await axios.post('/hr/shifts', f);
      toast.success('Vardiya planlandı');
      setDialog({
        open: false,
        form: null
      });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    } finally {
      setSaving(false);
    }
  };
  const deleteShift = async sh => {
    if (!(await confirmDialog({
      message: `${sh.staff_name} • ${sh.shift_date} ${sh.start_time} vardiyası silinsin mi?`
    }))) return;
    try {
      await axios.delete(`/hr/shifts/${sh.id}`);
      toast.success('Silindi');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };
  const headerActions = <>
      <Button variant="outline" size="sm" onClick={() => navigate('/hr')}>
        <ArrowLeft className="w-4 h-4 mr-1.5" />{t("cm.pages_ShiftPlannerPage.i_k_paneli")}</Button>
      <Button variant="outline" size="sm" onClick={downloadShiftsXlsx}>
        <Download className="w-4 h-4 mr-1.5" />{t("cm.pages_ShiftPlannerPage.excel")}</Button>
      <Button variant="outline" size="sm" onClick={load} disabled={loading}>
        <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />{t("cm.pages_ShiftPlannerPage.yenile")}</Button>
      <Button variant="outline" size="sm" onClick={openBulk} data-testid="btn-bulk-shift">
        <Copy className="w-4 h-4 mr-1.5" />{t("cm.pages_ShiftPlannerPage.toplu_olu\u015Ftur")}</Button>
      <Button size="sm" onClick={() => openAdd()}>
        <Plus className="w-4 h-4 mr-1.5" />{t("cm.pages_ShiftPlannerPage.vardiya_ekle")}</Button>
    </>;
  const moveWeek = delta => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + delta * 7);
    setWeekStart(d);
  };
  return <div className="p-2">
      <PageHeader icon={Calendar} title={t("cm.pages_ShiftPlannerPage.vardiya_planlay\u0131c\u0131")} subtitle="Haftalık personel vardiya planı — hücreye tıklayarak ekle/kaldır" actions={headerActions} />

      <div className="grid gap-3 md:grid-cols-4 mb-4">
        <KpiCard intent="info" icon={Users} label={t("cm.pages_ShiftPlannerPage.aktif_personel")} value={allStaffShown.length} />
        <KpiCard intent="success" icon={Calendar} label={t("cm.pages_ShiftPlannerPage.bu_hafta_vardiya")} value={shifts.length} />
        <KpiCard intent="warning" label={t("cm.pages_ShiftPlannerPage.bo\u015F_personel_g\xFCn")} value={Math.max(0, allStaffShown.length * 7 - shifts.length)} sub="planlanmamış" />
        <KpiCard intent="neutral" label={t("cm.pages_ShiftPlannerPage.hafta")} value={`${days[0].toLocaleDateString('tr-TR', {
        day: '2-digit',
        month: 'short'
      })} – ${days[6].toLocaleDateString('tr-TR', {
        day: '2-digit',
        month: 'short'
      })}`} />
      </div>

      {coverage.gaps.length > 0 && <Card className="mb-4 border-rose-200 bg-rose-50/50" data-testid="coverage-warning">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-rose-900 text-sm">
              <AlertTriangle className="w-4 h-4" />{t("cm.pages_ShiftPlannerPage.kapsama_a\xE7\u0131\u011F\u0131")}{coverage.gaps.length}) — {coverage.rules_count}{t("cm.pages_ShiftPlannerPage.kural")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xs grid gap-1 md:grid-cols-2 lg:grid-cols-3">
              {coverage.gaps.slice(0, 12).map((g, i) => <div key={g.id || i} className="rounded border border-rose-200 bg-white px-2 py-1">
                  <span className="font-medium">{g.date}</span> • <span className="capitalize">{g.department}</span> ({g.shift_type})
                  <span className="ml-1 text-rose-700">{g.actual}/{g.min_staff}</span>
                </div>)}
              {coverage.gaps.length > 12 && <div className="text-rose-500">+{coverage.gaps.length - 12}{t("cm.pages_ShiftPlannerPage.daha")}</div>}
            </div>
          </CardContent>
        </Card>}

      <div className="flex items-center gap-2 mb-3 text-sm">
        <Filter className="w-4 h-4 text-slate-500" />
        <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.departman")}</Label>
        <select value={deptFilter} onChange={e => setDeptFilter(e.target.value)} className="rounded-md border border-input px-2 py-1 text-xs" data-testid="select-dept-filter">
          <option value="">{t("cm.pages_ShiftPlannerPage.t\xFCm\xFC")}</option>
          {departments.map(d => <option key={d} value={d} className="capitalize">{d}</option>)}
        </select>
      </div>

      {incomingConsentRequests.length > 0 && <Card className="mb-4 border-sky-200 bg-sky-50/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sky-900">
              <Repeat className="w-4 h-4" />{t("cm.pages_ShiftPlannerPage.bana_gelen_devralma_talepleri")}{incomingConsentRequests.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {incomingConsentRequests.map(r => <div key={r.id} className="flex items-center gap-3 text-sm rounded border border-sky-200 bg-white p-2">
                  <div className="flex-1">
                    <div className="font-medium">
                      <span className="text-slate-700">{r.from_staff_name}</span>{t("cm.pages_ShiftPlannerPage.sizden_devralman\u0131z\u0131_istiyor")}</div>
                    <div className="text-xs text-slate-500">
                      {r.shift_date} • {r.shift_type}
                      {r.reason && ` • Sebep: ${r.reason}`}
                    </div>
                  </div>
                  <Button size="sm" onClick={() => consentSwap(r, 'approve')}>
                    <Check className="w-3.5 h-3.5 mr-1" />{t("cm.pages_ShiftPlannerPage.kabul_et")}</Button>
                  <Button size="sm" variant="outline" onClick={() => consentSwap(r, 'reject')}>
                    <X className="w-3.5 h-3.5 mr-1 text-rose-600" />{t("cm.pages_ShiftPlannerPage.reddet")}</Button>
                </div>)}
            </div>
          </CardContent>
        </Card>}

      {pendingSwaps.length > 0 && <Card className="mb-4 border-amber-200 bg-amber-50/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-amber-900">
              <Repeat className="w-4 h-4" />{t("cm.pages_ShiftPlannerPage.bekleyen_vardiya_de\u011Fi\u015Fim_talep")}{pendingSwaps.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {pendingSwaps.map(r => {
            const consentApproved = r.target_consent_status === 'approved';
            return <div key={r.id} className="flex items-center gap-3 text-sm rounded border border-amber-200 bg-white p-2">
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
                    <Button size="sm" variant="outline" disabled={!consentApproved} title={consentApproved ? 'Onayla' : 'Hedef personelin rızası alınmadan onaylanamaz'} onClick={() => decideSwap(r, 'approve')}>
                      <Check className="w-3.5 h-3.5 mr-1 text-emerald-600" />{t("cm.pages_ShiftPlannerPage.onayla")}</Button>
                    <Button size="sm" variant="outline" onClick={() => decideSwap(r, 'reject')}>
                      <X className="w-3.5 h-3.5 mr-1 text-rose-600" />{t("cm.pages_ShiftPlannerPage.reddet")}</Button>
                  </div>;
          })}
            </div>
          </CardContent>
        </Card>}

      <Card>
        <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => moveWeek(-1)}><ChevronLeft className="w-4 h-4" /></Button>
            <span className="px-2">
              {days[0].toLocaleDateString('tr-TR', {
              day: '2-digit',
              month: 'long',
              year: 'numeric'
            })}
              {' – '}
              {days[6].toLocaleDateString('tr-TR', {
              day: '2-digit',
              month: 'long'
            })}
            </span>
            <Button variant="outline" size="sm" onClick={() => moveWeek(1)}><ChevronRight className="w-4 h-4" /></Button>
            <Button variant="outline" size="sm" onClick={() => setWeekStart(startOfWeek(new Date()))}>{t("cm.pages_ShiftPlannerPage.bu_hafta")}</Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr>
                  <th className="text-left py-2 px-2 border-b w-44">{t("cm.pages_ShiftPlannerPage.personel")}</th>
                  {days.map(d => <th key={fmtDate(d)} className="text-left py-2 px-2 border-b">
                      <div className="font-medium">
                        {d.toLocaleDateString('tr-TR', {
                      weekday: 'short'
                    })}
                      </div>
                      <div className="text-slate-400 text-[11px]">
                        {d.toLocaleDateString('tr-TR', {
                      day: '2-digit',
                      month: '2-digit'
                    })}
                      </div>
                    </th>)}
                </tr>
              </thead>
              <tbody>
                {allStaffShown.map(p => <tr key={p.id} className="border-b border-slate-50">
                    <td className="py-2 px-2 align-top">
                      <button type="button" onClick={() => navigate(`/staff/${p.id}`)} className="font-medium text-slate-900 hover:text-sky-700 hover:underline text-left">
                        {p.name}
                      </button>
                      {p.department && <div className="text-[11px] text-slate-400 capitalize">{p.department}</div>}
                      {hoursByStaff[p.id] && (() => {
                    const h = hoursByStaff[p.id];
                    const total = Number(h.total_hours ?? h.hours ?? 0);
                    const over = Number(h.overtime_estimate ?? Math.max(0, total - 45));
                    const exceeds = total > 45 || h.exceeds_legal_limit;
                    return <div className={`text-[11px] mt-0.5 ${exceeds ? 'text-rose-700 font-medium' : 'text-slate-500'}`} data-testid={`wk-hours-${p.id}`} title={exceeds ? `Yasal sınır (45h) aşıldı — tahmini fazla mesai ${over.toFixed(1)}h` : 'Haftalık toplam'}>
                            {total.toFixed(1)}h{exceeds ? ` • +${over.toFixed(1)}h FM` : ''}
                          </div>;
                  })()}
                    </td>
                    {days.map(d => {
                  const ds = fmtDate(d);
                  const list = shiftsByStaffDay[`${p.id}__${ds}`] || [];
                  const overflow = overnightByStaffDay[`${p.id}__${ds}`] || [];
                  return <td key={ds} className="align-top py-1 px-1 border-l border-slate-50">
                          <div className="space-y-1">
                            {overflow.map(sh => {
                        const meta = SHIFT_TYPES[sh.shift_type] || SHIFT_TYPES.night;
                        return <div key={`ovf-${sh.id}`} className="flex items-center gap-1 rounded border border-dashed border-slate-200 bg-slate-50/60 px-1.5 py-1" title={`Önceki günden devam: ${sh.shift_date} ${sh.start_time}–${sh.end_time}`}>
                                  <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                                  <span className="text-[10px] text-slate-500">
                                    ← {sh.end_time} <span className="text-slate-400">{t("cm.pages_ShiftPlannerPage._\xF6nceki_g\xFCn")}</span>
                                  </span>
                                </div>;
                      })}
                            {list.map(sh => {
                        const meta = SHIFT_TYPES[sh.shift_type] || SHIFT_TYPES.morning;
                        return <div key={sh.id} className="group flex items-center justify-between rounded border border-slate-200 px-1.5 py-1">
                                  <div className="flex flex-col">
                                    <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                                    <span className="text-[10px] text-slate-500 mt-0.5">
                                      {sh.start_time}–{sh.end_time}
                                      {sh.crosses_midnight && <span className="ml-1 text-slate-400" title={t("cm.pages_ShiftPlannerPage.ertesi_g\xFCne_sarkar")}>{t("cm.pages_ShiftPlannerPage._1g")}</span>}
                                    </span>
                                  </div>
                                  <div className="opacity-0 group-hover:opacity-100 flex gap-0.5">
                                    <button type="button" onClick={() => openSwap(sh)} className="text-slate-400 hover:text-sky-600" title={t("cm.pages_ShiftPlannerPage.de\u011Fi\u015Fim_i_ste")}>
                                      <Repeat className="w-3 h-3" />
                                    </button>
                                    <button type="button" onClick={() => deleteShift(sh)} className="text-slate-400 hover:text-rose-600" title={t("cm.pages_ShiftPlannerPage.sil")}>
                                      <Trash2 className="w-3 h-3" />
                                    </button>
                                  </div>
                                </div>;
                      })}
                            <button type="button" onClick={() => openAdd(p.id, d)} className="w-full text-[10px] text-slate-400 hover:text-slate-700 hover:bg-slate-50 rounded py-0.5 border border-dashed border-slate-200">{t("cm.pages_ShiftPlannerPage._ekle")}</button>
                          </div>
                        </td>;
                })}
                  </tr>)}
                {allStaffShown.length === 0 && <tr><td colSpan={8} className="py-10 text-center text-slate-500">{t("cm.pages_ShiftPlannerPage.hen\xFCz_personel_yok_\xF6nce")}<button className="underline" onClick={() => navigate('/staff-management')}>{t("cm.pages_ShiftPlannerPage.personel_y\xF6netimi")}</button>{t("cm.pages_ShiftPlannerPage._nden_ekleyin")}</td></tr>}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Vardiya Değişim Talebi Dialog */}
      <Dialog open={swapDialog.open} onOpenChange={o => !o && setSwapDialog({
      open: false,
      shift: null,
      target_staff_id: '',
      reason: ''
    })}>
        <DialogContent>
          <DialogHeader><DialogTitle className="flex items-center gap-2">
            <Repeat className="w-5 h-5 text-sky-600" />{t("cm.pages_ShiftPlannerPage.vardiya_de\u011Fi\u015Fim_talebi")}</DialogTitle></DialogHeader>
          {swapDialog.shift && <form onSubmit={submitSwap} className="grid gap-3">
              <div className="rounded bg-slate-50 border border-slate-200 p-3 text-sm">
                <div className="font-medium">{swapDialog.shift.staff_name}</div>
                <div className="text-xs text-slate-600">
                  {swapDialog.shift.shift_date} • {swapDialog.shift.shift_type}
                  {' • '}{swapDialog.shift.start_time}–{swapDialog.shift.end_time}
                </div>
              </div>
              <div>
                <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.vardiyay\u0131_devralacak_personel")}</Label>
                <select required value={swapDialog.target_staff_id} onChange={e => setSwapDialog({
              ...swapDialog,
              target_staff_id: e.target.value
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                  <option value="">{t("cm.pages_ShiftPlannerPage._se\xE7in")}</option>
                  {allStaffShown.filter(p => p.id !== swapDialog.shift.staff_id).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.sebep_not")}</Label>
                <Textarea rows={3} value={swapDialog.reason} onChange={e => setSwapDialog({
              ...swapDialog,
              reason: e.target.value
            })} placeholder={t("cm.pages_ShiftPlannerPage.\xF6rn_doktor_randevusu_nedeniyle")} />
              </div>
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">{t("cm.pages_ShiftPlannerPage.talep_i_k_onay\u0131n\u0131_bekleyecek_o")}</div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setSwapDialog({
              open: false,
              shift: null,
              target_staff_id: '',
              reason: ''
            })}>{t("cm.pages_ShiftPlannerPage.vazge\xE7")}</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Gönderiliyor...' : 'Talep Gönder'}</Button>
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>

      <Dialog open={dialog.open} onOpenChange={o => !o && setDialog({
      open: false,
      form: null
    })}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("cm.pages_ShiftPlannerPage.vardiya_ekle")}</DialogTitle>
          </DialogHeader>
          {dialog.form && <form onSubmit={submit} className="grid gap-3">
              <div>
                <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.personel")}</Label>
                <select value={dialog.form.staff_id} onChange={e => setDialog({
              ...dialog,
              form: {
                ...dialog.form,
                staff_id: e.target.value
              }
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                  <option value="">{t("cm.pages_ShiftPlannerPage._se\xE7in")}</option>
                  {allStaffShown.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.tarih")}</Label>
                  <Input type="date" value={dialog.form.shift_date} onChange={e => setDialog({
                ...dialog,
                form: {
                  ...dialog.form,
                  shift_date: e.target.value
                }
              })} />
                </div>
                <div>
                  <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.vardiya_tipi")}</Label>
                  <select value={dialog.form.shift_type} onChange={e => onTypeChange(e.target.value)} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    {Object.entries(SHIFT_TYPES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.ba\u015Flang\u0131\xE7")}</Label>
                  <Input type="time" value={dialog.form.start_time} onChange={e => setDialog({
                ...dialog,
                form: {
                  ...dialog.form,
                  start_time: e.target.value
                }
              })} />
                </div>
                <div>
                  <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.biti\u015F")}{dialog.form.crosses_midnight && <span className="text-slate-400">{t("cm.pages_ShiftPlannerPage._ertesi_g\xFCn")}</span>}
                  </Label>
                  <Input type="time" value={dialog.form.end_time} onChange={e => setDialog({
                ...dialog,
                form: {
                  ...dialog.form,
                  end_time: e.target.value
                }
              })} />
                </div>
              </div>
              <label className="flex items-start gap-2 text-xs text-slate-700 rounded border border-slate-200 bg-slate-50 p-2 cursor-pointer">
                <input type="checkbox" className="mt-0.5" checked={!!dialog.form.crosses_midnight} onChange={e => setDialog({
              ...dialog,
              form: {
                ...dialog.form,
                crosses_midnight: e.target.checked
              }
            })} />
                <span>
                  <span className="font-medium">{t("cm.pages_ShiftPlannerPage.gece_vardiyas\u0131_ertesi_g\xFCne_sar")}</span>
                  <span className="block text-slate-500 mt-0.5">{t("cm.pages_ShiftPlannerPage.\xF6rn_22_00_06_00_biti\u015F_saati_ba")}</span>
                </span>
              </label>
              <div>
                <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.not")}</Label>
                <Input value={dialog.form.notes} onChange={e => setDialog({
              ...dialog,
              form: {
                ...dialog.form,
                notes: e.target.value
              }
            })} placeholder={t("cm.pages_ShiftPlannerPage.opsiyonel")} />
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setDialog({
              open: false,
              form: null
            })}>{t("cm.pages_ShiftPlannerPage.vazge\xE7")}</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ekle'}</Button>
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>
      {/* Toplu Vardiya Oluştur (Task #263) */}
      <Dialog open={bulkDialog.open} onOpenChange={o => !o && setBulkDialog({
      open: false
    })}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle className="flex items-center gap-2">
            <Copy className="w-5 h-5" />{t("cm.pages_ShiftPlannerPage.toplu_vardiya_olu\u015Ftur")}</DialogTitle></DialogHeader>
          <form onSubmit={submitBulk} className="grid gap-3">
            <div className="grid md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.vardiya_tipi")}</Label>
                <select value={bulkForm.shift_type} onChange={e => onBulkTypeChange(e.target.value)} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                  {Object.entries(SHIFT_TYPES).map(([k, v]) => <option key={k} value={k}>{v.label} ({v.times[0]}–{v.times[1]})</option>)}
                </select>
              </div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.ba\u015Flang\u0131\xE7")}</Label>
                  <Input type="time" value={bulkForm.start_time} onChange={e => setBulkForm({
                  ...bulkForm,
                  start_time: e.target.value
                })} />
                </div>
                <div className="flex-1">
                  <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.biti\u015F")}</Label>
                  <Input type="time" value={bulkForm.end_time} onChange={e => setBulkForm({
                  ...bulkForm,
                  end_time: e.target.value
                })} />
                </div>
              </div>
            </div>

            <div>
              <Label className="text-xs flex items-center justify-between">
                <span>{t("cm.pages_ShiftPlannerPage.personel")}{bulkForm.staff_ids.length}{t("cm.pages_ShiftPlannerPage.se\xE7ili")}</span>
                <button type="button" className="text-[11px] underline text-slate-600" onClick={() => setBulkForm({
                ...bulkForm,
                staff_ids: bulkForm.staff_ids.length === allStaffShown.length ? [] : allStaffShown.map(p => p.id)
              })}>
                  {bulkForm.staff_ids.length === allStaffShown.length ? 'Hiçbiri' : 'Tümü'}
                </button>
              </Label>
              <div className="max-h-44 overflow-y-auto rounded border border-slate-200 p-2 grid grid-cols-2 md:grid-cols-3 gap-1">
                {allStaffShown.map(p => <label key={p.id} className="flex items-center gap-1 text-xs cursor-pointer hover:bg-slate-50 rounded px-1 py-0.5">
                    <input type="checkbox" checked={bulkForm.staff_ids.includes(p.id)} onChange={() => toggleBulkStaff(p.id)} />
                    <span>{p.name}</span>
                  </label>)}
              </div>
            </div>

            <div>
              <Label className="text-xs flex items-center justify-between">
                <span>{t("cm.pages_ShiftPlannerPage.g\xFCnler")}{bulkForm.dates.length}{t("cm.pages_ShiftPlannerPage.se\xE7ili")}</span>
                <button type="button" className="text-[11px] underline text-slate-600" onClick={() => setBulkForm({
                ...bulkForm,
                dates: bulkForm.dates.length === 7 ? [] : days.map(fmtDate)
              })}>
                  {bulkForm.dates.length === 7 ? 'Hiçbiri' : 'Tüm Hafta'}
                </button>
              </Label>
              <div className="flex gap-1 flex-wrap">
                {days.map(d => {
                const ds = fmtDate(d);
                const on = bulkForm.dates.includes(ds);
                return <button key={ds} type="button" onClick={() => toggleBulkDate(ds)} className={`px-2 py-1 rounded text-[11px] border ${on ? 'bg-slate-900 text-white border-slate-900' : 'bg-white border-slate-200'}`}>
                      {d.toLocaleDateString('tr-TR', {
                    weekday: 'short',
                    day: '2-digit'
                  })}
                    </button>;
              })}
              </div>
            </div>

            <div>
              <Label className="text-xs">{t("cm.pages_ShiftPlannerPage.not")}</Label>
              <Textarea rows={2} value={bulkForm.notes} onChange={e => setBulkForm({
              ...bulkForm,
              notes: e.target.value
            })} />
            </div>

            <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">{t("cm.pages_ShiftPlannerPage.onayl\u0131_izinli_pasif_personelle")}</div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setBulkDialog({
              open: false
            })}>{t("cm.pages_ShiftPlannerPage.vazge\xE7")}</Button>
              <Button type="submit" disabled={bulkSubmitting} data-testid="btn-bulk-submit">
                {bulkSubmitting ? 'Oluşturuluyor...' : `${bulkForm.staff_ids.length * bulkForm.dates.length} Vardiya Oluştur`}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>;
};
export default ShiftPlannerPage;