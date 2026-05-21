import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  ArrowLeft, RefreshCw, User, Mail, Phone, Building2, Briefcase,
  Calendar, Clock, DollarSign, Award, FileText, AlertCircle,
  GraduationCap, Folder, TrendingUp, UserMinus, Plus, Trash2,
  Download, Upload, ChevronDown, ChevronRight, Target,
  Package, ShieldAlert, BookOpen, Check, RotateCcw,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { formatCurrency } from '@/lib/currency';
import { confirmDialog } from '@/lib/dialogs';

const LEAVE_TYPE_LABEL = {
  annual: 'Yıllık', sick: 'Hastalık', maternity: 'Doğum',
  paternity: 'Babalık', unpaid: 'Ücretsiz', bereavement: 'Vefat',
  excused: 'Mazeret',
};
const STATUS_INTENT = {
  pending: 'warning', approved: 'success', rejected: 'danger',
  scheduled: 'info', completed: 'success', missed: 'danger',
  on_track: 'success', at_risk: 'warning', blocked: 'danger', done: 'success',
};
const STATUS_LABEL = {
  pending: 'Beklemede', approved: 'Onaylandı', rejected: 'Reddedildi',
  scheduled: 'Planlı', completed: 'Tamamlandı', missed: 'Kaçırıldı',
  on_track: 'Yolunda', at_risk: 'Risk', blocked: 'Bloke', done: 'Tamam',
};
const DOC_TYPE_LABEL = {
  contract: 'Sözleşme', id: 'Kimlik', diploma: 'Diploma',
  health: 'Sağlık', insurance: 'Sigorta', tax: 'Vergi', other: 'Diğer',
};
const TERM_REASON_LABEL = {
  resign: 'İstifa', dismiss: 'İşten çıkarma', mutual: 'Karşılıklı anlaşma',
  retire: 'Emeklilik', end_of_contract: 'Sözleşme bitti', death: 'Vefat',
};
const CHANGE_TYPE_LABEL = {
  raise: 'Zam', promotion: 'Terfi', correction: 'Düzeltme', demotion: 'İndirim',
};

