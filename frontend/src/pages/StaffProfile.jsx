import { useTranslation } from "react-i18next";
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, RefreshCw, User, Mail, Phone, Building2, Briefcase, Calendar, Clock, DollarSign, Award, FileText, AlertCircle, GraduationCap, Folder, TrendingUp, UserMinus, Plus, Trash2, Download, Upload, ChevronDown, ChevronRight, Target, Package, ShieldAlert, BookOpen, Check, RotateCcw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { formatCurrency } from '@/lib/currency';
import { confirmDialog } from '@/lib/dialogs';
import PaginationBar from '@/components/PaginationBar';
import SkeletonRow from '@/components/SkeletonRow';
import { useHRPagination } from '@/hooks/useHRPagination';
const LEAVE_TYPE_LABEL = {
  annual: 'Yıllık',
  sick: 'Hastalık',
  maternity: 'Doğum',
  paternity: 'Babalık',
  unpaid: 'Ücretsiz',
  bereavement: 'Vefat',
  excused: 'Mazeret'
};
const STATUS_INTENT = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  scheduled: 'info',
  completed: 'success',
  missed: 'danger',
  on_track: 'success',
  at_risk: 'warning',
  blocked: 'danger',
  done: 'success'
};
const STATUS_LABEL = {
  pending: 'Beklemede',
  approved: 'Onaylandı',
  rejected: 'Reddedildi',
  scheduled: 'Planlı',
  completed: 'Tamamlandı',
  missed: 'Kaçırıldı',
  on_track: 'Yolunda',
  at_risk: 'Risk',
  blocked: 'Bloke',
  done: 'Tamam'
};
const DOC_TYPE_LABEL = {
  contract: 'Sözleşme',
  id: 'Kimlik',
  diploma: 'Diploma',
  health: 'Sağlık',
  insurance: 'Sigorta',
  tax: 'Vergi',
  other: 'Diğer'
};
const TERM_REASON_LABEL = {
  resign: 'İstifa',
  dismiss: 'İşten çıkarma',
  mutual: 'Karşılıklı anlaşma',
  retire: 'Emeklilik',
  end_of_contract: 'Sözleşme bitti',
  death: 'Vefat'
};
const CHANGE_TYPE_LABEL = {
  raise: 'Zam',
  promotion: 'Terfi',
  correction: 'Düzeltme',
  demotion: 'İndirim'
};
const StaffProfile = () => {
  const {
    t
  } = useTranslation();
  const {
    id
  } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [activeTab, setActiveTab] = useState('attendance');

  // ── Pagination hooks for the 6 lazy sub-resource tabs ──────────────
  // Each hook is enabled only when its corresponding tab is active,
  // so data fetches are lazy and page state is preserved per tab.
  const certsPage = useHRPagination(id ? `/hr/staff/${id}/certifications` : null, {}, {
    enabled: activeTab === 'certifications'
  });
  const docsPage = useHRPagination(id ? `/hr/staff/${id}/documents` : null, {}, {
    enabled: activeTab === 'documents'
  });
  const salaryPage = useHRPagination(id ? `/hr/staff/${id}/salary-history` : null, {}, {
    enabled: activeTab === 'salary'
  });
  const equipmentPage = useHRPagination(id ? `/hr/staff/${id}/equipment` : null, {}, {
    enabled: activeTab === 'equipment'
  });
  const warningsPage = useHRPagination(id ? `/hr/staff/${id}/warnings` : null, {}, {
    enabled: activeTab === 'warnings'
  });
  const trainingsPage = useHRPagination(id ? `/hr/staff/${id}/trainings` : null, {}, {
    enabled: activeTab === 'trainings'
  });

  // Legacy section states (kept for backward compat with existing render code)
  const [termination, setTermination] = useState(null);

  // Dialogs
  const [certDialog, setCertDialog] = useState({
    open: false,
    form: null
  });
  const [docDialog, setDocDialog] = useState({
    open: false,
    file: null,
    doc_type: 'contract',
    label: ''
  });
  const [salaryDialog, setSalaryDialog] = useState({
    open: false,
    form: null
  });
  const [termDialog, setTermDialog] = useState({
    open: false,
    form: null,
    outstanding: []
  });
  const [checkinDialog, setCheckinDialog] = useState({
    open: false,
    reviewId: null,
    form: null
  });
  const [eqDialog, setEqDialog] = useState({
    open: false,
    form: null
  });
  const [warnDialog, setWarnDialog] = useState({
    open: false,
    form: null
  });
  const [trainDialog, setTrainDialog] = useState({
    open: false,
    form: null
  });
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
  useEffect(() => {
    load();
    loadTermination();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, loadTermination]);

  // ===== Certifications =====
  const openCertDialog = () => setCertDialog({
    open: true,
    form: {
      name: '',
      issuer: '',
      issue_date: new Date().toISOString().slice(0, 10),
      expiry_date: '',
      certificate_no: '',
      file_url: '',
      notes: ''
    }
  });
  const submitCert = async e => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/staff/${id}/certifications`, certDialog.form);
      toast.success('Sertifika eklendi');
      setCertDialog({
        open: false,
        form: null
      });
      certsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    } finally {
      setSaving(false);
    }
  };
  const deleteCert = async cert => {
    if (!(await confirmDialog({
      message: `"${cert.name}" sertifikası silinsin mi?`
    }))) return;
    try {
      await axios.delete(`/hr/certifications/${cert.id}`);
      toast.success('Silindi');
      certsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  // ===== Documents =====
  const submitDoc = async e => {
    e.preventDefault();
    if (!docDialog.file) {
      toast.error('Dosya seçin');
      return;
    }
    setSaving(true);
    const fd = new FormData();
    fd.append('file', docDialog.file);
    try {
      await axios.post(`/hr/staff/${id}/documents`, fd, {
        params: {
          doc_type: docDialog.doc_type,
          label: docDialog.label || ''
        },
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      toast.success('Belge yüklendi');
      setDocDialog({
        open: false,
        file: null,
        doc_type: 'contract',
        label: ''
      });
      docsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yüklenemedi');
    } finally {
      setSaving(false);
    }
  };
  const downloadDoc = async doc => {
    try {
      const r = await axios.get(`/hr/documents/${doc.id}/download`, {
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([r.data], {
        type: doc.content_type
      }));
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.filename || 'belge';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast.error('İndirilemedi');
    }
  };
  const deleteDoc = async doc => {
    if (!(await confirmDialog({
      message: `"${doc.label || doc.filename}" silinsin mi?`
    }))) return;
    try {
      await axios.delete(`/hr/documents/${doc.id}`);
      toast.success('Silindi');
      docsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  // ===== Salary =====
  const openSalaryDialog = () => setSalaryDialog({
    open: true,
    form: {
      new_hourly_rate: data?.staff?.hourly_rate || '',
      effective_date: new Date().toISOString().slice(0, 10),
      change_type: 'raise',
      reason: ''
    }
  });
  const submitSalary = async e => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/staff/${id}/salary-change`, {
        ...salaryDialog.form,
        new_hourly_rate: parseFloat(salaryDialog.form.new_hourly_rate)
      });
      toast.success('Maaş değişikliği kaydedildi');
      setSalaryDialog({
        open: false,
        form: null
      });
      salaryPage.refresh();
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally {
      setSaving(false);
    }
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
      eligible_for_rehire: true
    },
    outstanding: (equipmentPage.items || []).filter(it => it.status === 'assigned')
  });
  const submitTerm = async (e, {
    forceRelease = false
  } = {}) => {
    if (e && e.preventDefault) e.preventDefault();
    if (!(await confirmDialog({
      message: forceRelease ? 'Personelin üzerinde iade alınmamış zimmet var. Yine de ayrılış kaydedilsin mi? (Zimmet kayıtları açık kalır.)' : 'Personeli pasifleştirmek üzeresiniz. Kıdem tazminatı hesabı kaydedilecek. Devam edilsin mi?'
    }))) return;
    setSaving(true);
    try {
      const payload = {
        ...termDialog.form
      };
      payload.severance_override = payload.severance_override === '' ? null : parseFloat(payload.severance_override);
      const url = forceRelease ? `/hr/staff/${id}/terminate?force_release=true` : `/hr/staff/${id}/terminate`;
      const r = await axios.post(url, payload);
      toast.success(`Ayrılış kaydedildi. Kıdem: ${formatCurrency(r.data.termination?.severance_paid || 0, 'TRY')}`);
      setTermDialog({
        open: false,
        form: null,
        outstanding: []
      });
      loadTermination();
      load();
      equipmentPage.refresh();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409 && detail && detail.code === 'outstanding_equipment') {
        setTermDialog(s => ({
          ...s,
          outstanding: detail.outstanding_equipment || []
        }));
        toast.error(detail.message || 'İade alınmamış zimmet var');
      } else {
        toast.error(typeof detail === 'string' ? detail : detail?.message || 'İşlem başarısız');
      }
    } finally {
      setSaving(false);
    }
  };
  const returnEqFromTerm = async eq => {
    try {
      await axios.post(`/hr/equipment/${eq.id}/return`, {
        returned_at: new Date().toISOString().slice(0, 10),
        condition_on_return: 'good'
      });
      toast.success(`"${eq.item_label}" iade alındı`);
      setTermDialog(s => ({
        ...s,
        outstanding: (s.outstanding || []).filter(x => x.id !== eq.id)
      }));
      equipmentPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İade alınamadı');
    }
  };

  // ===== Performance check-ins =====
  const toggleReviewExpand = async reviewId => {
    if (expandedReview === reviewId) {
      setExpandedReview(null);
      return;
    }
    setExpandedReview(reviewId);
    if (!checkinsByReview[reviewId]) {
      try {
        const r = await axios.get(`/hr/performance/${reviewId}/checkins`);
        setCheckinsByReview(prev => ({
          ...prev,
          [reviewId]: r.data.items || []
        }));
      } catch {/* ignore */}
    }
  };
  const openCheckinDialog = reviewId => setCheckinDialog({
    open: true,
    reviewId,
    form: {
      goal_text: '',
      progress_pct: 0,
      status: 'on_track',
      note: '',
      checkin_date: new Date().toISOString().slice(0, 10)
    }
  });
  const submitCheckin = async e => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/performance/${checkinDialog.reviewId}/checkin`, {
        ...checkinDialog.form,
        progress_pct: parseInt(checkinDialog.form.progress_pct, 10)
      });
      toast.success('Check-in eklendi');
      const rid = checkinDialog.reviewId;
      const r = await axios.get(`/hr/performance/${rid}/checkins`);
      setCheckinsByReview(prev => ({
        ...prev,
        [rid]: r.data.items || []
      }));
      setCheckinDialog({
        open: false,
        reviewId: null,
        form: null
      });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    } finally {
      setSaving(false);
    }
  };

  // ===== Task #265: Zimmet (Equipment) =====
  const openEqDialog = () => setEqDialog({
    open: true,
    form: {
      item_type: 'uniform',
      item_label: '',
      serial_no: '',
      assigned_at: new Date().toISOString().slice(0, 10),
      notes: ''
    }
  });
  const submitEq = async e => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/staff/${id}/equipment`, eqDialog.form);
      toast.success('Zimmet kaydedildi');
      setEqDialog({
        open: false,
        form: null
      });
      equipmentPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };
  const returnEq = async eq => {
    if (!(await confirmDialog({
      message: `"${eq.item_label}" iade alınsın mı?`
    }))) return;
    try {
      await axios.post(`/hr/equipment/${eq.id}/return`, {
        returned_at: new Date().toISOString().slice(0, 10),
        condition_on_return: 'good'
      });
      toast.success('İade alındı');
      equipmentPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İade alınamadı');
    }
  };
  const deleteEq = async eq => {
    if (!(await confirmDialog({
      message: `"${eq.item_label}" zimmet kaydı silinsin mi?`
    }))) return;
    try {
      await axios.delete(`/hr/equipment/${eq.id}`);
      toast.success('Silindi');
      equipmentPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  // ===== Task #265: Uyarılar (Warnings) =====
  const openWarnDialog = () => setWarnDialog({
    open: true,
    form: {
      warning_type: 'verbal',
      severity: 'medium',
      reason: '',
      issued_at: new Date().toISOString().slice(0, 10)
    }
  });
  const submitWarn = async e => {
    e.preventDefault();
    setSaving(true);
    try {
      await axios.post(`/hr/staff/${id}/warnings`, warnDialog.form);
      toast.success('Uyarı kaydedildi');
      setWarnDialog({
        open: false,
        form: null
      });
      warningsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };
  const ackWarn = async w => {
    try {
      await axios.post(`/hr/warnings/${w.id}/acknowledge`);
      toast.success('Onaylandı');
      warningsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Onaylanamadı');
    }
  };
  const deleteWarn = async w => {
    if (!(await confirmDialog({
      message: `Uyarı kaydı silinsin mi?`
    }))) return;
    try {
      await axios.delete(`/hr/warnings/${w.id}`);
      toast.success('Silindi');
      warningsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  // ===== Task #265: Eğitimler (Trainings) =====
  const openTrainDialog = () => setTrainDialog({
    open: true,
    form: {
      training_type: 'hygiene',
      title: '',
      provider: '',
      completed_at: new Date().toISOString().slice(0, 10),
      valid_until: '',
      hours: '',
      score: '',
      notes: ''
    }
  });
  const submitTrain = async e => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...trainDialog.form
      };
      if (!payload.valid_until) delete payload.valid_until;
      if (payload.provider === '') delete payload.provider;
      if (payload.notes === '') delete payload.notes;
      payload.hours = payload.hours === '' ? null : parseFloat(payload.hours);
      payload.score = payload.score === '' ? null : parseFloat(payload.score);
      await axios.post(`/hr/staff/${id}/trainings`, payload);
      toast.success('Eğitim kaydedildi');
      setTrainDialog({
        open: false,
        form: null
      });
      trainingsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };
  const deleteTrain = async t => {
    if (!(await confirmDialog({
      message: `"${t.title}" eğitim kaydı silinsin mi?`
    }))) return;
    try {
      await axios.delete(`/hr/trainings/${t.id}`);
      toast.success('Silindi');
      trainingsPage.refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };
  const headerActions = <>
      <Button variant="outline" size="sm" onClick={() => navigate('/staff-management')}>
        <ArrowLeft className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffProfile.personel_listesi")}</Button>
      <Button variant="outline" size="sm" onClick={load} disabled={loading}>
        <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />{t("cm.pages_StaffProfile.yenile")}</Button>
      {data?.staff?.active !== false && !termination && <Button variant="outline" size="sm" onClick={openTermDialog} className="text-rose-700 border-rose-300 hover:bg-rose-50">
          <UserMinus className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffProfile.ayr\u0131l\u0131\u015F_i_\u015Flemleri")}</Button>}
    </>;
  if (loading && !data) {
    return <div className="p-2">
        <PageHeader icon={User} title={t("cm.pages_StaffProfile.personel_profili")} subtitle="Yükleniyor..." actions={headerActions} />
      </div>;
  }
  if (!data) {
    return <div className="p-2">
        <PageHeader icon={User} title={t("cm.pages_StaffProfile.personel_bulunamad\u0131")} actions={headerActions} />
        <Card><CardContent className="py-10 text-center text-slate-500">
          <AlertCircle className="w-8 h-8 mx-auto mb-2 text-rose-500" />{t("cm.pages_StaffProfile.bu_personele_ait_kay\u0131t_yok_vey")}</CardContent></Card>
      </div>;
  }
  const s = data.staff || {};
  const att = data.attendance || {};
  const lv = data.leaves || {};
  const bal = data.leave_balance;
  const perf = data.performance || {};
  const pay = data.payroll || {};
  const shifts = data.upcoming_shifts || [];
  return <div className="p-2">
      <PageHeader icon={User} title={s.name || 'Personel'} subtitle={`${s.position || '—'} • ${s.department || '—'}`} actions={headerActions} />

      {/* Termination banner */}
      {termination && <Card className="mb-4 border-rose-200 bg-rose-50">
          <CardContent className="py-3 flex items-center gap-3 text-sm">
            <UserMinus className="w-5 h-5 text-rose-600" />
            <div className="flex-1">
              <div className="font-medium text-rose-900">{t("cm.pages_StaffProfile.personel_ayr\u0131lm\u0131\u015F")}{TERM_REASON_LABEL[termination.reason] || termination.reason}{t("cm.pages_StaffProfile._son_g\xFCn")}{termination.last_day}
              </div>
              <div className="text-xs text-rose-700">{t("cm.pages_StaffProfile.k\u0131dem_\xF6denen")}<strong>{formatCurrency(termination.severance_paid || 0, 'TRY')}</strong>
                {' '}{t("cm.pages_StaffProfile._k\u0131dem_s\xFCresi")}{termination.severance_calc?.years_of_service || 0}{t("cm.pages_StaffProfile.y\u0131l")}{termination.eligible_for_rehire ? ' • Tekrar işe alınabilir' : ' • Tekrar işe alınamaz'}
              </div>
            </div>
          </CardContent>
        </Card>}

      {/* Genel bilgi kartı */}
      <Card className="mb-4">
        <CardContent className="grid gap-3 md:grid-cols-4 py-4">
          <div className="flex items-center gap-2 text-sm text-slate-700"><Mail className="w-4 h-4 text-slate-400" /> {s.email || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Phone className="w-4 h-4 text-slate-400" /> {s.phone || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Building2 className="w-4 h-4 text-slate-400" /> {s.department || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Briefcase className="w-4 h-4 text-slate-400" /> {s.employment_type || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Calendar className="w-4 h-4 text-slate-400" />{t("cm.pages_StaffProfile.i_\u015Fe_giri\u015F")}{s.hire_date || '—'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><DollarSign className="w-4 h-4 text-slate-400" />{t("cm.pages_StaffProfile.saatlik")}{s.hourly_rate ? `${s.hourly_rate} TRY` : 'tanımsız (140 TRY default)'}</div>
          <div className="flex items-center gap-2 text-sm text-slate-700"><Clock className="w-4 h-4 text-slate-400" />{t("cm.pages_StaffProfile.ayl\u0131k_saat")}{s.monthly_hours || '195 (default)'}</div>
          <div className="flex items-center gap-2 text-sm">
            {s.active === false ? <StatusBadge intent="danger">{t("cm.pages_StaffProfile.pasif")}</StatusBadge> : s.derived_from === 'users' ? <StatusBadge intent="neutral">{t("cm.pages_StaffProfile.kullan\u0131c\u0131dan_t\xFCretildi")}</StatusBadge> : <StatusBadge intent="info">{t("cm.pages_StaffProfile.hr_y\xF6netimli")}</StatusBadge>}
          </div>
        </CardContent>
      </Card>

      {/* KPI özeti */}
      <div className="grid gap-3 md:grid-cols-4 mb-4">
        <KpiCard intent="info" icon={Clock} label={t("cm.pages_StaffProfile.son_30g_saat")} value={att.total_hours_30d || 0} sub={`${att.days_present_30d || 0} gün`} />
        <KpiCard intent="warning" icon={Calendar} label={t("cm.pages_StaffProfile.bekleyen_i_zin")} value={lv.pending || 0} sub={`Toplam ${lv.total || 0} talep`} />
        <KpiCard intent="success" icon={Award} label={t("cm.pages_StaffProfile.performans_ort")} value={perf.avg_score || 0} sub={`${perf.total || 0} değerlendirme`} />
        <KpiCard intent={certsPage.meta?.expired > 0 ? 'danger' : 'info'} icon={GraduationCap} label={t("cm.pages_StaffProfile.aktif_sertifika")} value={certsPage.meta?.active || 0} sub={certsPage.meta?.expired > 0 ? `${certsPage.meta?.expired} süresi geçmiş` : `${docsPage.total || 0} belge`} />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-11 text-xs">
          <TabsTrigger value="attendance">{t("cm.pages_StaffProfile.devam")}</TabsTrigger>
          <TabsTrigger value="leave">{t("cm.pages_StaffProfile.i_zin")}</TabsTrigger>
          <TabsTrigger value="performance">{t("cm.pages_StaffProfile.performans")}</TabsTrigger>
          <TabsTrigger value="payroll">{t("cm.pages_StaffProfile.bordro")}</TabsTrigger>
          <TabsTrigger value="shifts">{t("cm.pages_StaffProfile.vardiya")}</TabsTrigger>
          <TabsTrigger value="certifications">{t("cm.pages_StaffProfile.sertifika")}</TabsTrigger>
          <TabsTrigger value="trainings">{t("cm.pages_StaffProfile.e\u011Fitim")}</TabsTrigger>
          <TabsTrigger value="equipment">{t("cm.pages_StaffProfile.zimmet")}</TabsTrigger>
          <TabsTrigger value="warnings">{t("cm.pages_StaffProfile.uyar\u0131")}</TabsTrigger>
          <TabsTrigger value="documents">{t("cm.pages_StaffProfile.belgeler")}</TabsTrigger>
          <TabsTrigger value="salary">{t("cm.pages_StaffProfile.maa\u015F")}</TabsTrigger>
        </TabsList>

        <TabsContent value="attendance" className="mt-4">
          <Card>
            <CardHeader><CardTitle>{t("cm.pages_StaffProfile.son_30_g\xFCn_devam_kay\u0131tlar\u0131")}</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">{t("cm.pages_StaffProfile.tarih")}</th><th>{t("cm.pages_StaffProfile.giri\u015F")}</th><th>{t("cm.pages_StaffProfile.\xE7\u0131k\u0131\u015F")}</th><th className="text-right">{t("cm.pages_StaffProfile.saat")}</th>
                  </tr></thead>
                  <tbody>
                    {(att.records || []).map((r, i) => <tr key={r.id || i} className="border-t border-slate-100">
                        <td className="py-2">{r.date}</td>
                        <td>{(r.clock_in || '').slice(11, 16) || '—'}</td>
                        <td>{(r.clock_out || '').slice(11, 16) || '—'}</td>
                        <td className="text-right">{(r.total_hours || 0).toFixed(2)}</td>
                      </tr>)}
                    {(att.records || []).length === 0 && <tr><td colSpan={4} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.kay\u0131t_yok")}</td></tr>}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="leave" className="mt-4 space-y-3">
          {bal && <div className="grid gap-3 md:grid-cols-3">
              <KpiCard intent="info" label={`Yıllık İzin (${bal.year})`} value={`${bal.annual?.remaining ?? 0} / ${bal.annual?.total ?? 0}`} sub={`Hak: ${bal.annual?.entitlement} + ${bal.annual?.carry_over || 0} devir`} />
              <KpiCard intent="warning" label={t("cm.pages_StaffProfile.kullan\u0131lan_y\u0131ll\u0131k")} value={bal.annual?.used ?? 0} sub="onaylı" />
              <KpiCard intent="neutral" label={t("cm.pages_StaffProfile.hastal\u0131k_kalan_hak")} value={`${bal.sick?.remaining ?? 0} / ${bal.sick?.entitlement ?? 5}`} />
            </div>}
          <Card>
            <CardHeader><CardTitle>{t("cm.pages_StaffProfile.i_zin_ge\xE7mi\u015Fi")}</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">{t("cm.pages_StaffProfile.t\xFCr")}</th><th>{t("cm.pages_StaffProfile.ba\u015Fl")}</th><th>{t("cm.pages_StaffProfile.biti\u015F")}</th>
                    <th className="text-right">{t("cm.pages_StaffProfile.g\xFCn")}</th><th>{t("cm.pages_StaffProfile.durum")}</th><th>{t("cm.pages_StaffProfile.sebep")}</th>
                  </tr></thead>
                  <tbody>
                    {(lv.items || []).map(l => <tr key={l.id} className="border-t border-slate-100">
                        <td className="py-2">{LEAVE_TYPE_LABEL[l.leave_type] || l.leave_type}</td>
                        <td>{l.start_date}</td><td>{l.end_date}</td>
                        <td className="text-right">{l.total_days}</td>
                        <td><StatusBadge intent={STATUS_INTENT[l.status]}>{STATUS_LABEL[l.status]}</StatusBadge></td>
                        <td className="text-slate-600 text-xs max-w-xs truncate">{l.reason || '—'}</td>
                      </tr>)}
                    {(lv.items || []).length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.i_zin_kayd\u0131_yok")}</td></tr>}
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
                <span>{t("cm.pages_StaffProfile.performans_de\u011Ferlendirmeleri")}</span>
                <span className="text-xs text-slate-500 font-normal">{t("cm.pages_StaffProfile.sat\u0131ra_t\u0131klayarak_hedef_check")}</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2 w-6"></th><th>{t("cm.pages_StaffProfile.tarih")}</th><th>{t("cm.pages_StaffProfile.d\xF6nem")}</th>
                    <th className="text-right">{t("cm.pages_StaffProfile.puan")}</th><th>{t("cm.pages_StaffProfile.g\xFC\xE7l\xFC")}</th><th>{t("cm.pages_StaffProfile.geli\u015Fim")}</th><th></th>
                  </tr></thead>
                  <tbody>
                    {(perf.items || []).map(p => {
                    const expanded = expandedReview === p.id;
                    const checkins = checkinsByReview[p.id] || [];
                    return <React.Fragment key={p.id}>
                          <tr className="border-t border-slate-100 align-top hover:bg-slate-50 cursor-pointer" onClick={() => toggleReviewExpand(p.id)}>
                            <td className="py-2">{expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}</td>
                            <td>{(p.reviewed_at || '').slice(0, 10)}</td>
                            <td>{p.period || '—'}</td>
                            <td className="text-right font-semibold">{p.overall_score}</td>
                            <td className="text-slate-600 text-xs max-w-xs">{p.strengths || '—'}</td>
                            <td className="text-slate-600 text-xs max-w-xs">{p.improvement_areas || '—'}</td>
                            <td className="text-right">
                              <Button size="sm" variant="outline" onClick={e => {
                            e.stopPropagation();
                            openCheckinDialog(p.id);
                          }}>
                                <Plus className="w-3 h-3 mr-1" />{t("cm.pages_StaffProfile.check_in")}</Button>
                            </td>
                          </tr>
                          {expanded && <tr className="bg-slate-50/60">
                              <td></td>
                              <td colSpan={6} className="py-2 px-3">
                                <div className="space-y-2">
                                  <div className="text-xs font-semibold text-slate-700 flex items-center gap-1">
                                    <Target className="w-3 h-3" />{t("cm.pages_StaffProfile.hedef_i_lerleme_check_in_leri")}</div>
                                  {checkins.length === 0 ? <div className="text-xs text-slate-500">{t("cm.pages_StaffProfile.hen\xFCz_check_in_yok")}</div> : checkins.map(ci => <div key={ci.id} className="rounded border border-slate-200 bg-white p-2 text-xs flex items-start gap-3">
                                      <div className="w-12 text-slate-500">{ci.checkin_date}</div>
                                      <div className="flex-1">
                                        <div className="font-medium text-slate-800">{ci.goal_text}</div>
                                        {ci.note && <div className="text-slate-600 mt-0.5">{ci.note}</div>}
                                      </div>
                                      <div className="w-24">
                                        <div className="h-1.5 bg-slate-200 rounded overflow-hidden mb-0.5">
                                          <div className="h-full bg-emerald-500" style={{
                                    width: `${ci.progress_pct}%`
                                  }} />
                                        </div>
                                        <div className="text-[10px] text-slate-500">{ci.progress_pct}%</div>
                                      </div>
                                      <StatusBadge intent={STATUS_INTENT[ci.status] || 'info'}>{STATUS_LABEL[ci.status] || ci.status}</StatusBadge>
                                    </div>)}
                                </div>
                              </td>
                            </tr>}
                        </React.Fragment>;
                  })}
                    {(perf.items || []).length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.de\u011Ferlendirme_yok")}</td></tr>}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="payroll" className="mt-4">
          <Card>
            <CardHeader><CardTitle>{t("cm.pages_StaffProfile.bordro_ge\xE7mi\u015Fi")}</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">{t("cm.pages_StaffProfile.ay")}</th><th className="text-right">{t("cm.pages_StaffProfile.saat")}</th>
                    <th className="text-right">{t("cm.pages_StaffProfile.mesai")}</th><th className="text-right">{t("cm.pages_StaffProfile.br\xFCt")}</th><th className="text-right">{t("cm.pages_StaffProfile.net")}</th>
                  </tr></thead>
                  <tbody>
                    {(pay.recent || []).map((row, i) => <tr key={row.id || i} className="border-t border-slate-100">
                        <td className="py-2">{row.period_month}</td>
                        <td className="text-right">{(row.total_hours || 0).toFixed(1)}</td>
                        <td className="text-right text-amber-700">{(row.overtime_hours || 0).toFixed(1)}</td>
                        <td className="text-right">{formatCurrency(row.gross_pay || 0, 'TRY')}</td>
                        <td className="text-right font-semibold">{formatCurrency(row.net_salary || 0, 'TRY')}</td>
                      </tr>)}
                    {(pay.recent || []).length === 0 && <tr><td colSpan={5} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.hen\xFCz_bordro_yok")}</td></tr>}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="shifts" className="mt-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center justify-between">
              <span>{t("cm.pages_StaffProfile.yakla\u015Fan_vardiyalar")}</span>
              <Button size="sm" variant="outline" onClick={() => navigate('/hr/shifts')}>{t("cm.pages_StaffProfile.vardiya_planlay\u0131c\u0131")}</Button>
            </CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-slate-500 border-b">
                    <th className="py-2">{t("cm.pages_StaffProfile.tarih")}</th><th>{t("cm.pages_StaffProfile.tip")}</th><th>{t("cm.pages_StaffProfile.ba\u015Fl")}</th><th>{t("cm.pages_StaffProfile.biti\u015F")}</th><th>{t("cm.pages_StaffProfile.not")}</th>
                  </tr></thead>
                  <tbody>
                    {shifts.map(sh => <tr key={sh.id} className="border-t border-slate-100">
                        <td className="py-2">{sh.shift_date}</td>
                        <td className="capitalize">{sh.shift_type}</td>
                        <td>{sh.start_time}</td>
                        <td>
                          {sh.end_time}
                          {sh.crosses_midnight && <span className="ml-1 text-[10px] text-slate-400" title={t("cm.pages_StaffProfile.ertesi_g\xFCne_sarkar")}>{t("cm.pages_StaffProfile._1g")}</span>}
                        </td>
                        <td className="text-slate-600 text-xs">{sh.notes || '—'}</td>
                      </tr>)}
                    {shifts.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.planl\u0131_vardiya_yok")}</td></tr>}
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
                <span className="flex items-center gap-2"><GraduationCap className="w-4 h-4" />{t("cm.pages_StaffProfile.e\u011Fitim_ve_sertifikalar")}</span>
                <Button size="sm" onClick={openCertDialog}><Plus className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffProfile.sertifika_ekle")}</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {certsPage.error && <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {certsPage.error} <button onClick={certsPage.refresh} className="underline ml-2">{t("cm.pages_StaffProfile.tekrar_dene")}</button>
                </div>}
              <div className="overflow-x-auto">
                {certsPage.loading ? <SkeletonRow cols={5} rows={3} /> : <table className="w-full text-sm">
                    <thead><tr className="text-left text-slate-500 border-b">
                      <th className="py-2">{t("cm.pages_StaffProfile.sertifika")}</th><th>{t("cm.pages_StaffProfile.veren")}</th><th>{t("cm.pages_StaffProfile.verili\u015F")}</th>
                      <th>{t("cm.pages_StaffProfile.biti\u015F")}</th><th>{t("cm.pages_StaffProfile.numara")}</th><th>{t("cm.pages_StaffProfile.durum")}</th><th></th>
                    </tr></thead>
                    <tbody>
                      {certsPage.items.map(c => {
                    const today = new Date().toISOString().slice(0, 10);
                    const expired = c.expiry_date && c.expiry_date < today;
                    const expiringSoon = c.expiry_date && !expired && new Date(c.expiry_date) - new Date() < 90 * 86400000;
                    return <tr key={c.id} className="border-t border-slate-100">
                            <td className="py-2 font-medium">{c.name}{c.file_url && <a href={c.file_url} target="_blank" rel="noreferrer" className="ml-2 text-sky-600 hover:underline text-xs">{t("cm.pages_StaffProfile.dosya")}</a>}</td>
                            <td>{c.issuer || '—'}</td>
                            <td>{c.issue_date}</td>
                            <td>{c.expiry_date || 'süresiz'}</td>
                            <td className="text-xs">{c.certificate_no || '—'}</td>
                            <td>
                              {expired ? <StatusBadge intent="danger">{t("cm.pages_StaffProfile.s\xFCresi_ge\xE7mi\u015F")}</StatusBadge> : expiringSoon ? <StatusBadge intent="warning">{t("cm.pages_StaffProfile.yak\u0131nda_bitecek")}</StatusBadge> : <StatusBadge intent="success">{t("cm.pages_StaffProfile.ge\xE7erli")}</StatusBadge>}
                            </td>
                            <td className="text-right">
                              <Button size="sm" variant="ghost" onClick={() => deleteCert(c)}>
                                <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                              </Button>
                            </td>
                          </tr>;
                  })}
                      {certsPage.items.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.hen\xFCz_sertifika_yok_yang\u0131n_e\u011Fi")}</td></tr>}
                    </tbody>
                  </table>}
                {!certsPage.loading && certsPage.total > 0 && <PaginationBar page={certsPage.page} totalPages={certsPage.totalPages} total={certsPage.total} limit={certsPage.limit} onPageChange={certsPage.setPage} onLimitChange={certsPage.setLimit} />}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* BELGELER */}
        <TabsContent value="documents" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><Folder className="w-4 h-4" />{t("cm.pages_StaffProfile.personel_belgeleri")}</span>
                <Button size="sm" onClick={() => setDocDialog({
                open: true,
                file: null,
                doc_type: 'contract',
                label: ''
              })}>
                  <Upload className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffProfile.belge_y\xFCkle")}</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {docsPage.error && <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {docsPage.error} <button onClick={docsPage.refresh} className="underline ml-2">{t("cm.pages_StaffProfile.tekrar_dene")}</button>
                </div>}
              <div className="overflow-x-auto">
                {docsPage.loading ? <SkeletonRow cols={5} rows={3} /> : <table className="w-full text-sm">
                    <thead><tr className="text-left text-slate-500 border-b">
                      <th className="py-2">{t("cm.pages_StaffProfile.etiket")}</th><th>{t("cm.pages_StaffProfile.t\xFCr")}</th><th>{t("cm.pages_StaffProfile.dosya_ad\u0131")}</th>
                      <th className="text-right">{t("cm.pages_StaffProfile.boyut")}</th><th>{t("cm.pages_StaffProfile.y\xFCklenme")}</th><th></th>
                    </tr></thead>
                    <tbody>
                      {docsPage.items.map(d => <tr key={d.id} className="border-t border-slate-100">
                          <td className="py-2 font-medium">{d.label}</td>
                          <td><StatusBadge intent="neutral">{DOC_TYPE_LABEL[d.doc_type] || d.doc_type}</StatusBadge></td>
                          <td className="text-xs text-slate-600">{d.filename}</td>
                          <td className="text-right text-xs">{((d.size_bytes || 0) / 1024).toFixed(1)}{t("cm.pages_StaffProfile.kb")}</td>
                          <td className="text-xs">{(d.uploaded_at || '').slice(0, 10)}</td>
                          <td className="text-right space-x-1">
                            <Button size="sm" variant="ghost" onClick={() => downloadDoc(d)}>
                              <Download className="w-3.5 h-3.5" />
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => deleteDoc(d)}>
                              <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                            </Button>
                          </td>
                        </tr>)}
                      {docsPage.items.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.hen\xFCz_belge_yok_s\xF6zle\u015Fme_kimli")}</td></tr>}
                    </tbody>
                  </table>}
                {!docsPage.loading && docsPage.total > 0 && <PaginationBar page={docsPage.page} totalPages={docsPage.totalPages} total={docsPage.total} limit={docsPage.limit} onPageChange={docsPage.setPage} onLimitChange={docsPage.setLimit} />}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* MAAŞ */}
        <TabsContent value="salary" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><TrendingUp className="w-4 h-4" />{t("cm.pages_StaffProfile.maa\u015F_ge\xE7mi\u015Fi")}</span>
                <Button size="sm" onClick={openSalaryDialog}>
                  <Plus className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffProfile.zam_de\u011Fi\u015Fiklik")}</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {salaryPage.error && <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {salaryPage.error} <button onClick={salaryPage.refresh} className="underline ml-2">{t("cm.pages_StaffProfile.tekrar_dene")}</button>
                </div>}
              <div className="overflow-x-auto">
                {salaryPage.loading ? <SkeletonRow cols={5} rows={3} /> : <table className="w-full text-sm">
                    <thead><tr className="text-left text-slate-500 border-b">
                      <th className="py-2">{t("cm.pages_StaffProfile.y\xFCr\xFCrl\xFCk")}</th><th>{t("cm.pages_StaffProfile.t\xFCr")}</th>
                      <th className="text-right">{t("cm.pages_StaffProfile.eski")}</th><th className="text-right">{t("cm.pages_StaffProfile.yeni")}</th>
                      <th className="text-right">Δ%</th><th>{t("cm.pages_StaffProfile.sebep")}</th>
                    </tr></thead>
                    <tbody>
                      {salaryPage.items.map(r => <tr key={r.id} className="border-t border-slate-100">
                          <td className="py-2">{r.effective_date}</td>
                          <td><StatusBadge intent={r.change_type === 'demotion' ? 'danger' : r.change_type === 'promotion' ? 'success' : 'info'}>{CHANGE_TYPE_LABEL[r.change_type] || r.change_type}</StatusBadge></td>
                          <td className="text-right text-slate-500">{formatCurrency(r.old_hourly_rate, 'TRY')}</td>
                          <td className="text-right font-semibold">{formatCurrency(r.new_hourly_rate, 'TRY')}</td>
                          <td className={`text-right ${r.delta_pct > 0 ? 'text-emerald-700' : r.delta_pct < 0 ? 'text-rose-700' : ''}`}>
                            {r.delta_pct > 0 ? '+' : ''}{r.delta_pct}%
                          </td>
                          <td className="text-xs text-slate-600 max-w-xs">{r.reason || '—'}</td>
                        </tr>)}
                      {salaryPage.items.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.hen\xFCz_maa\u015F_de\u011Fi\u015Fikli\u011Fi_yok_\u015Fu")}{s.hourly_rate ? formatCurrency(s.hourly_rate, 'TRY') : '140 TRY (default)'}
                        </td></tr>}
                    </tbody>
                  </table>}
                {!salaryPage.loading && salaryPage.total > 0 && <PaginationBar page={salaryPage.page} totalPages={salaryPage.totalPages} total={salaryPage.total} limit={salaryPage.limit} onPageChange={salaryPage.setPage} onLimitChange={salaryPage.setLimit} />}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* EĞİTİM (Task #265 — sertifikadan ayrı operasyonel zorunlu eğitim) */}
        <TabsContent value="trainings" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><BookOpen className="w-4 h-4" />{t("cm.pages_StaffProfile.zorunlu_e\u011Fitimler")}</span>
                <Button size="sm" onClick={openTrainDialog}><Plus className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffProfile.e\u011Fitim_ekle")}</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {trainingsPage.error && <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {trainingsPage.error} <button onClick={trainingsPage.refresh} className="underline ml-2">{t("cm.pages_StaffProfile.tekrar_dene")}</button>
                </div>}
              <div className="mb-3 flex gap-2 text-xs">
                <StatusBadge intent="success">{trainingsPage.meta?.valid || 0}{t("cm.pages_StaffProfile.ge\xE7erli")}</StatusBadge>
                {(trainingsPage.meta?.expired || 0) > 0 && <StatusBadge intent="danger">{trainingsPage.meta?.expired || 0}{t("cm.pages_StaffProfile.tazelenmeli")}</StatusBadge>}
              </div>
              <div className="overflow-x-auto">
                {trainingsPage.loading ? <SkeletonRow cols={5} rows={3} /> : <table className="w-full text-sm">
                    <thead><tr className="text-left text-slate-500 border-b">
                      <th className="py-2">{t("cm.pages_StaffProfile.e\u011Fitim")}</th><th>{t("cm.pages_StaffProfile.t\xFCr")}</th><th>{t("cm.pages_StaffProfile.veren")}</th>
                      <th>{t("cm.pages_StaffProfile.tamamland\u0131")}</th><th>{t("cm.pages_StaffProfile.ge\xE7erlilik")}</th><th className="text-right">{t("cm.pages_StaffProfile.saat")}</th><th></th>
                    </tr></thead>
                    <tbody>
                      {trainingsPage.items.map(t => {
                    const today = new Date().toISOString().slice(0, 10);
                    const expired = t.valid_until && t.valid_until < today;
                    return <tr key={t.id} className="border-t border-slate-100">
                            <td className="py-2 font-medium">{t.title}</td>
                            <td className="text-xs uppercase">{t.training_type}</td>
                            <td>{t.provider || '—'}</td>
                            <td>{t.completed_at}</td>
                            <td>{t.valid_until ? expired ? <StatusBadge intent="danger">{t.valid_until}</StatusBadge> : <StatusBadge intent="success">{t.valid_until}</StatusBadge> : <span className="text-slate-400">{t("cm.pages_StaffProfile.s\xFCresiz")}</span>}</td>
                            <td className="text-right">{t.hours ?? '—'}</td>
                            <td className="text-right">
                              <Button size="sm" variant="ghost" onClick={() => deleteTrain(t)}>
                                <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                              </Button>
                            </td>
                          </tr>;
                  })}
                      {trainingsPage.items.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.hen\xFCz_e\u011Fitim_kayd\u0131_yok_hijyen")}</td></tr>}
                    </tbody>
                  </table>}
                {!trainingsPage.loading && trainingsPage.total > 0 && <PaginationBar page={trainingsPage.page} totalPages={trainingsPage.totalPages} total={trainingsPage.total} limit={trainingsPage.limit} onPageChange={trainingsPage.setPage} onLimitChange={trainingsPage.setLimit} />}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ZİMMET (Task #265 — üniforma/kart/anahtar/cihaz) */}
        <TabsContent value="equipment" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><Package className="w-4 h-4" />{t("cm.pages_StaffProfile.zimmet")}</span>
                <Button size="sm" onClick={openEqDialog}><Plus className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffProfile.zimmet_ata")}</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {equipmentPage.error && <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {equipmentPage.error} <button onClick={equipmentPage.refresh} className="underline ml-2">{t("cm.pages_StaffProfile.tekrar_dene")}</button>
                </div>}
              <div className="mb-3 flex gap-2 text-xs">
                <StatusBadge intent="warning">{equipmentPage.meta?.active || 0}{t("cm.pages_StaffProfile.aktif")}</StatusBadge>
                <StatusBadge intent="success">{equipmentPage.meta?.returned || 0}{t("cm.pages_StaffProfile.iade")}</StatusBadge>
                {(equipmentPage.meta?.lost_or_damaged || 0) > 0 && <StatusBadge intent="danger">{equipmentPage.meta?.lost_or_damaged || 0}{t("cm.pages_StaffProfile.kay\u0131p_hasar")}</StatusBadge>}
              </div>
              <div className="overflow-x-auto">
                {equipmentPage.loading ? <SkeletonRow cols={5} rows={3} /> : <table className="w-full text-sm">
                    <thead><tr className="text-left text-slate-500 border-b">
                      <th className="py-2">{t("cm.pages_StaffProfile.e\u015Fya")}</th><th>{t("cm.pages_StaffProfile.t\xFCr")}</th><th>{t("cm.pages_StaffProfile.seri_no")}</th>
                      <th>{t("cm.pages_StaffProfile.zimmet_tarihi")}</th><th>{t("cm.pages_StaffProfile.i_ade_tarihi")}</th><th>{t("cm.pages_StaffProfile.durum")}</th><th></th>
                    </tr></thead>
                    <tbody>
                      {equipmentPage.items.map(eq => <tr key={eq.id} className="border-t border-slate-100">
                          <td className="py-2 font-medium">{eq.item_label}</td>
                          <td className="text-xs uppercase">{eq.item_type}</td>
                          <td className="text-xs">{eq.serial_no || '—'}</td>
                          <td>{eq.assigned_at}</td>
                          <td>{eq.returned_at || '—'}</td>
                          <td>
                            {eq.status === 'assigned' && <StatusBadge intent="warning">{t("cm.pages_StaffProfile.aktif")}</StatusBadge>}
                            {eq.status === 'returned' && <StatusBadge intent="success">{t("cm.pages_StaffProfile.i_ade_al\u0131nd\u0131")}</StatusBadge>}
                            {eq.status === 'lost' && <StatusBadge intent="danger">{t("cm.pages_StaffProfile.kay\u0131p")}</StatusBadge>}
                            {eq.status === 'damaged' && <StatusBadge intent="danger">{t("cm.pages_StaffProfile.hasarl\u0131")}</StatusBadge>}
                          </td>
                          <td className="text-right whitespace-nowrap">
                            {eq.status === 'assigned' && <Button size="sm" variant="ghost" onClick={() => returnEq(eq)} title={t("cm.pages_StaffProfile.i_ade_al")}>
                                <RotateCcw className="w-3.5 h-3.5 text-emerald-700" />
                              </Button>}
                            <Button size="sm" variant="ghost" onClick={() => deleteEq(eq)}>
                              <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                            </Button>
                          </td>
                        </tr>)}
                      {equipmentPage.items.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.hen\xFCz_zimmet_yok_\xFCniforma_kart")}</td></tr>}
                    </tbody>
                  </table>}
                {!equipmentPage.loading && equipmentPage.total > 0 && <PaginationBar page={equipmentPage.page} totalPages={equipmentPage.totalPages} total={equipmentPage.total} limit={equipmentPage.limit} onPageChange={equipmentPage.setPage} onLimitChange={equipmentPage.setLimit} />}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* UYARI (Task #265 — sözlü/yazılı/son ihtar sicili) */}
        <TabsContent value="warnings" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2"><ShieldAlert className="w-4 h-4" />{t("cm.pages_StaffProfile.disiplin_uyar\u0131lar\u0131")}</span>
                <Button size="sm" onClick={openWarnDialog}><Plus className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffProfile.uyar\u0131_d\xFC\u015F")}</Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {warningsPage.error && <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {warningsPage.error} <button onClick={warningsPage.refresh} className="underline ml-2">{t("cm.pages_StaffProfile.tekrar_dene")}</button>
                </div>}
              <div className="mb-3 flex gap-2 text-xs">
                <StatusBadge intent="info">{warningsPage.meta?.by_type?.verbal || 0}{t("cm.pages_StaffProfile.s\xF6zl\xFC")}</StatusBadge>
                <StatusBadge intent="warning">{warningsPage.meta?.by_type?.written || 0}{t("cm.pages_StaffProfile.yaz\u0131l\u0131")}</StatusBadge>
                {(warningsPage.meta?.by_type?.final || 0) > 0 && <StatusBadge intent="danger">{warningsPage.meta?.by_type?.final || 0}{t("cm.pages_StaffProfile.son_ihtar")}</StatusBadge>}
              </div>
              <div className="overflow-x-auto">
                {warningsPage.loading ? <SkeletonRow cols={5} rows={3} /> : <table className="w-full text-sm">
                    <thead><tr className="text-left text-slate-500 border-b">
                      <th className="py-2">{t("cm.pages_StaffProfile.tarih")}</th><th>{t("cm.pages_StaffProfile.t\xFCr")}</th><th>{t("cm.pages_StaffProfile.\u015Fiddet")}</th>
                      <th>{t("cm.pages_StaffProfile.sebep")}</th><th>{t("cm.pages_StaffProfile.onay")}</th><th></th>
                    </tr></thead>
                    <tbody>
                      {warningsPage.items.map(w => <tr key={w.id} className="border-t border-slate-100">
                          <td className="py-2">{w.issued_at}</td>
                          <td>
                            {w.warning_type === 'verbal' && <StatusBadge intent="info">{t("cm.pages_StaffProfile.s\xF6zl\xFC")}</StatusBadge>}
                            {w.warning_type === 'written' && <StatusBadge intent="warning">{t("cm.pages_StaffProfile.yaz\u0131l\u0131")}</StatusBadge>}
                            {w.warning_type === 'final' && <StatusBadge intent="danger">{t("cm.pages_StaffProfile.son_ihtar")}</StatusBadge>}
                          </td>
                          <td className="text-xs uppercase">{w.severity}</td>
                          <td className="text-xs text-slate-700 max-w-md">{w.reason}</td>
                          <td className="text-xs">
                            {w.acknowledged_at ? <span className="text-emerald-700">✓ {w.acknowledged_at.slice(0, 10)}</span> : <Button size="sm" variant="outline" onClick={() => ackWarn(w)}>
                                  <Check className="w-3 h-3 mr-1" />{t("cm.pages_StaffProfile.onayla")}</Button>}
                          </td>
                          <td className="text-right">
                            <Button size="sm" variant="ghost" onClick={() => deleteWarn(w)}>
                              <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                            </Button>
                          </td>
                        </tr>)}
                      {warningsPage.items.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-500">{t("cm.pages_StaffProfile.disiplin_kayd\u0131_yok_i_\u015F_k_m_25")}</td></tr>}
                    </tbody>
                  </table>}
                {!warningsPage.loading && warningsPage.total > 0 && <PaginationBar page={warningsPage.page} totalPages={warningsPage.totalPages} total={warningsPage.total} limit={warningsPage.limit} onPageChange={warningsPage.setPage} onLimitChange={warningsPage.setLimit} />}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ============ DIALOGS ============ */}

      {/* Sertifika ekle */}
      <Dialog open={certDialog.open} onOpenChange={o => !o && setCertDialog({
      open: false,
      form: null
    })}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("cm.pages_StaffProfile.sertifika_ekle")}</DialogTitle></DialogHeader>
          {certDialog.form && <form onSubmit={submitCert} className="grid gap-3">
              <div><Label>{t("cm.pages_StaffProfile.sertifika_ad\u0131")}</Label><Input required value={certDialog.form.name} onChange={e => setCertDialog({
              ...certDialog,
              form: {
                ...certDialog.form,
                name: e.target.value
              }
            })} placeholder={t("cm.pages_StaffProfile.\xF6rn_yang\u0131n_e\u011Fitimi")} /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>{t("cm.pages_StaffProfile.veren_kurum")}</Label><Input value={certDialog.form.issuer} onChange={e => setCertDialog({
                ...certDialog,
                form: {
                  ...certDialog.form,
                  issuer: e.target.value
                }
              })} /></div>
                <div><Label>{t("cm.pages_StaffProfile.sertifika_no")}</Label><Input value={certDialog.form.certificate_no} onChange={e => setCertDialog({
                ...certDialog,
                form: {
                  ...certDialog.form,
                  certificate_no: e.target.value
                }
              })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>{t("cm.pages_StaffProfile.verili\u015F_tarihi")}</Label><Input required type="date" value={certDialog.form.issue_date} onChange={e => setCertDialog({
                ...certDialog,
                form: {
                  ...certDialog.form,
                  issue_date: e.target.value
                }
              })} /></div>
                <div><Label>{t("cm.pages_StaffProfile.biti\u015F_tarihi")}</Label><Input type="date" value={certDialog.form.expiry_date} onChange={e => setCertDialog({
                ...certDialog,
                form: {
                  ...certDialog.form,
                  expiry_date: e.target.value
                }
              })} /></div>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.dosya_url_opsiyonel")}</Label><Input value={certDialog.form.file_url} onChange={e => setCertDialog({
              ...certDialog,
              form: {
                ...certDialog.form,
                file_url: e.target.value
              }
            })} placeholder={t("cm.pages_StaffProfile.https")} /></div>
              <div><Label>{t("cm.pages_StaffProfile.not")}</Label><Textarea rows={2} value={certDialog.form.notes} onChange={e => setCertDialog({
              ...certDialog,
              form: {
                ...certDialog.form,
                notes: e.target.value
              }
            })} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setCertDialog({
              open: false,
              form: null
            })}>{t("cm.pages_StaffProfile.vazge\xE7")}</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ekle'}</Button>
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>

      {/* Belge yükle */}
      <Dialog open={docDialog.open} onOpenChange={o => !o && setDocDialog({
      open: false,
      file: null,
      doc_type: 'contract',
      label: ''
    })}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("cm.pages_StaffProfile.belge_y\xFCkle")}</DialogTitle></DialogHeader>
          <form onSubmit={submitDoc} className="grid gap-3">
            <div><Label>{t("cm.pages_StaffProfile.dosya_max_5mb_pdf_word_jpeg_pn")}</Label>
              <Input type="file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp" onChange={e => setDocDialog({
              ...docDialog,
              file: e.target.files?.[0] || null
            })} />
              {docDialog.file && <div className="text-xs text-slate-500 mt-1">{docDialog.file.name} • {(docDialog.file.size / 1024).toFixed(1)}{t("cm.pages_StaffProfile.kb")}</div>}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>{t("cm.pages_StaffProfile.t\xFCr")}</Label>
                <select value={docDialog.doc_type} onChange={e => setDocDialog({
                ...docDialog,
                doc_type: e.target.value
              })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                  {Object.entries(DOC_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.etiket")}</Label><Input value={docDialog.label} onChange={e => setDocDialog({
                ...docDialog,
                label: e.target.value
              })} placeholder={t("cm.pages_StaffProfile.opsiyonel_a\xE7\u0131klama")} /></div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDocDialog({
              open: false,
              file: null,
              doc_type: 'contract',
              label: ''
            })}>{t("cm.pages_StaffProfile.vazge\xE7")}</Button>
              <Button type="submit" disabled={saving || !docDialog.file}>{saving ? 'Yükleniyor...' : 'Yükle'}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Maaş değişikliği */}
      <Dialog open={salaryDialog.open} onOpenChange={o => !o && setSalaryDialog({
      open: false,
      form: null
    })}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("cm.pages_StaffProfile.zam_maa\u015F_de\u011Fi\u015Fikli\u011Fi")}</DialogTitle></DialogHeader>
          {salaryDialog.form && <form onSubmit={submitSalary} className="grid gap-3">
              <div className="text-xs text-slate-500">{t("cm.pages_StaffProfile.\u015Fu_anki")}<strong>{s.hourly_rate ? formatCurrency(s.hourly_rate, 'TRY') : '140 TRY (default)'}</strong>{t("cm.pages_StaffProfile._saat")}</div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>{t("cm.pages_StaffProfile.yeni_saatlik")}</Label><Input required type="number" step="0.01" value={salaryDialog.form.new_hourly_rate} onChange={e => setSalaryDialog({
                ...salaryDialog,
                form: {
                  ...salaryDialog.form,
                  new_hourly_rate: e.target.value
                }
              })} /></div>
                <div><Label>{t("cm.pages_StaffProfile.y\xFCr\xFCrl\xFCk")}</Label><Input required type="date" value={salaryDialog.form.effective_date} onChange={e => setSalaryDialog({
                ...salaryDialog,
                form: {
                  ...salaryDialog.form,
                  effective_date: e.target.value
                }
              })} /></div>
              </div>
              <div>
                <Label>{t("cm.pages_StaffProfile.t\xFCr")}</Label>
                <select value={salaryDialog.form.change_type} onChange={e => setSalaryDialog({
              ...salaryDialog,
              form: {
                ...salaryDialog.form,
                change_type: e.target.value
              }
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                  {Object.entries(CHANGE_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.sebep_not")}</Label><Textarea rows={2} value={salaryDialog.form.reason} onChange={e => setSalaryDialog({
              ...salaryDialog,
              form: {
                ...salaryDialog.form,
                reason: e.target.value
              }
            })} placeholder={t("cm.pages_StaffProfile.y\u0131ll\u0131k_enflasyon_zamm\u0131_terfi_v")} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setSalaryDialog({
              open: false,
              form: null
            })}>{t("cm.pages_StaffProfile.vazge\xE7")}</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Kaydet'}</Button>
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>

      {/* İşten ayrılma */}
      <Dialog open={termDialog.open} onOpenChange={o => !o && setTermDialog({
      open: false,
      form: null,
      outstanding: []
    })}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle className="flex items-center gap-2 text-rose-700">
            <UserMinus className="w-5 h-5" />{t("cm.pages_StaffProfile.i_\u015Ften_ayr\u0131lma_i_\u015Flemleri")}</DialogTitle></DialogHeader>
          {termDialog.form && <form onSubmit={submitTerm} className="grid gap-3">
              <div className="rounded bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">{t("cm.pages_StaffProfile.bu_i\u015Flem_personeli_pasifle\u015Ftir")}<strong>{t("cm.pages_StaffProfile.k\u0131dem_tazminat\u0131")}</strong>{t("cm.pages_StaffProfile.hesab\u0131n\u0131_otomatik_yapar_30_g\xFCn")}</div>
              {(termDialog.outstanding || []).length > 0 && <div className="rounded border border-rose-300 bg-rose-50 p-3 text-xs text-rose-900">
                  <div className="font-semibold mb-2">{t("cm.pages_StaffProfile.i_ade_al\u0131nmam\u0131\u015F_zimmet")}{termDialog.outstanding.length})
                  </div>
                  <div className="text-rose-800 mb-2">{t("cm.pages_StaffProfile.a\u015Fa\u011F\u0131daki_kay\u0131tlar_a\xE7\u0131k_\xF6nce_i")}</div>
                  <ul className="divide-y divide-rose-200 mb-2">
                    {termDialog.outstanding.map(eq => <li key={eq.id} className="flex items-center justify-between py-1.5 gap-2">
                        <div className="min-w-0">
                          <div className="font-medium truncate">{eq.item_label}</div>
                          <div className="text-[11px] text-rose-700">
                            {eq.item_type}{eq.serial_no ? ` • ${eq.serial_no}` : ''}{t("cm.pages_StaffProfile._verildi")}{eq.assigned_at}
                          </div>
                        </div>
                        <Button type="button" size="sm" variant="outline" className="border-rose-300 text-rose-700 hover:bg-rose-100" onClick={() => returnEqFromTerm(eq)}>{t("cm.pages_StaffProfile.i_ade_al\u0131nd\u0131_olarak_i\u015Faretle")}</Button>
                      </li>)}
                  </ul>
                </div>}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>{t("cm.pages_StaffProfile.ayr\u0131l\u0131\u015F_sebebi")}</Label>
                  <select required value={termDialog.form.reason} onChange={e => setTermDialog({
                ...termDialog,
                form: {
                  ...termDialog.form,
                  reason: e.target.value
                }
              })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    {Object.entries(TERM_REASON_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div><Label>{t("cm.pages_StaffProfile.son_\xE7al\u0131\u015Fma_g\xFCn\xFC")}</Label><Input required type="date" value={termDialog.form.last_day} onChange={e => setTermDialog({
                ...termDialog,
                form: {
                  ...termDialog.form,
                  last_day: e.target.value
                }
              })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>{t("cm.pages_StaffProfile.i_hbar_s\xFCresi_g\xFCn")}</Label><Input type="number" min="0" value={termDialog.form.notice_period_days} onChange={e => setTermDialog({
                ...termDialog,
                form: {
                  ...termDialog.form,
                  notice_period_days: parseInt(e.target.value || '0', 10)
                }
              })} /></div>
                <div><Label>{t("cm.pages_StaffProfile.k\u0131dem_override_bo\u015F_otomatik")}</Label><Input type="number" step="0.01" value={termDialog.form.severance_override} onChange={e => setTermDialog({
                ...termDialog,
                form: {
                  ...termDialog.form,
                  severance_override: e.target.value
                }
              })} placeholder={t("cm.pages_StaffProfile.otomatik_hesap_kullan")} /></div>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.\xE7\u0131k\u0131\u015F_g\xF6r\xFC\u015Fmesi_notlar\u0131")}</Label><Textarea rows={4} value={termDialog.form.exit_interview_notes} onChange={e => setTermDialog({
              ...termDialog,
              form: {
                ...termDialog.form,
                exit_interview_notes: e.target.value
              }
            })} placeholder={t("cm.pages_StaffProfile.ayr\u0131l\u0131\u015F_sebebi_geri_bildirimi")} /></div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={termDialog.form.eligible_for_rehire} onChange={e => setTermDialog({
              ...termDialog,
              form: {
                ...termDialog.form,
                eligible_for_rehire: e.target.checked
              }
            })} />{t("cm.pages_StaffProfile.tekrar_i\u015Fe_al\u0131nabilir")}</label>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setTermDialog({
              open: false,
              form: null,
              outstanding: []
            })}>{t("cm.pages_StaffProfile.vazge\xE7")}</Button>
                {(termDialog.outstanding || []).length > 0 ? <Button type="button" disabled={saving} onClick={() => submitTerm(null, {
              forceRelease: true
            })} className="bg-rose-600 hover:bg-rose-700 text-white">
                    {saving ? 'İşleniyor...' : 'Zimmetli olsa da kapat'}
                  </Button> : <Button type="submit" disabled={saving} className="bg-rose-600 hover:bg-rose-700 text-white">
                    {saving ? 'İşleniyor...' : 'Ayrılışı Kaydet'}
                  </Button>}
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>

      {/* Hedef check-in */}
      <Dialog open={checkinDialog.open} onOpenChange={o => !o && setCheckinDialog({
      open: false,
      reviewId: null,
      form: null
    })}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("cm.pages_StaffProfile.hedef_check_in_ekle")}</DialogTitle></DialogHeader>
          {checkinDialog.form && <form onSubmit={submitCheckin} className="grid gap-3">
              <div><Label>{t("cm.pages_StaffProfile.hedef")}</Label><Textarea required rows={2} value={checkinDialog.form.goal_text} onChange={e => setCheckinDialog({
              ...checkinDialog,
              form: {
                ...checkinDialog.form,
                goal_text: e.target.value
              }
            })} placeholder={t("cm.pages_StaffProfile.\xF6rn_q1_de_upsell_oran\u0131n\u0131_15_e")} /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>{t("cm.pages_StaffProfile.i_lerleme")}</Label><Input type="number" min="0" max="100" value={checkinDialog.form.progress_pct} onChange={e => setCheckinDialog({
                ...checkinDialog,
                form: {
                  ...checkinDialog.form,
                  progress_pct: e.target.value
                }
              })} /></div>
                <div>
                  <Label>{t("cm.pages_StaffProfile.durum")}</Label>
                  <select value={checkinDialog.form.status} onChange={e => setCheckinDialog({
                ...checkinDialog,
                form: {
                  ...checkinDialog.form,
                  status: e.target.value
                }
              })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="on_track">{t("cm.pages_StaffProfile.yolunda")}</option>
                    <option value="at_risk">{t("cm.pages_StaffProfile.risk_alt\u0131nda")}</option>
                    <option value="blocked">{t("cm.pages_StaffProfile.bloke")}</option>
                    <option value="done">{t("cm.pages_StaffProfile.tamamland\u0131")}</option>
                  </select>
                </div>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.tarih")}</Label><Input type="date" value={checkinDialog.form.checkin_date} onChange={e => setCheckinDialog({
              ...checkinDialog,
              form: {
                ...checkinDialog.form,
                checkin_date: e.target.value
              }
            })} /></div>
              <div><Label>{t("cm.pages_StaffProfile.not")}</Label><Textarea rows={2} value={checkinDialog.form.note} onChange={e => setCheckinDialog({
              ...checkinDialog,
              form: {
                ...checkinDialog.form,
                note: e.target.value
              }
            })} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setCheckinDialog({
              open: false,
              reviewId: null,
              form: null
            })}>{t("cm.pages_StaffProfile.vazge\xE7")}</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ekle'}</Button>
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>

      {/* Task #265: Zimmet ata */}
      <Dialog open={eqDialog.open} onOpenChange={o => !o && setEqDialog({
      open: false,
      form: null
    })}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("cm.pages_StaffProfile.zimmet_ata")}</DialogTitle></DialogHeader>
          {eqDialog.form && <form onSubmit={submitEq} className="grid gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>{t("cm.pages_StaffProfile.t\xFCr")}</Label>
                  <select value={eqDialog.form.item_type} onChange={e => setEqDialog({
                ...eqDialog,
                form: {
                  ...eqDialog.form,
                  item_type: e.target.value
                }
              })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="uniform">{t("cm.pages_StaffProfile.\xFCniforma")}</option>
                    <option value="card">{t("cm.pages_StaffProfile.kart")}</option>
                    <option value="key">{t("cm.pages_StaffProfile.anahtar")}</option>
                    <option value="radio">{t("cm.pages_StaffProfile.telsiz")}</option>
                    <option value="laptop">{t("cm.pages_StaffProfile.diz\xFCst\xFC")}</option>
                    <option value="phone">{t("cm.pages_StaffProfile.telefon")}</option>
                    <option value="tablet">{t("cm.pages_StaffProfile.tablet")}</option>
                    <option value="tool">{t("cm.pages_StaffProfile.alet")}</option>
                    <option value="vehicle">{t("cm.pages_StaffProfile.ara\xE7")}</option>
                    <option value="other">{t("cm.pages_StaffProfile.di\u011Fer")}</option>
                  </select>
                </div>
                <div><Label>{t("cm.pages_StaffProfile.zimmet_tarihi")}</Label><Input type="date" value={eqDialog.form.assigned_at} onChange={e => setEqDialog({
                ...eqDialog,
                form: {
                  ...eqDialog.form,
                  assigned_at: e.target.value
                }
              })} /></div>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.e\u015Fya_ad\u0131")}</Label><Input required value={eqDialog.form.item_label} onChange={e => setEqDialog({
              ...eqDialog,
              form: {
                ...eqDialog.form,
                item_label: e.target.value
              }
            })} placeholder={t("cm.pages_StaffProfile.\xF6rn_resepsiyon_\xFCniformas\u0131_xl")} /></div>
              <div><Label>{t("cm.pages_StaffProfile.seri_no")}</Label><Input value={eqDialog.form.serial_no} onChange={e => setEqDialog({
              ...eqDialog,
              form: {
                ...eqDialog.form,
                serial_no: e.target.value
              }
            })} /></div>
              <div><Label>{t("cm.pages_StaffProfile.not")}</Label><Textarea rows={2} value={eqDialog.form.notes} onChange={e => setEqDialog({
              ...eqDialog,
              form: {
                ...eqDialog.form,
                notes: e.target.value
              }
            })} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setEqDialog({
              open: false,
              form: null
            })}>{t("cm.pages_StaffProfile.vazge\xE7")}</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ata'}</Button>
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>

      {/* Task #265: Uyarı düş */}
      <Dialog open={warnDialog.open} onOpenChange={o => !o && setWarnDialog({
      open: false,
      form: null
    })}>
        <DialogContent>
          <DialogHeader><DialogTitle className="text-amber-700">{t("cm.pages_StaffProfile.disiplin_uyar\u0131s\u0131")}</DialogTitle></DialogHeader>
          {warnDialog.form && <form onSubmit={submitWarn} className="grid gap-3">
              <div className="rounded bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">{t("cm.pages_StaffProfile.i_\u015F_k_m_25_ii_referans\u0131yla_dis")}</div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <Label>{t("cm.pages_StaffProfile.t\xFCr")}</Label>
                  <select value={warnDialog.form.warning_type} onChange={e => setWarnDialog({
                ...warnDialog,
                form: {
                  ...warnDialog.form,
                  warning_type: e.target.value
                }
              })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="verbal">{t("cm.pages_StaffProfile.s\xF6zl\xFC")}</option>
                    <option value="written">{t("cm.pages_StaffProfile.yaz\u0131l\u0131")}</option>
                    <option value="final">{t("cm.pages_StaffProfile.son_ihtar")}</option>
                  </select>
                </div>
                <div>
                  <Label>{t("cm.pages_StaffProfile.\u015Fiddet")}</Label>
                  <select value={warnDialog.form.severity} onChange={e => setWarnDialog({
                ...warnDialog,
                form: {
                  ...warnDialog.form,
                  severity: e.target.value
                }
              })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="low">{t("cm.pages_StaffProfile.d\xFC\u015F\xFCk")}</option>
                    <option value="medium">{t("cm.pages_StaffProfile.orta")}</option>
                    <option value="high">{t("cm.pages_StaffProfile.y\xFCksek")}</option>
                  </select>
                </div>
                <div><Label>{t("cm.pages_StaffProfile.tarih")}</Label><Input type="date" value={warnDialog.form.issued_at} onChange={e => setWarnDialog({
                ...warnDialog,
                form: {
                  ...warnDialog.form,
                  issued_at: e.target.value
                }
              })} /></div>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.sebep")}</Label><Textarea required rows={4} value={warnDialog.form.reason} onChange={e => setWarnDialog({
              ...warnDialog,
              form: {
                ...warnDialog.form,
                reason: e.target.value
              }
            })} placeholder={t("cm.pages_StaffProfile.tekrar_eden_ge\xE7_kalma_g\xF6rev_ih")} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setWarnDialog({
              open: false,
              form: null
            })}>{t("cm.pages_StaffProfile.vazge\xE7")}</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Uyarı Kaydet'}</Button>
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>

      {/* Task #265: Eğitim ekle */}
      <Dialog open={trainDialog.open} onOpenChange={o => !o && setTrainDialog({
      open: false,
      form: null
    })}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("cm.pages_StaffProfile.e\u011Fitim_ekle")}</DialogTitle></DialogHeader>
          {trainDialog.form && <form onSubmit={submitTrain} className="grid gap-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>{t("cm.pages_StaffProfile.t\xFCr")}</Label>
                  <select value={trainDialog.form.training_type} onChange={e => setTrainDialog({
                ...trainDialog,
                form: {
                  ...trainDialog.form,
                  training_type: e.target.value
                }
              })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="hygiene">{t("cm.pages_StaffProfile.hijyen")}</option>
                    <option value="safety">{t("cm.pages_StaffProfile.i_\u015F_g\xFCvenli\u011Fi")}</option>
                    <option value="orientation">{t("cm.pages_StaffProfile.oryantasyon")}</option>
                    <option value="technical">{t("cm.pages_StaffProfile.teknik")}</option>
                    <option value="language">{t("cm.pages_StaffProfile.dil")}</option>
                    <option value="leadership">{t("cm.pages_StaffProfile.liderlik")}</option>
                    <option value="compliance">{t("cm.pages_StaffProfile.compliance")}</option>
                    <option value="other">{t("cm.pages_StaffProfile.di\u011Fer")}</option>
                  </select>
                </div>
                <div><Label>{t("cm.pages_StaffProfile.veren_kurum")}</Label><Input value={trainDialog.form.provider} onChange={e => setTrainDialog({
                ...trainDialog,
                form: {
                  ...trainDialog.form,
                  provider: e.target.value
                }
              })} /></div>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.e\u011Fitim_ad\u0131")}</Label><Input required value={trainDialog.form.title} onChange={e => setTrainDialog({
              ...trainDialog,
              form: {
                ...trainDialog.form,
                title: e.target.value
              }
            })} placeholder={t("cm.pages_StaffProfile.\xF6rn_y\u0131ll\u0131k_hijyen_tazeleme")} /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>{t("cm.pages_StaffProfile.tamamlanma")}</Label><Input required type="date" value={trainDialog.form.completed_at} onChange={e => setTrainDialog({
                ...trainDialog,
                form: {
                  ...trainDialog.form,
                  completed_at: e.target.value
                }
              })} /></div>
                <div><Label>{t("cm.pages_StaffProfile.ge\xE7erlilik_biti\u015F")}</Label><Input type="date" value={trainDialog.form.valid_until} onChange={e => setTrainDialog({
                ...trainDialog,
                form: {
                  ...trainDialog.form,
                  valid_until: e.target.value
                }
              })} /></div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>{t("cm.pages_StaffProfile.saat")}</Label><Input type="number" min="0" step="0.5" value={trainDialog.form.hours} onChange={e => setTrainDialog({
                ...trainDialog,
                form: {
                  ...trainDialog.form,
                  hours: e.target.value
                }
              })} /></div>
                <div><Label>{t("cm.pages_StaffProfile.skor_0_100")}</Label><Input type="number" min="0" max="100" value={trainDialog.form.score} onChange={e => setTrainDialog({
                ...trainDialog,
                form: {
                  ...trainDialog.form,
                  score: e.target.value
                }
              })} /></div>
              </div>
              <div><Label>{t("cm.pages_StaffProfile.not")}</Label><Textarea rows={2} value={trainDialog.form.notes} onChange={e => setTrainDialog({
              ...trainDialog,
              form: {
                ...trainDialog.form,
                notes: e.target.value
              }
            })} /></div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setTrainDialog({
              open: false,
              form: null
            })}>{t("cm.pages_StaffProfile.vazge\xE7")}</Button>
                <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor...' : 'Ekle'}</Button>
              </DialogFooter>
            </form>}
        </DialogContent>
      </Dialog>
    </div>;
};
export default StaffProfile;