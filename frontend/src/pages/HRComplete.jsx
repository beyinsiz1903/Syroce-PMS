import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Clock, Calendar, DollarSign, Briefcase, UserPlus, Download,
  Users, FileSpreadsheet, RefreshCw, Plus, CheckCircle2, XCircle,
  TrendingUp, ExternalLink, FileDown, Award,
} from 'lucide-react';

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
  approved: 'success',
  rejected: 'danger',
  active: 'success',
  closed: 'neutral',
};

const STATUS_LABEL = {
  pending: 'Beklemede',
  approved: 'Onaylandı',
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

  // Staff (gerçek backend'den)
  const [staffList, setStaffList] = useState([]);
  const [selectedStaffId, setSelectedStaffId] = useState('');

  // Attendance
  const [attendanceSummary, setAttendanceSummary] = useState(null);
  const [attendanceRecords, setAttendanceRecords] = useState([]);
  const [recordsRange, setRecordsRange] = useState({ start: '', end: '' });

  // Payroll
  const [exportMonth, setExportMonth] = useState(todayMonth);
  const [exporting, setExporting] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [payrollPreview, setPayrollPreview] = useState(null);

  // Leave
  const [leaveItems, setLeaveItems] = useState([]);
  const [leaveCounts, setLeaveCounts] = useState({ pending: 0, approved: 0, rejected: 0 });
  const [leaveForm, setLeaveForm] = useState({
    staff_id: '', leave_type: 'annual', start_date: '', end_date: '', reason: '',
  });
  const [creatingLeave, setCreatingLeave] = useState(false);

  // Performance
  const [performanceItems, setPerformanceItems] = useState([]);
  const [perfAvg, setPerfAvg] = useState(0);
  const [perfForm, setPerfForm] = useState({
    staff_id: '', period: '', overall_score: '', strengths: '', improvement_areas: '', goals: '',
  });
  const [creatingPerf, setCreatingPerf] = useState(false);

  // Recruitment
  const [jobItems, setJobItems] = useState([]);
  const [jobForm, setJobForm] = useState({
    title: '', department: '', employment_type: 'full_time',
    location: '', salary_range: '', description: '',
  });
  const [creatingJob, setCreatingJob] = useState(false);

  // Loaders
  const loadStaff = useCallback(async () => {
    try {
      const res = await axios.get('/hr/staff');
      const list = res.data?.staff || [];
      setStaffList(list);
      if (!selectedStaffId && list.length > 0) {
        setSelectedStaffId(list[0].id);
        setLeaveForm((f) => ({ ...f, staff_id: list[0].id }));
        setPerfForm((f) => ({ ...f, staff_id: list[0].id }));
      }
    } catch (e) {
      console.error('Staff yüklenemedi', e);
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

  const loadLeaves = useCallback(async () => {
    try {
      const res = await axios.get('/hr/leave-requests');
      setLeaveItems(res.data?.items || []);
      setLeaveCounts(res.data?.counts || { pending: 0, approved: 0, rejected: 0 });
    } catch (e) {
      console.error('Leave yüklenemedi', e);
    }
  }, []);

  const loadPerformance = useCallback(async () => {
    try {
      const res = await axios.get('/hr/performance');
      setPerformanceItems(res.data?.items || []);
      setPerfAvg(res.data?.avg_score || 0);
    } catch (e) {
      console.error('Performance yüklenemedi', e);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      const res = await axios.get('/hr/job-postings');
      setJobItems(res.data?.items || []);
    } catch (e) {
      console.error('İş ilanları yüklenemedi', e);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([loadStaff(), loadAttendance(), loadLeaves(), loadPerformance(), loadJobs()]);
    } finally {
      setRefreshing(false);
    }
  }, [loadStaff, loadAttendance, loadLeaves, loadPerformance, loadJobs]);

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const handlePayrollPreview = async () => {
    try {
      const res = await axios.get('/hr/payroll/export', {
        params: { month: exportMonth, format: 'json' },
      });
      setPayrollPreview(res.data);
    } catch (error) {
      const msg = error.response?.status === 403
        ? 'Bordro görüntüleme yetkiniz yok'
        : 'Önizleme alınamadı';
      toast.error(msg);
    }
  };

  const handlePayrollFinalize = async () => {
    try {
      setFinalizing(true);
      const res = await axios.post('/hr/payroll/finalize', { month: exportMonth });
      if (res.data?.success) {
        toast.success(`${res.data.count} bordro kaydı oluşturuldu`);
        handlePayrollPreview();
      } else {
        toast.warning(res.data?.message || 'Finalize edilecek veri yok');
      }
    } catch (error) {
      const msg = error.response?.data?.detail || 'Bordro kaydedilemedi';
      toast.error(msg);
    } finally {
      setFinalizing(false);
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
      loadLeaves();
    } catch (error) {
      const msg = error.response?.data?.detail || 'İzin talebi oluşturulamadı';
      toast.error(typeof msg === 'string' ? msg : 'Hata');
    } finally {
      setCreatingLeave(false);
    }
  };

  const decideLeave = async (id, decision) => {
    try {
      await axios.post(`/hr/leave-request/${id}/decision`, { decision });
      toast.success(decision === 'approve' ? 'İzin onaylandı' : 'İzin reddedildi');
      loadLeaves();
    } catch (error) {
      const msg = error.response?.status === 403
        ? 'Onay yetkiniz yok'
        : 'İşlem başarısız';
      toast.error(msg);
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
      });
      toast.success('Performans değerlendirmesi kaydedildi');
      setPerfForm({ ...perfForm, period: '', overall_score: '', strengths: '', improvement_areas: '', goals: '' });
      loadPerformance();
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
    staff_count: 0, total_hours: 0, avg_hours_per_staff: 0,
  };

  const topPerformers = useMemo(() => {
    if (!attendanceSummary?.summary) return [];
    return [...attendanceSummary.summary]
      .sort((a, b) => b.total_hours - a.total_hours)
      .slice(0, 3);
  }, [attendanceSummary]);

  const selectedStaffName = useMemo(
    () => staffList.find((s) => s.id === selectedStaffId)?.name || '',
    [staffList, selectedStaffId],
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
        <TabsList className="grid w-full grid-cols-5">
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
          <TabsTrigger value="recruitment" data-testid="tab-recruitment">
            <UserPlus className="w-4 h-4 mr-2" />{t('cm.pages_HRComplete.ise_alim')}
          </TabsTrigger>
        </TabsList>

        {/* === ATTENDANCE === */}
        <TabsContent value="attendance" className="mt-4">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-3">
              <KpiCard intent="info" icon={Users} label={t('cm.pages_HRComplete.toplam_calisan')}
                value={attendanceMetrics.staff_count}
                sub="aktif takip edilen personel" />
              <KpiCard intent="success" icon={Clock} label={t('cm.pages_HRComplete.toplam_saat')}
                value={(attendanceMetrics.total_hours || 0).toFixed(1)}
                sub="son 30 gün" />
              <KpiCard intent="warning" icon={TrendingUp} label={t('cm.pages_HRComplete.ortalama_saat')}
                value={(attendanceMetrics.avg_hours_per_staff || 0).toFixed(1)}
                sub="personel başı" />
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
                    {staffList.length === 0 && <option value="">— Personel yok —</option>}
                    {staffList.map((s) => (
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
                {staffList.length === 0 && (
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
                    <FileSpreadsheet className="w-4 h-4 mr-1.5" />{t('cm.pages_HRComplete.onizle')}
                  </Button>
                  <Button size="sm" onClick={handlePayrollFinalize} disabled={finalizing} data-testid="btn-payroll-finalize">
                    <CheckCircle2 className="w-4 h-4 mr-1.5" />
                    {finalizing ? 'Kaydediliyor...' : 'Bordroyu Kaydet'}
                  </Button>
                  <Button variant="outline" size="sm" onClick={handlePayrollExport} disabled={exporting} data-testid="btn-payroll-csv">
                    <FileDown className="w-4 h-4 mr-1.5" />
                    {exporting ? 'İndiriliyor...' : 'CSV İndir'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
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
            <div className="grid gap-3 md:grid-cols-3">
              <KpiCard intent="warning" label={t('cm.pages_HRComplete.beklemede')} value={leaveCounts.pending} />
              <KpiCard intent="success" label="Onaylanan" value={leaveCounts.approved} />
              <KpiCard intent="danger" label="Reddedilen" value={leaveCounts.rejected} />
            </div>

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
                      {staffList.map((s) => (
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
                      {leaveItems.map((item) => (
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
                              <div className="flex justify-end gap-1">
                                <Button size="sm" variant="outline" onClick={() => decideLeave(item.id, 'approve')} data-testid={`btn-approve-${item.id}`}>
                                  <CheckCircle2 className="w-3.5 h-3.5 mr-1" />{t('cm.pages_HRComplete.onayla')}
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => decideLeave(item.id, 'reject')} data-testid={`btn-reject-${item.id}`}>
                                  <XCircle className="w-3.5 h-3.5 mr-1" />{t('cm.pages_HRComplete.reddet')}
                                </Button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {leaveItems.length === 0 && (
                        <tr><td colSpan={7} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.henuz_izin_talebi_yok')}</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === PERFORMANCE === */}
        <TabsContent value="performance" className="mt-4">
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <KpiCard intent="info" icon={Award} label={t('cm.pages_HRComplete.toplam_degerlendirme')} value={performanceItems.length} />
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
                      {performanceItems.map((item) => (
                        <tr key={item.id} className="border-t border-slate-100 align-top">
                          <td className="py-2 font-medium">{item.staff_name}</td>
                          <td>{item.period || '—'}</td>
                          <td>{(item.reviewed_at || '').slice(0, 10)}</td>
                          <td className="text-right font-semibold">{item.overall_score}</td>
                          <td className="text-slate-600 max-w-md truncate">{item.strengths || item.goals || '—'}</td>
                        </tr>
                      ))}
                      {performanceItems.length === 0 && (
                        <tr><td colSpan={5} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.henuz_degerlendirme_yok')}</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* === RECRUITMENT === */}
        <TabsContent value="recruitment" className="mt-4">
          <div className="space-y-4">
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Plus className="w-4 h-4" />{t('cm.pages_HRComplete.yeni_is_ilani')}</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={submitJob} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  <div>
                    <Label className="text-xs">Pozisyon</Label>
                    <Input value={jobForm.title}
                      onChange={(e) => setJobForm({ ...jobForm, title: e.target.value })}
                      placeholder="Resepsiyonist" />
                  </div>
                  <div>
                    <Label className="text-xs">Departman</Label>
                    <Input value={jobForm.department}
                      onChange={(e) => setJobForm({ ...jobForm, department: e.target.value })}
                      placeholder="front_desk" />
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.calisma_sekli')}</Label>
                    <select
                      value={jobForm.employment_type}
                      onChange={(e) => setJobForm({ ...jobForm, employment_type: e.target.value })}
                      className="w-full rounded-md border border-input px-3 py-2 text-sm"
                    >
                      <option value="full_time">{t('cm.pages_HRComplete.tam_zamanli')}</option>
                      <option value="part_time">{t('cm.pages_HRComplete.yari_zamanli')}</option>
                      <option value="seasonal">Sezonluk</option>
                      <option value="contract">{t('cm.pages_HRComplete.sozlesmeli')}</option>
                      <option value="intern">Stajyer</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">Lokasyon</Label>
                    <Input value={jobForm.location}
                      onChange={(e) => setJobForm({ ...jobForm, location: e.target.value })} />
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_HRComplete.ucret_araligi')}</Label>
                    <Input value={jobForm.salary_range}
                      onChange={(e) => setJobForm({ ...jobForm, salary_range: e.target.value })}
                      placeholder="22.000 – 30.000 TL" />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3">
                    <Label className="text-xs">{t('cm.pages_HRComplete.aciklama_1babd')}</Label>
                    <Textarea rows={3} value={jobForm.description}
                      onChange={(e) => setJobForm({ ...jobForm, description: e.target.value })} />
                  </div>
                  <div className="md:col-span-2 lg:col-span-3 flex justify-end">
                    <Button type="submit" disabled={creatingJob}>
                      <Plus className="w-4 h-4 mr-1.5" />
                      {creatingJob ? 'Yayınlanıyor...' : 'İlanı Yayınla'}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>{t('cm.pages_HRComplete.aktif_ilanlar')}</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b">
                        <th className="py-2">Pozisyon</th>
                        <th>Departman</th>
                        <th>{t('cm.pages_HRComplete.calisma')}</th>
                        <th>{t('cm.pages_HRComplete.ucret')}</th>
                        <th>{t('cm.pages_HRComplete.durum_074f4')}</th>
                        <th className="text-right">{t('cm.pages_HRComplete.basvuru')}</th>
                        <th className="text-right">{t('cm.pages_HRComplete.islem_792e7')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobItems.map((job) => (
                        <tr key={job.id} className="border-t border-slate-100">
                          <td className="py-2 font-medium">{job.title}</td>
                          <td className="capitalize text-slate-600">{job.department}</td>
                          <td className="text-slate-600">{job.employment_type}</td>
                          <td className="text-slate-600">{job.salary_range || '—'}</td>
                          <td><StatusBadge intent={STATUS_INTENT[job.status]}>{STATUS_LABEL[job.status] || job.status}</StatusBadge></td>
                          <td className="text-right">{job.applicants_count || 0}</td>
                          <td className="text-right">
                            {job.status === 'active' && (
                              <Button size="sm" variant="outline" onClick={() => closeJob(job.id)}>
                                <XCircle className="w-3.5 h-3.5 mr-1" />{t('cm.pages_HRComplete.kapat')}
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {jobItems.length === 0 && (
                        <tr><td colSpan={7} className="py-6 text-center text-slate-500">{t('cm.pages_HRComplete.henuz_is_ilani_yok')}</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default HRComplete;
