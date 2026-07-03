import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Clock, Calendar, DollarSign, Briefcase, UserPlus, Download,
  Users, FileSpreadsheet, RefreshCw, Plus, CheckCircle2, XCircle,
  TrendingUp, ExternalLink, FileDown, Award, Info, AlertCircle,
  Bell, FileText, ClipboardList, Send, ThumbsUp, ThumbsDown,
  Timer, Check, X, Package, GraduationCap, Star, ListChecks, Mail, Phone,
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
  const perfMetrics = useMemo(() => {
    if (!performancePage?.items) return { high_performers: 0, low_performers: 0 };
    return {
      high_performers: performancePage.items.filter(i => parseFloat(i.overall_score) >= 8.0).length,
      low_performers: performancePage.items.filter(i => parseFloat(i.overall_score) < 5.0).length,
    };
  }, [performancePage.items]);

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

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6">
      {/* PROFESSIONAL HEADER */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 bg-gradient-to-r from-teal-50 to-white rounded-2xl border border-teal-100 px-6 py-5 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="p-3 rounded-2xl bg-teal-600 text-white shadow-lg shadow-teal-200">
            <Users className="w-7 h-7" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{t('cm.pages_HRComplete.ik_yonetim_paketi')}</h1>
            <p className="text-sm text-slate-500 mt-0.5">{t('cm.pages_HRComplete.devam_takibi_bordro_izin_performans_ve_i')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="border-slate-200 bg-white hover:bg-slate-50 text-slate-700"
            onClick={() => navigate('/staff-management')}
            data-testid="btn-staff-management"
          >
            <Users className="w-4 h-4 mr-2" />
            Personel Yönetimi
            <ExternalLink className="w-3 h-3 ml-1.5 opacity-50" />
          </Button>
          <Button
            variant="outline"
            className="border-slate-200 bg-white hover:bg-slate-50 text-slate-700"
            onClick={loadAll}
            disabled={refreshing}
            data-testid="btn-refresh-hr"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-6 bg-slate-100/80 p-1.5 rounded-xl border border-slate-200">
          <TabsTrigger value="attendance" data-testid="tab-attendance" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-md rounded-lg text-sm font-medium transition-all">
            <Clock className="w-4 h-4 mr-2" />Devam
          </TabsTrigger>
          <TabsTrigger value="payroll" data-testid="tab-payroll" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-md rounded-lg text-sm font-medium transition-all">
            <DollarSign className="w-4 h-4 mr-2" />Bordro
          </TabsTrigger>
          <TabsTrigger value="leave" data-testid="tab-leave" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-md rounded-lg text-sm font-medium transition-all">
            <Calendar className="w-4 h-4 mr-2" />İzin
          </TabsTrigger>
          <TabsTrigger value="performance" data-testid="tab-performance" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-md rounded-lg text-sm font-medium transition-all">
            <Briefcase className="w-4 h-4 mr-2" />Performans
          </TabsTrigger>
          <TabsTrigger value="overtime" data-testid="tab-overtime" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-md rounded-lg text-sm font-medium transition-all">
            <Timer className="w-4 h-4 mr-1.5" />
            Mesai Onayı
            {overtimeCounts.pending > 0 && (
              <span className="ml-1.5 px-1.5 rounded-full bg-amber-500 text-white text-[10px]">{overtimeCounts.pending}</span>
            )}
          </TabsTrigger>
          <TabsTrigger value="recruitment" data-testid="tab-recruitment" className="data-[state=active]:bg-teal-600 data-[state=active]:text-white data-[state=active]:shadow-md rounded-lg text-sm font-medium transition-all">
            <ClipboardList className="w-4 h-4 mr-2" />Personel Talebi
          </TabsTrigger>
        </TabsList>

        {/* === ATTENDANCE === */}
        <TabsContent value="attendance" className="mt-4">
          <div className="space-y-6 mt-6">
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-5">
              <div className="rounded-2xl border border-teal-100 bg-gradient-to-br from-teal-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-teal-100 text-teal-700"><Users className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Toplam Çalışan</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{attendanceMetrics.total_active_staff ?? attendanceMetrics.staff_count}</div>
                <div className="text-[11px] text-slate-500 mt-1">aktif personel • {attendanceMetrics.staff_count} devam kayıtlı</div>
              </div>
              <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-emerald-100 text-emerald-700"><Clock className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Toplam Saat</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{(attendanceMetrics.total_hours || 0).toFixed(1)}</div>
                <div className="text-[11px] text-slate-500 mt-1">son 30 gün</div>
              </div>
              <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-indigo-100 text-indigo-700"><TrendingUp className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Ortalama Saat</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{(attendanceMetrics.avg_hours_per_active_staff || attendanceMetrics.avg_hours_per_staff || 0).toFixed(1)}</div>
                <div className="text-[11px] text-slate-500 mt-1">personel başı (son 30 gün)</div>
              </div>
              <div className={`rounded-2xl border p-5 shadow-sm ${outstandingEquipTotal > 0 ? 'border-amber-100 bg-gradient-to-br from-amber-50 to-white' : 'border-slate-100 bg-gradient-to-br from-slate-50 to-white'}`}>
                <div className="flex items-center gap-3 mb-2">
                  <div className={`p-2 rounded-lg ${outstandingEquipTotal > 0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-200 text-slate-700'}`}><Package className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Açık Zimmet</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{outstandingEquipTotal}</div>
                <div className="text-[11px] text-slate-500 mt-1">iade alınmamış</div>
              </div>
              <div className={`rounded-2xl border p-5 shadow-sm ${expiringTrainTotal > 0 ? 'border-rose-100 bg-gradient-to-br from-rose-50 to-white' : 'border-slate-100 bg-gradient-to-br from-slate-50 to-white'}`}>
                <div className="flex items-center gap-3 mb-2">
                  <div className={`p-2 rounded-lg ${expiringTrainTotal > 0 ? 'bg-rose-100 text-rose-700' : 'bg-slate-200 text-slate-700'}`}><GraduationCap className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Süresi Dolan Eğitim</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{expiringTrainTotal}</div>
                <div className="text-[11px] text-slate-500 mt-1">önümüzdeki 60 gün</div>
              </div>
            </div>

            <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden">
              <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between bg-slate-50/50 border-b border-slate-100 pb-4">
                <CardTitle className="text-lg font-bold text-slate-800">Giriş / Çıkış Kaydı</CardTitle>
                <div className="flex flex-wrap gap-3 items-center bg-white p-2 rounded-xl border border-slate-200 shadow-sm">
                  <div className="flex items-center gap-2 pl-2">
                    <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personel</Label>
                    <select
                      value={selectedStaffId}
                      onChange={(e) => setSelectedStaffId(e.target.value)}
                      className="rounded-lg border-0 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-700 focus:ring-2 focus:ring-teal-500 min-w-[200px]"
                      data-testid="select-staff"
                    >
                      {staffDropdown.length === 0 && <option value="">— Personel yok —</option>}
                      {staffDropdown.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} {s.department ? `(${s.department})` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="h-6 w-px bg-slate-200 mx-1"></div>
                  <Button size="sm" onClick={clockIn} disabled={!selectedStaffId} data-testid="btn-clock-in" className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg shadow-sm">
                    <Clock className="w-4 h-4 mr-1.5" />Giriş Yap
                  </Button>
                  <Button size="sm" variant="outline" onClick={clockOut} disabled={!selectedStaffId} data-testid="btn-clock-out" className="border-rose-200 text-rose-700 hover:bg-rose-50 rounded-lg shadow-sm">
                    <Clock className="w-4 h-4 mr-1.5" />Çıkış Yap
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {staffDropdown.length === 0 && (
                  <div className="m-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5" />
                    <div>
                      <p className="font-semibold mb-1">Personel listesi boş</p>
                      <p>
                        Personel eklemek için <button className="font-semibold underline hover:text-amber-900" onClick={() => navigate('/staff-management')}>Personel Yönetimi</button> sayfasını kullanın.
                      </p>
                    </div>
                  </div>
                )}
                <div className="px-5 py-3 border-b border-slate-100 bg-slate-50 text-xs font-medium text-slate-500">
                  <span className="uppercase tracking-wider">İzlenen Aralık:</span> {recordsRange.start || '—'} → {recordsRange.end || '—'}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left bg-white border-b border-slate-200">
                        <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personel</th>
                        <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Departman</th>
                        <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Gün</th>
                        <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Giriş</th>
                        <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Çıkış</th>
                        <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Saat</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {attendanceRecords.map((record) => (
                        <tr key={record.id || record.clock_in} className="hover:bg-slate-50/80 transition-colors bg-white">
                          <td className="py-3 px-5 font-semibold text-slate-800">{record.staff_name || record.staff_id}</td>
                          <td className="py-3 px-5 capitalize text-slate-600">
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">{record.department || '—'}</span>
                          </td>
                          <td className="py-3 px-5 text-slate-600 font-medium">{record.date}</td>
                          <td className="py-3 px-5">
                            <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-100">
                              {fmtTime(record.clock_in)}
                            </span>
                          </td>
                          <td className="py-3 px-5">
                            {record.clock_out ? (
                              <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-bold bg-rose-50 text-rose-700 border border-rose-100">
                                {fmtTime(record.clock_out)}
                              </span>
                            ) : (
                              <span className="text-slate-400 text-xs italic">Devam ediyor</span>
                            )}
                          </td>
                          <td className="py-3 px-5 text-right font-bold text-slate-700">{record.total_hours?.toFixed(2) ?? '—'}</td>
                        </tr>
                      ))}
                      {attendanceRecords.length === 0 && (
                        <tr>
                          <td colSpan={6} className="py-12">
                            <div className="flex flex-col items-center justify-center text-slate-400">
                              <Clock className="w-10 h-10 mb-3 opacity-20" />
                              <p className="font-medium text-slate-600">Kayıt bulunamadı</p>
                              <p className="text-xs mt-1">Seçili tarih aralığında giriş-çıkış kaydı yok.</p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-2xl border-slate-200 shadow-sm">
              <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-4">
                <CardTitle className="flex items-center gap-2 text-lg font-bold text-slate-800">
                  <Award className="w-5 h-5 text-amber-500" />En Yüksek Saat (Top 3)
                </CardTitle>
              </CardHeader>
              <CardContent className="p-5">
                <div className="grid gap-4 md:grid-cols-3">
                  {topPerformers.map((s, idx) => (
                    <div key={s.staff_id} className="relative flex items-center p-4 rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                      <div className={`absolute top-0 left-0 w-1 h-full ${idx === 0 ? 'bg-amber-500' : idx === 1 ? 'bg-slate-400' : 'bg-amber-700'}`}></div>
                      <div className="flex-1 pl-2">
                        <p className="font-bold text-slate-900 truncate">{s.staff_name}</p>
                        <p className="text-xs text-slate-500 capitalize mt-0.5">{s.department}</p>
                      </div>
                      <div className="text-right ml-3">
                        <p className="text-[10px] uppercase font-bold tracking-wider text-slate-400">Toplam</p>
                        <p className="text-xl font-black text-slate-900">{s.total_hours?.toFixed(1)}<span className="text-xs font-medium text-slate-500 ml-0.5">sa</span></p>
                      </div>
                    </div>
                  ))}
                </div>
                {topPerformers.length === 0 && (
                  <div className="text-center py-8">
                    <Award className="w-10 h-10 mx-auto text-slate-300 mb-3" />
                    <p className="text-sm font-medium text-slate-600">Yeterli devam verisi yok</p>
                    <Button variant="outline" size="sm" className="mt-3 rounded-lg" onClick={() => navigate('/staff-management')}>
                      <UserPlus className="w-4 h-4 mr-1.5" />Personel Ekle
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === PAYROLL === */}
        <TabsContent value="payroll" className="mt-4">
          <div className="space-y-6 mt-6">
            <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden">
              <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between bg-slate-50/50 border-b border-slate-100 pb-4">
                <div>
                  <CardTitle className="flex items-center gap-2 text-lg font-bold text-slate-800">
                    <div className="p-1.5 rounded-md bg-teal-100 text-teal-700"><DollarSign className="w-5 h-5" /></div>
                    Bordro İşlemleri
                  </CardTitle>
                  <p className="text-sm text-slate-500 mt-1.5 ml-9">
                    Devam kayıtlarından otomatik hesap (TR İş K. uyumlu: %14 SGK + %1 İşsizlik + %15 Gelir + %0.759 Damga)
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3 bg-white p-2 rounded-xl border border-slate-200 shadow-sm">
                  <div className="flex items-center gap-2 pl-2">
                    <Label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Ay</Label>
                    <Input
                      type="month"
                      value={exportMonth}
                      onChange={(e) => setExportMonth(e.target.value)}
                      className="w-40 h-9 rounded-lg border-slate-200 bg-slate-50 focus:ring-teal-500"
                      data-testid="input-payroll-month"
                    />
                  </div>
                  <div className="h-6 w-px bg-slate-200 mx-1"></div>
                  <Button variant="outline" size="sm" onClick={handlePayrollPreview} className="rounded-lg shadow-sm" data-testid="btn-payroll-preview">
                    <RefreshCw className="w-4 h-4 mr-1.5 text-slate-500" />Önizle
                  </Button>
                  <Button size="sm" onClick={handlePayrollSaveDraft} disabled={savingDraft} data-testid="btn-payroll-save-draft" className="bg-slate-900 text-white hover:bg-slate-800 rounded-lg shadow-sm">
                    <FileText className="w-4 h-4 mr-1.5" />
                    {savingDraft ? 'Kaydediliyor...' : 'Taslak Kaydet'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handlePayrollExport} disabled={exporting} data-testid="btn-payroll-csv" className="rounded-lg shadow-sm text-sky-700 border-sky-200 hover:bg-sky-50">
                    <FileDown className="w-4 h-4 mr-1.5" />
                    {exporting ? 'İndiriliyor...' : 'CSV İndir'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="p-5 space-y-6">
                
                {/* Collapsible Guide */}
                <details className="rounded-xl border border-sky-200 bg-gradient-to-br from-sky-50 to-white shadow-sm overflow-hidden group">
                  <summary className="px-5 py-3 cursor-pointer text-sm font-semibold text-sky-800 flex items-center gap-2 hover:bg-sky-100/50 transition-colors">
                    <Info className="w-5 h-5 text-sky-600" />
                    Bordro Yaşam Döngüsü Rehberi (Önbordro / Muhasebe İhracı)
                  </summary>
                  <div className="px-5 pb-5 pt-2 border-t border-sky-100/50">
                    <ol className="list-decimal pl-5 space-y-2 text-slate-700 text-sm">
                      <li><strong>Önizle</strong>: Devam kayıtlarından dry-run hesap. Hiçbir muhasebe etkisi YOKTUR.</li>
                      <li><strong>Taslak Kaydet</strong>: Bu ayın hesabı <code>payroll_runs</code> veritabanına <em>draft</em> olarak kaydedilir; aynı gün tekrar bastığınızda mevcut taslak güncellenir.</li>
                      <li><strong>Kilitle</strong>: Taslak satır bazında dondurulur (<em>locked</em>, immutable). Yalnızca HR Admin / Finance / Süper Admin.</li>
                      <li><strong>Revizyon Aç</strong>: Kilitli bordro değişmez; yeni bir taslak ile düzeltme akışı başlar (audit zinciri korunur).</li>
                      <li><strong>CSV / XLSX</strong>: Muhasebe ihracı; XLSX kalem (avans, prim, yemek, yol, kesinti, mesai) detayı içerir.</li>
                    </ol>
                    <div className="mt-4 p-3 rounded-lg bg-amber-50 border border-amber-100 text-xs text-amber-800 flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
                      <p>
                        {(() => {
                          const r = taxRates?.rates || { sgk_employee: 14, unemployment: 1, income_tax: 15, stamp_tax: 0.759 };
                          const fmt = (n) => Number(n).toLocaleString('tr-TR', { maximumFractionDigits: 3 });
                          return `Kesintiler: %${fmt(r.sgk_employee)} SGK + %${fmt(r.unemployment)} İşsizlik + %${fmt(r.income_tax)} Gelir Vergisi (matrah − SGK) + %${fmt(r.stamp_tax)} Damga.`;
                        })()}
                        {' '}Asgari ücret muafiyeti / AGİ / özel kesintiler için muhasebenizle doğrulayın.
                      </p>
                    </div>
                  </div>
                </details>

                {/* Runs listesi */}
                {payrollRuns.length > 0 && (
                  <div className="rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                    <div className="px-5 py-3 border-b bg-slate-50 text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                      <FileText className="w-4 h-4 text-slate-400" />
                      {exportMonth} Ayı Bordro Çalışmaları ({payrollRuns.length})
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left bg-white border-b border-slate-200">
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Durum</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Run ID</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Personel</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Brüt</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Net</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Güncellendi</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">İşlem</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {payrollRuns.map((r) => (
                            <tr key={r.id} className={`hover:bg-slate-50 transition-colors ${selectedRun?.id === r.id ? 'bg-teal-50/50' : 'bg-white'}`}>
                              <td className="py-3 px-5">
                                <StatusBadge intent={r.status === 'locked' ? 'success' : 'warning'}>
                                  {r.status === 'locked' ? 'Kilitli' : 'Taslak'}
                                </StatusBadge>
                              </td>
                              <td className="py-3 px-5 font-mono text-xs text-slate-600">{r.id.slice(0, 8)}…</td>
                              <td className="py-3 px-5 text-right font-medium">{r.summary?.staff_count ?? '—'}</td>
                              <td className="py-3 px-5 text-right text-slate-600">{r.summary ? fmtCurrency(r.summary.total_gross) : '—'}</td>
                              <td className="py-3 px-5 text-right font-bold text-slate-800">{r.summary ? fmtCurrency(r.summary.total_net) : '—'}</td>
                              <td className="py-3 px-5 text-xs text-slate-500">{(r.updated_at || r.created_at || '').slice(0, 16).replace('T', ' ')}</td>
                              <td className="py-3 px-5 text-right">
                                <Button size="sm" variant="outline" className="rounded-lg text-teal-700 border-teal-200 hover:bg-teal-50" onClick={() => loadRunDetail(r.id)} data-testid={`btn-run-detail-${r.id.slice(0, 8)}`}>
                                  Detay
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
                  <div className="rounded-xl border border-teal-200 bg-white overflow-hidden shadow-sm">
                    <div className="px-5 py-4 border-b bg-teal-50/50 flex flex-wrap items-center justify-between gap-4">
                      <div className="text-sm">
                        <span className="font-bold text-teal-900">Çalışma Detayı: </span>
                        <span className="font-mono text-teal-700 bg-teal-100 px-2 py-0.5 rounded-md ml-1">{selectedRun.id.slice(0, 8)}…</span>
                        <span className="ml-3">
                          <StatusBadge intent={selectedRun.status === 'locked' ? 'success' : 'warning'}>
                            {selectedRun.status === 'locked' ? 'Kilitli' : 'Taslak'}
                          </StatusBadge>
                        </span>
                        {selectedRun.parent_run_id && (
                          <span className="ml-3 text-teal-600 text-xs">
                            (revizyon — üst: <span className="font-mono">{selectedRun.parent_run_id.slice(0, 8)}…</span>)
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {selectedRun.status === 'draft' && (
                          <Button size="sm" onClick={() => handlePayrollFinalize(selectedRun.id)} disabled={finalizing}
                            className="bg-emerald-600 text-white hover:bg-emerald-700 rounded-lg shadow-sm" data-testid="btn-payroll-finalize">
                            <CheckCircle2 className="w-4 h-4 mr-1.5" />
                            {finalizing ? 'Kilitleniyor...' : 'Kilitle'}
                          </Button>
                        )}
                        {selectedRun.status === 'locked' && (
                          <Button size="sm" variant="outline" onClick={() => handleRevisionOpen(selectedRun.id)} disabled={revising} data-testid="btn-payroll-revision" className="rounded-lg border-amber-200 text-amber-700 hover:bg-amber-50">
                            <RefreshCw className="w-4 h-4 mr-1.5" />
                            {revising ? 'Açılıyor...' : 'Revizyon Aç'}
                          </Button>
                        )}
                        <Button size="sm" variant="outline" onClick={() => handleRunXlsx(selectedRun.id)} data-testid="btn-payroll-xlsx" className="rounded-lg border-teal-200 text-teal-700 hover:bg-teal-50">
                          <FileDown className="w-4 h-4 mr-1.5" />XLSX İndir
                        </Button>
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left bg-white border-b border-slate-200">
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personel</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Departman</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Saat</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Mesai</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Brüt</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Ek Kazanç</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Ek Kesinti</th>
                            <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Net</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {(selectedRun.rows || []).map((row) => (
                            <tr key={row.staff_id} className="hover:bg-slate-50 transition-colors bg-white">
                              <td className="py-3 px-5 font-bold text-slate-800">{row.staff_name}</td>
                              <td className="py-3 px-5 capitalize text-slate-600">
                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">{row.department}</span>
                              </td>
                              <td className="py-3 px-5 text-right font-medium">{Number(row.total_hours || 0).toFixed(1)}</td>
                              <td className="py-3 px-5 text-right font-bold text-amber-600">{Number(row.overtime_hours || 0).toFixed(1)}</td>
                              <td className="py-3 px-5 text-right text-slate-600">{fmtCurrency(row.gross_pay)}</td>
                              <td className="py-3 px-5 text-right text-emerald-600">{fmtCurrency(row.extra_earnings || 0)}</td>
                              <td className="py-3 px-5 text-right text-rose-600">{fmtCurrency(row.extra_deductions || 0)}</td>
                              <td className="py-3 px-5 text-right font-black text-slate-900">{fmtCurrency(row.net_salary)}</td>
                            </tr>
                          ))}
                          {(!selectedRun.rows || selectedRun.rows.length === 0) && (
                            <tr>
                              <td colSpan={8} className="py-12">
                                <div className="flex flex-col items-center justify-center text-slate-400">
                                  <FileText className="w-10 h-10 mb-3 opacity-20" />
                                  <p className="font-medium text-slate-600">Kayıt yok</p>
                                </div>
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                    {runRevisions.length > 0 && (
                      <div className="border-t border-slate-200 bg-slate-50 p-5">
                        <div className="font-bold text-sm text-slate-700 mb-3 flex items-center gap-2">
                          <RefreshCw className="w-4 h-4" /> Revizyon Geçmişi ({runRevisions.length})
                        </div>
                        <ul className="space-y-2">
                          {runRevisions.map((rev) => (
                            <li key={rev.id} className="flex flex-wrap items-center gap-3 text-sm bg-white p-2 rounded-lg border border-slate-200 shadow-sm">
                              <span className="text-slate-400 text-xs px-2 py-1 bg-slate-100 rounded-md">{(rev.created_at || '').slice(0, 16).replace('T', ' ')}</span>
                              <span className="font-mono text-xs text-sky-700 bg-sky-50 px-2 py-1 rounded-md">{rev.new_run_id?.slice(0, 8)}…</span>
                              <span className="text-slate-400">—</span>
                              <span className="font-medium text-slate-700">{rev.reason}</span>
                              <span className="text-slate-500 text-xs ml-auto">
                                (brüt <span className="line-through opacity-70">{fmtCurrency(rev.diff?.gross_before)}</span> → <span className="font-bold text-emerald-600">{fmtCurrency(rev.diff?.gross_after)}</span>)
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {payrollPreview ? (
                  <div className="space-y-6">
                    <div className="grid gap-4 md:grid-cols-3">
                      <div className="rounded-2xl border border-sky-100 bg-gradient-to-br from-sky-50 to-white p-5 shadow-sm">
                        <div className="flex items-center gap-3 mb-2">
                          <div className="p-2 rounded-lg bg-sky-100 text-sky-700"><Users className="w-5 h-5" /></div>
                          <div className="text-sm font-semibold text-slate-600">Personel</div>
                        </div>
                        <div className="text-3xl font-bold text-slate-900">{payrollPreview.staff_count}</div>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <div className="flex items-center gap-3 mb-2">
                          <div className="p-2 rounded-lg bg-slate-100 text-slate-700"><DollarSign className="w-5 h-5" /></div>
                          <div className="text-sm font-semibold text-slate-600">Toplam Brüt</div>
                        </div>
                        <div className="text-3xl font-bold text-slate-900">{fmtCurrency(payrollPreview.total_gross_pay)}</div>
                      </div>
                      <div className="rounded-2xl border border-teal-100 bg-gradient-to-br from-teal-50 to-white p-5 shadow-sm">
                        <div className="flex items-center gap-3 mb-2">
                          <div className="p-2 rounded-lg bg-teal-100 text-teal-700"><DollarSign className="w-5 h-5" /></div>
                          <div className="text-sm font-semibold text-slate-600">Toplam Net</div>
                        </div>
                        <div className="text-3xl font-bold text-slate-900">{fmtCurrency(payrollPreview.total_net_pay)}</div>
                      </div>
                    </div>
                    
                    <div className="rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left bg-slate-50 border-b border-slate-200">
                              <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personel</th>
                              <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Departman</th>
                              <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Saat</th>
                              <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Mesai</th>
                              <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Brüt</th>
                              <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">SGK + İşsiz.</th>
                              <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Vergi</th>
                              <th className="py-3 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Net</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {payrollPreview.payroll?.map((row) => (
                              <tr key={row.staff_id} className="hover:bg-slate-50 transition-colors bg-white">
                                <td className="py-3 px-5 font-bold text-slate-800">{row.staff_name}</td>
                                <td className="py-3 px-5 capitalize text-slate-600">
                                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">{row.department}</span>
                                </td>
                                <td className="py-3 px-5 text-right font-medium">{row.total_hours.toFixed(1)}</td>
                                <td className="py-3 px-5 text-right font-bold text-amber-600">{row.overtime_hours.toFixed(1)}</td>
                                <td className="py-3 px-5 text-right text-slate-600">{fmtCurrency(row.gross_pay)}</td>
                                <td className="py-3 px-5 text-right text-slate-500">{fmtCurrency(row.sgk_employee + row.unemployment)}</td>
                                <td className="py-3 px-5 text-right text-rose-600/80">{fmtCurrency(row.income_tax + row.stamp_tax)}</td>
                                <td className="py-3 px-5 text-right font-black text-slate-900">{fmtCurrency(row.net_salary)}</td>
                              </tr>
                            ))}
                            {(!payrollPreview.payroll || payrollPreview.payroll.length === 0) && (
                              <tr>
                                <td colSpan={8} className="py-12">
                                  <div className="flex flex-col items-center justify-center text-slate-400">
                                    <FileText className="w-10 h-10 mb-3 opacity-20" />
                                    <p className="font-medium text-slate-600">Bu ayda devam kaydı yok</p>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 p-12 text-center text-slate-500">
                    <DollarSign className="w-12 h-12 mx-auto text-slate-300 mb-4" />
                    <p className="text-base font-medium text-slate-700 mb-2">Bordro önizlemek için ay seçin ve <strong>Önizle</strong>'ye basın.</p>
                    <p className="text-sm">Kalıcı kayıt için <strong>Taslak Kaydet</strong>'e basabilir veya doğrudan <strong>CSV İndir</strong> diyebilirsiniz.</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === LEAVE === */}
        <TabsContent value="leave" className="mt-4">
          <div className="space-y-6 mt-6">
            {/* Akış açıklaması */}
            <div className="rounded-xl border border-sky-200 bg-gradient-to-r from-sky-50 to-white p-4 shadow-sm flex items-start gap-3">
              <div className="p-2 bg-sky-100 rounded-lg text-sky-700 shrink-0">
                <Bell className="w-5 h-5" />
              </div>
              <div className="text-slate-700 text-sm space-y-1 mt-0.5">
                <p><strong>İzin Akışı:</strong> Talep oluşturulduğunda HR yöneticilerine (admin/supervisor/finance rolleri) in-app bildirim düşer. Karar verildiğinde talep sahibine geri bildirim gider.</p>
                <p className="text-xs text-slate-500">Yıllık izin hakkı varsayılan <strong>14 gün</strong> (İş K. m.53). Personel kartında ya da <code>POST /hr/leave-balance</code> ile özelleştirilebilir. Onaylı talepler bakiyeden düşülür.</p>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-2xl border border-amber-100 bg-gradient-to-br from-amber-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-amber-100 text-amber-700"><Clock className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Beklemede</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{leaveCounts.pending}</div>
                <div className="text-[11px] text-slate-500 mt-1">onay bekleyen talep</div>
              </div>
              <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-emerald-100 text-emerald-700"><CheckCircle2 className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Onaylanan</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{leaveCounts.approved}</div>
                <div className="text-[11px] text-slate-500 mt-1">bu yıl içinde</div>
              </div>
              <div className="rounded-2xl border border-rose-100 bg-gradient-to-br from-rose-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-rose-100 text-rose-700"><XCircle className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Reddedilen</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{leaveCounts.rejected}</div>
                <div className="text-[11px] text-slate-500 mt-1">bu yıl içinde</div>
              </div>
            </div>

            <div className="grid lg:grid-cols-3 gap-6">
              {/* İzin Talebi Formu (Sol Taraf) */}
              <div className="lg:col-span-1">
                <Card className="rounded-2xl border-slate-200 shadow-sm h-full">
                  <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-4">
                    <CardTitle className="flex items-center gap-2 text-lg font-bold text-slate-800">
                      <div className="p-1.5 rounded-md bg-teal-100 text-teal-700"><Plus className="w-5 h-5" /></div>
                      Yeni İzin Talebi
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-5">
                    <form onSubmit={submitLeave} className="space-y-4">
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-600">Personel</Label>
                        <select
                          value={leaveForm.staff_id}
                          onChange={(e) => setLeaveForm({ ...leaveForm, staff_id: e.target.value })}
                          className="w-full rounded-lg border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-teal-500"
                          data-testid="select-leave-staff"
                        >
                          <option value="">Seçiniz...</option>
                          {staffDropdown.map((s) => (
                            <option key={s.id} value={s.id}>{s.name}</option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-600">İzin Türü</Label>
                        <select
                          value={leaveForm.leave_type}
                          onChange={(e) => setLeaveForm({ ...leaveForm, leave_type: e.target.value })}
                          className="w-full rounded-lg border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-teal-500"
                        >
                          {Object.entries(LEAVE_TYPE_LABEL).map(([k, v]) => (
                            <option key={k} value={k}>{v}</option>
                          ))}
                        </select>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label className="text-xs font-semibold text-slate-600">Başlangıç</Label>
                          <Input type="date" value={leaveForm.start_date} className="rounded-lg border-slate-200 bg-slate-50"
                            onChange={(e) => setLeaveForm({ ...leaveForm, start_date: e.target.value })} />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs font-semibold text-slate-600">Bitiş</Label>
                          <Input type="date" value={leaveForm.end_date} className="rounded-lg border-slate-200 bg-slate-50"
                            onChange={(e) => setLeaveForm({ ...leaveForm, end_date: e.target.value })} />
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-600">Açıklama (Opsiyonel)</Label>
                        <Textarea
                          rows={3}
                          value={leaveForm.reason}
                          className="rounded-lg border-slate-200 bg-slate-50 resize-none"
                          onChange={(e) => setLeaveForm({ ...leaveForm, reason: e.target.value })}
                          placeholder="Mazeret veya ek açıklama..."
                        />
                      </div>
                      <Button type="submit" disabled={creatingLeave} data-testid="btn-submit-leave" className="w-full bg-teal-600 hover:bg-teal-700 text-white rounded-lg shadow-sm py-5 mt-2">
                        {creatingLeave ? (
                          <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                          <Plus className="w-4 h-4 mr-2" />
                        )}
                        {creatingLeave ? 'Oluşturuluyor...' : 'Talep Oluştur'}
                      </Button>
                    </form>
                  </CardContent>
                </Card>
              </div>

              {/* Tablolar (Sağ Taraf) */}
              <div className="lg:col-span-2 space-y-6">
                
                {/* Personel İzin Bakiyesi */}
                <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden">
                  <CardHeader className="flex flex-row items-center justify-between bg-slate-50/50 border-b border-slate-100 pb-3 pt-4">
                    <CardTitle className="flex items-center gap-2 text-base font-bold text-slate-800">
                      <Calendar className="w-4 h-4 text-slate-500" />Personel İzin Bakiyesi ({new Date().getFullYear()})
                    </CardTitle>
                    <Button size="sm" variant="outline" className="h-8 rounded-lg" onClick={() => loadLeaveBalances(staffPage.items.map((s) => s.id))} disabled={balanceLoading}>
                      <RefreshCw className={`w-3.5 h-3.5 mr-1 text-slate-500 ${balanceLoading ? 'animate-spin' : ''}`} />Yenile
                    </Button>
                  </CardHeader>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left bg-white border-b border-slate-200">
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personel</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Hak Edilen</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Devreden</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Kullanılan</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Kalan (Yıllık)</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Hastalık (Kalan/Hak)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {staffPage.items.map((s) => {
                            const b = leaveBalances[s.id];
                            if (!b) return (
                              <tr key={s.id} className="bg-white">
                                <td className="py-3 px-4 font-medium">{s.name}</td>
                                <td colSpan={5} className="py-3 px-4 text-slate-400 text-xs text-center animate-pulse">Yükleniyor...</td>
                              </tr>
                            );
                            const remaining = b.annual?.remaining ?? 0;
                            const entitlement = (b.annual?.entitlement || 0) + (b.annual?.carry_over || 0);
                            const usagePct = entitlement > 0 ? (b.annual?.used / entitlement) * 100 : 0;
                            
                            let intent = 'success';
                            if (remaining <= 2) intent = 'danger';
                            else if (remaining <= 5) intent = 'warning';
                            
                            return (
                              <tr key={s.id} className="hover:bg-slate-50 transition-colors bg-white">
                                <td className="py-3 px-4 font-bold text-slate-800">{s.name}</td>
                                <td className="py-3 px-4 text-right text-slate-600 font-medium">{b.annual?.entitlement}</td>
                                <td className="py-3 px-4 text-right text-slate-500">{b.annual?.carry_over > 0 ? `+${b.annual?.carry_over}` : 0}</td>
                                <td className="py-3 px-4 text-right">
                                  <div className="flex flex-col items-end gap-1">
                                    <span className="font-semibold text-slate-700">{b.annual?.used}</span>
                                    <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                      <div className="h-full bg-amber-400 rounded-full" style={{ width: `${Math.min(100, usagePct)}%` }}></div>
                                    </div>
                                  </div>
                                </td>
                                <td className="py-3 px-4 text-right">
                                  <StatusBadge intent={intent}>{remaining} gün</StatusBadge>
                                </td>
                                <td className="py-3 px-4 text-right text-slate-600 font-medium">
                                  {b.sick?.remaining} <span className="text-slate-400 font-normal">/ {b.sick?.entitlement}</span>
                                </td>
                              </tr>
                            );
                          })}
                          {staffPage.items.length === 0 && (
                            <tr><td colSpan={6} className="py-8 text-center text-slate-400 italic">Personel yok</td></tr>
                          )}
                        </tbody>
                      </table>
                    {!staffPage.loading && staffPage.total > 0 && (
                      <div className="border-t border-slate-100 px-4 py-2">
                        <PaginationBar
                          page={staffPage.page}
                          totalPages={staffPage.totalPages}
                          total={staffPage.total}
                          limit={staffPage.limit}
                          onPageChange={staffPage.setPage}
                          onLimitChange={staffPage.setLimit}
                        />
                      </div>
                    )}
                    </div>
                  </CardContent>
                </Card>

                {/* İzin Talepleri */}
                <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden">
                  <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-3 pt-4">
                    <CardTitle className="text-base font-bold text-slate-800">İzin Talepleri</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left bg-white border-b border-slate-200">
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personel</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Tür</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Tarih Aralığı</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Gün</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Durum</th>
                            <th className="py-2.5 px-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">İşlem</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {leavePage.loading ? (
                            <tr><td colSpan={6} className="p-0"><SkeletonRow cols={6} rows={3} /></td></tr>
                          ) : (
                            <>
                              {leavePage.items.map((item) => (
                                <tr key={item.id} className="hover:bg-slate-50 transition-colors bg-white">
                                  <td className="py-3 px-4 font-bold text-slate-800">{item.staff_name}</td>
                                  <td className="py-3 px-4">
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-700">
                                      {LEAVE_TYPE_LABEL[item.leave_type] || item.leave_type}
                                    </span>
                                  </td>
                                  <td className="py-3 px-4 text-xs font-medium text-slate-600">
                                    {item.start_date.slice(5)} <span className="text-slate-400 px-1">→</span> {item.end_date.slice(5)}
                                  </td>
                                  <td className="py-3 px-4 text-right font-bold text-slate-700">{item.total_days}</td>
                                  <td className="py-3 px-4">
                                    <StatusBadge intent={STATUS_INTENT[item.status]}>{STATUS_LABEL[item.status] || item.status}</StatusBadge>
                                  </td>
                                  <td className="py-3 px-4 text-right">
                                    {item.status === 'pending' && (
                                      <div className="flex justify-end gap-1.5 flex-wrap">
                                        <Button size="sm" className="h-7 bg-indigo-600 hover:bg-indigo-700 text-white text-[11px] px-2 rounded-md" onClick={() => decideLeave(item.id, 'dept_approve')} data-testid={`btn-dept-approve-${item.id}`}>
                                          <CheckCircle2 className="w-3.5 h-3.5 mr-1" />Departman Onayı
                                        </Button>
                                        <Button size="sm" variant="outline" className="h-7 text-rose-600 border-rose-200 hover:bg-rose-50 text-[11px] px-2 rounded-md" onClick={() => decideLeave(item.id, 'reject')} data-testid={`btn-reject-${item.id}`}>
                                          <XCircle className="w-3.5 h-3.5 mr-1" />Reddet
                                        </Button>
                                      </div>
                                    )}
                                    {item.status === 'dept_approved' && (
                                      <div className="flex justify-end gap-1.5 flex-wrap">
                                        <Button size="sm" className="h-7 bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] px-2 rounded-md" onClick={() => decideLeave(item.id, 'approve')} data-testid={`btn-hr-final-${item.id}`}>
                                          <CheckCircle2 className="w-3.5 h-3.5 mr-1" />İK Final Onayı
                                        </Button>
                                        <Button size="sm" variant="outline" className="h-7 text-rose-600 border-rose-200 hover:bg-rose-50 text-[11px] px-2 rounded-md" onClick={() => decideLeave(item.id, 'reject')} data-testid={`btn-hr-reject-${item.id}`}>
                                          <XCircle className="w-3.5 h-3.5 mr-1" />Reddet
                                        </Button>
                                      </div>
                                    )}
                                  </td>
                                </tr>
                              ))}
                              {leavePage.items.length === 0 && (
                                <tr>
                                  <td colSpan={6} className="py-10">
                                    <div className="flex flex-col items-center justify-center text-slate-400">
                                      <Calendar className="w-8 h-8 mb-3 opacity-20" />
                                      <p className="font-medium text-slate-600">İzin talebi yok</p>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </>
                          )}
                        </tbody>
                      </table>
                    {!leavePage.loading && leavePage.total > 0 && (
                      <div className="border-t border-slate-100 px-4 py-2">
                        <PaginationBar
                          page={leavePage.page}
                          totalPages={leavePage.totalPages}
                          total={leavePage.total}
                          limit={leavePage.limit}
                          onPageChange={leavePage.setPage}
                          onLimitChange={leavePage.setLimit}
                        />
                      </div>
                    )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* === PERFORMANCE === */}
        <TabsContent value="performance" className="mt-4">
          <div className="space-y-6 mt-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-indigo-100 text-indigo-700"><Briefcase className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Toplam Değerlendirme</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{performancePage.total || 0}</div>
              </div>
              <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-emerald-100 text-emerald-700"><Star className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Ortalama Puan</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{(perfAvg || 0).toFixed(2)} <span className="text-lg text-slate-400 font-medium">/ 10.0</span></div>
              </div>
              <div className="rounded-2xl border border-amber-100 bg-gradient-to-br from-amber-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-amber-100 text-amber-700"><Award className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Yüksek Performans (8+)</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{perfMetrics?.high_performers || 0}</div>
                <div className="text-[11px] text-slate-500 mt-1">personel</div>
              </div>
              <div className="rounded-2xl border border-rose-100 bg-gradient-to-br from-rose-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-rose-100 text-rose-700"><AlertCircle className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Gelişim Bekleyen ({"<"}5)</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{perfMetrics?.low_performers || 0}</div>
                <div className="text-[11px] text-slate-500 mt-1">personel</div>
              </div>
            </div>

            <div className="grid lg:grid-cols-3 gap-6">
              {/* Değerlendirme Formu */}
              <div className="lg:col-span-1">
                <Card className="rounded-2xl border-slate-200 shadow-sm h-full">
                  <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-4">
                    <CardTitle className="flex items-center gap-2 text-lg font-bold text-slate-800">
                      <div className="p-1.5 rounded-md bg-teal-100 text-teal-700"><Star className="w-5 h-5" /></div>
                      Yeni Değerlendirme
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-5">
                    <form onSubmit={submitPerformance} className="space-y-4">
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-600">Personel</Label>
                        <select
                          value={perfForm.staff_id}
                          onChange={(e) => setPerfForm({ ...perfForm, staff_id: e.target.value })}
                          className="w-full rounded-lg border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-teal-500"
                        >
                          <option value="">Seçiniz...</option>
                          {staffDropdown.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                        </select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-600">Şablon (opsiyonel)</Label>
                        <select
                          value={perfForm.template_id}
                          onChange={(e) => onTemplateChange(e.target.value)}
                          className="w-full rounded-lg border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-teal-500"
                        >
                          <option value="">— Şablon yok —</option>
                          {perfTemplates.map((tpl) => (
                            <option key={tpl.id} value={tpl.id}>{tpl.name} ({tpl.competencies?.length || 0} yetkinlik)</option>
                          ))}
                        </select>
                      </div>
                      {perfForm.template_id && Object.keys(perfForm.competency_scores || {}).length > 0 && (
                        <div className="rounded-xl border border-sky-100 bg-sky-50/50 p-4 space-y-3">
                          <div className="text-xs font-bold text-sky-800 flex items-center gap-1.5 uppercase tracking-wider">
                            <ListChecks className="w-4 h-4" />Yetkinlik Puanları (0–10)
                          </div>
                          <div className="grid gap-3 md:grid-cols-2">
                            {Object.entries(perfForm.competency_scores).map(([name, score]) => (
                              <div key={name} className="space-y-1">
                                <Label className="text-[11px] font-semibold text-slate-600 leading-tight">{name}</Label>
                                <Input type="number" min="0" max="10" step="0.1" value={score}
                                  className="h-8 text-sm rounded-lg border-slate-200"
                                  onChange={(e) => setCompetencyScore(name, e.target.value)} />
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label className="text-xs font-semibold text-slate-600">Dönem</Label>
                          <Input value={perfForm.period} onChange={(e) => setPerfForm({ ...perfForm, period: e.target.value })} placeholder="2026 Q1" className="rounded-lg border-slate-200 bg-slate-50" />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs font-semibold text-slate-600">Genel Puan (0–10)</Label>
                          <Input type="number" min="0" max="10" step="0.1"
                            value={perfForm.overall_score}
                            className="rounded-lg border-slate-200 bg-slate-50 font-bold"
                            onChange={(e) => setPerfForm({ ...perfForm, overall_score: e.target.value })} />
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-600">Güçlü Yönler</Label>
                        <Textarea rows={2} value={perfForm.strengths} className="rounded-lg border-slate-200 bg-slate-50 resize-none text-sm"
                          onChange={(e) => setPerfForm({ ...perfForm, strengths: e.target.value })} />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-600">Gelişim Alanları</Label>
                        <Textarea rows={2} value={perfForm.improvement_areas} className="rounded-lg border-slate-200 bg-slate-50 resize-none text-sm"
                          onChange={(e) => setPerfForm({ ...perfForm, improvement_areas: e.target.value })} />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-600">Hedefler</Label>
                        <Textarea rows={2} value={perfForm.goals} className="rounded-lg border-slate-200 bg-slate-50 resize-none text-sm"
                          onChange={(e) => setPerfForm({ ...perfForm, goals: e.target.value })} />
                      </div>
                      <Button type="submit" disabled={creatingPerf} className="w-full bg-teal-600 hover:bg-teal-700 text-white rounded-lg shadow-sm py-5 mt-2">
                        {creatingPerf ? (
                          <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                          <Plus className="w-4 h-4 mr-2" />
                        )}
                        {creatingPerf ? 'Kaydediliyor...' : 'Değerlendirme Kaydet'}
                      </Button>
                    </form>
                  </CardContent>
                </Card>
              </div>

              {/* Geçmiş Değerlendirmeler */}
              <div className="lg:col-span-2">
                <Card className="rounded-2xl border-slate-200 shadow-sm h-full overflow-hidden flex flex-col">
                  <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-3 pt-4">
                    <CardTitle className="text-base font-bold text-slate-800 flex items-center gap-2">
                      <ListChecks className="w-4 h-4 text-slate-500" />Değerlendirme Geçmişi
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0 flex-1 flex flex-col">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left bg-white border-b border-slate-200">
                            <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Tarih</th>
                            <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personel</th>
                            <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Dönem</th>
                            <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Puan</th>
                            <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Özet</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {performancePage.loading ? (
                            <tr><td colSpan={5} className="p-0"><SkeletonRow cols={5} rows={5} /></td></tr>
                          ) : (
                            <>
                              {performancePage.items.map((item) => (
                                <tr key={item.id} className="hover:bg-slate-50 transition-colors bg-white">
                                  <td className="py-3 px-5 text-xs text-slate-500">{(item.reviewed_at || '').slice(0, 10)}</td>
                                  <td className="py-3 px-5 font-bold text-slate-800">{item.staff_name}</td>
                                  <td className="py-3 px-5">
                                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-700">
                                      {item.period || '—'}
                                    </span>
                                  </td>
                                  <td className="py-3 px-5 text-right">
                                    <div className="flex items-center justify-end gap-1.5">
                                      <Star className={`w-3.5 h-3.5 ${item.overall_score >= 8 ? 'text-amber-500 fill-amber-500' : item.overall_score >= 5 ? 'text-emerald-500 fill-emerald-500' : 'text-rose-500 fill-rose-500'}`} />
                                      <span className="font-bold text-slate-700">{Number(item.overall_score).toFixed(1)}</span>
                                    </div>
                                  </td>
                                  <td className="py-3 px-5">
                                    <div className="max-w-[200px] lg:max-w-xs text-xs text-slate-600 line-clamp-2" title={item.strengths || item.goals || '—'}>
                                      {item.strengths || item.goals || '—'}
                                    </div>
                                  </td>
                                </tr>
                              ))}
                              {performancePage.items.length === 0 && (
                                <tr>
                                  <td colSpan={5} className="py-12">
                                    <div className="flex flex-col items-center justify-center text-slate-400">
                                      <Briefcase className="w-10 h-10 mb-3 opacity-20" />
                                      <p className="font-medium text-slate-600">Değerlendirme bulunamadı</p>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </>
                          )}
                        </tbody>
                      </table>
                    </div>
                    {!performancePage.loading && performancePage.total > 0 && (
                      <div className="mt-auto border-t border-slate-100 px-5 py-3 bg-slate-50/50">
                        <PaginationBar
                          page={performancePage.page}
                          totalPages={performancePage.totalPages}
                          total={performancePage.total}
                          limit={performancePage.limit}
                          onPageChange={performancePage.setPage}
                          onLimitChange={performancePage.setLimit}
                        />
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* === MESAİ ONAYI === */}
        <TabsContent value="overtime" className="mt-4">
          <div className="space-y-6 mt-6">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-2xl border border-amber-100 bg-gradient-to-br from-amber-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-amber-100 text-amber-700"><Timer className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Bekleyen Talep</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{overtimeCounts.pending || 0}</div>
                <div className="text-[11px] text-slate-500 mt-1">onay bekliyor</div>
              </div>
              <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-emerald-100 text-emerald-700"><CheckCircle2 className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Onaylanan</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{overtimeCounts.approved || 0}</div>
                <div className="text-[11px] text-slate-500 mt-1">bu yıl</div>
              </div>
              <div className="rounded-2xl border border-rose-100 bg-gradient-to-br from-rose-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-rose-100 text-rose-700"><XCircle className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Reddedilen</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{overtimeCounts.rejected || 0}</div>
              </div>
            </div>

            {severanceCap && (
              <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden">
                <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-4">
                  <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-base font-bold text-slate-800">
                      <div className="p-1.5 rounded-md bg-sky-100 text-sky-700"><Timer className="w-4 h-4" /></div>
                      Kıdem Tazminatı Tavanı <span className="text-xs font-normal text-slate-500 bg-slate-200/50 px-2 py-0.5 rounded-full">(Tenant Ayarı)</span>
                    </span>
                    <Button size="sm" variant="outline" onClick={updateSeveranceCap} disabled={savingSeverance} className="rounded-lg">
                      {savingSeverance ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : null}
                      {savingSeverance ? 'Kaydediliyor…' : 'Tavanı Güncelle'}
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-5">
                  <div className="grid gap-4 md:grid-cols-3 text-sm">
                    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm relative overflow-hidden">
                      <div className="text-xs font-semibold text-slate-500">Günlük Brüt Tavan</div>
                      <div className="text-2xl font-bold text-slate-900 mt-2">
                        ₺{Number(severanceCap.daily_cap || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                      </div>
                      {severanceCap.is_default && (
                        <div className="absolute top-0 right-0 bg-amber-100 text-amber-700 text-[9px] font-bold px-2 py-0.5 rounded-bl-lg">VARSAYILAN</div>
                      )}
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                      <div className="text-xs font-semibold text-slate-500">30 Günlük Tavan (yaklaşık)</div>
                      <div className="text-2xl font-bold text-slate-900 mt-2">
                        ₺{Number(severanceCap.monthly_cap_estimate || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col justify-center">
                      <div className="text-xs font-semibold text-slate-500">Son Güncelleme</div>
                      <div className="text-sm font-medium text-slate-700 mt-1 flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        {severanceCap.updated_at ? severanceCap.updated_at.slice(0, 10) : 'Hiç güncellenmemiş'}
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 mt-4 bg-slate-50 p-3 rounded-lg border border-slate-100 flex items-start gap-2">
                    <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                    <p>{severanceCap.note}</p>
                  </div>
                </CardContent>
              </Card>
            )}

            {taxRates && (
              <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden">
                <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-4">
                  <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-base font-bold text-slate-800">
                      <div className="p-1.5 rounded-md bg-indigo-100 text-indigo-700"><AlertCircle className="w-4 h-4" /></div>
                      Vergi Oranlarını Güncelle <span className="text-xs font-normal text-slate-500 bg-slate-200/50 px-2 py-0.5 rounded-full">(Bordro Kesintileri)</span>
                    </span>
                    {taxRates.can_edit && (
                      <Button size="sm" variant="outline" onClick={updateTaxRates} disabled={savingTaxRates} className="rounded-lg">
                        {savingTaxRates ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : null}
                        {savingTaxRates ? 'Kaydediliyor…' : 'Oranları Kaydet'}
                      </Button>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-5">
                  <div className="grid gap-4 md:grid-cols-4 text-sm">
                    {[
                      { key: 'sgk_employee', label: 'SGK İşçi Payı' },
                      { key: 'unemployment', label: 'İşsizlik Sigortası' },
                      { key: 'income_tax', label: 'Gelir Vergisi' },
                      { key: 'stamp_tax', label: 'Damga Vergisi' },
                    ].map(({ key, label }) => {
                      const isCustom = taxRatesForm
                        && Number(taxRatesForm[key]) !== Number(taxRates.defaults?.[key]);
                      return (
                        <div key={key} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm relative overflow-hidden transition-all focus-within:ring-2 focus-within:ring-teal-500 focus-within:border-teal-500">
                          <div className="text-xs font-semibold text-slate-600 mb-2">{label}</div>
                          <div className="flex items-center gap-2">
                            <Input
                              type="number"
                              step="0.001"
                              min="0"
                              max="100"
                              className="h-9 font-bold text-lg bg-slate-50 border-slate-200 rounded-lg text-slate-800 focus:bg-white"
                              value={taxRatesForm ? (taxRatesForm[key] ?? '') : ''}
                              disabled={!taxRates.can_edit}
                              onChange={(e) => setTaxRatesForm((f) => ({ ...(f || {}), [key]: e.target.value }))}
                            />
                            <span className="text-slate-400 font-bold">%</span>
                          </div>
                          {isCustom ? (
                            <div className="absolute top-0 right-0 bg-sky-100 text-sky-700 text-[9px] font-bold px-2 py-0.5 rounded-bl-lg">ÖZEL</div>
                          ) : (
                            <div className="absolute top-0 right-0 bg-slate-100 text-slate-500 text-[9px] font-bold px-2 py-0.5 rounded-bl-lg">VARSAYILAN</div>
                          )}
                          {isCustom && (
                            <div className="text-[10px] mt-2 text-sky-600 font-medium">
                              Varsayılan: %{Number(taxRates.defaults?.[key]).toLocaleString('tr-TR', { maximumFractionDigits: 3 })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-4 mt-5 bg-slate-50 p-3 rounded-lg border border-slate-100">
                    <div className="text-xs text-slate-500 flex items-start gap-2">
                      <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                      <p>{taxRates.note}</p>
                    </div>
                    <div className="text-xs font-medium text-slate-500 bg-white px-3 py-1.5 rounded-md border border-slate-200 shadow-sm">
                      Son güncelleme: {taxRates.updated_at ? taxRates.updated_at.slice(0, 10) : 'Hiç güncellenmemiş'}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden flex flex-col">
              <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-3 pt-4">
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-base font-bold text-slate-800">
                    <Timer className="w-4 h-4 text-slate-500" />Mesai Talepleri
                  </span>
                  <span className="text-xs text-slate-500 font-normal bg-white border border-slate-200 px-2 py-1 rounded-md shadow-sm">
                    İş K. m.41/3 — yıllık 270 saat üst sınırı otomatik kontrol edilir
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0 flex-1 flex flex-col">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left bg-white border-b border-slate-200">
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personel</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Tarih</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Saat</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Sebep</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Durum</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">İstek</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">İşlem</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {overtimeItems.map((req) => (
                        <tr key={req.id} className="hover:bg-slate-50 transition-colors bg-white">
                          <td className="py-3 px-5 font-bold text-slate-800">{req.staff_name}</td>
                          <td className="py-3 px-5 text-slate-600">{req.work_date}</td>
                          <td className="py-3 px-5 text-right font-bold text-slate-700">{req.hours}h</td>
                          <td className="py-3 px-5 text-slate-600 text-xs max-w-xs">{req.reason}</td>
                          <td className="py-3 px-5">
                            <StatusBadge intent={STATUS_INTENT[req.status] || 'neutral'}>
                              {STATUS_LABEL[req.status] || req.status}
                            </StatusBadge>
                            {req.decision_note && (
                              <div className="text-[10px] text-slate-500 mt-1 max-w-[160px] truncate" title={req.decision_note}>
                                {req.decision_note}
                              </div>
                            )}
                          </td>
                          <td className="py-3 px-5 text-xs text-slate-500">{(req.requested_at || '').slice(0, 10)}</td>
                          <td className="py-3 px-5 text-right">
                            {req.status === 'pending' && (
                              <div className="flex justify-end gap-2 flex-wrap">
                                <Button size="sm" onClick={() => decideOvertime(req, 'dept_approve')} data-testid={`ot-dept-${req.id}`} className="bg-teal-600 hover:bg-teal-700 text-white shadow-sm">
                                  <Check className="w-3.5 h-3.5 mr-1" />Dept Onay
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideOvertime(req, 'reject')} data-testid={`ot-reject-${req.id}`} className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200">
                                  <X className="w-3.5 h-3.5 mr-1" />Reddet
                                </Button>
                              </div>
                            )}
                            {req.status === 'dept_approved' && (
                              <div className="flex justify-end gap-2 flex-wrap">
                                <Button size="sm" onClick={() => decideOvertime(req, 'approve')} data-testid={`ot-hr-final-${req.id}`} className="bg-teal-600 hover:bg-teal-700 text-white shadow-sm">
                                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" />HR Final (Bordro)
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideOvertime(req, 'reject')} data-testid={`ot-hr-reject-${req.id}`} className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200">
                                  <X className="w-3.5 h-3.5 mr-1" />Reddet
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
          <div className="space-y-6 mt-6">
            {/* Akış açıklaması */}
            <div className="rounded-xl border border-sky-100 bg-gradient-to-r from-sky-50 to-white p-4 shadow-sm flex items-start gap-3">
              <div className="p-2 bg-sky-100 text-sky-600 rounded-lg shrink-0 mt-0.5"><Info className="w-5 h-5" /></div>
              <div className="text-slate-700 text-sm space-y-1.5 leading-relaxed">
                <p><strong>Bu modül dış yayınlama (LinkedIn/Kariyer.net) yapmaz.</strong> Departman müdürü personel ihtiyacını bildirir, HR yöneticisi onaylar, onaylı pozisyonlara aday eklenip süreç (görüşme/teklif/işe alım) takip edilir.</p>
                <p>Talep oluşturulduğunda HR yöneticilerine bildirim gider. Karar (onay/red) talep sahibine bildirim olarak döner.</p>
              </div>
            </div>

            {/* KPI özet */}
            <div className="grid gap-4 md:grid-cols-4">
              <div className="rounded-2xl border border-amber-100 bg-gradient-to-br from-amber-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-amber-100 text-amber-700"><Timer className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Onay Bekleyen</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{jobItems.filter((j) => j.status === 'pending_approval').length}</div>
                <div className="text-[11px] text-slate-500 mt-1">talep</div>
              </div>
              <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-emerald-100 text-emerald-700"><CheckCircle2 className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Açık Pozisyon</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{jobItems.filter((j) => j.status === 'active').length}</div>
                <div className="text-[11px] text-slate-500 mt-1">aktif</div>
              </div>
              <div className="rounded-2xl border border-sky-100 bg-gradient-to-br from-sky-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-sky-100 text-sky-700"><Users className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Toplam İhtiyaç</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">
                  {jobItems.filter((j) => ['pending_approval', 'active'].includes(j.status)).reduce((sum, j) => sum + (j.headcount_needed || 1), 0)}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">kişi</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-slate-200 text-slate-700"><UserPlus className="w-5 h-5" /></div>
                  <div className="text-sm font-semibold text-slate-600">Toplam Aday</div>
                </div>
                <div className="text-3xl font-bold text-slate-900">{jobItems.reduce((sum, j) => sum + (j.applicants_count || 0), 0)}</div>
                <div className="text-[11px] text-slate-500 mt-1">aday</div>
              </div>
            </div>

            <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden">
              <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-4">
                <CardTitle className="flex items-center gap-2 text-lg font-bold text-slate-800">
                  <div className="p-1.5 rounded-md bg-teal-100 text-teal-700"><Plus className="w-5 h-5" /></div>
                  Yeni Personel Talebi
                </CardTitle>
                <p className="text-xs font-medium text-slate-500 mt-1 pl-9">
                  Departman müdürü olarak doldurun. Onay sonrası aday eklemeye açılır.
                </p>
              </CardHeader>
              <CardContent className="p-5">
                <form onSubmit={submitJob} className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">Pozisyon <span className="text-rose-500">*</span></Label>
                    <Input required value={jobForm.title} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setJobForm({ ...jobForm, title: e.target.value })}
                      placeholder="Örn: Resepsiyonist" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">Departman <span className="text-rose-500">*</span></Label>
                    <Input required value={jobForm.department} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setJobForm({ ...jobForm, department: e.target.value })}
                      placeholder="Örn: front_desk" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">İhtiyaç Sayısı (Kişi)</Label>
                    <Input type="number" min="1" max="50" value={jobForm.headcount_needed} className="rounded-lg border-slate-200 bg-slate-50 font-bold text-sm focus:bg-white"
                      onChange={(e) => setJobForm({ ...jobForm, headcount_needed: parseInt(e.target.value) || 1 })} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">Aciliyet</Label>
                    <select value={jobForm.urgency}
                      onChange={(e) => setJobForm({ ...jobForm, urgency: e.target.value })}
                      className="w-full rounded-lg border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:bg-white focus:ring-teal-500">
                      <option value="low">Düşük</option>
                      <option value="normal">Normal</option>
                      <option value="high">Yüksek</option>
                      <option value="critical">Kritik</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">Çalışma Şekli</Label>
                    <select value={jobForm.employment_type}
                      onChange={(e) => setJobForm({ ...jobForm, employment_type: e.target.value })}
                      className="w-full rounded-lg border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:bg-white focus:ring-teal-500">
                      <option value="full_time">Tam Zamanlı</option>
                      <option value="part_time">Yarı Zamanlı</option>
                      <option value="seasonal">Sezonluk</option>
                      <option value="contract">Sözleşmeli</option>
                      <option value="intern">Stajyer</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">İhtiyaç Tarihi</Label>
                    <Input type="date" value={jobForm.needed_by} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setJobForm({ ...jobForm, needed_by: e.target.value })} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">Ücret Aralığı (Öneri)</Label>
                    <Input value={jobForm.salary_range} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setJobForm({ ...jobForm, salary_range: e.target.value })}
                      placeholder="22.000 – 30.000 TL" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">Lokasyon</Label>
                    <Input value={jobForm.location} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setJobForm({ ...jobForm, location: e.target.value })} />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">Gerekçe (HR'a not)</Label>
                    <Textarea rows={2} value={jobForm.justification} className="rounded-lg border-slate-200 bg-slate-50 text-sm resize-none focus:bg-white"
                      onChange={(e) => setJobForm({ ...jobForm, justification: e.target.value })}
                      placeholder="Örn: yaz sezonu için ek personel; mevcut kadronun yetersizliği vb." />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-600">Pozisyon Açıklaması</Label>
                    <Textarea rows={3} value={jobForm.description} className="rounded-lg border-slate-200 bg-slate-50 text-sm resize-none focus:bg-white"
                      onChange={(e) => setJobForm({ ...jobForm, description: e.target.value })}
                      placeholder="Sorumluluklar, beklentiler, gerekli niteliklere dair detaylar" />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 flex justify-end mt-2">
                    <Button type="submit" disabled={creatingJob} className="bg-teal-600 hover:bg-teal-700 text-white rounded-lg shadow-sm py-5 px-6">
                      {creatingJob ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
                      {creatingJob ? 'Gönderiliyor...' : 'Talep Oluştur (HR\'a Gönder)'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card className="rounded-2xl border-slate-200 shadow-sm overflow-hidden flex flex-col">
              <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-3 pt-4">
                <CardTitle className="text-base font-bold text-slate-800 flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-slate-500" />Talepler & Açık Pozisyonlar
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0 flex-1 flex flex-col">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left bg-white border-b border-slate-200">
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Pozisyon</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Departman</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-center">İhtiyaç</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Aciliyet</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">İhtiyaç Tarihi</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Talep Eden</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Durum</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-center">Aday</th>
                        <th className="py-2.5 px-5 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">İşlem</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {jobItems.map((job) => (
                        <tr key={job.id} className="hover:bg-slate-50 transition-colors bg-white">
                          <td className="py-3 px-5">
                            <div className="font-bold text-slate-800">{job.title}</div>
                            {job.justification && (
                              <div className="text-xs text-slate-500 max-w-xs truncate" title={job.justification}>
                                {job.justification}
                              </div>
                            )}
                          </td>
                          <td className="py-3 px-5 capitalize text-slate-600 font-medium">{job.department}</td>
                          <td className="py-3 px-5 text-center font-bold text-slate-700">{job.headcount_needed || 1}</td>
                          <td className="py-3 px-5">
                            {job.urgency === 'critical' && <StatusBadge intent="danger">Kritik</StatusBadge>}
                            {job.urgency === 'high' && <StatusBadge intent="warning">Yüksek</StatusBadge>}
                            {job.urgency === 'normal' && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-600">Normal</span>}
                            {job.urgency === 'low' && <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-500">Düşük</span>}
                          </td>
                          <td className="py-3 px-5 text-slate-600 text-xs">{job.needed_by || '—'}</td>
                          <td className="py-3 px-5 text-slate-600 text-xs">{job.created_by_name || '—'}</td>
                          <td className="py-3 px-5">
                            {job.status === 'pending_approval' && <StatusBadge intent="warning">Onay Bekliyor</StatusBadge>}
                            {job.status === 'active' && <StatusBadge intent="success">Açık</StatusBadge>}
                            {job.status === 'rejected' && <StatusBadge intent="danger">Reddedildi</StatusBadge>}
                            {job.status === 'closed' && <StatusBadge intent="neutral">Kapalı</StatusBadge>}
                          </td>
                          <td className="py-3 px-5 text-center">
                            <button type="button" onClick={() => openApplicants(job)}
                              className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-sky-50 text-sky-600 font-bold hover:bg-sky-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                              disabled={job.status === 'pending_approval'}>
                              {job.applicants_count || 0}
                            </button>
                          </td>
                          <td className="py-3 px-5 text-right">
                            <div className="flex justify-end gap-2 flex-wrap">
                              {job.status === 'pending_approval' && (
                                <>
                                  <Button size="sm" onClick={() => decideJob(job.id, 'approve')} title="HR yöneticisi olarak onayla" className="bg-teal-600 hover:bg-teal-700 text-white shadow-sm">
                                    <ThumbsUp className="w-3.5 h-3.5 mr-1" />Onayla
                                  </Button>
                                  <Button size="sm" variant="outline" onClick={() => decideJob(job.id, 'reject')} className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200">
                                    <ThumbsDown className="w-3.5 h-3.5 mr-1" />Reddet
                                  </Button>
                                </>
                              )}
                              {job.status === 'active' && (
                                <>
                                  <Button size="sm" variant="outline" onClick={() => openApplicants(job)} className="border-sky-200 text-sky-700 hover:bg-sky-50">
                                    <UserPlus className="w-3.5 h-3.5 mr-1" />Aday İşlemleri
                                  </Button>
                                  <Button size="sm" variant="outline" onClick={() => closeJob(job.id)} title="Pozisyonu Kapat" className="text-slate-500 hover:text-slate-700 hover:bg-slate-50">
                                    <XCircle className="w-4 h-4" />
                                  </Button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {jobItems.length === 0 && (
                        <tr>
                          <td colSpan={9} className="py-12">
                            <div className="flex flex-col items-center justify-center text-slate-400">
                              <Briefcase className="w-10 h-10 mb-3 opacity-20" />
                              <p className="font-medium text-slate-600">Henüz talep yok. Yukarıdaki formdan ilk personel talebini oluşturun.</p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Adaylar Modal */}
          <Dialog open={applicantsDialog.open} onOpenChange={(o) => !o && setApplicantsDialog({ open: false, job: null, list: [], counts: {} })}>
            <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto p-0 rounded-2xl">
              <div className="bg-slate-50/80 border-b border-slate-100 p-6 flex flex-col gap-3">
                <DialogTitle className="text-xl font-bold text-slate-800 flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-sky-100 text-sky-700"><Users className="w-5 h-5" /></div>
                  Adaylar — {applicantsDialog.job?.title}
                  <span className="text-sm text-slate-500 font-medium ml-2 px-2 py-0.5 bg-white rounded-md border border-slate-200">
                    {applicantsDialog.job?.department}
                  </span>
                </DialogTitle>
                
                {/* Aday durum sayaçları */}
                <div className="flex flex-wrap gap-2">
                  {Object.entries(applicantsDialog.counts || {}).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 rounded-lg bg-white border border-slate-200 px-3 py-1.5 shadow-sm">
                      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{k}</span>
                      <span className="text-sm font-bold text-slate-800 bg-slate-100 px-2 rounded-md">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-6 space-y-6">
                {/* Yeni aday formu */}
                <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
                  <div className="text-sm font-bold text-slate-800 flex items-center gap-2 mb-4">
                    <div className="p-1 rounded-md bg-teal-100 text-teal-700"><UserPlus className="w-4 h-4" /></div>
                    Yeni Aday Ekle
                  </div>
                  <form onSubmit={submitApplicant} className="grid gap-3 md:grid-cols-2">
                    <Input placeholder="Ad Soyad *" value={applicantForm.name} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setApplicantForm({ ...applicantForm, name: e.target.value })} />
                    <Input placeholder="E-posta" type="email" value={applicantForm.email} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setApplicantForm({ ...applicantForm, email: e.target.value })} />
                    <Input placeholder="Telefon" value={applicantForm.phone} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setApplicantForm({ ...applicantForm, phone: e.target.value })} />
                    <Input placeholder="CV URL (opsiyonel)" value={applicantForm.cv_url} className="rounded-lg border-slate-200 bg-slate-50 text-sm focus:bg-white"
                      onChange={(e) => setApplicantForm({ ...applicantForm, cv_url: e.target.value })} />
                    <div className="md:col-span-2">
                      <Textarea rows={2} placeholder="Notlar (deneyim, görüşme izlenimi, vb.)" className="rounded-lg border-slate-200 bg-slate-50 text-sm resize-none focus:bg-white"
                        value={applicantForm.notes}
                        onChange={(e) => setApplicantForm({ ...applicantForm, notes: e.target.value })} />
                    </div>
                    <div className="md:col-span-2 flex justify-end mt-1">
                      <Button type="submit" disabled={savingApplicant} className="bg-teal-600 hover:bg-teal-700 text-white rounded-lg px-6">
                        {savingApplicant ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
                        {savingApplicant ? 'Ekleniyor...' : 'Adayı Kaydet'}
                      </Button>
                    </div>
                  </form>
                </div>

                {/* Aday listesi */}
                <div>
                  <div className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
                    <ListChecks className="w-4 h-4 text-slate-500" /> Aday Listesi 
                    <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full text-xs">{applicantsDialog.list.length}</span>
                  </div>
                  <div className="space-y-3">
                    {applicantsDialog.list.map((a) => (
                      <div key={a.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300 transition-colors flex flex-col md:flex-row md:items-start justify-between gap-4">
                        <div className="space-y-2 flex-1">
                          <div className="font-bold text-slate-800 text-base">{a.name}</div>
                          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 font-medium">
                            {a.email && <div className="flex items-center gap-1"><Mail className="w-3.5 h-3.5 text-slate-400" /> {a.email}</div>}
                            {a.phone && <div className="flex items-center gap-1"><Phone className="w-3.5 h-3.5 text-slate-400" /> {a.phone}</div>}
                          </div>
                          {a.notes && <div className="text-sm text-slate-600 bg-slate-50 p-2 rounded-lg border border-slate-100 mt-2">{a.notes}</div>}
                          {a.cv_url && (
                            <a href={a.cv_url} target="_blank" rel="noreferrer"
                              className="inline-flex items-center gap-1.5 text-xs font-semibold text-sky-600 hover:text-sky-700 hover:bg-sky-50 px-2 py-1 rounded-md transition-colors mt-2">
                              <ExternalLink className="w-3.5 h-3.5" /> CV Görüntüle
                            </a>
                          )}
                        </div>
                        <div className="flex flex-row md:flex-col items-center md:items-end justify-between md:justify-start gap-3 w-full md:w-auto shrink-0 border-t md:border-t-0 pt-3 md:pt-0">
                          <select value={a.status || 'new'}
                            onChange={(e) => setApplicantStatus(a.id, e.target.value)}
                            className="text-sm font-semibold rounded-lg border-slate-200 bg-slate-50 px-3 py-1.5 focus:ring-teal-500 focus:bg-white w-full md:w-auto">
                            <option value="new">Yeni</option>
                            <option value="screening">Eleme</option>
                            <option value="interview">Görüşme</option>
                            <option value="offer">Teklif</option>
                            <option value="hired">İşe Alındı</option>
                            <option value="rejected">Reddedildi</option>
                          </select>
                          <span className="text-[11px] font-medium text-slate-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {(a.created_at || '').slice(0, 10)}
                          </span>
                        </div>
                      </div>
                    ))}
                    {applicantsDialog.list.length === 0 && (
                      <div className="py-12 rounded-xl border border-dashed border-slate-200 bg-slate-50 flex flex-col items-center justify-center text-slate-400">
                        <Users className="w-10 h-10 mb-3 opacity-20" />
                        <p className="font-medium text-slate-600">Henüz aday yok</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <DialogFooter className="p-6 border-t border-slate-100 bg-slate-50/50">
                <Button variant="outline" onClick={() => setApplicantsDialog({ open: false, job: null, list: [], counts: {} })} className="rounded-lg">
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
