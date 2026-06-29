import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Clock, Calendar, DollarSign, Briefcase, UserPlus, Download,
  Users, FileSpreadsheet, RefreshCw, Plus, CheckCircle2, XCircle,
  TrendingUp, ExternalLink, FileDown, Award, Info, AlertCircle,
  Bell, FileText, ClipboardList, Send, ThumbsUp, ThumbsDown,
  Timer, Check, X, Package, GraduationCap,
} from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { promptDialog, confirmDialog } from '@/lib/dialogs';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { formatCurrency } from '@/lib/currency';
import { useTranslation } from 'react-i18next';
import PaginationBar from '@/components/PaginationBar';
import SkeletonRow from '@/components/SkeletonRow';
import { useHRPagination } from '@/hooks/useHRPagination';

const LEAVE_TYPE_LABEL = {
  annual: 'Yıllık İzin',
  sick: 'Hastalık',
  maternity: 'Doğum',
  paternity: 'Babalık',
  unpaid: 'Ücretsiz',
  bereavement: 'Vefat',
  excused: 'Mazeret',
};

const STATUS_INTENT = {
  pending: 'warning',
  dept_approved: 'info',
  approved: 'success',
  hr_approved: 'success',
  rejected: 'danger',
  active: 'success',
  closed: 'neutral',
};

const STATUS_LABEL = {
  pending: 'Beklemede',
  dept_approved: 'Dept Onaylı (HR Bekliyor)',
  approved: 'Onaylandı',
  hr_approved: 'Onaylandı',
  rejected: 'Reddedildi',
  active: 'Aktif',
  closed: 'Kapalı',
};

const todayMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