const StaffProfile = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

  // Section states
  const [certs, setCerts] = useState({ items: [], active: 0, expired: 0, error: null });
  const [docs, setDocs] = useState([]);
  const [docsError, setDocsError] = useState(null);
  const [salaryHistory, setSalaryHistory] = useState([]);
  const [salaryError, setSalaryError] = useState(null);
  const [termination, setTermination] = useState(null);
  // Task #265 (İK v2 Lifecycle): Zimmet / Uyarı / Eğitim section state.
  const [equipment, setEquipment] = useState({ items: [], active: 0, returned: 0, lost: 0, error: null });
  const [warnings, setWarnings] = useState({ items: [], by_type: { verbal: 0, written: 0, final: 0 }, error: null });
  const [trainings, setTrainings] = useState({ items: [], valid: 0, expired: 0, error: null });

  // Dialogs
  const [certDialog, setCertDialog] = useState({ open: false, form: null });
  const [docDialog, setDocDialog] = useState({ open: false, file: null, doc_type: 'contract', label: '' });
  const [salaryDialog, setSalaryDialog] = useState({ open: false, form: null });
  const [termDialog, setTermDialog] = useState({ open: false, form: null, outstanding: [] });
  const [checkinDialog, setCheckinDialog] = useState({ open: false, reviewId: null, form: null });
  const [eqDialog, setEqDialog] = useState({ open: false, form: null });
  const [warnDialog, setWarnDialog] = useState({ open: false, form: null });
  const [trainDialog, setTrainDialog] = useState({ open: false, form: null });
  const [checkinsByReview, setCheckinsByReview] = useState({});
  const [expandedReview, setExpandedReview] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/hr/staff/${id}/profile`);
      setData(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Profil yüklenemedi');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadCerts = useCallback(async () => {
    try {
      const r = await axios.get(`/hr/staff/${id}/certifications`);
      setCerts({ items: r.data.items || [], active: r.data.active || 0, expired: r.data.expired || 0, error: null });
    } catch (err) {
      setCerts((s) => ({ ...s, error: err?.response?.data?.detail || 'Sertifikalar yüklenemedi' }));
    }
  }, [id]);

  const loadDocs = useCallback(async () => {
    try {
      const r = await axios.get(`/hr/staff/${id}/documents`);
      setDocs(r.data.items || []);
      setDocsError(null);
    } catch (err) {
      setDocsError(err?.response?.data?.detail || 'Belgeler yüklenemedi');
    }
  }, [id]);

  const loadSalary = useCallback(async () => {
    try {
      const r = await axios.get(`/hr/staff/${id}/salary-history`);
      setSalaryHistory(r.data.items || []);
      setSalaryError(null);
    } catch (err) {
      setSalaryError(err?.response?.data?.detail || 'Maaş geçmişi yüklenemedi');
    }
  }, [id]);

  const loadTermination = useCallback(async () => {
    try {
      const r = await axios.get(`/hr/staff/${id}/termination`);
      setTermination(r.data.record || null);
    } catch (err) {
      // 404 beklenen — aktif personelde ayrılış kaydı olmayabilir
      if (err?.response?.status !== 404) {
        toast.error(err?.response?.data?.detail || 'Ayrılış bilgisi yüklenemedi');
      }
      setTermination(null);
    }
  }, [id]);

  const loadEquipment = useCallback(async () => {
    try {
      const r = await axios.get(`/hr/staff/${id}/equipment`);
      setEquipment({
        items: r.data.items || [], active: r.data.active || 0,
        returned: r.data.returned || 0, lost: r.data.lost_or_damaged || 0, error: null,
      });
    } catch (err) {
      setEquipment((s) => ({ ...s, error: err?.response?.data?.detail || 'Zimmet listesi yüklenemedi' }));
    }
  }, [id]);

  const loadWarnings = useCallback(async () => {
    try {
      const r = await axios.get(`/hr/staff/${id}/warnings`);
      setWarnings({
        items: r.data.items || [],
        by_type: r.data.by_type || { verbal: 0, written: 0, final: 0 },
        error: null,
      });
    } catch (err) {
      setWarnings((s) => ({ ...s, error: err?.response?.data?.detail || 'Uyarı geçmişi yüklenemedi' }));
    }
  }, [id]);

  const loadTrainings = useCallback(async () => {
    try {
      const r = await axios.get(`/hr/staff/${id}/trainings`);
      setTrainings({
        items: r.data.items || [], valid: r.data.valid || 0,
        expired: r.data.expired || 0, error: null,
      });
    } catch (err) {
      setTrainings((s) => ({ ...s, error: err?.response?.data?.detail || 'Eğitim geçmişi yüklenemedi' }));
    }
  }, [id]);

  useEffect(() => {
    load();
    loadCerts();
    loadDocs();
    loadSalary();
    loadTermination();
    loadEquipment();
    loadWarnings();
    loadTrainings();
  }, [load, loadCerts, loadDocs, loadSalary, loadTermination, loadEquipment, loadWarnings, loadTrainings]);

  // ===== Certifications =====
  const openCertDialog = () => setCertDialog({
    open: true,
    form: { name: '', issuer: '', issue_date: new Date().toISOString().slice(0, 10), expiry_date: '', certificate_no: '', file_url: '', notes: '' },
  });
  const submitCert = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/staff/${id}/certifications`, certDialog.form);
      toast.success('Sertifika eklendi');
      setCertDialog({ open: false, form: null });
      loadCerts();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    } finally { setSaving(false); }
  };
  const deleteCert = async (cert) => {
    if (!await confirmDialog({ message: `"${cert.name}" sertifikası silinsin mi?` })) return;
    try {
      await axios.delete(`/hr/certifications/${cert.id}`);
      toast.success('Silindi'); loadCerts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };

  // ===== Documents =====
  const submitDoc = async (e) => {
    e.preventDefault();
    if (!docDialog.file) { toast.error('Dosya seçin'); return; }
    setSaving(true);
    const fd = new FormData();
    fd.append('file', docDialog.file);
    try {
      await axios.post(
        `/hr/staff/${id}/documents`,
        fd,
        {
          params: { doc_type: docDialog.doc_type, label: docDialog.label || '' },
          headers: { 'Content-Type': 'multipart/form-data' },
        }
      );
      toast.success('Belge yüklendi');
      setDocDialog({ open: false, file: null, doc_type: 'contract', label: '' });
      loadDocs();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yüklenemedi');
    } finally { setSaving(false); }
  };
  const downloadDoc = async (doc) => {
    try {
      const r = await axios.get(`/hr/documents/${doc.id}/download`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: doc.content_type }));
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.filename || 'belge';
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) { toast.error('İndirilemedi'); }
  };
  const deleteDoc = async (doc) => {
    if (!await confirmDialog({ message: `"${doc.label || doc.filename}" silinsin mi?` })) return;
    try {
      await axios.delete(`/hr/documents/${doc.id}`);
      toast.success('Silindi'); loadDocs();
    } catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };

  // ===== Salary =====
  const openSalaryDialog = () => setSalaryDialog({
    open: true,
    form: {
      new_hourly_rate: data?.staff?.hourly_rate || '',
      effective_date: new Date().toISOString().slice(0, 10),
      change_type: 'raise', reason: '',
    },
  });
  const submitSalary = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/staff/${id}/salary-change`, {
        ...salaryDialog.form,
        new_hourly_rate: parseFloat(salaryDialog.form.new_hourly_rate),
      });
      toast.success('Maaş değişikliği kaydedildi');
      setSalaryDialog({ open: false, form: null });
      loadSalary();
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally { setSaving(false); }
  };

  // ===== Termination =====
  const openTermDialog = () => setTermDialog({
    open: true,
    form: {
      reason: 'resign',
      last_day: new Date().toISOString().slice(0, 10),
      notice_period_days: 0,
      exit_interview_notes: '',
      severance_override: '',
      eligible_for_rehire: true,
    },
    outstanding: (equipment.items || []).filter((it) => it.status === 'assigned'),
  });
  const submitTerm = async (e, { forceRelease = false } = {}) => {
    if (e && e.preventDefault) e.preventDefault();
    if (!await confirmDialog({
      message: forceRelease
        ? 'Personelin üzerinde iade alınmamış zimmet var. Yine de ayrılış kaydedilsin mi? (Zimmet kayıtları açık kalır.)'
        : 'Personeli pasifleştirmek üzeresiniz. Kıdem tazminatı hesabı kaydedilecek. Devam edilsin mi?',
    })) return;
    setSaving(true);
    try {
      const payload = { ...termDialog.form };
      payload.severance_override = payload.severance_override === ''
        ? null : parseFloat(payload.severance_override);
      const url = forceRelease
        ? `/hr/staff/${id}/terminate?force_release=true`
        : `/hr/staff/${id}/terminate`;
      const r = await axios.post(url, payload);
      toast.success(`Ayrılış kaydedildi. Kıdem: ${formatCurrency(r.data.termination?.severance_paid || 0, 'TRY')}`);
      setTermDialog({ open: false, form: null, outstanding: [] });
      loadTermination(); load(); loadEquipment();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409 && detail && detail.code === 'outstanding_equipment') {
        setTermDialog((s) => ({ ...s, outstanding: detail.outstanding_equipment || [] }));
        toast.error(detail.message || 'İade alınmamış zimmet var');
      } else {
        toast.error(typeof detail === 'string' ? detail : (detail?.message || 'İşlem başarısız'));
      }
    } finally { setSaving(false); }
  };
  const returnEqFromTerm = async (eq) => {
    try {
      await axios.post(`/hr/equipment/${eq.id}/return`, {
        returned_at: new Date().toISOString().slice(0, 10),
        condition_on_return: 'good',
      });
      toast.success(`"${eq.item_label}" iade alındı`);
      setTermDialog((s) => ({
        ...s,
        outstanding: (s.outstanding || []).filter((x) => x.id !== eq.id),
      }));
      loadEquipment();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İade alınamadı');
    }
  };

  // ===== Performance check-ins =====
  const toggleReviewExpand = async (reviewId) => {
    if (expandedReview === reviewId) { setExpandedReview(null); return; }
    setExpandedReview(reviewId);
    if (!checkinsByReview[reviewId]) {
      try {
        const r = await axios.get(`/hr/performance/${reviewId}/checkins`);
        setCheckinsByReview((prev) => ({ ...prev, [reviewId]: r.data.items || [] }));
      } catch { /* ignore */ }
    }
  };
  const openCheckinDialog = (reviewId) => setCheckinDialog({
    open: true, reviewId,
    form: { goal_text: '', progress_pct: 0, status: 'on_track', note: '', checkin_date: new Date().toISOString().slice(0, 10) },
  });
  const submitCheckin = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/performance/${checkinDialog.reviewId}/checkin`, {
        ...checkinDialog.form,
        progress_pct: parseInt(checkinDialog.form.progress_pct, 10),
      });
      toast.success('Check-in eklendi');
      const rid = checkinDialog.reviewId;
      const r = await axios.get(`/hr/performance/${rid}/checkins`);
      setCheckinsByReview((prev) => ({ ...prev, [rid]: r.data.items || [] }));
      setCheckinDialog({ open: false, reviewId: null, form: null });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    } finally { setSaving(false); }
  };

  // ===== Task #265: Zimmet (Equipment) =====
  const openEqDialog = () => setEqDialog({
    open: true,
    form: {
      item_type: 'uniform', item_label: '', serial_no: '',
      assigned_at: new Date().toISOString().slice(0, 10), notes: '',
    },
  });
  const submitEq = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/staff/${id}/equipment`, eqDialog.form);
      toast.success('Zimmet kaydedildi');
      setEqDialog({ open: false, form: null });
      loadEquipment();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally { setSaving(false); }
  };
  const returnEq = async (eq) => {
    if (!await confirmDialog({ message: `"${eq.item_label}" iade alınsın mı?` })) return;
    try {
      await axios.post(`/hr/equipment/${eq.id}/return`, {
        returned_at: new Date().toISOString().slice(0, 10),
        condition_on_return: 'good',
      });
      toast.success('İade alındı'); loadEquipment();
    } catch (err) { toast.error(err.response?.data?.detail || 'İade alınamadı'); }
  };
  const deleteEq = async (eq) => {
    if (!await confirmDialog({ message: `"${eq.item_label}" zimmet kaydı silinsin mi?` })) return;
    try {
      await axios.delete(`/hr/equipment/${eq.id}`);
      toast.success('Silindi'); loadEquipment();
    } catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };

  // ===== Task #265: Uyarılar (Warnings) =====
  const openWarnDialog = () => setWarnDialog({
    open: true,
    form: { warning_type: 'verbal', severity: 'medium', reason: '', issued_at: new Date().toISOString().slice(0, 10) },
  });
  const submitWarn = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/staff/${id}/warnings`, warnDialog.form);
      toast.success('Uyarı kaydedildi');
      setWarnDialog({ open: false, form: null });
      loadWarnings();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally { setSaving(false); }
  };
  const ackWarn = async (w) => {
    try {
      await axios.post(`/hr/warnings/${w.id}/acknowledge`);
      toast.success('Onaylandı'); loadWarnings();
    } catch (err) { toast.error(err.response?.data?.detail || 'Onaylanamadı'); }
  };
  const deleteWarn = async (w) => {
    if (!await confirmDialog({ message: `Uyarı kaydı silinsin mi?` })) return;
    try {
      await axios.delete(`/hr/warnings/${w.id}`);
      toast.success('Silindi'); loadWarnings();
    } catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };

  // ===== Task #265: Eğitimler (Trainings) =====
  const openTrainDialog = () => setTrainDialog({
    open: true,
    form: {
      training_type: 'hygiene', title: '', provider: '',
      completed_at: new Date().toISOString().slice(0, 10),
      valid_until: '', hours: '', score: '', notes: '',
    },
  });
  const submitTrain = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...trainDialog.form };
      if (!payload.valid_until) delete payload.valid_until;
      if (payload.provider === '') delete payload.provider;
      if (payload.notes === '') delete payload.notes;
      payload.hours = payload.hours === '' ? null : parseFloat(payload.hours);
      payload.score = payload.score === '' ? null : parseFloat(payload.score);
      await axios.post(`/hr/staff/${id}/trainings`, payload);
      toast.success('Eğitim kaydedildi');
      setTrainDialog({ open: false, form: null });
      loadTrainings();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally { setSaving(false); }
  };
  const deleteTrain = async (t) => {
    if (!await confirmDialog({ message: `"${t.title}" eğitim kaydı silinsin mi?` })) return;
    try {
      await axios.delete(`/hr/trainings/${t.id}`);
      toast.success('Silindi'); loadTrainings();
    } catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };

  const headerActions = (
    <>
      <Button variant="outline" size="sm" onClick={() => navigate('/staff-management')}>
        <ArrowLeft className="w-4 h-4 mr-1.5" />Personel Listesi
      </Button>
      <Button variant="outline" size="sm" onClick={load} disabled={loading}>
        <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Yenile
      </Button>
      {data?.staff?.active !== false && !termination && (
        <Button variant="outline" size="sm" onClick={openTermDialog} className="text-rose-700 border-rose-300 hover:bg-rose-50">
          <UserMinus className="w-4 h-4 mr-1.5" />Ayrılış İşlemleri
        </Button>
      )}
    </>
  );

  if (loading && !data) {
    return (
      <div className="p-2">
        <PageHeader icon={User} title="Personel Profili" subtitle="Yükleniyor..." actions={headerActions} />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="p-2">
        <PageHeader icon={User} title="Personel Bulunamadı" actions={headerActions} />
        <Card><CardContent className="py-10 text-center text-slate-500">
          <AlertCircle className="w-8 h-8 mx-auto mb-2 text-rose-500" />
          Bu personele ait kayıt yok veya bu otele ait değil.
        </CardContent></Card>
      </div>
    );
  }

  const s = data.staff || {};
  const att = data.attendance || {};
  const lv = data.leaves || {};
  const bal = data.leave_balance;
  const perf = data.performance || {};
  const pay = data.payroll || {};
  const shifts = data.upcoming_shifts || [];

  return (
    <div className="p-2">
      <PageHeader
        icon={User}
        title={s.name || 'Personel'}
        subtitle={`${s.position || '—'} • ${s.department || '—'}`}
        actions={headerActions}
      />

      {/* Termination banner */}
      {termination && (
        <Card className="mb-4 border-rose-200 bg-rose-50">
          <CardContent className="py-3 flex items-center gap-3 text-sm">
            <UserMinus className="w-5 h-5 text-rose-600" />
            <div className="flex-1">
              <div className="font-medium text-rose-900">
                Personel ayrılmış: {TERM_REASON_LABEL[termination.reason] || termination.reason} • Son gün {termination.last_day}
              </div>
              <div className="text-xs text-rose-700">
                Kıdem ödenen: <strong>{formatCurrency(termination.severance_paid || 0, 'TRY')}</strong>
                {' '}• Kıdem süresi: {termination.severance_calc?.years_of_service || 0} yıl
                {termination.eligible_for_rehire ? ' • Tekrar işe alınabilir' : ' • Tekrar işe alınamaz'}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Genel bilgi kartı */}
      <Card className="mb-4">
        <CardContent className="grid gap-3 md:grid-cols-4 py-4">
          <div className="flex items-center gap-2 text-sm text-slate-700"><Mail className="w-4 h-4 text-slate-400" /> {s.email || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Phone className="w-4 h-4 text-slate-400" /> {s.phone || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Building2 className="w-4 h-4 text-slate-400" /> {s.department || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Briefcase className="w-4 h-4 text-slate-400" /> {s.employment_type || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Calendar className="w-4 h-4 text-slate-400" /> İşe Giriş: {s.hire_date || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><DollarSign className="w-4 h-4 text-slate-400" /> Saatlik: {s.hourly_rate ? `${s.hourly_rate} TRY` : 'tanımsız (140 TRY default)'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Clock className="w-4 h-4 text-slate-400" /> Aylık Saat: {s.monthly_hours || '195 (default)'}</div>
          <div className="flex items-center gap-2 text-sm">
            {s.active === false
              ? <StatusBadge intent="danger">Pasif</StatusBadge>
              : s.derived_from === 'users'
                ? <StatusBadge intent="neutral">Kullanıcıdan türetildi</StatusBadge>
                : <StatusBadge intent="info">HR-yönetimli</StatusBadge>}
          </div>
        </CardContent>
      </Card>

      {/* KPI özeti */}
      <div className="grid gap-3 md:grid-cols-4 mb-4">
        <KpiCard intent="info" icon={Clock} label="Son 30g Saat" value={att.total_hours_30d || 0} sub={`${att.days_present_30d || 0} gün`} />
        <KpiCard intent="warning" icon={Calendar} label="Bekleyen İzin" value={lv.pending || 0} sub={`Toplam ${lv.total || 0} talep`} />
        <KpiCard intent="success" icon={Award} label="Performans Ort." value={perf.avg_score || 0} sub={`${perf.total || 0} değerlendirme`} />
        <KpiCard intent={certs.expired > 0 ? 'danger' : 'info'} icon={GraduationCap} label="Aktif Sertifika" value={certs.active} sub={certs.expired > 0 ? `${certs.expired} süresi geçmiş` : `${docs.length} belge`} />
      </div>

      <Tabs defaultValue="attendance">
        <TabsList className="grid w-full grid-cols-11 text-xs">
          <TabsTrigger value="attendance">Devam</TabsTrigger>
          <TabsTrigger value="leave">İzin</TabsTrigger>
          <TabsTrigger value="performance">Performans</TabsTrigger>
          <TabsTrigger value="payroll">Bordro</TabsTrigger>
          <TabsTrigger value="shifts">Vardiya</TabsTrigger>
          <TabsTrigger value="certifications">Sertifika</TabsTrigger>
          <TabsTrigger value="trainings">Eğitim</TabsTrigger>
          <TabsTrigger value="equipment">Zimmet</TabsTrigger>
          <TabsTrigger value="warnings">Uyarı</TabsTrigger>
          <TabsTrigger value="documents">Belgeler</TabsTrigger>
          <TabsTrigger value="salary">Maaş</TabsTrigger>
        </TabsList>

        <TabsContent value="attendance" className="mt-4">
          <Card>
            <CardHeader><CardTitle>Son 30 Gün Devam Kayıtları</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Tarih</th><th>Giriş</th><th>Çıkış</th><th className="text-right">Saat</th>
                  </tr></thead>
                  <tbody>
                    {(att.records || []).map((r, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="py-2">{r.date}</td>
                        <td>{(r.clock_in || '').slice(11, 16) || '—'}</td>
                        <td>{(r.clock_out || '').slice(11, 16) || '—'}</td>
                        <td className="text-right">{(r.total_hours || 0).toFixed(2)}</td>
                      </tr>
                    ))}
                    {(att.records || []).length === 0 && (
                      <tr><td colSpan={4} className="py-6 text-center text-slate-500">Kayıt yok</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="leave" className="mt-4 space-y-3">
          {bal && (
            <div className="grid gap-3 md:grid-cols-3">
              <KpiCard intent="info" label={`Yıllık İzin (${bal.year})`} value={`${bal.annual?.remaining ?? 0} / ${bal.annual?.total ?? 0}`}
                sub={`Hak: ${bal.annual?.entitlement} + ${bal.annual?.carry_over || 0} devir`} />
              <KpiCard intent="warning" label="Kullanılan Yıllık" value={bal.annual?.used ?? 0} sub="onaylı" />
              <KpiCard intent="neutral" label="Hastalık (kalan/hak)" value={`${bal.sick?.remaining ?? 0} / ${bal.sick?.entitlement ?? 5}`} />
            </div>
          )}
          <Card>
            <CardHeader><CardTitle>İzin Geçmişi</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Tür</th><th>Başl.</th><th>Bitiş</th>
                    <th className="text-right">Gün</th><th>Durum</th><th>Sebep</th>
                  </tr></thead>
                  <tbody>
                    {(lv.items || []).map((l) => (
                      <tr key={l.id} className="border-t border-slate-100">
                        <td className="py-2">{LEAVE_TYPE_LABEL[l.leave_type] || l.leave_type}</td>
                        <td>{l.start_date}</td><td>{l.end_date}</td>
                        <td className="text-right">{l.total_days}</td>
                        <td><StatusBadge intent={STATUS_INTENT[l.status]}>{STATUS_LABEL[l.status]}</StatusBadge></td>
                        <td className="text-slate-600 text-xs max-w-xs truncate">{l.reason || '—'}</td>
                      </tr>
                    ))}
                    {(lv.items || []).length === 0 && (
                      <tr><td colSpan={6} className="py-6 text-center text-slate-500">İzin kaydı yok</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="performance" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Performans Değerlendirmeleri</span>
                <span className="text-xs text-slate-500 font-normal">Satıra tıklayarak hedef check-in'lerini görün</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2 w-6"></th><th>Tarih</th><th>Dönem</th>
                    <th className="text-right">Puan</th><th>Güçlü</th><th>Gelişim</th><th></th>
                  </tr></thead>
                  <tbody>
                    {(perf.items || []).map((p) => {
                      const expanded = expandedReview === p.id;
                      const checkins = checkinsByReview[p.id] || [];
                      return (
                        <React.Fragment key={p.id}>
                          <tr className="border-t border-slate-100 align-top hover:bg-slate-50 cursor-pointer" onClick={() => toggleReviewExpand(p.id)}>
                            <td className="py-2">{expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}</td>
                            <td>{(p.reviewed_at || '').slice(0, 10)}</td>
                            <td>{p.period || '—'}</td>
                            <td className="text-right font-semibold">{p.overall_score}</td>
                            <td className="text-slate-600 text-xs max-w-xs">{p.strengths || '—'}</td>
                            <td className="text-slate-600 text-xs max-w-xs">{p.improvement_areas || '—'}</td>
                            <td className="text-right">
                              <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); openCheckinDialog(p.id); }}>
                                <Plus className="w-3 h-3 mr-1" />Check-in
                              </Button>
                            </td>
                          </tr>
                          {expanded && (
                            <tr className="bg-slate-50/60">
                              <td></td>
                              <td colSpan={6} className="py-2 px-3">
                                <div className="space-y-2">
                                  <div className="text-xs font-semibold text-slate-700 flex items-center gap-1">
                                    <Target className="w-3 h-3" /> Hedef İlerleme Check-in'leri
                                  </div>
                                  {checkins.length === 0 ? (
                                    <div className="text-xs text-slate-500">Henüz check-in yok</div>
                                  ) : checkins.map((ci) => (
                                    <div key={ci.id} className="rounded border border-slate-200 bg-white p-2 text-xs flex items-start gap-3">
                                      <div className="w-12 text-slate-500">{ci.checkin_date}</div>
                                      <div className="flex-1">
                                        <div className="font-medium text-slate-800">{ci.goal_text}</div>
                                        {ci.note && <div className="text-slate-600 mt-0.5">{ci.note}</div>}
                                      </div>
                                      <div className="w-24">
                                        <div className="h-1.5 bg-slate-200 rounded overflow-hidden mb-0.5">
                                          <div className="h-full bg-emerald-500" style={{ width: `${ci.progress_pct}%` }} />
                                        </div>
                                        <div className="text-[10px] text-slate-500">{ci.progress_pct}%</div>
                                      </div>
                                      <StatusBadge intent={STATUS_INTENT[ci.status] || 'info'}>{STATUS_LABEL[ci.status] || ci.status}</StatusBadge>
                                    </div>
                                  ))}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                    {(perf.items || []).length === 0 && (
                      <tr><td colSpan={7} className="py-6 text-center text-slate-500">Değerlendirme yok</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="payroll" className="mt-4">
          <Card>
            <CardHeader><CardTitle>Bordro Geçmişi</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Ay</th><th className="text-right">Saat</th>
                    <th className="text-right">Mesai</th><th className="text-right">Brüt</th><th className="text-right">Net</th>
                  </tr></thead>
                  <tbody>
                    {(pay.recent || []).map((row, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="py-2">{row.period_month}</td>
                        <td className="text-right">{(row.total_hours || 0).toFixed(1)}</td>
                        <td className="text-right text-amber-700">{(row.overtime_hours || 0).toFixed(1)}</td>
                        <td className="text-right">{formatCurrency(row.gross_pay || 0, 'TRY')}</td>
                        <td className="text-right font-semibold">{formatCurrency(row.net_salary || 0, 'TRY')}</td>
                      </tr>
                    ))}
                    {(pay.recent || []).length === 0 && (
                      <tr><td colSpan={5} className="py-6 text-center text-slate-500">Henüz bordro yok</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="shifts" className="mt-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center justify-between">
              <span>Yaklaşan Vardiyalar</span>
              <Button size="sm" variant="outline" onClick={() => navigate('/hr/shifts')}>Vardiya Planlayıcı</Button>
            </CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Tarih</th><th>Tip</th><th>Başl.</th><th>Bitiş</th><th>Not</th>
                  </tr></thead>
                  <tbody>
                    {shifts.map((sh) => (
                      <tr key={sh.id} className="border-t border-slate-100">
                        <td className="py-2">{sh.shift_date}</td>
                        <td className="capitalize">{sh.shift_type}</td>
                        <td>{sh.start_time}</td>
                        <td>
                          {sh.end_time}
                          {sh.crosses_midnight && (
                            <span className="ml-1 text-[10px] text-slate-400" title="Ertesi güne sarkar">+1g</span>
                          )}
                        </td>
                        <td className="text-slate-600 text-xs">{sh.notes || '—'}</td>
                      </tr>
                    ))}
                    {shifts.length === 0 && (
                      <tr><td colSpan={5} className="py-6 text-center text-slate-500">Planlı vardiya yok</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* SERTİFİKA */}
        <TabsContent value="certifications" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><GraduationCap className="w-4 h-4" /> Eğitim ve Sertifikalar</span>
                <Button size="sm" onClick={openCertDialog}><Plus className="w-4 h-4 mr-1.5" />Sertifika Ekle</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {certs.error && (
                <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {certs.error} <button onClick={loadCerts} className="underline ml-2">Tekrar dene</button>
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Sertifika</th><th>Veren</th><th>Veriliş</th>
                    <th>Bitiş</th><th>Numara</th><th>Durum</th><th></th>
                  </tr></thead>
                  <tbody>
                    {certs.items.map((c) => {
                      const today = new Date().toISOString().slice(0, 10);
                      const expired = c.expiry_date && c.expiry_date < today;
                      const expiringSoon = c.expiry_date && !expired && new Date(c.expiry_date) - new Date() < 90 * 86400000;
                      return (
                        <tr key={c.id} className="border-t border-slate-100">
                          <td className="py-2 font-medium">{c.name}{c.file_url && <a href={c.file_url} target="_blank" rel="noreferrer" className="ml-2 text-sky-600 hover:underline text-xs">dosya</a>}</td>
                          <td>{c.issuer || '—'}</td>
                          <td>{c.issue_date}</td>
                          <td>{c.expiry_date || 'süresiz'}</td>
                          <td className="text-xs">{c.certificate_no || '—'}</td>
                          <td>
                            {expired
                              ? <StatusBadge intent="danger">Süresi geçmiş</StatusBadge>
                              : expiringSoon
                                ? <StatusBadge intent="warning">Yakında bitecek</StatusBadge>
                                : <StatusBadge intent="success">Geçerli</StatusBadge>}
                          </td>
                          <td className="text-right">
                            <Button size="sm" variant="ghost" onClick={() => deleteCert(c)}>
                              <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                    {certs.items.length === 0 && (
                      <tr><td colSpan={7} className="py-6 text-center text-slate-500">
                        Henüz sertifika yok — yangın eğitimi, hijyen sertifikası gibi compliance kayıtlarını ekleyin
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* BELGELER */}
        <TabsContent value="documents" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><Folder className="w-4 h-4" /> Personel Belgeleri</span>
                <Button size="sm" onClick={() => setDocDialog({ open: true, file: null, doc_type: 'contract', label: '' })}>
                  <Upload className="w-4 h-4 mr-1.5" />Belge Yükle
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {docsError && (
                <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {docsError} <button onClick={loadDocs} className="underline ml-2">Tekrar dene</button>
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Etiket</th><th>Tür</th><th>Dosya Adı</th>
                    <th className="text-right">Boyut</th><th>Yüklenme</th><th></th>
                  </tr></thead>
                  <tbody>
                    {docs.map((d) => (
                      <tr key={d.id} className="border-t border-slate-100">
                        <td className="py-2 font-medium">{d.label}</td>
                        <td><StatusBadge intent="neutral">{DOC_TYPE_LABEL[d.doc_type] || d.doc_type}</StatusBadge></td>
                        <td className="text-xs text-slate-600">{d.filename}</td>
                        <td className="text-right text-xs">{((d.size_bytes || 0) / 1024).toFixed(1)} KB</td>
                        <td className="text-xs">{(d.uploaded_at || '').slice(0, 10)}</td>
                        <td className="text-right space-x-1">
                          <Button size="sm" variant="ghost" onClick={() => downloadDoc(d)}>
                            <Download className="w-3.5 h-3.5" />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => deleteDoc(d)}>
                            <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                    {docs.length === 0 && (
                      <tr><td colSpan={6} className="py-6 text-center text-slate-500">
                        Henüz belge yok — sözleşme, kimlik, diploma gibi belgeleri yükleyin (max 5MB, PDF/Word/JPEG)
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* MAAŞ */}
        <TabsContent value="salary" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Maaş Geçmişi</span>
                <Button size="sm" onClick={openSalaryDialog}>
                  <Plus className="w-4 h-4 mr-1.5" />Zam / Değişiklik
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {salaryError && (
                <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {salaryError} <button onClick={loadSalary} className="underline ml-2">Tekrar dene</button>
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Yürürlük</th><th>Tür</th>
                    <th className="text-right">Eski</th><th className="text-right">Yeni</th>
                    <th className="text-right">Δ%</th><th>Sebep</th>
                  </tr></thead>
                  <tbody>
                    {salaryHistory.map((r) => (
                      <tr key={r.id} className="border-t border-slate-100">
                        <td className="py-2">{r.effective_date}</td>
                        <td><StatusBadge intent={r.change_type === 'demotion' ? 'danger' : r.change_type === 'promotion' ? 'success' : 'info'}>{CHANGE_TYPE_LABEL[r.change_type] || r.change_type}</StatusBadge></td>
                        <td className="text-right text-slate-500">{formatCurrency(r.old_hourly_rate, 'TRY')}</td>
                        <td className="text-right font-semibold">{formatCurrency(r.new_hourly_rate, 'TRY')}</td>
                        <td className={`text-right ${r.delta_pct > 0 ? 'text-emerald-700' : r.delta_pct < 0 ? 'text-rose-700' : ''}`}>
                          {r.delta_pct > 0 ? '+' : ''}{r.delta_pct}%
                        </td>
                        <td className="text-xs text-slate-600 max-w-xs">{r.reason || '—'}</td>
                      </tr>
                    ))}
                    {salaryHistory.length === 0 && (
                      <tr><td colSpan={6} className="py-6 text-center text-slate-500">
                        Henüz maaş değişikliği yok — şu anki saatlik: {s.hourly_rate ? formatCurrency(s.hourly_rate, 'TRY') : '140 TRY (default)'}
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* EĞİTİM (Task #265 — sertifikadan ayrı operasyonel zorunlu eğitim) */}
        <TabsContent value="trainings" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><BookOpen className="w-4 h-4" /> Zorunlu Eğitimler</span>
                <Button size="sm" onClick={openTrainDialog}><Plus className="w-4 h-4 mr-1.5" />Eğitim Ekle</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {trainings.error && (
                <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {trainings.error} <button onClick={loadTrainings} className="underline ml-2">Tekrar dene</button>
                </div>
              )}
              <div className="mb-3 flex gap-2 text-xs">
                <StatusBadge intent="success">{trainings.valid} geçerli</StatusBadge>
                {trainings.expired > 0 && <StatusBadge intent="danger">{trainings.expired} tazelenmeli</StatusBadge>}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Eğitim</th><th>Tür</th><th>Veren</th>
                    <th>Tamamlandı</th><th>Geçerlilik</th><th className="text-right">Saat</th><th></th>
                  </tr></thead>
                  <tbody>
                    {trainings.items.map((t) => {
                      const today = new Date().toISOString().slice(0, 10);
                      const expired = t.valid_until && t.valid_until < today;
                      return (
                        <tr key={t.id} className="border-t border-slate-100">
                          <td className="py-2 font-medium">{t.title}</td>
                          <td className="text-xs uppercase">{t.training_type}</td>
                          <td>{t.provider || '—'}</td>
                          <td>{t.completed_at}</td>
                          <td>{t.valid_until
                            ? (expired
                              ? <StatusBadge intent="danger">{t.valid_until}</StatusBadge>
                              : <StatusBadge intent="success">{t.valid_until}</StatusBadge>)
                            : <span className="text-slate-400">süresiz</span>}</td>
                          <td className="text-right">{t.hours ?? '—'}</td>
                          <td className="text-right">
                            <Button size="sm" variant="ghost" onClick={() => deleteTrain(t)}>
                              <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                    {trainings.items.length === 0 && (
                      <tr><td colSpan={7} className="py-6 text-center text-slate-500">
                        Henüz eğitim kaydı yok — hijyen tazeleme, iş güvenliği yıllık, oryantasyon gibi periyodik eğitimleri ekleyin
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ZİMMET (Task #265 — üniforma/kart/anahtar/cihaz) */}
        <TabsContent value="equipment" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><Package className="w-4 h-4" /> Zimmet</span>
                <Button size="sm" onClick={openEqDialog}><Plus className="w-4 h-4 mr-1.5" />Zimmet Ata</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {equipment.error && (
                <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {equipment.error} <button onClick={loadEquipment} className="underline ml-2">Tekrar dene</button>
                </div>
              )}
              <div className="mb-3 flex gap-2 text-xs">
                <StatusBadge intent="warning">{equipment.active} aktif</StatusBadge>
                <StatusBadge intent="success">{equipment.returned} iade</StatusBadge>
                {equipment.lost > 0 && <StatusBadge intent="danger">{equipment.lost} kayıp/hasar</StatusBadge>}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Eşya</th><th>Tür</th><th>Seri No</th>
                    <th>Zimmet Tarihi</th><th>İade Tarihi</th><th>Durum</th><th></th>
                  </tr></thead>
                  <tbody>
                    {equipment.items.map((eq) => (
                      <tr key={eq.id} className="border-t border-slate-100">
                        <td className="py-2 font-medium">{eq.item_label}</td>
                        <td className="text-xs uppercase">{eq.item_type}</td>
                        <td className="text-xs">{eq.serial_no || '—'}</td>
                        <td>{eq.assigned_at}</td>
                        <td>{eq.returned_at || '—'}</td>
                        <td>
                          {eq.status === 'assigned' && <StatusBadge intent="warning">Aktif</StatusBadge>}
                          {eq.status === 'returned' && <StatusBadge intent="success">İade alındı</StatusBadge>}
                          {eq.status === 'lost' && <StatusBadge intent="danger">Kayıp</StatusBadge>}
                          {eq.status === 'damaged' && <StatusBadge intent="danger">Hasarlı</StatusBadge>}
                        </td>
                        <td className="text-right whitespace-nowrap">
                          {eq.status === 'assigned' && (
                            <Button size="sm" variant="ghost" onClick={() => returnEq(eq)} title="İade al">
                              <RotateCcw className="w-3.5 h-3.5 text-emerald-700" />
                            </Button>
                          )}
                          <Button size="sm" variant="ghost" onClick={() => deleteEq(eq)}>
                            <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                    {equipment.items.length === 0 && (
                      <tr><td colSpan={7} className="py-6 text-center text-slate-500">
                        Henüz zimmet yok — üniforma, kart, telsiz, anahtar gibi tahsis edilen eşyaları kaydedin
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* UYARI (Task #265 — sözlü/yazılı/son ihtar sicili) */}
        <TabsContent value="warnings" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><ShieldAlert className="w-4 h-4" /> Disiplin Uyarıları</span>
                <Button size="sm" onClick={openWarnDialog}><Plus className="w-4 h-4 mr-1.5" />Uyarı Düş</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {warnings.error && (
                <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {warnings.error} <button onClick={loadWarnings} className="underline ml-2">Tekrar dene</button>
                </div>
              )}
              <div className="mb-3 flex gap-2 text-xs">
                <StatusBadge intent="info">{warnings.by_type.verbal} sözlü</StatusBadge>
                <StatusBadge intent="warning">{warnings.by_type.written} yazılı</StatusBadge>
                {warnings.by_type.final > 0 && <StatusBadge intent="danger">{warnings.by_type.final} son ihtar</StatusBadge>}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">Tarih</th><th>Tür</th><th>Şiddet</th>
                    <th>Sebep</th><th>Onay</th><th></th>
                  </tr></thead>
                  <tbody>
                    {warnings.items.map((w) => (
                      <tr key={w.id} className="border-t border-slate-100">
                        <td className="py-2">{w.issued_at}</td>
                        <td>
                          {w.warning_type === 'verbal' && <StatusBadge intent="info">Sözlü</StatusBadge>}
                          {w.warning_type === 'written' && <StatusBadge intent="warning">Yazılı</StatusBadge>}
                          {w.warning_type === 'final' && <StatusBadge intent="danger">Son ihtar</StatusBadge>}
                        </td>
                        <td className="text-xs uppercase">{w.severity}</td>
                        <td className="text-xs text-slate-700 max-w-md">{w.reason}</td>
                        <td className="text-xs">
                          {w.acknowledged_at
                            ? <span className="text-emerald-700">✓ {w.acknowledged_at.slice(0, 10)}</span>
                            : <Button size="sm" variant="outline" onClick={() => ackWarn(w)}>
                                <Check className="w-3 h-3 mr-1" />Onayla
                              </Button>}
                        </td>
                        <td className="text-right">
                          <Button size="sm" variant="ghost" onClick={() => deleteWarn(w)}>
                            <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                    {warnings.items.length === 0 && (
                      <tr><td colSpan={6} className="py-6 text-center text-slate-500">
                        Disiplin kaydı yok — İş K. m.25/II referansıyla sözlü/yazılı/son ihtar süreçlerini buradan yönetin
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ============ DIALOGS ============ */}

      {/* Sertifika ekle */}
      <Dialog open={certDialog.open} onOpenChange={(o) => !o && setCertDialog({ open: false, form: null })}>
        <DialogContent>
          <DialogHeader><DialogTitle>Sertifika Ekle</DialogTitle></DialogHeader>
          {certDialog.form && (
            <form onSubmit={submitCert} className="grid gap-3">
              <div><Label>Sertifika Adı *</Label><Input required value={certDialog.form.name}
                onChange={(e) => setCertDialog({ ...certDialog, form: { ...certDialog.form, name: e.target.value } })} placeholder="Örn. Yangın Eğitimi" /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Veren Kurum</Label><Input value={certDialog.form.issuer}
                  onChange={(e) => setCertDialog({ ...certDialog, form: { ...certDialog.form, issuer: e.target.value } })} /></div>
                <div><Label>Sertifika No</Label><Input value={certDialog.form.certificate_no}
                  onChange={(e) => setCertDialog({ ...certDialog, form: { ...certDialog.form, certificate_no: e.target.value } })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Veriliş Tarihi *</Label><Input required type="date" value={certDialog.form.issue_date}
                  onChange={(e) => setCertDialog({ ...certDialog, form: { ...certDialog.form, issue_date: e.target.value } })} /></div>
                <div><Label>Bitiş Tarihi</Label><Input type="date" value={certDialog.form.expiry_date}
                  onChange={(e) => setCertDialog({ ...certDialog, form: { ...certDialog.form, expiry_date: e.target.value } })} /></div>
              </div>
              <div><Label>Dosya URL (opsiyonel)</Label><Input value={certDialog.form.file_url}
                onChange={(e) => setCertDialog({ ...certDialog, form: { ...certDialog.form, file_url: e.target.value } })} placeholder="https://..." /></div>
              <div><Label>Not</Label><Textarea rows={2} value={certDialog.form.notes}
                onChange={(e) => setCertDialog({ ...certDialog, form: { ...certDialog.form, notes: e.target.value } })} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setCertDialog({ open: false, form: null })}>Vazgeç</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ekle'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Belge yükle */}
      <Dialog open={docDialog.open} onOpenChange={(o) => !o && setDocDialog({ open: false, file: null, doc_type: 'contract', label: '' })}>
        <DialogContent>
          <DialogHeader><DialogTitle>Belge Yükle</DialogTitle></DialogHeader>
          <form onSubmit={submitDoc} className="grid gap-3">
            <div><Label>Dosya * (max 5MB, PDF/Word/JPEG/PNG)</Label>
              <Input type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp"
                onChange={(e) => setDocDialog({ ...docDialog, file: e.target.files?.[0] || null })} />
              {docDialog.file && <div className="text-xs text-slate-500 mt-1">{docDialog.file.name} • {(docDialog.file.size / 1024).toFixed(1)} KB</div>}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>Tür</Label>
                <select value={docDialog.doc_type} onChange={(e) => setDocDialog({ ...docDialog, doc_type: e.target.value })}
                  className="w-full rounded-md border border-input px-3 py-2 text-sm">
                  {Object.entries(DOC_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div><Label>Etiket</Label><Input value={docDialog.label}
                onChange={(e) => setDocDialog({ ...docDialog, label: e.target.value })} placeholder="Opsiyonel açıklama" /></div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDocDialog({ open: false, file: null, doc_type: 'contract', label: '' })}>Vazgeç</Button>
              <Button type="submit" disabled={saving || !docDialog.file}>{saving ? 'Yükleniyor...' : 'Yükle'}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Maaş değişikliği */}
      <Dialog open={salaryDialog.open} onOpenChange={(o) => !o && setSalaryDialog({ open: false, form: null })}>
        <DialogContent>
          <DialogHeader><DialogTitle>Zam / Maaş Değişikliği</DialogTitle></DialogHeader>
          {salaryDialog.form && (
            <form onSubmit={submitSalary} className="grid gap-3">
              <div className="text-xs text-slate-500">Şu anki: <strong>{s.hourly_rate ? formatCurrency(s.hourly_rate, 'TRY') : '140 TRY (default)'}</strong>/saat</div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Yeni Saatlik *</Label><Input required type="number" step="0.01" value={salaryDialog.form.new_hourly_rate}
                  onChange={(e) => setSalaryDialog({ ...salaryDialog, form: { ...salaryDialog.form, new_hourly_rate: e.target.value } })} /></div>
                <div><Label>Yürürlük *</Label><Input required type="date" value={salaryDialog.form.effective_date}
                  onChange={(e) => setSalaryDialog({ ...salaryDialog, form: { ...salaryDialog.form, effective_date: e.target.value } })} /></div>
              </div>
              <div>
                <Label>Tür</Label>
                <select value={salaryDialog.form.change_type} onChange={(e) => setSalaryDialog({ ...salaryDialog, form: { ...salaryDialog.form, change_type: e.target.value } })}
                  className="w-full rounded-md border border-input px-3 py-2 text-sm">
                  {Object.entries(CHANGE_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div><Label>Sebep / Not</Label><Textarea rows={2} value={salaryDialog.form.reason}
                onChange={(e) => setSalaryDialog({ ...salaryDialog, form: { ...salaryDialog.form, reason: e.target.value } })} placeholder="Yıllık enflasyon zammı, terfi vb." /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setSalaryDialog({ open: false, form: null })}>Vazgeç</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Kaydet'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* İşten ayrılma */}
      <Dialog open={termDialog.open} onOpenChange={(o) => !o && setTermDialog({ open: false, form: null, outstanding: [] })}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle className="flex items-center gap-2 text-rose-700">
            <UserMinus className="w-5 h-5" />İşten Ayrılma İşlemleri
          </DialogTitle></DialogHeader>
          {termDialog.form && (
            <form onSubmit={submitTerm} className="grid gap-3">
              <div className="rounded bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
                Bu işlem personeli pasifleştirir, ayrılış kaydı oluşturur ve İş K. m.14'e göre <strong>kıdem tazminatı</strong> hesabını otomatik yapar
                (30 gün × tam yıl × günlük brüt). 1 yıldan az kıdemde tazminat sıfırdır.
              </div>
              {(termDialog.outstanding || []).length > 0 && (
                <div className="rounded border border-rose-300 bg-rose-50 p-3 text-xs text-rose-900">
                  <div className="font-semibold mb-2">
                    İade alınmamış zimmet ({termDialog.outstanding.length})
                  </div>
                  <div className="text-rose-800 mb-2">
                    Aşağıdaki kayıtlar açık. Önce iade alın ya da "Zimmetli olsa da kapat" ile devam edin
                    (zimmet kayıtları açık kalır).
                  </div>
                  <ul className="divide-y divide-rose-200 mb-2">
                    {termDialog.outstanding.map((eq) => (
                      <li key={eq.id} className="flex items-center justify-between py-1.5 gap-2">
                        <div className="min-w-0">
                          <div className="font-medium truncate">{eq.item_label}</div>
                          <div className="text-[11px] text-rose-700">
                            {eq.item_type}{eq.serial_no ? ` • ${eq.serial_no}` : ''} • Verildi: {eq.assigned_at}
                          </div>
                        </div>
                        <Button type="button" size="sm" variant="outline"
                          className="border-rose-300 text-rose-700 hover:bg-rose-100"
                          onClick={() => returnEqFromTerm(eq)}>
                          İade alındı olarak işaretle
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>Ayrılış Sebebi *</Label>
                  <select required value={termDialog.form.reason}
                    onChange={(e) => setTermDialog({ ...termDialog, form: { ...termDialog.form, reason: e.target.value } })}
                    className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    {Object.entries(TERM_REASON_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div><Label>Son Çalışma Günü *</Label><Input required type="date" value={termDialog.form.last_day}
                  onChange={(e) => setTermDialog({ ...termDialog, form: { ...termDialog.form, last_day: e.target.value } })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>İhbar Süresi (gün)</Label><Input type="number" min="0" value={termDialog.form.notice_period_days}
                  onChange={(e) => setTermDialog({ ...termDialog, form: { ...termDialog.form, notice_period_days: parseInt(e.target.value || '0', 10) } })} /></div>
                <div><Label>Kıdem Override (boş = otomatik)</Label><Input type="number" step="0.01" value={termDialog.form.severance_override}
                  onChange={(e) => setTermDialog({ ...termDialog, form: { ...termDialog.form, severance_override: e.target.value } })} placeholder="Otomatik hesap kullan" /></div>
              </div>
              <div><Label>Çıkış Görüşmesi Notları</Label><Textarea rows={4} value={termDialog.form.exit_interview_notes}
                onChange={(e) => setTermDialog({ ...termDialog, form: { ...termDialog.form, exit_interview_notes: e.target.value } })}
                placeholder="Ayrılış sebebi, geri bildirimi, geliştirilebilecek alanlar vb." /></div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={termDialog.form.eligible_for_rehire}
                  onChange={(e) => setTermDialog({ ...termDialog, form: { ...termDialog.form, eligible_for_rehire: e.target.checked } })} />
                Tekrar işe alınabilir
              </label>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setTermDialog({ open: false, form: null, outstanding: [] })}>Vazgeç</Button>
                {(termDialog.outstanding || []).length > 0 ? (
                  <Button type="button" disabled={saving}
                    onClick={() => submitTerm(null, { forceRelease: true })}
                    className="bg-rose-600 hover:bg-rose-700 text-white">
                    {saving ? 'İşleniyor...' : 'Zimmetli olsa da kapat'}
                  </Button>
                ) : (
                  <Button type="submit" disabled={saving} className="bg-rose-600 hover:bg-rose-700 text-white">
                    {saving ? 'İşleniyor...' : 'Ayrılışı Kaydet'}
                  </Button>
                )}
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Hedef check-in */}
      <Dialog open={checkinDialog.open} onOpenChange={(o) => !o && setCheckinDialog({ open: false, reviewId: null, form: null })}>
        <DialogContent>
          <DialogHeader><DialogTitle>Hedef Check-in Ekle</DialogTitle></DialogHeader>
          {checkinDialog.form && (
            <form onSubmit={submitCheckin} className="grid gap-3">
              <div><Label>Hedef *</Label><Textarea required rows={2} value={checkinDialog.form.goal_text}
                onChange={(e) => setCheckinDialog({ ...checkinDialog, form: { ...checkinDialog.form, goal_text: e.target.value } })}
                placeholder="Örn: Q1'de upsell oranını %15'e çıkar" /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>İlerleme (%)</Label><Input type="number" min="0" max="100" value={checkinDialog.form.progress_pct}
                  onChange={(e) => setCheckinDialog({ ...checkinDialog, form: { ...checkinDialog.form, progress_pct: e.target.value } })} /></div>
                <div>
                  <Label>Durum</Label>
                  <select value={checkinDialog.form.status}
                    onChange={(e) => setCheckinDialog({ ...checkinDialog, form: { ...checkinDialog.form, status: e.target.value } })}
                    className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="on_track">Yolunda</option>
                    <option value="at_risk">Risk altında</option>
                    <option value="blocked">Bloke</option>
                    <option value="done">Tamamlandı</option>
                  </select>
                </div>
              </div>
              <div><Label>Tarih</Label><Input type="date" value={checkinDialog.form.checkin_date}
                onChange={(e) => setCheckinDialog({ ...checkinDialog, form: { ...checkinDialog.form, checkin_date: e.target.value } })} /></div>
              <div><Label>Not</Label><Textarea rows={2} value={checkinDialog.form.note}
                onChange={(e) => setCheckinDialog({ ...checkinDialog, form: { ...checkinDialog.form, note: e.target.value } })} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setCheckinDialog({ open: false, reviewId: null, form: null })}>Vazgeç</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ekle'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Task #265: Zimmet ata */}
      <Dialog open={eqDialog.open} onOpenChange={(o) => !o && setEqDialog({ open: false, form: null })}>
        <DialogContent>
          <DialogHeader><DialogTitle>Zimmet Ata</DialogTitle></DialogHeader>
          {eqDialog.form && (
            <form onSubmit={submitEq} className="grid gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>Tür *</Label>
                  <select value={eqDialog.form.item_type}
                    onChange={(e) => setEqDialog({ ...eqDialog, form: { ...eqDialog.form, item_type: e.target.value } })}
                    className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="uniform">Üniforma</option>
                    <option value="card">Kart</option>
                    <option value="key">Anahtar</option>
                    <option value="radio">Telsiz</option>
                    <option value="laptop">Dizüstü</option>
                    <option value="phone">Telefon</option>
                    <option value="tablet">Tablet</option>
                    <option value="tool">Alet</option>
                    <option value="vehicle">Araç</option>
                    <option value="other">Diğer</option>
                  </select>
                </div>
                <div><Label>Zimmet Tarihi</Label><Input type="date" value={eqDialog.form.assigned_at}
                  onChange={(e) => setEqDialog({ ...eqDialog, form: { ...eqDialog.form, assigned_at: e.target.value } })} /></div>
              </div>
              <div><Label>Eşya Adı *</Label><Input required value={eqDialog.form.item_label}
                onChange={(e) => setEqDialog({ ...eqDialog, form: { ...eqDialog.form, item_label: e.target.value } })} placeholder="Örn. Resepsiyon üniforması XL" /></div>
              <div><Label>Seri No</Label><Input value={eqDialog.form.serial_no}
                onChange={(e) => setEqDialog({ ...eqDialog, form: { ...eqDialog.form, serial_no: e.target.value } })} /></div>
              <div><Label>Not</Label><Textarea rows={2} value={eqDialog.form.notes}
                onChange={(e) => setEqDialog({ ...eqDialog, form: { ...eqDialog.form, notes: e.target.value } })} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setEqDialog({ open: false, form: null })}>Vazgeç</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ata'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Task #265: Uyarı düş */}
      <Dialog open={warnDialog.open} onOpenChange={(o) => !o && setWarnDialog({ open: false, form: null })}>
        <DialogContent>
          <DialogHeader><DialogTitle className="text-amber-700">Disiplin Uyarısı</DialogTitle></DialogHeader>
          {warnDialog.form && (
            <form onSubmit={submitWarn} className="grid gap-3">
              <div className="rounded bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
                İş K. m.25/II referansıyla disiplin sicili kaydı oluşturulur. Personel "Onayla" diyene kadar tebliğ edilmemiş sayılır.
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <Label>Tür *</Label>
                  <select value={warnDialog.form.warning_type}
                    onChange={(e) => setWarnDialog({ ...warnDialog, form: { ...warnDialog.form, warning_type: e.target.value } })}
                    className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="verbal">Sözlü</option>
                    <option value="written">Yazılı</option>
                    <option value="final">Son ihtar</option>
                  </select>
                </div>
                <div>
                  <Label>Şiddet</Label>
                  <select value={warnDialog.form.severity}
                    onChange={(e) => setWarnDialog({ ...warnDialog, form: { ...warnDialog.form, severity: e.target.value } })}
                    className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="low">Düşük</option>
                    <option value="medium">Orta</option>
                    <option value="high">Yüksek</option>
                  </select>
                </div>
                <div><Label>Tarih</Label><Input type="date" value={warnDialog.form.issued_at}
                  onChange={(e) => setWarnDialog({ ...warnDialog, form: { ...warnDialog.form, issued_at: e.target.value } })} /></div>
              </div>
              <div><Label>Sebep *</Label><Textarea required rows={4} value={warnDialog.form.reason}
                onChange={(e) => setWarnDialog({ ...warnDialog, form: { ...warnDialog.form, reason: e.target.value } })}
                placeholder="Tekrar eden geç kalma, görev ihmali, müşteri şikayeti vb." /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setWarnDialog({ open: false, form: null })}>Vazgeç</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Uyarı Kaydet'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Task #265: Eğitim ekle */}
      <Dialog open={trainDialog.open} onOpenChange={(o) => !o && setTrainDialog({ open: false, form: null })}>
        <DialogContent>
          <DialogHeader><DialogTitle>Eğitim Ekle</DialogTitle></DialogHeader>
          {trainDialog.form && (
            <form onSubmit={submitTrain} className="grid gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>Tür *</Label>
                  <select value={trainDialog.form.training_type}
                    onChange={(e) => setTrainDialog({ ...trainDialog, form: { ...trainDialog.form, training_type: e.target.value } })}
                    className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="hygiene">Hijyen</option>
                    <option value="safety">İş Güvenliği</option>
                    <option value="orientation">Oryantasyon</option>
                    <option value="technical">Teknik</option>
                    <option value="language">Dil</option>
                    <option value="leadership">Liderlik</option>
                    <option value="compliance">Compliance</option>
                    <option value="other">Diğer</option>
                  </select>
                </div>
                <div><Label>Veren Kurum</Label><Input value={trainDialog.form.provider}
                  onChange={(e) => setTrainDialog({ ...trainDialog, form: { ...trainDialog.form, provider: e.target.value } })} /></div>
              </div>
              <div><Label>Eğitim Adı *</Label><Input required value={trainDialog.form.title}
                onChange={(e) => setTrainDialog({ ...trainDialog, form: { ...trainDialog.form, title: e.target.value } })} placeholder="Örn. Yıllık Hijyen Tazeleme" /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Tamamlanma *</Label><Input required type="date" value={trainDialog.form.completed_at}
                  onChange={(e) => setTrainDialog({ ...trainDialog, form: { ...trainDialog.form, completed_at: e.target.value } })} /></div>
                <div><Label>Geçerlilik Bitiş</Label><Input type="date" value={trainDialog.form.valid_until}
                  onChange={(e) => setTrainDialog({ ...trainDialog, form: { ...trainDialog.form, valid_until: e.target.value } })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Saat</Label><Input type="number" min="0" step="0.5" value={trainDialog.form.hours}
                  onChange={(e) => setTrainDialog({ ...trainDialog, form: { ...trainDialog.form, hours: e.target.value } })} /></div>
                <div><Label>Skor (0-100)</Label><Input type="number" min="0" max="100" value={trainDialog.form.score}
                  onChange={(e) => setTrainDialog({ ...trainDialog, form: { ...trainDialog.form, score: e.target.value } })} /></div>
              </div>
              <div><Label>Not</Label><Textarea rows={2} value={trainDialog.form.notes}
                onChange={(e) => setTrainDialog({ ...trainDialog, form: { ...trainDialog.form, notes: e.target.value } })} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setTrainDialog({ open: false, form: null })}>Vazgeç</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ekle'}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default StaffProfile;
