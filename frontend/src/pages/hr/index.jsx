import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Clock, Calendar, DollarSign, Briefcase, UserPlus, Download, Users, FileSpreadsheet, RefreshCw, Plus, CheckCircle2, XCircle, TrendingUp, ExternalLink, FileDown, Award, Info, AlertCircle, Bell, FileText, ClipboardList, Send, ThumbsUp, ThumbsDown, Timer, Check, X, Package, GraduationCap } from 'lucide-react';
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
import HRAttendanceTab from './HRAttendanceTab';
import HRPayrollTab from './HRPayrollTab';
import HRLeaveTab from './HRLeaveTab';
import HRPerformanceTab from './HRPerformanceTab';
import HROvertimeTab from './HROvertimeTab';
import HRRecruitmentTab from './HRRecruitmentTab';
const LEAVE_TYPE_LABEL = {
  annual: 'Yıllık İzin',
  sick: 'Hastalık',
  maternity: 'Doğum',
  paternity: 'Babalık',
  unpaid: 'Ücretsiz',
  bereavement: 'Vefat',
  excused: 'Mazeret'
};
const STATUS_INTENT = {
  pending: 'warning',
  dept_approved: 'info',
  approved: 'success',
  hr_approved: 'success',
  rejected: 'danger',
  active: 'success',
  closed: 'neutral'
};
const STATUS_LABEL = {
  pending: 'Beklemede',
  dept_approved: 'Dept Onaylı (HR Bekliyor)',
  approved: 'Onaylandı',
  hr_approved: 'Onaylandı',
  rejected: 'Reddedildi',
  active: 'Aktif',
  closed: 'Kapalı'
};
const todayMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};
const HRComplete = () => {
  const {
    t
  } = useTranslation();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('attendance');
  const [refreshing, setRefreshing] = useState(false);

  // Staff (dropdown data only)
  const [staffDropdown, setStaffDropdown] = useState([]);
  const [selectedStaffId, setSelectedStaffId] = useState('');

  // Attendance
  const [attendanceSummary, setAttendanceSummary] = useState(null);
  const [attendanceRecords, setAttendanceRecords] = useState([]);
  const [recordsRange, setRecordsRange] = useState({
    start: '',
    end: ''
  });

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
  const staffPage = useHRPagination('/hr/staff', {}, {
    enabled: activeTab === 'leave' || activeTab === 'performance' || activeTab === 'attendance' || activeTab === 'payroll'
  });
  const leavePage = useHRPagination('/hr/leave-requests', {}, {
    enabled: activeTab === 'leave'
  });
  const performancePage = useHRPagination('/hr/performance', {}, {
    enabled: activeTab === 'performance'
  });

  // Leave Dropdown & Form
  const [leaveCounts, setLeaveCounts] = useState({
    pending: 0,
    approved: 0,
    rejected: 0
  });
  const [leaveForm, setLeaveForm] = useState({
    staff_id: '',
    leave_type: 'annual',
    start_date: '',
    end_date: '',
    reason: ''
  });
  const [creatingLeave, setCreatingLeave] = useState(false);

  // Performance Form
  const [perfAvg, setPerfAvg] = useState(0);
  const [perfTemplates, setPerfTemplates] = useState([]);
  const [perfForm, setPerfForm] = useState({
    staff_id: '',
    period: '',
    overall_score: '',
    strengths: '',
    improvement_areas: '',
    goals: '',
    template_id: '',
    competency_scores: {}
  });
  const [creatingPerf, setCreatingPerf] = useState(false);

  // Overtime requests (Mesai Onayı)
  const [overtimeItems, setOvertimeItems] = useState([]);
  const [overtimeCounts, setOvertimeCounts] = useState({
    pending: 0,
    approved: 0,
    rejected: 0
  });

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
    title: '',
    department: '',
    employment_type: 'full_time',
    location: '',
    salary_range: '',
    description: '',
    headcount_needed: 1,
    urgency: 'normal',
    justification: '',
    needed_by: ''
  });
  const [creatingJob, setCreatingJob] = useState(false);
  const [applicantsDialog, setApplicantsDialog] = useState({
    open: false,
    job: null,
    list: [],
    counts: {}
  });
  const [applicantForm, setApplicantForm] = useState({
    name: '',
    email: '',
    phone: '',
    notes: '',
    cv_url: ''
  });
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
      const res = await axios.get('/hr/staff', {
        params: {
          limit: 500,
          source: 'hr'
        }
      });
      const list = res.data?.staff || res.data?.items || [];
      setStaffDropdown(list);
      if (!selectedStaffId && list.length > 0) {
        setSelectedStaffId(list[0].id);
        setLeaveForm(f => ({
          ...f,
          staff_id: list[0].id
        }));
        setPerfForm(f => ({
          ...f,
          staff_id: list[0].id
        }));
      }
    } catch (e) {
      console.error('Dropdown staff listesi yüklenemedi', e);
      toast.error('Personel listesi yüklenemedi');
    }
  }, [selectedStaffId]);
  const loadAttendance = useCallback(async () => {
    try {
      const [summaryRes, recordsRes] = await Promise.all([axios.get('/hr/attendance/summary'), axios.get('/hr/attendance/records', {
        params: {
          limit: 100
        }
      })]);
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
    } catch {/* yetki yoksa sessiz geç */}
  }, []);
  const loadTaxRates = useCallback(async () => {
    try {
      const res = await axios.get('/hr/settings/payroll-tax-rates');
      setTaxRates(res.data || null);
      setTaxRatesForm(res.data?.rates ? {
        ...res.data.rates
      } : null);
    } catch {/* yetki yoksa sessiz geç */}
  }, []);
  const loadCompliance = useCallback(async () => {
    try {
      const [eqRes, trRes] = await Promise.all([axios.get('/hr/equipment/outstanding').catch(() => ({
        data: {
          items: [],
          total: 0
        }
      })), axios.get('/hr/trainings/expiring', {
        params: {
          days_ahead: 60
        }
      }).catch(() => ({
        data: {
          items: [],
          total: 0
        }
      }))]);
      setOutstandingEquipTotal(eqRes.data?.total ?? (eqRes.data?.items || []).length);
      setExpiringTrainTotal(trRes.data?.total ?? (trRes.data?.items || []).length);
    } catch {/* yetki yoksa sessiz geç */}
  }, []);
  const updateSeveranceCap = async () => {
    const current = severanceCap?.daily_cap || '';
    const input = await promptDialog({
      message: 'Yeni günlük kıdem tazminatı tavanı (TL):',
      defaultValue: String(current)
    });
    if (input === null) return;
    const val = parseFloat(String(input).replace(',', '.'));
    if (!Number.isFinite(val) || val <= 0) {
      toast.error('Geçerli bir tutar girin');
      return;
    }
    try {
      setSavingSeverance(true);
      await axios.put('/hr/settings/severance-cap', {
        daily_cap: val
      });
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
      setOvertimeCounts(res.data?.counts || {
        pending: 0,
        approved: 0,
        rejected: 0
      });
    } catch (e) {
      console.error('Mesai talepleri yüklenemedi', e);
    }
  }, []);
  const decideOvertime = async (req, action) => {
    try {
      let note = '';
      if (action === 'reject') {
        note = await promptDialog({
          message: 'Red sebebi (ZORUNLU):',
          defaultValue: ''
        });
        if (note === null) return;
        if (!String(note || '').trim()) {
          toast.error('Red sebebi zorunludur');
          return;
        }
      } else if (action === 'dept_approve') {
        note = await promptDialog({
          message: 'Departman onayı notu (opsiyonel):',
          defaultValue: ''
        });
        if (note === null) return;
      }
      await axios.post(`/hr/overtime-request/${req.id}/decision`, {
        action,
        note
      });
      const msg = action === 'reject' ? 'Mesai reddedildi' : action === 'dept_approve' ? 'Departman onayı verildi (HR final onayı bekleniyor)' : 'Mesai onaylandı (bordroya hazır)';
      toast.success(msg);
      loadOvertimeRequests();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem başarısız');
    }
  };
  const onTemplateChange = async tplId => {
    // Daha önce girilmiş skor varsa kullanıcıya kayıp uyarısı göster.
    const hasScores = Object.values(perfForm.competency_scores || {}).some(v => typeof v === 'number' && v > 0);
    if (hasScores) {
      const ok = await confirmDialog({
        title: 'Şablonu değiştir?',
        description: 'Mevcut yetkinlik puanlarınız sıfırlanacak. Devam edilsin mi?',
        confirmText: 'Devam et',
        cancelText: 'Vazgeç'
      });
      if (!ok) return;
    }
    const tpl = perfTemplates.find(t => t.id === tplId);
    const competency_scores = {};
    if (tpl?.competencies) {
      tpl.competencies.forEach(c => {
        competency_scores[c.name] = 0;
      });
    }
    setPerfForm(f => ({
      ...f,
      template_id: tplId,
      competency_scores
    }));
  };
  const setCompetencyScore = (name, val) => {
    setPerfForm(f => ({
      ...f,
      competency_scores: {
        ...f.competency_scores,
        [name]: parseFloat(val) || 0
      }
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
  const loadLeaveBalances = useCallback(async staffIds => {
    if (!staffIds?.length) return;
    setBalanceLoading(true);
    try {
      const results = await Promise.all(staffIds.map(sid => axios.get(`/hr/leave-balance/${sid}`).then(r => [sid, r.data]).catch(() => [sid, null])));
      const map = {};
      results.forEach(([sid, data]) => {
        if (data) map[sid] = data;
      });
      setLeaveBalances(map);
    } finally {
      setBalanceLoading(false);
    }
  }, []);
  const openApplicants = async job => {
    try {
      const res = await axios.get(`/hr/job-postings/${job.id}/applicants`);
      setApplicantsDialog({
        open: true,
        job,
        list: res.data?.items || [],
        counts: res.data?.counts || {}
      });
      setApplicantForm({
        name: '',
        email: '',
        phone: '',
        notes: '',
        cv_url: ''
      });
    } catch (err) {
      toast.error('Adaylar yüklenemedi');
    }
  };
  const refreshApplicants = async () => {
    if (!applicantsDialog.job) return;
    try {
      const res = await axios.get(`/hr/job-postings/${applicantsDialog.job.id}/applicants`);
      setApplicantsDialog(d => ({
        ...d,
        list: res.data?.items || [],
        counts: res.data?.counts || {}
      }));
    } catch {/* ignore */}
  };
  const submitApplicant = async e => {
    e.preventDefault();
    if (!applicantForm.name.trim()) {
      toast.error('Aday adı zorunlu');
      return;
    }
    try {
      setSavingApplicant(true);
      await axios.post(`/hr/job-postings/${applicantsDialog.job.id}/applicants`, applicantForm);
      toast.success('Aday eklendi');
      setApplicantForm({
        name: '',
        email: '',
        phone: '',
        notes: '',
        cv_url: ''
      });
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
      await axios.post(`/hr/applicants/${applicantId}/status`, {
        status
      });
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
      message: isApprove ? 'İsteğe bağlı: onay notu (örn. bütçe kodu, başlama tarihi).' : 'Lütfen ret gerekçesini kısaca yazın (talep sahibine iletilir).',
      placeholder: isApprove ? 'Onaylandı — pozisyon yayına alınabilir.' : 'Bütçe yetersiz / pozisyon doldu vb.',
      confirmText: isApprove ? 'Onayla' : 'Reddet',
      cancelText: 'Vazgeç'
    });
    if (note === null) return;
    try {
      await axios.post(`/hr/job-posting/${jobId}/${action}`, {
        note: note || undefined
      });
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
        if (staffPage.items.length > 0) loadLeaveBalances(staffPage.items.map(s => s.id));
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
      const res = await axios.post('/hr/clock-in', {
        staff_id: selectedStaffId
      });
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
      const res = await axios.post('/hr/clock-out', {
        staff_id: selectedStaffId
      });
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
        params: {
          month: exportMonth
        },
        responseType: 'blob'
      });
      const blob = new Blob([res.data], {
        type: 'text/csv;charset=utf-8'
      });
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
      const msg = error.response?.status === 403 ? 'Bordro indirme yetkiniz yok' : 'Bordro indirilemedi';
      toast.error(msg);
    } finally {
      setExporting(false);
    }
  };
  const loadPayrollRuns = useCallback(async month => {
    try {
      const res = await axios.get('/hr/payroll/runs', {
        params: {
          month
        }
      });
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
      const msg = error.response?.status === 403 ? 'Bordro görüntüleme yetkiniz yok' : 'Önizleme alınamadı';
      toast.error(msg);
    }
  };
  const handlePayrollSaveDraft = async () => {
    const ok = await confirmDialog({
      title: 'Bordroyu Taslak Olarak Kaydet',
      message: `${exportMonth} ayı için TASLAK bordro kaydedilecek. Bu işlem ` + 'muhasebe etkisi yaratmaz; kilitleme ayrı bir adımdır. Devam edilsin mi?',
      confirmText: 'Taslağı Kaydet',
      cancelText: 'Vazgeç'
    });
    if (!ok) return;
    try {
      setSavingDraft(true);
      const res = await axios.post(`/hr/payroll/${exportMonth}/save`, {
        extras: []
      });
      if (res.data?.success) {
        toast.success(res.data.is_idempotent_update ? 'Mevcut taslak güncellendi' : 'Taslak bordro oluşturuldu');
        await loadPayrollRuns(exportMonth);
      }
    } catch (error) {
      const msg = error.response?.status === 409 ? error.response?.data?.detail || 'Bu ay için kilitli bordro var' : error.response?.data?.detail || 'Taslak kaydedilemedi';
      toast.error(msg);
    } finally {
      setSavingDraft(false);
    }
  };
  const loadRunDetail = async runId => {
    try {
      setLoadingRun(true);
      const [detail, revs] = await Promise.all([axios.get(`/hr/payroll/runs/${runId}`), axios.get(`/hr/payroll/runs/${runId}/revisions`)]);
      setSelectedRun(detail.data);
      setRunRevisions(revs.data?.items || []);
    } catch (error) {
      toast.error('Bordro çalışması alınamadı');
    } finally {
      setLoadingRun(false);
    }
  };
  const handlePayrollFinalize = async runId => {
    const ok = await confirmDialog({
      title: 'Bordroyu Kilitle',
      message: 'Kilitlenen bordro DEĞİŞTİRİLEMEZ. Sonraki düzeltmeler ancak ' + 'revizyon açarak yeni bir taslak üzerinden yapılabilir. Onaylıyor musunuz?',
      confirmText: 'Evet, Kilitle',
      cancelText: 'Vazgeç'
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
      const msg = error.response?.status === 403 ? 'Kilitleme yetkiniz yok (HR Admin / Finance gerekli)' : error.response?.data?.detail || 'Bordro kilitlenemedi';
      toast.error(msg);
    } finally {
      setFinalizing(false);
    }
  };
  const handleRevisionOpen = async runId => {
    const reason = await promptDialog({
      title: 'Revizyon Aç',
      message: 'Kilitli bordro değişmez. Bu işlem yeni bir TASLAK açacaktır. Sebep:',
      placeholder: 'Örn: Onaylı mesai eklendi / avans düzeltildi.',
      confirmText: 'Revizyon Aç',
      cancelText: 'Vazgeç'
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
        extras: []
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
  const handleRunXlsx = async runId => {
    try {
      const res = await axios.get(`/hr/payroll/runs/${runId}/export.xlsx`, {
        responseType: 'blob'
      });
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
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
  const submitLeave = async e => {
    e.preventDefault();
    if (!leaveForm.staff_id || !leaveForm.start_date || !leaveForm.end_date) {
      toast.error('Personel, başlangıç ve bitiş tarihi zorunlu');
      return;
    }
    try {
      setCreatingLeave(true);
      await axios.post('/hr/leave-request', leaveForm);
      toast.success('İzin talebi oluşturuldu');
      setLeaveForm({
        ...leaveForm,
        start_date: '',
        end_date: '',
        reason: ''
      });
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
          message: 'Red sebebi (ZORUNLU):',
          defaultValue: ''
        });
        if (note === null) return;
        if (!String(note || '').trim()) {
          toast.error('Red sebebi zorunludur');
          return;
        }
      } else if (decision === 'dept_approve') {
        note = await promptDialog({
          message: 'Departman onayı notu (opsiyonel):',
          defaultValue: ''
        });
        if (note === null) return;
      }
      const res = await axios.post(`/hr/leave-request/${id}/decision`, {
        decision,
        note
      });
      const created = res.data?.on_leave_shifts_created || 0;
      const msg = decision === 'reject' ? 'İzin reddedildi' : decision === 'dept_approve' ? 'Departman onayı verildi (HR final onayı bekleniyor)' : `İzin onaylandı${created ? ` • ${created} gün vardiyaya 'izinli' işlendi` : ''}`;
      toast.success(msg);
      leavePage.refresh();
    } catch (error) {
      const msg = error.response?.status === 403 ? 'Onay yetkiniz yok' : error.response?.data?.detail || 'İşlem başarısız';
      toast.error(typeof msg === 'string' ? msg : 'İşlem başarısız');
    }
  };

  // Performance actions
  const submitPerformance = async e => {
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
        competency_scores: perfForm.competency_scores || {}
      });
      toast.success('Performans değerlendirmesi kaydedildi');
      setPerfForm({
        ...perfForm,
        period: '',
        overall_score: '',
        strengths: '',
        improvement_areas: '',
        goals: '',
        competency_scores: {}
      });
      performancePage.refresh();
    } catch (error) {
      const msg = error.response?.data?.detail || 'Kaydedilemedi';
      toast.error(typeof msg === 'string' ? msg : 'Hata');
    } finally {
      setCreatingPerf(false);
    }
  };

  // Recruitment actions
  const submitJob = async e => {
    e.preventDefault();
    if (!jobForm.title || !jobForm.department) {
      toast.error('Başlık ve departman zorunlu');
      return;
    }
    try {
      setCreatingJob(true);
      await axios.post('/hr/job-posting', jobForm);
      toast.success('İş ilanı yayınlandı');
      setJobForm({
        ...jobForm,
        title: '',
        location: '',
        salary_range: '',
        description: ''
      });
      loadJobs();
    } catch (error) {
      const msg = error.response?.data?.detail || 'Yayınlanamadı';
      toast.error(typeof msg === 'string' ? msg : 'Hata');
    } finally {
      setCreatingJob(false);
    }
  };
  const closeJob = async id => {
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
    avg_hours_per_active_staff: 0
  };
  const topPerformers = useMemo(() => {
    if (!attendanceSummary?.summary) return [];
    return [...attendanceSummary.summary].sort((a, b) => b.total_hours - a.total_hours).slice(0, 3);
  }, [attendanceSummary]);
  const selectedStaffName = useMemo(() => staffDropdown.find(s => s.id === selectedStaffId)?.name || '', [staffDropdown, selectedStaffId]);
  const fmtCurrency = v => formatCurrency(v ?? 0, 'TRY');
  const fmtTime = iso => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleTimeString('tr-TR', {
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return '—';
    }
  };
  const headerActions = <>
      <Button variant="outline" size="sm" onClick={() => navigate('/staff-management')} data-testid="btn-staff-management">
        <Users className="w-4 h-4 mr-1.5" />
        {t('cm.pages_HRComplete.personel_yonetimi')}
        <ExternalLink className="w-3 h-3 ml-1" />
      </Button>
      <Button variant="outline" size="sm" onClick={loadAll} disabled={refreshing} data-testid="btn-refresh-hr">
        <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />
        {t('cm.pages_HRComplete.yenile')}
      </Button>
    </>;
  return <div className="p-2">
      <PageHeader icon={Users} title={t('cm.pages_HRComplete.ik_yonetim_paketi')} subtitle={t('cm.pages_HRComplete.devam_takibi_bordro_izin_performans_ve_i')} actions={headerActions} />

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
            {overtimeCounts.pending > 0 && <span className="ml-1.5 px-1.5 rounded-full bg-amber-500 text-white text-[10px]">{overtimeCounts.pending}</span>}
          </TabsTrigger>
          <TabsTrigger value="recruitment" data-testid="tab-recruitment">
            <ClipboardList className="w-4 h-4 mr-2" />Personel Talebi
          </TabsTrigger>
        </TabsList>

        {/* === ATTENDANCE === */}
        <HRAttendanceTab Users={Users} attendanceMetrics={attendanceMetrics} Clock={Clock} TrendingUp={TrendingUp} outstandingEquipTotal={outstandingEquipTotal} Package={Package} expiringTrainTotal={expiringTrainTotal} GraduationCap={GraduationCap} selectedStaffId={selectedStaffId} setSelectedStaffId={setSelectedStaffId} staffDropdown={staffDropdown} clockIn={clockIn} clockOut={clockOut} navigate={navigate} recordsRange={recordsRange} attendanceRecords={attendanceRecords} fmtTime={fmtTime} topPerformers={topPerformers} />

        {/* === PAYROLL === */}
        <HRPayrollTab exportMonth={exportMonth} setExportMonth={setExportMonth} handlePayrollPreview={handlePayrollPreview} handlePayrollSaveDraft={handlePayrollSaveDraft} savingDraft={savingDraft} handlePayrollExport={handlePayrollExport} exporting={exporting} taxRates={taxRates} payrollRuns={payrollRuns} selectedRun={selectedRun} fmtCurrency={fmtCurrency} loadRunDetail={loadRunDetail} handlePayrollFinalize={handlePayrollFinalize} finalizing={finalizing} handleRevisionOpen={handleRevisionOpen} revising={revising} handleRunXlsx={handleRunXlsx} runRevisions={runRevisions} payrollPreview={payrollPreview} Users={Users} DollarSign={DollarSign} />

        {/* === LEAVE === */}
        <HRLeaveTab leaveCounts={leaveCounts} loadLeaveBalances={loadLeaveBalances} staffPage={staffPage} balanceLoading={balanceLoading} leaveBalances={leaveBalances} submitLeave={submitLeave} leaveForm={leaveForm} setLeaveForm={setLeaveForm} staffDropdown={staffDropdown} LEAVE_TYPE_LABEL={LEAVE_TYPE_LABEL} creatingLeave={creatingLeave} leavePage={leavePage} STATUS_INTENT={STATUS_INTENT} STATUS_LABEL={STATUS_LABEL} decideLeave={decideLeave} />

        {/* === PERFORMANCE === */}
        <HRPerformanceTab Award={Award} performancePage={performancePage} TrendingUp={TrendingUp} perfAvg={perfAvg} submitPerformance={submitPerformance} perfForm={perfForm} setPerfForm={setPerfForm} staffDropdown={staffDropdown} onTemplateChange={onTemplateChange} perfTemplates={perfTemplates} setCompetencyScore={setCompetencyScore} creatingPerf={creatingPerf} />

        {/* === MESAİ ONAYI === */}
        <HROvertimeTab Timer={Timer} overtimeCounts={overtimeCounts} CheckCircle2={CheckCircle2} XCircle={XCircle} severanceCap={severanceCap} updateSeveranceCap={updateSeveranceCap} savingSeverance={savingSeverance} taxRates={taxRates} updateTaxRates={updateTaxRates} savingTaxRates={savingTaxRates} taxRatesForm={taxRatesForm} setTaxRatesForm={setTaxRatesForm} overtimeItems={overtimeItems} STATUS_INTENT={STATUS_INTENT} STATUS_LABEL={STATUS_LABEL} decideOvertime={decideOvertime} />

        {/* === PERSONEL TALEBİ (eski "İşe Alım") === */}
        <HRRecruitmentTab jobItems={jobItems} submitJob={submitJob} jobForm={jobForm} setJobForm={setJobForm} parseInt={parseInt} creatingJob={creatingJob} openApplicants={openApplicants} decideJob={decideJob} closeJob={closeJob} applicantsDialog={applicantsDialog} setApplicantsDialog={setApplicantsDialog} submitApplicant={submitApplicant} applicantForm={applicantForm} setApplicantForm={setApplicantForm} savingApplicant={savingApplicant} setApplicantStatus={setApplicantStatus} />
      </Tabs>
    </div>;
};
export default HRComplete;