const HRComplete = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('attendance');
  const [refreshing, setRefreshing] = useState(false);

  // Staff (dropdown data only)
  const [staffDropdown, setStaffDropdown] = useState([]);
  const [selectedStaffId, setSelectedStaffId] = useState('');

  // Attendance
  const [attendanceSummary, setAttendanceSummary] = useState(null);
  const [attendanceRecords, setAttendanceRecords] = useState([]);
  const [recordsRange, setRecordsRange] = useState({ start: '', end: '' });

  // Payroll v2 (Task #264) — dry-run + draft + locked + revisions
  const [exportMonth, setExportMonth] = useState(todayMonth);
  const [exporting, setExporting] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [payrollPreview, setPayrollPreview] = useState(null);
  const [payrollRuns, setPayrollRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runRevisions, setRunRevisions] = useState([]);
  const [savingDraft, setSavingDraft] = useState(false);
  const [revising, setRevising] = useState(false);
  const [loadingRun, setLoadingRun] = useState(false);

  // Pagination hooks
  const staffPage = useHRPagination('/hr/staff', {}, { enabled: activeTab === 'leave' || activeTab === 'performance' || activeTab === 'attendance' || activeTab === 'payroll' });
  const leavePage = useHRPagination('/hr/leave-requests', {}, { enabled: activeTab === 'leave' });
  const performancePage = useHRPagination('/hr/performance', {}, { enabled: activeTab === 'performance' });

  // Leave Dropdown & Form
  const [leaveCounts, setLeaveCounts] = useState({ pending: 0, approved: 0, rejected: 0 });
  const [leaveForm, setLeaveForm] = useState({
    staff_id: '', leave_type: 'annual', start_date: '', end_date: '', reason: '',
  });
  const [creatingLeave, setCreatingLeave] = useState(false);

  // Performance Form
  const [perfAvg, setPerfAvg] = useState(0);
  const [perfTemplates, setPerfTemplates] = useState([]);
  const [perfForm, setPerfForm] = useState({
    staff_id: '', period: '', overall_score: '', strengths: '', improvement_areas: '', goals: '',
    template_id: '', competency_scores: {},
  });
  const [creatingPerf, setCreatingPerf] = useState(false);

  // Overtime requests (Mesai Onayı)
  const [overtimeItems, setOvertimeItems] = useState([]);
  const [overtimeCounts, setOvertimeCounts] = useState({ pending: 0, approved: 0, rejected: 0 });

  // Kıdem tazminatı tavanı (tenant ayarı)
  const [severanceCap, setSeveranceCap] = useState(null);
  const [savingSeverance, setSavingSeverance] = useState(false);

  // Bordro vergi/kesinti oranları (tenant ayarı)
  const [taxRates, setTaxRates] = useState(null);
  const [taxRatesForm, setTaxRatesForm] = useState(null);
  const [savingTaxRates, setSavingTaxRates] = useState(false);

  // Recruitment / Personel Talebi
  const [jobItems, setJobItems] = useState([]);
  const [jobForm, setJobForm] = useState({
    title: '', department: '', employment_type: 'full_time',
    location: '', salary_range: '', description: '',
    headcount_needed: 1, urgency: 'normal', justification: '', needed_by: '',
  });
  const [creatingJob, setCreatingJob] = useState(false);
  const [applicantsDialog, setApplicantsDialog] = useState({ open: false, job: null, list: [], counts: {} });
  const [applicantForm, setApplicantForm] = useState({ name: '', email: '', phone: '', notes: '', cv_url: '' });
  const [savingApplicant, setSavingApplicant] = useState(false);

  // Leave balances cache (per staff_id)
  const [leaveBalances, setLeaveBalances] = useState({});
  const [balanceLoading, setBalanceLoading] = useState(false);

  // Compliance KPI (Task #269): outstanding equipment + expiring trainings.
  const [outstandingEquipTotal, setOutstandingEquipTotal] = useState(0);
  const [expiringTrainTotal, setExpiringTrainTotal] = useState(0);

  // Loaders
  const loadStaffDropdown = useCallback(async () => {
    try {
      const res = await axios.get('/hr/staff', { params: { limit: 500, source: 'hr' } });
      const list = res.data?.staff || res.data?.items || [];
      setStaffDropdown(list);
      if (!selectedStaffId && list.length > 0) {
        setSelectedStaffId(list[0].id);
        setLeaveForm((f) => ({ ...f, staff_id: list[0].id }));
        setPerfForm((f) => ({ ...f, staff_id: list[0].id }));
      }
    } catch (e) {
      console.error('Dropdown staff listesi yüklenemedi', e);
      toast.error('Personel listesi yüklenemedi');
    }
  }, [selectedStaffId]);

  const loadAttendance = useCallback(async () => {
    try {
      const [summaryRes, recordsRes] = await Promise.all([
        axios.get('/hr/attendance/summary'),
        axios.get('/hr/attendance/records', { params: { limit: 100 } }),
      ]);
      setAttendanceSummary(summaryRes.data);
      setAttendanceRecords(recordsRes.data?.records || []);
      setRecordsRange(recordsRes.data?.range || {});
    } catch (e) {
      console.error('Attendance yüklenemedi', e);
      toast.error('Devam verileri yüklenemedi');
    }
  }, []);

  const loadPerfTemplates = useCallback(async () => {
    try {
      const res = await axios.get('/hr/performance-templates');
      setPerfTemplates(res.data?.items || []);
    } catch (e) {
      console.error('Şablonlar yüklenemedi', e);
    }
  }, []);

  const loadSeveranceCap = useCallback(async () => {
    try {
      const res = await axios.get('/hr/settings/severance-cap');
      setSeveranceCap(res.data || null);
    } catch { /* yetki yoksa sessiz geç */ }
  }, []);

  const loadTaxRates = useCallback(async () => {
    try {
      const res = await axios.get('/hr/settings/payroll-tax-rates');
      setTaxRates(res.data || null);
      setTaxRatesForm(res.data?.rates ? { ...res.data.rates } : null);
    } catch { /* yetki yoksa sessiz geç */ }
  }, []);

  const loadCompliance = useCallback(async () => {
    try {
      const [eqRes, trRes] = await Promise.all([
        axios.get('/hr/equipment/outstanding').catch(() => ({ data: { items: [], total: 0 } })),
        axios.get('/hr/trainings/expiring', { params: { days_ahead: 60 } })
          .catch(() => ({ data: { items: [], total: 0 } })),
      ]);
      setOutstandingEquipTotal(eqRes.data?.total ?? (eqRes.data?.items || []).length);
      setExpiringTrainTotal(trRes.data?.total ?? (trRes.data?.items || []).length);
    } catch { /* yetki yoksa sessiz geç */ }
  }, []);

  const updateSeveranceCap = async () => {
    const current = severanceCap?.daily_cap || '';
    const input = await promptDialog({
      message: 'Yeni günlük kıdem tazminatı tavanı (TL):',
      defaultValue: String(current),
    });
    if (input === null) return;
    const val = parseFloat(String(input).replace(',', '.'));
    if (!Number.isFinite(val) || val <= 0) {
      toast.error('Geçerli bir tutar girin');
      return;
    }
    try {
      setSavingSeverance(true);
      await axios.put('/hr/settings/severance-cap', { daily_cap: val });
      toast.success('Kıdem tavanı güncellendi');
      loadSeveranceCap();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Güncellenemedi');
    } finally {
      setSavingSeverance(false);
    }
  };

  const updateTaxRates = async () => {
    if (!taxRatesForm) return;
    const keys = ['sgk_employee', 'unemployment', 'income_tax', 'stamp_tax'];
    const payload = {};
    for (const k of keys) {
      const val = parseFloat(String(taxRatesForm[k] ?? '').replace(',', '.'));
      if (!Number.isFinite(val) || val < 0 || val > 100) {
        toast.error('Oranlar 0 ile 100 arasında geçerli yüzde değerleri olmalı');
        return;
      }
      payload[k] = val;
    }
    try {
      setSavingTaxRates(true);
      await axios.put('/hr/settings/payroll-tax-rates', payload);
      toast.success('Vergi oranları güncellendi');
      loadTaxRates();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Güncellenemedi');
    } finally {
      setSavingTaxRates(false);
    }
  };

  const loadOvertimeRequests = useCallback(async () => {
    try {
      const res = await axios.get('/hr/overtime-requests');
      setOvertimeItems(res.data?.items || []);
      setOvertimeCounts(res.data?.counts || { pending: 0, approved: 0, rejected: 0 });
    } catch (e) {
      console.error('Mesai talepleri yüklenemedi', e);
    }
  }, []);

  const decideOvertime = async (req, action) => {
    try {
      let note = '';
      if (action === 'reject') {
        note = await promptDialog({
          message: 'Red sebebi (ZORUNLU):', defaultValue: '',
        });
        if (note === null) return;
        if (!String(note || '').trim()) {
          toast.error('Red sebebi zorunludur');
          return;
        }
      } else if (action === 'dept_approve') {
        note = await promptDialog({
          message: 'Departman onayı notu (opsiyonel):', defaultValue: '',
        });
        if (note === null) return;
      }
      await axios.post(`/hr/overtime-request/${req.id}/decision`, { action, note });
      const msg = action === 'reject' ? 'Mesai reddedildi'
        : action === 'dept_approve' ? 'Departman onayı verildi (HR final onayı bekleniyor)'
        : 'Mesai onaylandı (bordroya hazır)';
      toast.success(msg);
      loadOvertimeRequests();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem başarısız');
    }
  };

  const onTemplateChange = async (tplId) => {
    // Daha önce girilmiş skor varsa kullanıcıya kayıp uyarısı göster.
    const hasScores = Object.values(perfForm.competency_scores || {})
      .some((v) => typeof v === 'number' && v > 0);
    if (hasScores) {
      const ok = await confirmDialog({
        title: 'Şablonu değiştir?',
        description: 'Mevcut yetkinlik puanlarınız sıfırlanacak. Devam edilsin mi?',
        confirmText: 'Devam et', cancelText: 'Vazgeç',
      });
      if (!ok) return;
    }
    const tpl = perfTemplates.find((t) => t.id === tplId);
    const competency_scores = {};
    if (tpl?.competencies) {
      tpl.competencies.forEach((c) => { competency_scores[c.name] = 0; });
    }
    setPerfForm((f) => ({ ...f, template_id: tplId, competency_scores }));
  };

  const setCompetencyScore = (name, val) => {
    setPerfForm((f) => ({
      ...f,
      competency_scores: { ...f.competency_scores, [name]: parseFloat(val) || 0 },
    }));
  };

  const loadJobs = useCallback(async () => {
    try {
      const res = await axios.get('/hr/job-postings');
      setJobItems(res.data?.items || []);
    } catch (e) {
      console.error('Personel talepleri yüklenemedi', e);
    }
  }, []);

  const loadLeaveBalances = useCallback(async (staffIds) => {
    if (!staffIds?.length) return;
    setBalanceLoading(true);
    try {
      const results = await Promise.all(
        staffIds.map((sid) =>
          axios.get(`/hr/leave-balance/${sid}`).then((r) => [sid, r.data]).catch(() => [sid, null])
        )
      );
      const map = {};
      results.forEach(([sid, data]) => { if (data) map[sid] = data; });
      setLeaveBalances(map);
    } finally {
      setBalanceLoading(false);
    }
  }, []);

  const openApplicants = async (job) => {
    try {
      const res = await axios.get(`/hr/job-postings/${job.id}/applicants`);
      setApplicantsDialog({
        open: true, job,
        list: res.data?.items || [],
        counts: res.data?.counts || {},
      });
      setApplicantForm({ name: '', email: '', phone: '', notes: '', cv_url: '' });
    } catch (err) {
      toast.error('Adaylar yüklenemedi');
    }
  };

  const refreshApplicants = async () => {
    if (!applicantsDialog.job) return;
    try {
      const res = await axios.get(`/hr/job-postings/${applicantsDialog.job.id}/applicants`);
      setApplicantsDialog((d) => ({ ...d, list: res.data?.items || [], counts: res.data?.counts || {} }));
    } catch { /* ignore */ }
  };

  const submitApplicant = async (e) => {
    e.preventDefault();
    if (!applicantForm.name.trim()) { toast.error('Aday adı zorunlu'); return; }
    try {
      setSavingApplicant(true);
      await axios.post(`/hr/job-postings/${applicantsDialog.job.id}/applicants`, applicantForm);
      toast.success('Aday eklendi');
      setApplicantForm({ name: '', email: '', phone: '', notes: '', cv_url: '' });
      refreshApplicants();
      loadJobs();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Aday eklenemedi');
    } finally {
      setSavingApplicant(false);
    }
  };

  const setApplicantStatus = async (applicantId, status) => {
    try {
      await axios.post(`/hr/applicants/${applicantId}/status`, { status });
      toast.success('Durum güncellendi');
      refreshApplicants();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Güncellenemedi');
    }
  };

  const decideJob = async (jobId, action) => {
    const isApprove = action === 'approve';
    const note = await promptDialog({
      title: isApprove ? 'Talebi Onayla' : 'Talebi Reddet',
      message: isApprove
        ? 'İsteğe bağlı: onay notu (örn. bütçe kodu, başlama tarihi).'
        : 'Lütfen ret gerekçesini kısaca yazın (talep sahibine iletilir).',
      placeholder: isApprove ? 'Onaylandı — pozisyon yayına alınabilir.' : 'Bütçe yetersiz / pozisyon doldu vb.',
      confirmText: isApprove ? 'Onayla' : 'Reddet',
      cancelText: 'Vazgeç',
    });
    if (note === null) return;
    try {
      await axios.post(`/hr/job-posting/${jobId}/${action}`, { note: note || undefined });
      toast.success(isApprove ? 'Talep onaylandı' : 'Talep reddedildi');
      loadJobs();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem başarısız');
    }
  };

  const loadAll = useCallback(async () => {
    setRefreshing(true);
    try {
      // Sadece en temel (herkese lazım olan veya KPI için gereken) verileri önden yükle
      await Promise.all([loadStaffDropdown(), loadCompliance()]);
    } finally {
      setRefreshing(false);
    }
  }, [loadStaffDropdown, loadCompliance]);

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Tab-based data loading (Lazy fan-out reduction)
  useEffect(() => {
    switch (activeTab) {
      case 'attendance':
        if (!attendanceSummary) loadAttendance();
        if (!overtimeCounts) loadOvertimeRequests();
        break;
      case 'leave':
        if (staffPage.items.length > 0) loadLeaveBalances(staffPage.items.map((s) => s.id));
        break;
      case 'performance':
        if (perfTemplates.length === 0) loadPerfTemplates();
        break;
      case 'recruitment':
        if (jobItems.length === 0) loadJobs();
        break;
      case 'payroll':
        if (!taxRates) loadTaxRates();
        if (!severanceCap) loadSeveranceCap();
        // and optionally load current month payroll preview
        break;
      default:
        break;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, staffPage.items]);

  // Attendance actions
  const clockIn = async () => {
    if (!selectedStaffId) {
      toast.error('Personel seçin');
      return;
    }
    try {
      const res = await axios.post('/hr/clock-in', { staff_id: selectedStaffId });
      if (res.data?.success) {
        toast.success('Giriş kaydedildi');
      } else {
        toast.warning(res.data?.message || 'Açık giriş kaydı zaten var');
      }
      loadAttendance();
    } catch (error) {
      const msg = error.response?.data?.detail || 'Giriş kaydedilemedi';
      toast.error(msg);
    }
  };

  const clockOut = async () => {
    if (!selectedStaffId) {
      toast.error('Personel seçin');
      return;
    }
    try {
      const res = await axios.post('/hr/clock-out', { staff_id: selectedStaffId });
      if (res.data?.success) {
        toast.success(`Çıkış kaydedildi (${res.data.hours_worked} saat)`);
      } else {
        toast.warning(res.data?.message || 'Açık giriş kaydı bulunamadı');
      }
      loadAttendance();
    } catch (error) {
      const msg = error.response?.data?.detail || 'Çıkış kaydedilemedi';
      toast.error(msg);
    }
  };

  // Payroll actions
  const handlePayrollExport = async () => {
    try {
      setExporting(true);
      // Streaming endpoint: tarayıcı 2MB data: URL limitini atlar
      const res = await axios.get('/hr/payroll/export/csv', {
        params: { month: exportMonth },
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `payroll_${exportMonth}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success('Bordro CSV indirildi');
    } catch (error) {
      const msg = error.response?.status === 403
        ? 'Bordro indirme yetkiniz yok'
        : 'Bordro indirilemedi';
      toast.error(msg);
    } finally {
      setExporting(false);
    }
  };

  const loadPayrollRuns = useCallback(async (month) => {
    try {
      const res = await axios.get('/hr/payroll/runs', { params: { month } });
      setPayrollRuns(res.data?.items || []);
    } catch (error) {
      if (error.response?.status !== 403) {
        toast.error('Bordro kayıt listesi alınamadı');
      }
      setPayrollRuns([]);
    }
  }, []);

  const handlePayrollPreview = async () => {
    try {
      // Task #264: yeni endpoint daima dry-run + runs özetiyle döner.
      const res = await axios.get(`/hr/payroll/${exportMonth}`);
      setPayrollPreview(res.data);
      await loadPayrollRuns(exportMonth);
      // Üst kayıt değişebileceği için seçimi sıfırla
      setSelectedRun(null);
      setRunRevisions([]);
    } catch (error) {
      const msg = error.response?.status === 403
        ? 'Bordro görüntüleme yetkiniz yok'
        : 'Önizleme alınamadı';
      toast.error(msg);
    }
  };

  const handlePayrollSaveDraft = async () => {
    const ok = await confirmDialog({
      title: 'Bordroyu Taslak Olarak Kaydet',
      message: (
        `${exportMonth} ayı için TASLAK bordro kaydedilecek. Bu işlem ` +
        'muhasebe etkisi yaratmaz; kilitleme ayrı bir adımdır. Devam edilsin mi?'
      ),
      confirmText: 'Taslağı Kaydet',
      cancelText: 'Vazgeç',
    });
    if (!ok) return;
    try {
      setSavingDraft(true);
      const res = await axios.post(`/hr/payroll/${exportMonth}/save`, { extras: [] });
      if (res.data?.success) {
        toast.success(
          res.data.is_idempotent_update
            ? 'Mevcut taslak güncellendi'
            : 'Taslak bordro oluşturuldu',
        );
        await loadPayrollRuns(exportMonth);
      }
    } catch (error) {
      const msg = error.response?.status === 409
        ? (error.response?.data?.detail || 'Bu ay için kilitli bordro var')
        : (error.response?.data?.detail || 'Taslak kaydedilemedi');
      toast.error(msg);
    } finally {
      setSavingDraft(false);
    }
  };

  const loadRunDetail = async (runId) => {
    try {
      setLoadingRun(true);
      const [detail, revs] = await Promise.all([
        axios.get(`/hr/payroll/runs/${runId}`),
        axios.get(`/hr/payroll/runs/${runId}/revisions`),
      ]);
      setSelectedRun(detail.data);
      setRunRevisions(revs.data?.items || []);
    } catch (error) {
      toast.error('Bordro çalışması alınamadı');
    } finally {
      setLoadingRun(false);
    }
  };

  const handlePayrollFinalize = async (runId) => {
    const ok = await confirmDialog({
      title: 'Bordroyu Kilitle',
      message: (
        'Kilitlenen bordro DEĞİŞTİRİLEMEZ. Sonraki düzeltmeler ancak ' +
        'revizyon açarak yeni bir taslak üzerinden yapılabilir. Onaylıyor musunuz?'
      ),
      confirmText: 'Evet, Kilitle',
      cancelText: 'Vazgeç',
    });
    if (!ok) return;
    try {
      setFinalizing(true);
      const res = await axios.post(`/hr/payroll/${runId}/finalize`);
      if (res.data?.success) {
        toast.success('Bordro kilitlendi');
        await Promise.all([loadPayrollRuns(exportMonth), loadRunDetail(runId)]);
      }
    } catch (error) {
      const msg = error.response?.status === 403
        ? 'Kilitleme yetkiniz yok (HR Admin / Finance gerekli)'
        : (error.response?.data?.detail || 'Bordro kilitlenemedi');
      toast.error(msg);
    } finally {
      setFinalizing(false);
    }
  };

  const handleRevisionOpen = async (runId) => {
    const reason = await promptDialog({
      title: 'Revizyon Aç',
      message: 'Kilitli bordro değişmez. Bu işlem yeni bir TASLAK açacaktır. Sebep:',
      placeholder: 'Örn: Onaylı mesai eklendi / avans düzeltildi.',
      confirmText: 'Revizyon Aç',
      cancelText: 'Vazgeç',
    });
    if (reason === null) return;
    if (!reason.trim()) {
      toast.error('Revizyon sebebi zorunludur');
      return;
    }
    try {
      setRevising(true);
      const res = await axios.post(`/hr/payroll/${runId}/revisions`, {
        reason: reason.trim(),
        extras: [],
      });
      if (res.data?.success) {
        toast.success('Revizyon açıldı — yeni taslak hazır');
        await loadPayrollRuns(exportMonth);
        await loadRunDetail(res.data.new_run_id);
      }
    } catch (error) {
      const msg = error.response?.data?.detail || 'Revizyon açılamadı';
      toast.error(msg);
    } finally {
      setRevising(false);
    }
  };

  const handleRunXlsx = async (runId) => {
    try {
      const res = await axios.get(`/hr/payroll/runs/${runId}/export.xlsx`, {
        responseType: 'blob',
      });
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `payroll_${runId}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error('XLSX indirilemedi');
    }
  };

  // Leave actions
  const submitLeave = async (e) => {
    e.preventDefault();
    if (!leaveForm.staff_id || !leaveForm.start_date || !leaveForm.end_date) {
      toast.error('Personel, başlangıç ve bitiş tarihi zorunlu');
      return;
    }
    try {
      setCreatingLeave(true);
      await axios.post('/hr/leave-request', leaveForm);
      toast.success('İzin talebi oluşturuldu');
      setLeaveForm({ ...leaveForm, start_date: '', end_date: '', reason: '' });
      leavePage.refresh();
    } catch (error) {
      const msg = error.response?.data?.detail || 'İzin talebi oluşturulamadı';
      toast.error(typeof msg === 'string' ? msg : 'Hata');
    } finally {
      setCreatingLeave(false);
    }
  };

  const decideLeave = async (id, decision) => {
    try {
      let note = '';
      if (decision === 'reject') {
        note = await promptDialog({
          message: 'Red sebebi (ZORUNLU):', defaultValue: '',
        });
        if (note === null) return;
        if (!String(note || '').trim()) {
          toast.error('Red sebebi zorunludur');
          return;
        }
      } else if (decision === 'dept_approve') {
        note = await promptDialog({
          message: 'Departman onayı notu (opsiyonel):', defaultValue: '',
        });
        if (note === null) return;
      }
      const res = await axios.post(`/hr/leave-request/${id}/decision`, { decision, note });
      const created = res.data?.on_leave_shifts_created || 0;
      const msg = decision === 'reject' ? 'İzin reddedildi'
        : decision === 'dept_approve' ? 'Departman onayı verildi (HR final onayı bekleniyor)'
        : `İzin onaylandı${created ? ` • ${created} gün vardiyaya 'izinli' işlendi` : ''}`;
      toast.success(msg);
      leavePage.refresh();
    } catch (error) {
      const msg = error.response?.status === 403
        ? 'Onay yetkiniz yok'
        : (error.response?.data?.detail || 'İşlem başarısız');
      toast.error(typeof msg === 'string' ? msg : 'İşlem başarısız');
    }
  };

  // Performance actions
  const submitPerformance = async (e) => {
    e.preventDefault();
    if (!perfForm.staff_id || !perfForm.overall_score) {
      toast.error('Personel ve puan zorunlu');
      return;
    }
    try {
      setCreatingPerf(true);
      await axios.post('/hr/performance', {
        ...perfForm,
        overall_score: parseFloat(perfForm.overall_score),
        competency_scores: perfForm.competency_scores || {},
      });
      toast.success('Performans değerlendirmesi kaydedildi');
      setPerfForm({ ...perfForm, period: '', overall_score: '', strengths: '', improvement_areas: '', goals: '', competency_scores: {} });
      performancePage.refresh();
    } catch (error) {
      const msg = error.response?.data?.detail || 'Kaydedilemedi';
      toast.error(typeof msg === 'string' ? msg : 'Hata');
    } finally {
      setCreatingPerf(false);
    }
  };

  // Recruitment actions
  const submitJob = async (e) => {
    e.preventDefault();
    if (!jobForm.title || !jobForm.department) {
      toast.error('Başlık ve departman zorunlu');
      return;
    }
    try {
      setCreatingJob(true);
      await axios.post('/hr/job-posting', jobForm);
      toast.success('İş ilanı yayınlandı');
      setJobForm({ ...jobForm, title: '', location: '', salary_range: '', description: '' });
      loadJobs();
    } catch (error) {
      const msg = error.response?.data?.detail || 'Yayınlanamadı';
      toast.error(typeof msg === 'string' ? msg : 'Hata');
    } finally {
      setCreatingJob(false);
    }
  };

  const closeJob = async (id) => {
    try {
      await axios.post(`/hr/job-posting/${id}/close`);
      toast.success('İlan kapatıldı');
      loadJobs();
    } catch {
      toast.error('Kapatılamadı');
    }
  };

  // Derived
  const attendanceMetrics = attendanceSummary?.metrics || {
    staff_count: 0,
    total_active_staff: 0,
    total_hours: 0,
    avg_hours_per_staff: 0,
    avg_hours_per_active_staff: 0,
  };

  const topPerformers = useMemo(() => {
    if (!attendanceSummary?.summary) return [];
    return [...attendanceSummary.summary]
      .sort((a, b) => b.total_hours - a.total_hours)
      .slice(0, 3);
  }, [attendanceSummary]);

  const selectedStaffName = useMemo(
    () => staffDropdown.find((s) => s.id === selectedStaffId)?.name || '',
    [staffDropdown, selectedStaffId],
  );

  const fmtCurrency = (v) => formatCurrency(v ?? 0, 'TRY');
  const fmtTime = (iso) => {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }); }
    catch { return '—'; }
  };

  const headerActions = (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => navigate('/staff-management')}
        data-testid="btn-staff-management"
      >
        <Users className="w-4 h-4 mr-1.5" />
        {t('cm.pages_HRComplete.personel_yonetimi')}
        <ExternalLink className="w-3 h-3 ml-1" />
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={loadAll}
        disabled={refreshing}
        data-testid="btn-refresh-hr"
      >
        <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />
        {t('cm.pages_HRComplete.yenile')}
      </Button>
    </>
  );

  return (
    <div className="p-2">
      <PageHeader
        icon={Users}
        title={t('cm.pages_HRComplete.ik_yonetim_paketi')}
        subtitle={t('cm.pages_HRComplete.devam_takibi_bordro_izin_performans_ve_i')}
        actions={headerActions}
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="attendance" data-testid="tab-attendance">
            <Clock className="w-4 h-4 mr-2" />Devam
          </TabsTrigger>
          <TabsTrigger value="payroll" data-testid="tab-payroll">
            <DollarSign className="w-4 h-4 mr-2" />Bordro
          </TabsTrigger>
          <TabsTrigger value="leave" data-testid="tab-leave">
            <Calendar className="w-4 h-4 mr-2" />{t('cm.pages_HRComplete.izin')}
          </TabsTrigger>
          <TabsTrigger value="performance" data-testid="tab-performance">
            <Briefcase className="w-4 h-4 mr-2" />Performans
          </TabsTrigger>
          <TabsTrigger value="overtime" data-testid="tab-overtime">
            <Timer className="w-4 h-4 mr-1.5" />
            Mesai Onayı
            {overtimeCounts.pending > 0 && (
              <span className="ml-1.5 px-1.5 rounded-full bg-amber-500 text-white text-[10px]">{overtimeCounts.pending}</span>
            )}
          </TabsTrigger>
          <TabsTrigger value="recruitment" data-testid="tab-recruitment">
            <ClipboardList className="w-4 h-4 mr-2" />Personel Talebi
          </TabsTrigger>
        </TabsList>

        {/* === ATTENDANCE === */}
        <TabsContent value="attendance" className="mt-4">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
              <KpiCard intent="info" icon={Users} label={t('cm.pages_HRComplete.toplam_calisan')}
                value={attendanceMetrics.total_active_staff ?? attendanceMetrics.staff_count}
                sub={`aktif personel${attendanceMetrics.staff_count ? ` • ${attendanceMetrics.staff_count} devam kayıtlı` : ''}`} />
              <KpiCard intent="success" icon={Clock} label={t('cm.pages_HRComplete.toplam_saat')}
                value={(attendanceMetrics.total_hours || 0).toFixed(1)}
                sub="son 30 gün" />
              <KpiCard intent="warning" icon={TrendingUp} label={t('cm.pages_HRComplete.ortalama_saat')}
                value={(attendanceMetrics.avg_hours_per_active_staff || attendanceMetrics.avg_hours_per_staff || 0).toFixed(1)}
                sub="personel başı (son 30 gün)" />
              <KpiCard intent={outstandingEquipTotal > 0 ? 'warning' : 'neutral'} icon={Package}
                label="Açık Zimmet" value={outstandingEquipTotal} sub="iade alınmamış" />
              <KpiCard intent={expiringTrainTotal > 0 ? 'warning' : 'neutral'} icon={GraduationCap}
                label="Süresi Dolan Eğitim" value={expiringTrainTotal} sub="önümüzdeki 60 gün" />
            </div>

            <Card>
              <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <CardTitle>{t('cm.pages_HRComplete.giris_cikis_kaydi')}</CardTitle>
                <div className="flex flex-wrap gap-2 items-center">
                  <Label className="text-xs">Personel</Label>
                  <select
                    value={selectedStaffId}
                    onChange={(e) => setSelectedStaffId(e.target.value)}
                    className="rounded-md border border-input px-3 py-1.5 text-sm min-w-[200px]"
                    data-testid="select-staff"
                  >
                    {staffDropdown.length === 0 && <option value="">— Personel yok —</option>}
                    {staffDropdown.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} {s.department ? `(${s.department})` : ''}
                      </option>
                    ))}
                  </select>
                  <Button size="sm" onClick={clockIn} disabled={!selectedStaffId} data-testid="btn-clock-in">
                    <Clock className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.giris_yap')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={clockOut} disabled={!selectedStaffId} data-testid="btn-clock-out">
                    <Clock className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.cikis_yap')}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {staffDropdown.length === 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                    {t('cm.pages_HRComplete.personel_listesi_bos_personel_eklemek_ic')}
                    <Button variant="link" size="sm" className="px-1.5" onClick={() => navigate('/staff-management')}>
                      {t('cm.pages_HRComplete.personel_yonetimi_28ee4')}
                    </Button>
                    {t('cm.pages_HRComplete.sayfasini_kullanin')}
                  </div>
                )}
                <div className="rounded-md border bg-slate-50 p-3 text-xs text-slate-600">
                  {t('cm.pages_HRComplete.izlenen_aralik')} {recordsRange.start || '—'} → {recordsRange.end || '—'}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th>Departman</th>
                        <th>{t('cm.pages_HRComplete.gun')}</th>
                        <th>{t('cm.pages_HRComplete.giris')}</th>
                        <th>{t('cm.pages_HRComplete.cikis')}</th>
                        <th className="text-right">{t('cm.pages_HRComplete.saat')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attendanceRecords.map((record) => (
                        <tr key={record.id || record.clock_in} className="border-t border-slate-100">
                          <td className="py-2 font-medium">{record.staff_name || record.staff_id}</td>
                          <td className="capitalize text-slate-600">{record.department || '—'}</td>
                          <td className="text-slate-600">{record.date}</td>
                          <td>{fmtTime(record.clock_in)}</td>
                          <td>{record.clock_out ? fmtTime(record.clock_out) : '—'}</td>
                          <td className="text-right">{record.total_hours?.toFixed(2) ?? '—'}</td>
                        </tr>
                      ))}
                      {attendanceRecords.length === 0 && (
                        <tr><td colSpan={6} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.kayit_bulunamadi')}</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Award className="w-4 h-4" />{t('cm.pages_HRComplete.en_yuksek_saat_top_3')}</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {topPerformers.map((s) => (
                  <div key={s.staff_id} className="flex items-center justify-between rounded border border-slate-100 bg-white px-3 py-2 text-sm">
                    <div>
                      <p className="font-semibold text-slate-800">{s.staff_name}</p>
                      <p className="text-xs text-slate-500 capitalize">{s.department}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-400">{t('cm.pages_HRComplete.toplam_saat_f69c5')}</p>
                      <p className="text-lg font-bold text-slate-900">{s.total_hours?.toFixed(1)}</p>
                    </div>
                  </div>
                ))}
                {topPerformers.length === 0 && (
                  <div className="text-center py-6 space-y-2">
                    <p className="text-sm text-slate-500">Yeterli devam verisi yok</p>
                    <Button variant="outline" size="sm" onClick={() => navigate('/staff-management')}>
                      <UserPlus className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.personel_ekle')}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === PAYROLL === */}
        <TabsContent value="payroll" className="mt-4">
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2"><DollarSign className="w-4 h-4" />{t('cm.pages_HRComplete.bordro_islemleri')}</CardTitle>
                  <p className="text-xs text-slate-500 mt-1">
                    {t('cm.pages_HRComplete.devam_kayitlarindan_otomatik_hesap_tr_is')}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Label className="text-xs">{t('cm.pages_HRComplete.ay')}</Label>
                  <Input
                    type="month"
                    value={exportMonth}
                    onChange={(e) => setExportMonth(e.target.value)}
                    className="w-40"
                    data-testid="input-payroll-month"
                  />
                  <Button variant="outline" size="sm" onClick={handlePayrollPreview} data-testid="btn-payroll-preview">
                    <RefreshCw className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.onizle')}
                  </Button>
                  <Button size="sm" onClick={handlePayrollSaveDraft} disabled={savingDraft} data-testid="btn-payroll-save-draft" className="bg-slate-900 text-white hover:bg-slate-800">
                    <FileText className="w-4 h-4 mr-1.5" />
                    {savingDraft ? 'Kaydediliyor...' : 'Taslak Kaydet'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handlePayrollExport} disabled={exporting} data-testid="btn-payroll-csv">
                    <FileDown className="w-4 h-4 mr-1.5" />
                    {exporting ? 'İndiriliyor...' : 'CSV İndir'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Task #264: Dry-run + draft/locked/revisions akış rehberi */}
                <div className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm">
                  <div className="flex items-start gap-2">
                    <Info className="w-4 h-4 mt-0.5 text-sky-600 shrink-0" />
                    <div className="space-y-2">
                      <p className="font-medium text-sky-900">Bordro yaşam döngüsü (önbordro / muhasebe ihracı)</p>
                      <ol className="list-decimal pl-5 space-y-1 text-slate-700 text-xs">
                        <li><strong>Önizle</strong>: Devam kayıtlarından dry-run hesap. Hiçbir muhasebe etkisi YOKTUR.</li>
                        <li><strong>Taslak Kaydet</strong>: Bu ayın hesabı `payroll_runs` koleksiyonuna <em>draft</em> olarak kaydedilir; aynı gün tekrar bastığınızda mevcut taslak güncellenir.</li>
                        <li><strong>Kilitle</strong>: Taslak satır bazında dondurulur (<em>locked</em>, immutable). Yalnızca HR Admin / Finance / Süper Admin.</li>
                        <li><strong>Revizyon Aç</strong>: Kilitli bordro değişmez; yeni bir taslak ile düzeltme akışı başlar (audit zinciri korunur).</li>
                        <li><strong>CSV / XLSX</strong>: Muhasebe ihracı; XLSX kalem (avans, prim, yemek, yol, kesinti, mesai) detayı içerir.</li>
                      </ol>
                      <p className="text-xs text-amber-700">
                        <AlertCircle className="w-3 h-3 inline mr-1" />
                        {(() => {
                          const r = taxRates?.rates || { sgk_employee: 14, unemployment: 1, income_tax: 15, stamp_tax: 0.759 };
                          const fmt = (n) => Number(n).toLocaleString('tr-TR', { maximumFractionDigits: 3 });
                          return `Kesintiler: %${fmt(r.sgk_employee)} SGK + %${fmt(r.unemployment)} işsizlik + %${fmt(r.income_tax)} gelir vergisi (matrah − SGK) + %${fmt(r.stamp_tax)} damga.`;
                        })()}
                        {' '}Asgari ücret muafiyeti / AGİ / özel kesintiler için muhasebenizle doğrulayın.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Runs listesi */}
                {payrollRuns.length > 0 && (
                  <div className="rounded-md border bg-white">
                    <div className="px-3 py-2 border-b bg-slate-50 text-xs font-semibold text-slate-700">
                      {exportMonth} ayı bordro çalışmaları ({payrollRuns.length})
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-slate-500 border-b text-xs">
                            <th className="py-2 px-3">Durum</th>
                            <th className="px-3">Run ID</th>
                            <th className="px-3 text-right">Personel</th>
                            <th className="px-3 text-right">Brüt</th>
                            <th className="px-3 text-right">Net</th>
                            <th className="px-3">Güncellendi</th>
                            <th className="px-3 text-right">İşlem</th>
                          </tr>
                        </thead>
                        <tbody>
                          {payrollRuns.map((r) => (
                            <tr key={r.id} className={`border-t border-slate-100 ${selectedRun?.id === r.id ? 'bg-slate-50' : ''}`}>
                              <td className="py-2 px-3">
                                <StatusBadge intent={r.status === 'locked' ? 'success' : 'warning'}>
                                  {r.status === 'locked' ? 'Kilitli' : 'Taslak'}
                                </StatusBadge>
                              </td>
                              <td className="px-3 font-mono text-xs text-slate-600">{r.id.slice(0, 8)}…</td>
                              <td className="px-3 text-right">{r.summary?.staff_count ?? '—'}</td>
                              <td className="px-3 text-right">{r.summary ? fmtCurrency(r.summary.total_gross) : '—'}</td>
                              <td className="px-3 text-right">{r.summary ? fmtCurrency(r.summary.total_net) : '—'}</td>
                              <td className="px-3 text-xs text-slate-500">{(r.updated_at || r.created_at || '').slice(0, 16).replace('T', ' ')}</td>
                              <td className="px-3 text-right">
                                <Button size="sm" variant="outline" onClick={() => loadRunDetail(r.id)} data-testid={`btn-run-detail-${r.id.slice(0, 8)}`}>
                                  Aç
                                </Button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Seçili run detayı */}
                {selectedRun && (
                  <div className="rounded-md border bg-white">
                    <div className="px-3 py-2 border-b bg-slate-50 flex flex-wrap items-center justify-between gap-2">
                      <div className="text-xs">
                        <span className="font-semibold text-slate-700">Run </span>
                        <span className="font-mono">{selectedRun.id.slice(0, 8)}…</span>
                        <span className="ml-2">
                          <StatusBadge intent={selectedRun.status === 'locked' ? 'success' : 'warning'}>
                            {selectedRun.status === 'locked' ? 'Kilitli' : 'Taslak'}
                          </StatusBadge>
                        </span>
                        {selectedRun.parent_run_id && (
                          <span className="ml-2 text-slate-500">
                            (revizyon — üst: <span className="font-mono">{selectedRun.parent_run_id.slice(0, 8)}…</span>)
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {selectedRun.status === 'draft' && (
                          <Button size="sm" onClick={() => handlePayrollFinalize(selectedRun.id)} disabled={finalizing}
                            className="bg-slate-900 text-white hover:bg-slate-800" data-testid="btn-payroll-finalize">
                            <CheckCircle2 className="w-4 h-4 mr-1.5" />
                            {finalizing ? 'Kilitleniyor...' : 'Kilitle'}
                          </Button>
                        )}
                        {selectedRun.status === 'locked' && (
                          <Button size="sm" variant="outline" onClick={() => handleRevisionOpen(selectedRun.id)} disabled={revising} data-testid="btn-payroll-revision">
                            <RefreshCw className="w-4 h-4 mr-1.5" />
                            {revising ? 'Açılıyor...' : 'Revizyon Aç'}
                          </Button>
                        )}
                        <Button size="sm" variant="outline" onClick={() => handleRunXlsx(selectedRun.id)} data-testid="btn-payroll-xlsx">
                          <FileDown className="w-4 h-4 mr-1.5" />XLSX İndir
                        </Button>
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-slate-500 border-b text-xs">
                            <th className="py-2 px-3">Personel</th>
                            <th className="px-3">Departman</th>
                            <th className="px-3 text-right">Saat</th>
                            <th className="px-3 text-right">Mesai</th>
                            <th className="px-3 text-right">Brüt</th>
                            <th className="px-3 text-right">Ek Kazanç</th>
                            <th className="px-3 text-right">Ek Kesinti</th>
                            <th className="px-3 text-right">Net</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(selectedRun.rows || []).map((row) => (
                            <tr key={row.staff_id} className="border-t border-slate-100">
                              <td className="py-2 px-3 font-medium">{row.staff_name}</td>
                              <td className="px-3 capitalize text-slate-600">{row.department}</td>
                              <td className="px-3 text-right">{Number(row.total_hours || 0).toFixed(1)}</td>
                              <td className="px-3 text-right text-amber-700">{Number(row.overtime_hours || 0).toFixed(1)}</td>
                              <td className="px-3 text-right">{fmtCurrency(row.gross_pay)}</td>
                              <td className="px-3 text-right text-emerald-700">{fmtCurrency(row.extra_earnings || 0)}</td>
                              <td className="px-3 text-right text-rose-700">{fmtCurrency(row.extra_deductions || 0)}</td>
                              <td className="px-3 text-right font-semibold">{fmtCurrency(row.net_salary)}</td>
                            </tr>
                          ))}
                          {(!selectedRun.rows || selectedRun.rows.length === 0) && (
                            <tr><td colSpan={8} className="py-6 text-center text-slate-500">Bu run'da satır yok</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                    {runRevisions.length > 0 && (
                      <div className="border-t bg-slate-50 px-3 py-2 text-xs">
                        <div className="font-semibold text-slate-700 mb-1">Revizyon geçmişi ({runRevisions.length})</div>
                        <ul className="space-y-1">
                          {runRevisions.map((rev) => (
                            <li key={rev.id} className="flex flex-wrap items-center gap-2 text-slate-600">
                              <span className="text-slate-400">{(rev.created_at || '').slice(0, 16).replace('T', ' ')}</span>
                              <span className="font-mono">{rev.new_run_id?.slice(0, 8)}…</span>
                              <span>—</span>
                              <span>{rev.reason}</span>
                              <span className="text-slate-400">
                                (brüt {fmtCurrency(rev.diff?.gross_before)} → {fmtCurrency(rev.diff?.gross_after)})
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {payrollPreview ? (
                  <>
                    <div className="grid gap-3 md:grid-cols-3">
                      <KpiCard intent="info" icon={Users} label="Personel" value={payrollPreview.staff_count} />
                      <KpiCard intent="success" icon={DollarSign} label={t('cm.pages_HRComplete.toplam_brut')}
                        value={fmtCurrency(payrollPreview.total_gross_pay)} />
                      <KpiCard intent="warning" icon={DollarSign} label={t('cm.pages_HRComplete.toplam_net')}
                        value={fmtCurrency(payrollPreview.total_net_pay)} />
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-slate-500 border-b">
                            <th className="py-2">Personel</th>
                            <th>Departman</th>
                            <th className="text-right">{t('cm.pages_HRComplete.saat_2460e')}</th>
                            <th className="text-right">Mesai</th>
                            <th className="text-right">{t('cm.pages_HRComplete.brut')}</th>
                            <th className="text-right">{t('cm.pages_HRComplete.sgk_issiz')}</th>
                            <th className="text-right">Vergi</th>
                            <th className="text-right">Net</th>
                          </tr>
                        </thead>
                        <tbody>
                          {payrollPreview.payroll?.map((row) => (
                            <tr key={row.staff_id} className="border-t border-slate-100">
                              <td className="py-2 font-medium">{row.staff_name}</td>
                              <td className="capitalize text-slate-600">{row.department}</td>
                              <td className="text-right">{row.total_hours.toFixed(1)}</td>
                              <td className="text-right text-amber-700">{row.overtime_hours.toFixed(1)}</td>
                              <td className="text-right">{fmtCurrency(row.gross_pay)}</td>
                              <td className="text-right text-slate-600">{fmtCurrency(row.sgk_employee + row.unemployment)}</td>
                              <td className="text-right text-slate-600">{fmtCurrency(row.income_tax + row.stamp_tax)}</td>
                              <td className="text-right font-semibold">{fmtCurrency(row.net_salary)}</td>
                            </tr>
                          ))}
                          {(!payrollPreview.payroll || payrollPreview.payroll.length === 0) && (
                            <tr><td colSpan={8} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.bu_ayda_devam_kaydi_yok')}</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <div className="rounded-md border bg-slate-50 p-4 text-sm text-slate-600">
                    {t('cm.pages_HRComplete.bordro_onizlemek_icin_ay_secin_ve')} <strong>{t('cm.pages_HRComplete.onizle_d9316')}</strong>{t('cm.pages_HRComplete.ye_basin_kalici_kayit_icin')} <strong>{t('cm.pages_HRComplete.bordroyu_kaydet')}</strong>{t('cm.pages_HRComplete.disa_aktarmak_icin')} <strong>{t('cm.pages_HRComplete.csv_indir')}</strong>.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === LEAVE === */}
        <TabsContent value="leave" className="mt-4">
          <div className="space-y-4">
            {/* Akış açıklaması */}
            <div className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm flex items-start gap-2">
              <Bell className="w-4 h-4 mt-0.5 text-sky-600 shrink-0" />
              <div className="text-slate-700 text-xs space-y-1">
                <p><strong>İzin akışı:</strong> Talep oluşturulduğunda HR yöneticilerine (admin/supervisor/finance rolleri) <strong>in-app bildirim</strong> düşer (bildirim zilinde görünür). Karar verildiğinde talep sahibine geri bildirim gider.</p>
                <p>Yıllık izin hakkı varsayılan <strong>14 gün</strong> (İş K. m.53). Personel kartında ya da <code>POST /hr/leave-balance</code> ile özelleştirilebilir. Onaylı talepler bakiyeden düşülür.</p>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <KpiCard intent="warning" label={t('cm.pages_HRComplete.beklemede')} value={leaveCounts.pending} />
              <KpiCard intent="success" label="Onaylanan" value={leaveCounts.approved} />
              <KpiCard intent="danger" label="Reddedilen" value={leaveCounts.rejected} />
            </div>

            {/* İzin Bakiyeleri */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2"><Calendar className="w-4 h-4" />Personel İzin Bakiyesi ({new Date().getFullYear()})</CardTitle>
                <Button size="sm" variant="outline" onClick={() => loadLeaveBalances(staffPage.items.map((s) => s.id))} disabled={balanceLoading}>
                  <RefreshCw className={`w-3.5 h-3.5 mr-1 ${balanceLoading ? 'animate-spin' : ''}`} />Yenile
                </Button>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th className="text-right">Yıllık Hak</th>
                        <th className="text-right">Devir</th>
                        <th className="text-right">Kullanılan</th>
                        <th className="text-right">Kalan</th>
                        <th className="text-right">Hastalık (kalan/hak)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {staffPage.items.map((s) => {
                        const b = leaveBalances[s.id];
                        if (!b) return (
                          <tr key={s.id} className="border-t border-slate-100">
                            <td className="py-2">{s.name}</td>
                            <td colSpan={5} className="text-slate-400 text-xs text-center">Yükleniyor...</td>
                          </tr>
                        );
                        const remaining = b.annual?.remaining ?? 0;
                        const intent = remaining <= 2 ? 'danger' : remaining <= 5 ? 'warning' : 'success';
                        return (
                          <tr key={s.id} className="border-t border-slate-100">
                            <td className="py-2 font-medium">{s.name}</td>
                            <td className="text-right">{b.annual?.entitlement}</td>
                            <td className="text-right text-slate-500">{b.annual?.carry_over || 0}</td>
                            <td className="text-right">{b.annual?.used}</td>
                            <td className="text-right">
                              <StatusBadge intent={intent}>{remaining} gün</StatusBadge>
                            </td>
                            <td className="text-right text-slate-600">{b.sick?.remaining}/{b.sick?.entitlement}</td>
                          </tr>
                        );
                      })}
                      {staffPage.items.length === 0 && (
                        <tr><td colSpan={6} className="py-6 text-center text-slate-500">Personel yok</td></tr>
                      )}
                    </tbody>
                  </table>
                {!staffPage.loading && staffPage.total > 0 && (
                  <PaginationBar
                    page={staffPage.page}
                    totalPages={staffPage.totalPages}
                    total={staffPage.total}
                    limit={staffPage.limit}
                    onPageChange={staffPage.setPage}
                    onLimitChange={staffPage.setLimit}
                  />
                )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Plus className="w-4 h-4" />{t('cm.pages_HRComplete.yeni_izin_talebi')}</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={submitLeave} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <Label className="text-xs">Personel</Label>
                    <select
                      value={leaveForm.staff_id}
                      onChange={(e) => setLeaveForm({ ...leaveForm, staff_id: e.target.value })}
                      className="w-full rounded-md border border-input px-3 py-2 text-sm"
                      data-testid="select-leave-staff"
                    >
                      <option value="">{t('cm.pages_HRComplete.secin')}</option>
                      {staffDropdown.map((s) => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.izin_turu')}</Label>
                    <select
                      value={leaveForm.leave_type}
                      onChange={(e) => setLeaveForm({ ...leaveForm, leave_type: e.target.value })}
                      className="w-full rounded-md border border-input px-3 py-2 text-sm"
                    >
                      {Object.entries(LEAVE_TYPE_LABEL).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-xs">{t('cm.pages_HRComplete.baslangic')}</Label>
                      <Input type="date" value={leaveForm.start_date}
                        onChange={(e) => setLeaveForm({ ...leaveForm, start_date: e.target.value })} />
                    </div>
                    <div>
                      <Label className="text-xs">{t('cm.pages_HRComplete.bitis')}</Label>
                      <Input type="date" value={leaveForm.end_date}
                        onChange={(e) => setLeaveForm({ ...leaveForm, end_date: e.target.value })} />
                    </div>
                  </div>
                  <div className="md:col-span-2 lg:col-span-3">
                    <Label className="text-xs">{t('cm.pages_HRComplete.aciklama')}</Label>
                    <Textarea
                      rows={2}
                      value={leaveForm.reason}
                      onChange={(e) => setLeaveForm({ ...leaveForm, reason: e.target.value })}
                      placeholder={t('cm.pages_HRComplete.istege_bagli')}
                    />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 flex justify-end">
                    <Button type="submit" disabled={creatingLeave} data-testid="btn-submit-leave">
                      <Plus className="w-4 h-4 mr-1.5" />
                      {creatingLeave ? 'Oluşturuluyor...' : 'Talep Oluştur'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>{t('cm.pages_HRComplete.izin_talepleri')}</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th>{t('cm.pages_HRComplete.tur')}</th>
                        <th>{t('cm.pages_HRComplete.baslangic_677c8')}</th>
                        <th>{t('cm.pages_HRComplete.bitis_7cd21')}</th>
                        <th className="text-right">{t('cm.pages_HRComplete.gun_18b2f')}</th>
                        <th>{t('cm.pages_HRComplete.durum')}</th>
                        <th className="text-right">{t('cm.pages_HRComplete.islem')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leavePage.loading ? (
                        <SkeletonRow cols={7} rows={3} />
                      ) : (
                        <>
                          {leavePage.items.map((item) => (
                            <tr key={item.id} className="border-t border-slate-100">
                              <td className="py-2 font-medium">{item.staff_name}</td>
                          <td>{LEAVE_TYPE_LABEL[item.leave_type] || item.leave_type}</td>
                          <td>{item.start_date}</td>
                          <td>{item.end_date}</td>
                          <td className="text-right">{item.total_days}</td>
                          <td>
                            <StatusBadge intent={STATUS_INTENT[item.status]}>{STATUS_LABEL[item.status] || item.status}</StatusBadge>
                          </td>
                          <td className="text-right">
                            {item.status === 'pending' && (
                              <div className="flex justify-end gap-1 flex-wrap">
                                <Button size="sm" onClick={() => decideLeave(item.id, 'dept_approve')} data-testid={`btn-dept-approve-${item.id}`}>
                                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" />Dept Onay
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideLeave(item.id, 'reject')} data-testid={`btn-reject-${item.id}`}>
                                  <XCircle className="w-3.5 h-3.5 mr-1" />{t('cm.pages_HRComplete.reddet')}
                                </Button>
                              </div>
                            )}
                            {item.status === 'dept_approved' && (
                              <div className="flex justify-end gap-1 flex-wrap">
                                <Button size="sm" onClick={() => decideLeave(item.id, 'approve')} data-testid={`btn-hr-final-${item.id}`}>
                                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" />HR Final Onay
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideLeave(item.id, 'reject')} data-testid={`btn-hr-reject-${item.id}`}>
                                  <XCircle className="w-3.5 h-3.5 mr-1" />Reddet
                                </Button>
                              </div>
                            )}
                          </td>
                        </tr>
                          ))}
                          {leavePage.items.length === 0 && (
                            <tr><td colSpan={7} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.henuz_izin_talebi_yok')}</td></tr>
                          )}
                        </>
                      )}
                    </tbody>
                  </table>
                {!leavePage.loading && leavePage.total > 0 && (
                  <PaginationBar
                    page={leavePage.page}
                    totalPages={leavePage.totalPages}
                    total={leavePage.total}
                    limit={leavePage.limit}
                    onPageChange={leavePage.setPage}
                    onLimitChange={leavePage.setLimit}
                  />
                )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === PERFORMANCE === */}
        <TabsContent value="performance" className="mt-4">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <KpiCard intent="info" icon={Award} label={t('cm.pages_HRComplete.toplam_degerlendirme')} value={performancePage.total || 0} />
              <KpiCard intent="success" icon={TrendingUp} label="Ortalama Puan" value={(perfAvg || 0).toFixed(2)} sub="0–10 ölçek" />
            </div>

            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Plus className="w-4 h-4" />{t('cm.pages_HRComplete.yeni_degerlendirme')}</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={submitPerformance} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <Label className="text-xs">Personel</Label>
                    <select
                      value={perfForm.staff_id}
                      onChange={(e) => setPerfForm({ ...perfForm, staff_id: e.target.value })}
                      className="w-full rounded-md border border-input px-3 py-2 text-sm"
                    >
                      <option value="">{t('cm.pages_HRComplete.secin_4f7bd')}</option>
                      {staffList.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">Şablon (opsiyonel)</Label>
                    <select
                      value={perfForm.template_id}
                      onChange={(e) => onTemplateChange(e.target.value)}
                      className="w-full rounded-md border border-input px-3 py-2 text-sm"
                    >
                      <option value="">— Şablon yok —</option>
                      {perfTemplates.map((tpl) => (
                        <option key={tpl.id} value={tpl.id}>{tpl.name} ({tpl.competencies?.length || 0} yetkinlik)</option>
                      ))}
                    </select>
                  </div>
                  {perfForm.template_id && Object.keys(perfForm.competency_scores || {}).length > 0 && (
                    <div className="md:col-span-2 lg:col-span-3 rounded border border-slate-200 bg-slate-50 p-3">
                      <div className="text-xs font-semibold text-slate-700 mb-2">Yetkinlik Puanları (0–10)</div>
                      <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                        {Object.entries(perfForm.competency_scores).map(([name, score]) => (
                          <div key={name}>
                            <Label className="text-xs">{name}</Label>
                            <Input type="number" min="0" max="10" step="0.1" value={score}
                              onChange={(e) => setCompetencyScore(name, e.target.value)} />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.donem')}</Label>
                    <Input value={perfForm.period} onChange={(e) => setPerfForm({ ...perfForm, period: e.target.value })} placeholder="2026 Q1" />
                  </div>
                  <div>
                    <Label className="text-xs">Genel Puan (0–10)</Label>
                    <Input type="number" min="0" max="10" step="0.1"
                      value={perfForm.overall_score}
                      onChange={(e) => setPerfForm({ ...perfForm, overall_score: e.target.value })} />
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.guclu_yonler')}</Label>
                    <Textarea rows={2} value={perfForm.strengths}
                      onChange={(e) => setPerfForm({ ...perfForm, strengths: e.target.value })} />
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.gelisim_alanlari')}</Label>
                    <Textarea rows={2} value={perfForm.improvement_areas}
                      onChange={(e) => setPerfForm({ ...perfForm, improvement_areas: e.target.value })} />
                  </div>
                  <div>
                    <Label className="text-xs">Hedefler</Label>
                    <Textarea rows={2} value={perfForm.goals}
                      onChange={(e) => setPerfForm({ ...perfForm, goals: e.target.value })} />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 flex justify-end">
                    <Button type="submit" disabled={creatingPerf}>
                      <Plus className="w-4 h-4 mr-1.5" />
                      {creatingPerf ? 'Kaydediliyor...' : 'Değerlendirme Kaydet'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>{t('cm.pages_HRComplete.gecmis_degerlendirmeler')}</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th>{t('cm.pages_HRComplete.donem_625f5')}</th>
                        <th>{t('cm.pages_HRComplete.tarih')}</th>
                        <th className="text-right">Puan</th>
                        <th>{t('cm.pages_HRComplete.ozet')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {performancePage.loading ? (
                        <SkeletonRow cols={5} rows={3} />
                      ) : (
                        <>
                          {performancePage.items.map((item) => (
                            <tr key={item.id} className="border-t border-slate-100 align-top">
                              <td className="py-2 font-medium">{item.staff_name}</td>
                          <td>{item.period || '—'}</td>
                          <td>{(item.reviewed_at || '').slice(0, 10)}</td>
                          <td className="text-right font-semibold">{item.overall_score}</td>
                          <td className="text-slate-600 max-w-md truncate">{item.strengths || item.goals || '—'}</td>
                        </tr>
                          ))}
                          {performancePage.items.length === 0 && (
                            <tr><td colSpan={5} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.henuz_degerlendirme_yok')}</td></tr>
                          )}
                        </>
                      )}
                    </tbody>
                  </table>
                {!performancePage.loading && performancePage.total > 0 && (
                  <PaginationBar
                    page={performancePage.page}
                    totalPages={performancePage.totalPages}
                    total={performancePage.total}
                    limit={performancePage.limit}
                    onPageChange={performancePage.setPage}
                    onLimitChange={performancePage.setLimit}
                  />
                )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === MESAİ ONAYI === */}
        <TabsContent value="overtime" className="mt-4">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <KpiCard intent="warning" icon={Timer} label="Bekleyen Talep" value={overtimeCounts.pending || 0}
                sub="onay bekliyor" />
              <KpiCard intent="success" icon={CheckCircle2} label="Onaylanan" value={overtimeCounts.approved || 0}
                sub="bu yıl" />
              <KpiCard intent="danger" icon={XCircle} label="Reddedilen" value={overtimeCounts.rejected || 0} />
            </div>

            {severanceCap && (
              <Card className="border-slate-200">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-base">
                      <Timer className="w-4 h-4" />Kıdem Tazminatı Tavanı (Tenant Ayarı)
                    </span>
                    <Button size="sm" variant="outline" onClick={updateSeveranceCap} disabled={savingSeverance}>
                      {savingSeverance ? 'Kaydediliyor…' : 'Tavanı Güncelle'}
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 md:grid-cols-3 text-sm">
                    <div className="rounded border border-slate-200 p-3">
                      <div className="text-xs text-slate-500">Günlük Brüt Tavan</div>
                      <div className="text-lg font-semibold mt-1">
                        ₺{Number(severanceCap.daily_cap || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                      </div>
                      {severanceCap.is_default && (
                        <div className="text-[11px] text-amber-600 mt-1">Default değer kullanılıyor</div>
                      )}
                    </div>
                    <div className="rounded border border-slate-200 p-3">
                      <div className="text-xs text-slate-500">30 Günlük Tavan (yaklaşık)</div>
                      <div className="text-lg font-semibold mt-1">
                        ₺{Number(severanceCap.monthly_cap_estimate || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div className="rounded border border-slate-200 p-3">
                      <div className="text-xs text-slate-500">Son Güncelleme</div>
                      <div className="text-sm mt-1">
                        {severanceCap.updated_at ? severanceCap.updated_at.slice(0, 10) : 'Hiç güncellenmemiş'}
                      </div>
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-3">
                    {severanceCap.note}
                  </div>
                </CardContent>
              </Card>
            )}

            {taxRates && (
              <Card className="border-slate-200">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-base">
                      <AlertCircle className="w-4 h-4" />Vergi Oranlarını Güncelle (Bordro Kesintileri)
                    </span>
                    {taxRates.can_edit && (
                      <Button size="sm" variant="outline" onClick={updateTaxRates} disabled={savingTaxRates}>
                        {savingTaxRates ? 'Kaydediliyor…' : 'Oranları Kaydet'}
                      </Button>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 md:grid-cols-4 text-sm">
                    {[
                      { key: 'sgk_employee', label: 'SGK İşçi Payı' },
                      { key: 'unemployment', label: 'İşsizlik Sigortası' },
                      { key: 'income_tax', label: 'Gelir Vergisi' },
                      { key: 'stamp_tax', label: 'Damga Vergisi' },
                    ].map(({ key, label }) => {
                      const isCustom = taxRatesForm
                        && Number(taxRatesForm[key]) !== Number(taxRates.defaults?.[key]);
                      return (
                        <div key={key} className="rounded border border-slate-200 p-3">
                          <div className="text-xs text-slate-500">{label}</div>
                          <div className="flex items-center gap-1 mt-1">
                            <Input
                              type="number"
                              step="0.001"
                              min="0"
                              max="100"
                              className="h-9"
                              value={taxRatesForm ? (taxRatesForm[key] ?? '') : ''}
                              disabled={!taxRates.can_edit}
                              onChange={(e) => setTaxRatesForm((f) => ({ ...(f || {}), [key]: e.target.value }))}
                            />
                            <span className="text-slate-500">%</span>
                          </div>
                          <div className="text-[11px] mt-1">
                            {isCustom ? (
                              <span className="text-sky-600">
                                Tenant'a özel (varsayılan %{Number(taxRates.defaults?.[key]).toLocaleString('tr-TR', { maximumFractionDigits: 3 })})
                              </span>
                            ) : (
                              <span className="text-amber-600">Varsayılan değer</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
                    <div className="text-[11px] text-slate-500">
                      {taxRates.note}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      Son güncelleme: {taxRates.updated_at ? taxRates.updated_at.slice(0, 10) : 'Hiç güncellenmemiş'}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2"><Timer className="w-4 h-4" />Mesai Talepleri</span>
                  <span className="text-xs text-slate-500 font-normal">İş K. m.41/3 — yıllık 270 saat üst sınırı otomatik kontrol edilir</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Personel</th>
                        <th>Tarih</th>
                        <th className="text-right">Saat</th>
                        <th>Sebep</th>
                        <th>Durum</th>
                        <th>İstek</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {overtimeItems.map((req) => (
                        <tr key={req.id} className="border-t border-slate-100 align-top">
                          <td className="py-2 font-medium">{req.staff_name}</td>
                          <td>{req.work_date}</td>
                          <td className="text-right">{req.hours}h</td>
                          <td className="text-slate-600 text-xs max-w-xs">{req.reason}</td>
                          <td>
                            <StatusBadge intent={STATUS_INTENT[req.status] || 'neutral'}>
                              {STATUS_LABEL[req.status] || req.status}
                            </StatusBadge>
                            {req.decision_note && (
                              <div className="text-[10px] text-slate-500 mt-1 max-w-[160px] truncate" title={req.decision_note}>
                                {req.decision_note}
                              </div>
                            )}
                          </td>
                          <td className="text-xs text-slate-500">{(req.requested_at || '').slice(0, 10)}</td>
                          <td className="text-right">
                            {req.status === 'pending' && (
                              <div className="flex justify-end gap-1 flex-wrap">
                                <Button size="sm" onClick={() => decideOvertime(req, 'dept_approve')} data-testid={`ot-dept-${req.id}`}>
                                  <Check className="w-3.5 h-3.5 mr-1" />Dept Onay
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideOvertime(req, 'reject')} data-testid={`ot-reject-${req.id}`}>
                                  <X className="w-3.5 h-3.5 mr-1 text-rose-600" />Reddet
                                </Button>
                              </div>
                            )}
                            {req.status === 'dept_approved' && (
                              <div className="flex justify-end gap-1 flex-wrap">
                                <Button size="sm" onClick={() => decideOvertime(req, 'approve')} data-testid={`ot-hr-final-${req.id}`}>
                                  <Check className="w-3.5 h-3.5 mr-1" />HR Final (Bordro)
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideOvertime(req, 'reject')} data-testid={`ot-hr-reject-${req.id}`}>
                                  <X className="w-3.5 h-3.5 mr-1 text-rose-600" />Reddet
                                </Button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {overtimeItems.length === 0 && (
                        <tr><td colSpan={7} className="py-6 text-center text-slate-500">
                          Mesai talebi yok — personel uygulamadan talep gönderdiğinde burada görünür
                        </td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === PERSONEL TALEBİ (eski "İşe Alım") === */}
        <TabsContent value="recruitment" className="mt-4">
          <div className="space-y-4">
            {/* Akış açıklaması */}
            <div className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm flex items-start gap-2">
              <Info className="w-4 h-4 mt-0.5 text-sky-600 shrink-0" />
              <div className="text-slate-700 text-xs space-y-1">
                <p><strong>Bu modül dış yayınlama (LinkedIn/Kariyer.net) yapmaz.</strong> Departman müdürü personel ihtiyacını bildirir, HR yöneticisi onaylar, onaylı pozisyonlara aday eklenip süreç (görüşme/teklif/işe alım) takip edilir.</p>
                <p>Talep oluşturulduğunda HR yöneticilerine bildirim gider. Karar (onay/red) talep sahibine bildirim olarak döner.</p>
              </div>
            </div>

            {/* KPI özet */}
            <div className="grid gap-3 md:grid-cols-4">
              <KpiCard intent="warning" label="Onay Bekleyen Talep"
                value={jobItems.filter((j) => j.status === 'pending_approval').length} />
              <KpiCard intent="success" label="Açık Pozisyon"
                value={jobItems.filter((j) => j.status === 'active').length} />
              <KpiCard intent="info" label="Toplam İhtiyaç (kişi)"
                value={jobItems.filter((j) => ['pending_approval', 'active'].includes(j.status))
                  .reduce((sum, j) => sum + (j.headcount_needed || 1), 0)} />
              <KpiCard intent="neutral" label="Toplam Aday"
                value={jobItems.reduce((sum, j) => sum + (j.applicants_count || 0), 0)} />
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Plus className="w-4 h-4" />Yeni Personel Talebi</CardTitle>
                <p className="text-xs text-slate-500 mt-1">
                  Departman müdürü olarak doldurun. Onay sonrası aday eklemeye açılır.
                </p>
              </CardHeader>
              <CardContent>
                <form onSubmit={submitJob} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <Label className="text-xs">Pozisyon *</Label>
                    <Input required value={jobForm.title}
                      onChange={(e) => setJobForm({ ...jobForm, title: e.target.value })}
                      placeholder="Resepsiyonist" />
                  </div>
                  <div>
                    <Label className="text-xs">Departman *</Label>
                    <Input required value={jobForm.department}
                      onChange={(e) => setJobForm({ ...jobForm, department: e.target.value })}
                      placeholder="front_desk" />
                  </div>
                  <div>
                    <Label className="text-xs">İhtiyaç Sayısı (kişi)</Label>
                    <Input type="number" min="1" max="50" value={jobForm.headcount_needed}
                      onChange={(e) => setJobForm({ ...jobForm, headcount_needed: parseInt(e.target.value) || 1 })} />
                  </div>
                  <div>
                    <Label className="text-xs">Aciliyet</Label>
                    <select value={jobForm.urgency}
                      onChange={(e) => setJobForm({ ...jobForm, urgency: e.target.value })}
                      className="w-full rounded-md border border-input px-3 py-2 text-sm">
                      <option value="low">Düşük</option>
                      <option value="normal">Normal</option>
                      <option value="high">Yüksek</option>
                      <option value="critical">Kritik</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">Çalışma Şekli</Label>
                    <select value={jobForm.employment_type}
                      onChange={(e) => setJobForm({ ...jobForm, employment_type: e.target.value })}
                      className="w-full rounded-md border border-input px-3 py-2 text-sm">
                      <option value="full_time">Tam Zamanlı</option>
                      <option value="part_time">Yarı Zamanlı</option>
                      <option value="seasonal">Sezonluk</option>
                      <option value="contract">Sözleşmeli</option>
                      <option value="intern">Stajyer</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">İhtiyaç Tarihi</Label>
                    <Input type="date" value={jobForm.needed_by}
                      onChange={(e) => setJobForm({ ...jobForm, needed_by: e.target.value })} />
                  </div>
                  <div>
                    <Label className="text-xs">Ücret Aralığı (öneri)</Label>
                    <Input value={jobForm.salary_range}
                      onChange={(e) => setJobForm({ ...jobForm, salary_range: e.target.value })}
                      placeholder="22.000 – 30.000 TL" />
                  </div>
                  <div>
                    <Label className="text-xs">Lokasyon</Label>
                    <Input value={jobForm.location}
                      onChange={(e) => setJobForm({ ...jobForm, location: e.target.value })} />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3">
                    <Label className="text-xs">Gerekçe (HR'a not)</Label>
                    <Textarea rows={2} value={jobForm.justification}
                      onChange={(e) => setJobForm({ ...jobForm, justification: e.target.value })}
                      placeholder="Örn: yaz sezonu için ek personel; mevcut kadronun yetersizliği vb." />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3">
                    <Label className="text-xs">Pozisyon Açıklaması</Label>
                    <Textarea rows={3} value={jobForm.description}
                      onChange={(e) => setJobForm({ ...jobForm, description: e.target.value })}
                      placeholder="Sorumluluklar, beklentiler, gerekli niteliklere dair detaylar" />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 flex justify-end">
                    <Button type="submit" disabled={creatingJob}>
                      <Send className="w-4 h-4 mr-1.5" />
                      {creatingJob ? 'Gönderiliyor...' : 'Talep Oluştur (HR\'a Gönder)'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Talepler & Açık Pozisyonlar</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Pozisyon</th>
                        <th>Departman</th>
                        <th className="text-right">İhtiyaç</th>
                        <th>Aciliyet</th>
                        <th>İhtiyaç Tarihi</th>
                        <th>Talep Eden</th>
                        <th>Durum</th>
                        <th className="text-right">Aday</th>
                        <th className="text-right">İşlem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobItems.map((job) => (
                        <tr key={job.id} className="border-t border-slate-100 align-top">
                          <td className="py-2">
                            <div className="font-medium">{job.title}</div>
                            {job.justification && (
                              <div className="text-xs text-slate-400 max-w-xs truncate" title={job.justification}>
                                {job.justification}
                              </div>
                            )}
                          </td>
                          <td className="capitalize text-slate-600">{job.department}</td>
                          <td className="text-right">{job.headcount_needed || 1}</td>
                          <td>
                            {job.urgency === 'critical' && <StatusBadge intent="danger">Kritik</StatusBadge>}
                            {job.urgency === 'high' && <StatusBadge intent="warning">Yüksek</StatusBadge>}
                            {job.urgency === 'normal' && <span className="text-xs text-slate-500">Normal</span>}
                            {job.urgency === 'low' && <span className="text-xs text-slate-400">Düşük</span>}
                          </td>
                          <td className="text-slate-600 text-xs">{job.needed_by || '—'}</td>
                          <td className="text-slate-600 text-xs">{job.created_by_name || '—'}</td>
                          <td>
                            {job.status === 'pending_approval' && <StatusBadge intent="warning">Onay Bekliyor</StatusBadge>}
                            {job.status === 'active' && <StatusBadge intent="success">Açık</StatusBadge>}
                            {job.status === 'rejected' && <StatusBadge intent="danger">Reddedildi</StatusBadge>}
                            {job.status === 'closed' && <StatusBadge intent="neutral">Kapalı</StatusBadge>}
                          </td>
                          <td className="text-right">
                            <button type="button" onClick={() => openApplicants(job)}
                              className="text-sky-600 hover:underline" disabled={job.status === 'pending_approval'}>
                              {job.applicants_count || 0}
                            </button>
                          </td>
                          <td className="text-right">
                            <div className="flex justify-end gap-1">
                              {job.status === 'pending_approval' && (
                                <>
                                  <Button size="sm" variant="outline" onClick={() => decideJob(job.id, 'approve')}
                                    title="HR yöneticisi olarak onayla">
                                    <ThumbsUp className="w-3.5 h-3.5 mr-1" />Onayla
                                  </Button>
                                  <Button size="sm" variant="outline" onClick={() => decideJob(job.id, 'reject')}>
                                    <ThumbsDown className="w-3.5 h-3.5 mr-1" />Reddet
                                  </Button>
                                </>
                              )}
                              {job.status === 'active' && (
                                <>
                                  <Button size="sm" variant="outline" onClick={() => openApplicants(job)}>
                                    <UserPlus className="w-3.5 h-3.5 mr-1" />Aday
                                  </Button>
                                  <Button size="sm" variant="outline" onClick={() => closeJob(job.id)}>
                                    <XCircle className="w-3.5 h-3.5" />
                                  </Button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {jobItems.length === 0 && (
                        <tr><td colSpan={9} className="py-10 text-center text-slate-500">
                          Henüz talep yok. Yukarıdaki formdan ilk personel talebini oluşturun.
                        </td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Adaylar Modal */}
          <Dialog open={applicantsDialog.open} onOpenChange={(o) => !o && setApplicantsDialog({ open: false, job: null, list: [], counts: {} })}>
            <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>
                  Adaylar — {applicantsDialog.job?.title}
                  <span className="text-xs text-slate-500 ml-2 font-normal">
                    ({applicantsDialog.job?.department})
                  </span>
                </DialogTitle>
              </DialogHeader>

              {/* Aday durum sayaçları */}
              <div className="flex flex-wrap gap-2 text-xs">
                {Object.entries(applicantsDialog.counts || {}).map(([k, v]) => (
                  <span key={k} className="rounded-full bg-slate-100 px-2 py-0.5">
                    {k}: <strong>{v}</strong>
                  </span>
                ))}
              </div>

              {/* Yeni aday formu */}
              <form onSubmit={submitApplicant} className="grid gap-2 md:grid-cols-2 border-t pt-3 mt-2">
                <div className="md:col-span-2 text-sm font-medium flex items-center gap-2">
                  <UserPlus className="w-4 h-4" />Yeni Aday Ekle
                </div>
                <Input placeholder="Ad Soyad *" value={applicantForm.name}
                  onChange={(e) => setApplicantForm({ ...applicantForm, name: e.target.value })} />
                <Input placeholder="E-posta" type="email" value={applicantForm.email}
                  onChange={(e) => setApplicantForm({ ...applicantForm, email: e.target.value })} />
                <Input placeholder="Telefon" value={applicantForm.phone}
                  onChange={(e) => setApplicantForm({ ...applicantForm, phone: e.target.value })} />
                <Input placeholder="CV URL (opsiyonel)" value={applicantForm.cv_url}
                  onChange={(e) => setApplicantForm({ ...applicantForm, cv_url: e.target.value })} />
                <div className="md:col-span-2">
                  <Textarea rows={2} placeholder="Notlar (deneyim, görüşme izlenimi, vb.)"
                    value={applicantForm.notes}
                    onChange={(e) => setApplicantForm({ ...applicantForm, notes: e.target.value })} />
                </div>
                <div className="md:col-span-2 flex justify-end">
                  <Button type="submit" size="sm" disabled={savingApplicant}>
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    {savingApplicant ? 'Ekleniyor...' : 'Adayı Kaydet'}
                  </Button>
                </div>
              </form>

              {/* Aday listesi */}
              <div className="border-t pt-3">
                <div className="text-sm font-medium mb-2">Aday Listesi ({applicantsDialog.list.length})</div>
                <div className="space-y-2">
                  {applicantsDialog.list.map((a) => (
                    <div key={a.id} className="rounded border border-slate-200 p-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="font-medium">{a.name}</div>
                          <div className="text-xs text-slate-500">
                            {a.email || '—'} • {a.phone || '—'}
                          </div>
                          {a.notes && <div className="text-xs text-slate-600 mt-1">{a.notes}</div>}
                          {a.cv_url && (
                            <a href={a.cv_url} target="_blank" rel="noreferrer"
                              className="text-xs text-sky-600 hover:underline">
                              <ExternalLink className="w-3 h-3 inline mr-0.5" />CV
                            </a>
                          )}
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          <select value={a.status || 'new'}
                            onChange={(e) => setApplicantStatus(a.id, e.target.value)}
                            className="text-xs rounded border border-input px-2 py-1">
                            <option value="new">Yeni</option>
                            <option value="screening">Eleme</option>
                            <option value="interview">Görüşme</option>
                            <option value="offer">Teklif</option>
                            <option value="hired">İşe Alındı</option>
                            <option value="rejected">Reddedildi</option>
                          </select>
                          <span className="text-[10px] text-slate-400">
                            {(a.created_at || '').slice(0, 10)}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                  {applicantsDialog.list.length === 0 && (
                    <p className="text-center text-sm text-slate-500 py-6">Henüz aday yok</p>
                  )}
                </div>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setApplicantsDialog({ open: false, job: null, list: [], counts: {} })}>
                  Kapat
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default HRComplete;
