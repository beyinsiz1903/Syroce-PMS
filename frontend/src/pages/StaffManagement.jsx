import { useTranslation } from "react-i18next";
import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Users, UserPlus, RefreshCw, Search, Pencil, UserMinus, ExternalLink, Building2, Briefcase, Calendar, Clock, Plus, X, Filter, RotateCw, Package, AlertTriangle, GraduationCap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { confirmDialog, promptDialog } from '@/lib/dialogs';
import { deptLabel, positionLabel, employmentTypeLabel, EMPLOYMENT_TYPE_OPTIONS } from '@/lib/hrLabels';
import UserProvisionDialog from '@/components/UserProvisionDialog';
import { FixedSizeList } from 'react-window';

// ── Virtualized staff table ───────────────────────────────────────────────
const SM_ROW_H = 52;
const SM_GRID = '1fr 108px 108px 140px 84px 84px 110px 72px 90px';
const SM_MIN_W = 890;

const SmStaffRow = React.memo(function SmStaffRow({ data, index, style }) {
  const {
    filtered, equipmentByStaff, warningsByStaff, trainingsByStaff,
    navigate, openEdit, offboardStaff, t,
  } = data;
  const s = filtered[index];
  if (!s) return null;
  const eqCount = equipmentByStaff[s.id] || 0;
  const wn = warningsByStaff[s.id] || { final: false, written: 0 };
  const trCount = trainingsByStaff[s.id] || 0;
  const hasCompliance = eqCount > 0 || wn.final || wn.written > 0 || trCount > 0;
  return (
    <div
      style={{ ...style, display: 'grid', gridTemplateColumns: SM_GRID, minWidth: SM_MIN_W, alignItems: 'center' }}
      className="border-t border-slate-100 hover:bg-slate-50 text-sm"
    >
      <div className="py-1.5 px-2 min-w-0 overflow-hidden">
        <button type="button" onClick={() => navigate(`/staff/${s.id}`)}
          className="font-medium text-slate-900 hover:text-sky-700 hover:underline text-left truncate max-w-full block">
          {s.name}
        </button>
      </div>
      <div className="text-slate-600 text-xs truncate px-1">{deptLabel(s.department)}</div>
      <div className="text-slate-600 text-xs truncate px-1">{positionLabel(s.position)}</div>
      <div className="text-slate-600 px-1 overflow-hidden">
        <div className="text-xs truncate">{s.email || '\u2014'}</div>
        {s.phone && <div className="text-xs text-slate-400 truncate">{s.phone}</div>}
      </div>
      <div className="text-slate-600 text-xs px-1">{s.hire_date || '\u2014'}</div>
      <div className="text-slate-600 text-xs px-1">{employmentTypeLabel(s.employment_type)}</div>
      <div className="px-1">
        {hasCompliance ? (
          <div className="flex flex-wrap gap-0.5">
            {eqCount > 0 && (
              <StatusBadge intent="warning" title={`${eqCount} a\u00e7\u0131k zimmet`}>
                <Package className="w-3 h-3 mr-0.5 inline" />{eqCount}
              </StatusBadge>
            )}
            {wn.final && (
              <StatusBadge intent="danger" title={t('cm.pages_StaffManagement.son_ihtar_mevcut')}>
                <AlertTriangle className="w-3 h-3 mr-0.5 inline" />{t('cm.pages_StaffManagement.son_ihtar')}
              </StatusBadge>
            )}
            {!wn.final && wn.written > 0 && (
              <StatusBadge intent="warning" title={`${wn.written} yaz\u0131l\u0131 uyar\u0131`}>
                <AlertTriangle className="w-3 h-3 mr-0.5 inline" />{wn.written}
              </StatusBadge>
            )}
            {trCount > 0 && (
              <StatusBadge intent="warning" title={`${trCount} e\u011fitim 60 g\u00fcn i\u00e7inde`}>
                <GraduationCap className="w-3 h-3 mr-0.5 inline" />{trCount}
              </StatusBadge>
            )}
          </div>
        ) : (
          <span className="text-slate-300 text-xs">\u2014</span>
        )}
      </div>
      <div className="px-1">
        {s.derived_from === 'users'
          ? <StatusBadge intent="neutral">{t('cm.pages_StaffManagement.kullan\u0131c\u0131')}</StatusBadge>
          : <StatusBadge intent="info">{t('cm.pages_StaffManagement.hr')}</StatusBadge>}
      </div>
      <div className="flex items-center justify-end gap-0.5 pr-1">
        <Button size="sm" variant="ghost" onClick={() => navigate(`/staff/${s.id}`)} title={t('cm.pages_StaffManagement.profil')} className="h-7 w-7 p-0">
          <ExternalLink className="w-3.5 h-3.5" />
        </Button>
        <Button size="sm" variant="ghost" onClick={() => openEdit(s)} title="D\u00fczenle" className="h-7 w-7 p-0">
          <Pencil className="w-3.5 h-3.5" />
        </Button>
        <Button size="sm" variant="ghost" onClick={() => offboardStaff(s)}
          title={t('cm.pages_StaffManagement.i_\u015Ften_ayr\u0131l\u0131\u015F_silmez_pasifle\u015F')}
          className="h-7 w-7 p-0 text-rose-600 hover:text-rose-700 hover:bg-rose-50">
          <UserMinus className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
});

const EMPTY_STAFF = {
  name: '',
  email: '',
  phone: '',
  department: '',
  position: '',
  hire_date: '',
  employment_type: 'full_time',
  hourly_rate: '',
  monthly_hours: '',
  annual_leave_entitlement: 14
};
const StaffManagement = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [refreshing, setRefreshing] = useState(false);
  const [staff, setStaff] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [positions, setPositions] = useState([]);
  const [leaveCounts, setLeaveCounts] = useState({
    pending: 0,
    approved: 0
  });
  const [shifts, setShifts] = useState([]);
  const [search, setSearch] = useState('');
  // Compliance rozetleri için per-staff agregasyon.
  // equipmentByStaff: staff_id -> outstanding count
  // warningsByStaff: staff_id -> { final: bool, written: count }
  // trainingsByStaff: staff_id -> expiring count (60 gün)
  const [equipmentByStaff, setEquipmentByStaff] = useState({});
  const [warningsByStaff, setWarningsByStaff] = useState({});
  const [trainingsByStaff, setTrainingsByStaff] = useState({});
  const [outstandingEquipTotal, setOutstandingEquipTotal] = useState(0);
  const [expiringTrainTotal, setExpiringTrainTotal] = useState(0);
  const [staffDialog, setStaffDialog] = useState({
    open: false,
    mode: 'create',
    form: EMPTY_STAFF,
    id: null
  });
  const [savingStaff, setSavingStaff] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newDept, setNewDept] = useState({
    name: '',
    code: '',
    description: ''
  });
  const [newPos, setNewPos] = useState({
    title: '',
    department: '',
    default_hourly_rate: ''
  });
  const [syncingDepts, setSyncingDepts] = useState(false);

  // Virtual table container measurement
  const tableContainerRef = useRef(null);
  const [tableWidth, setTableWidth] = useState(SM_MIN_W);
  useEffect(() => {
    const el = tableContainerRef.current;
    if (!el) return;
    const obs = new ResizeObserver(([entry]) => {
      setTableWidth(entry.contentRect.width);
    });
    obs.observe(el);
    setTableWidth(el.offsetWidth);
    return () => obs.disconnect();
  }, []);

  // v2 Foundation: source tab + gelişmiş filtreler.
  // source: 'hr' (gerçek personel) | 'users' (sistem kullanıcıları)
  const [sourceTab, setSourceTab] = useState('hr');
  const [filterOpen, setFilterOpen] = useState(false);
  const [filterDept, setFilterDept] = useState('');
  const [filterPosition, setFilterPosition] = useState('');
  const [filterEmpType, setFilterEmpType] = useState('');
  const [filterHireFrom, setFilterHireFrom] = useState('');
  const [filterHireTo, setFilterHireTo] = useState('');
  const loadAll = useCallback(async () => {
    setRefreshing(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const staffParams = {
        source: sourceTab
      };
      if (filterDept) staffParams.department = filterDept;
      if (filterEmpType) staffParams.employment_type = filterEmpType;
      if (filterHireFrom) staffParams.hire_date_from = filterHireFrom;
      if (filterHireTo) staffParams.hire_date_to = filterHireTo;
      const [stRes, dRes, pRes, lRes, shRes, eqRes, wnRes, trRes] = await Promise.all([axios.get('/hr/staff', {
        params: staffParams
      }), axios.get('/hr/departments').catch(() => ({
        data: {
          items: []
        }
      })), axios.get('/hr/positions').catch(() => ({
        data: {
          items: []
        }
      })), axios.get('/hr/leave-requests').catch(() => ({
        data: {
          counts: {}
        }
      })), axios.get('/hr/shifts', {
        params: {
          start: today,
          end: today
        }
      }).catch(() => ({
        data: {
          items: []
        }
      })), axios.get('/hr/equipment/outstanding').catch(() => ({
        data: {
          items: [],
          total: 0
        }
      })), axios.get('/hr/warnings/active').catch(() => ({
        data: {
          items: []
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
      setStaff(stRes.data?.staff || []);
      setDepartments(dRes.data?.items || []);
      setPositions(pRes.data?.items || []);
      setLeaveCounts(lRes.data?.counts || {});
      setShifts(shRes.data?.items || []);
      const eqMap = {};
      (eqRes.data?.items || []).forEach(it => {
        if (!it.staff_id) return;
        eqMap[it.staff_id] = (eqMap[it.staff_id] || 0) + 1;
      });
      setEquipmentByStaff(eqMap);
      setOutstandingEquipTotal(eqRes.data?.total ?? (eqRes.data?.items || []).length);
      const wnMap = {};
      (wnRes.data?.items || []).forEach(it => {
        if (!it.staff_id) return;
        const cur = wnMap[it.staff_id] || {
          final: false,
          written: 0
        };
        if (it.warning_type === 'final') cur.final = true;
        if (it.warning_type === 'written') cur.written += 1;
        wnMap[it.staff_id] = cur;
      });
      setWarningsByStaff(wnMap);
      const trMap = {};
      (trRes.data?.items || []).forEach(it => {
        if (!it.staff_id) return;
        trMap[it.staff_id] = (trMap[it.staff_id] || 0) + 1;
      });
      setTrainingsByStaff(trMap);
      setExpiringTrainTotal(trRes.data?.total ?? (trRes.data?.items || []).length);
    } catch (e) {
      console.error(e);
      toast.error('Personel verileri yüklenemedi');
    } finally {
      setRefreshing(false);
    }
  }, [sourceTab, filterDept, filterEmpType, filterHireFrom, filterHireTo]);
  useEffect(() => {
    loadAll();
  }, [loadAll]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = staff;
    if (filterPosition) {
      const pq = filterPosition.toLowerCase();
      rows = rows.filter(s => (s.position || '').toLowerCase().includes(pq));
    }
    if (!q) return rows;
    return rows.filter(s => (s.name || '').toLowerCase().includes(q) || (s.email || '').toLowerCase().includes(q) || (s.department || '').toLowerCase().includes(q) || (s.position || '').toLowerCase().includes(q));
  }, [staff, search, filterPosition]);

  const activeFilterCount = (filterDept ? 1 : 0) + (filterPosition ? 1 : 0) + (filterEmpType ? 1 : 0) + (filterHireFrom ? 1 : 0) + (filterHireTo ? 1 : 0);
  const resetFilters = () => {
    setFilterDept('');
    setFilterPosition('');
    setFilterEmpType('');
    setFilterHireFrom('');
    setFilterHireTo('');
  };
  const newHires30d = useMemo(() => {
    const cutoff = Date.now() - 30 * 24 * 3600 * 1000;
    return staff.filter(s => {
      const hd = s.hire_date || s.created_at;
      if (!hd) return false;
      return new Date(hd).getTime() >= cutoff;
    }).length;
  }, [staff]);
  const openCreate = () => setStaffDialog({
    open: true,
    mode: 'create',
    form: EMPTY_STAFF,
    id: null,
    derived: false
  });
  const openEdit = useCallback(s => {
    setStaffDialog({
      open: true,
      mode: 'edit',
      id: s.id,
      derived: s.derived_from === 'users',
      form: {
        name: s.name || '',
        email: s.email || '',
        phone: s.phone || '',
        department: s.department || '',
        position: s.position || '',
        hire_date: s.hire_date || '',
        employment_type: s.employment_type || 'full_time',
        hourly_rate: s.hourly_rate ?? '',
        monthly_hours: s.monthly_hours ?? '',
        annual_leave_entitlement: s.annual_leave_entitlement ?? 14
      }
    });
  }, []); // setStaffDialog is a stable setState setter
  const submitStaff = async e => {
    e.preventDefault();
    const f = staffDialog.form;
    if (!f.name?.trim()) {
      toast.error('İsim zorunludur');
      return;
    }
    let payload;
    if (staffDialog.mode === 'edit' && staffDialog.derived) {
      // Users-derived personel: sadece iletişim alanları gönder
      payload = {
        name: f.name,
        email: f.email || null,
        phone: f.phone || null
      };
    } else {
      payload = {
        ...f,
        hourly_rate: f.hourly_rate === '' ? undefined : Number(f.hourly_rate),
        monthly_hours: f.monthly_hours === '' ? undefined : Number(f.monthly_hours),
        annual_leave_entitlement: Number(f.annual_leave_entitlement) || 14
      };
    }
    try {
      setSavingStaff(true);
      if (staffDialog.mode === 'create') {
        await axios.post('/hr/staff', payload);
        toast.success('Personel eklendi');
      } else {
        await axios.put(`/hr/staff/${staffDialog.id}`, payload);
        toast.success('İletişim bilgileri güncellendi');
      }
      setStaffDialog({
        open: false,
        mode: 'create',
        form: EMPTY_STAFF,
        id: null,
        derived: false
      });
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally {
      setSavingStaff(false);
    }
  };
  const offboardStaff = useCallback(async s => {
    // Personel ASLA silinmez. "Ayrılış" = pasifleştirme; bordro/devam/izin
    // kayıtları korunur, sadece aktif listeden çıkar. Yanlışlıkla tıklamayı
    // önlemek için ad-yazarak onay iste.
    const expected = (s.name || '').trim();
    const typed = await promptDialog({
      title: 'İşten Ayrılış Kaydı',
      message: `"${expected}" personeli için ayrılış işlemi yapılacak.\n\n` + 'Personel sistemden silinmez — bordro, devam ve izin geçmişi korunur, ' + 'sadece aktif listeden çıkar.\n\n' + 'Onaylamak için personelin tam adını aşağıya yazın:',
      placeholder: expected,
      confirmText: 'Ayrılışı Onayla',
      cancelText: 'Vazgeç'
    });
    if (typed === null) return; // iptal
    if ((typed || '').trim().toLocaleLowerCase('tr-TR') !== expected.toLocaleLowerCase('tr-TR')) {
      toast.error('Ad eşleşmedi. Ayrılış iptal edildi.');
      return;
    }
    try {
      await axios.delete(`/hr/staff/${s.id}`);
      toast.success(`${expected} ayrılış olarak işaretlendi (kayıtlar korundu)`);
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ayrılış işlenemedi');
    }
  }, [loadAll]); // promptDialog/confirmDialog/axios/toast are stable imports
  const addDepartment = async e => {
    e.preventDefault();
    if (!newDept.name.trim()) return;
    try {
      await axios.post('/hr/departments', newDept);
      toast.success('Departman eklendi');
      setNewDept({
        name: '',
        code: '',
        description: ''
      });
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    }
  };
  const removeDepartment = async (id, name) => {
    // v2 Foundation: backend soft-delete (pasifleştirme); aktif personeli varsa 409 döner.
    if (!(await confirmDialog({
      message: `"${name}" departmanı pasifleştirilecek (silinmez). Aktif personeli varsa işlem reddedilir. Devam edilsin mi?`
    }))) return;
    try {
      await axios.delete(`/hr/departments/${id}`);
      toast.success('Departman pasifleştirildi');
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem yapılamadı');
    }
  };
  const syncDepartmentsFromStaff = async () => {
    if (!(await confirmDialog({
      message: 'Personel verisinden eksik departman master kayıtları oluşturulsun mu?\n\nMevcut kayıtlar etkilenmez (idempotent).'
    }))) return;
    try {
      setSyncingDepts(true);
      const r = await axios.post('/hr/departments/sync-from-staff');
      const count = r.data?.created_count ?? 0;
      toast.success(count > 0 ? `${count} yeni departman eklendi` : 'Eklenecek yeni departman yok');
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Senkronizasyon başarısız');
    } finally {
      setSyncingDepts(false);
    }
  };
  const addPosition = async e => {
    e.preventDefault();
    if (!newPos.title.trim()) return;
    try {
      await axios.post('/hr/positions', {
        ...newPos,
        default_hourly_rate: newPos.default_hourly_rate === '' ? undefined : Number(newPos.default_hourly_rate)
      });
      toast.success('Pozisyon eklendi');
      setNewPos({
        title: '',
        department: '',
        default_hourly_rate: ''
      });
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    }
  };
  const removePosition = async (id, title) => {
    // v2 Foundation: backend soft-delete; aktif personeli varsa 409 döner.
    if (!(await confirmDialog({
      message: `"${title}" pozisyonu pasifleştirilecek (silinmez). Aktif personeli varsa işlem reddedilir. Devam edilsin mi?`
    }))) return;
    try {
      await axios.delete(`/hr/positions/${id}`);
      toast.success('Pozisyon pasifleştirildi');
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşlem yapılamadı');
    }
  };
  const headerActions = <div className="flex flex-wrap gap-2 items-center">
      <Button variant="outline" size="sm" onClick={() => navigate('/hr')} className="rounded-lg shadow-sm border-slate-200 hover:bg-slate-50 text-slate-600">
        <ExternalLink className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffManagement.i_k_paneli")}</Button>
      <Button variant="outline" size="sm" onClick={() => navigate('/hr/shifts')} className="rounded-lg shadow-sm border-slate-200 hover:bg-slate-50 text-slate-600">
        <Calendar className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffManagement.vardiya_plan\u0131")}</Button>
      <Button variant="outline" size="sm" onClick={() => setSettingsOpen(true)} className="rounded-lg shadow-sm border-slate-200 hover:bg-slate-50 text-slate-600">
        <Building2 className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffManagement.departman_pozisyon")}</Button>
      <Button variant="outline" size="sm" onClick={loadAll} disabled={refreshing} className="rounded-lg shadow-sm border-slate-200 hover:bg-slate-50 text-slate-600">
        <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />{t("cm.pages_StaffManagement.yenile")}</Button>
      <div className="border-l border-slate-200 h-6 mx-1"></div>
      <UserProvisionDialog departments={departments} onCreated={loadAll} />
      <Button size="sm" onClick={openCreate} data-testid="btn-add-staff" className="rounded-lg shadow-sm bg-gradient-to-r from-teal-600 to-emerald-600 hover:from-teal-700 hover:to-emerald-700 text-white border-0">
        <UserPlus className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffManagement.yeni_personel_girissiz")}</Button>
    </div>;
  // itemData for react-window SmStaffRow (navigate/handlers are stable across renders)
  const staffRowData = useMemo(() => ({
    filtered, equipmentByStaff, warningsByStaff, trainingsByStaff,
    navigate, openEdit, offboardStaff, t,
  }), [filtered, equipmentByStaff, warningsByStaff, trainingsByStaff, navigate, openEdit, offboardStaff, t]);

  return <div className="p-2">
      <PageHeader icon={Users} title={t("cm.pages_StaffManagement.personel_y\xF6netimi")} subtitle="Çalışanlar, departmanlar, pozisyonlar — tek noktadan yönet" actions={headerActions} />

      <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6 mb-6">
        <div className="rounded-2xl border border-sky-100 bg-gradient-to-br from-sky-50 to-white p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-md bg-sky-100 text-sky-700"><Users className="w-4 h-4" /></div>
            <div className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">{t("cm.pages_StaffManagement.aktif_personel")}</div>
          </div>
          <div className="text-2xl font-bold text-slate-900 leading-none">{staff.length}</div>
          <div className="text-[11px] text-slate-500 mt-1.5">{departments.length ? `${departments.length} departman` : 'departman tanımı yok'}</div>
        </div>

        <div className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-white p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-md bg-emerald-100 text-emerald-700"><Clock className="w-4 h-4" /></div>
            <div className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">{t("cm.pages_StaffManagement.bug\xFCnk\xFC_vardiya")}</div>
          </div>
          <div className="text-2xl font-bold text-slate-900 leading-none">{shifts.length}</div>
          <div className="text-[11px] text-slate-500 mt-1.5">{shifts.length ? 'planlanmış' : 'Vardiya Planı\'ndan ekleyin'}</div>
        </div>

        <div className="rounded-2xl border border-amber-100 bg-gradient-to-br from-amber-50 to-white p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-md bg-amber-100 text-amber-700"><Calendar className="w-4 h-4" /></div>
            <div className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">{t("cm.pages_StaffManagement.bekleyen_i_zin")}</div>
          </div>
          <div className="text-2xl font-bold text-slate-900 leading-none">{leaveCounts.pending || 0}</div>
          <div className="text-[11px] text-slate-500 mt-1.5">onay bekliyor</div>
        </div>

        <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50 to-white p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-md bg-indigo-100 text-indigo-700"><UserPlus className="w-4 h-4" /></div>
            <div className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">{t("cm.pages_StaffManagement.son_30g_i_\u015Fe_al\u0131m")}</div>
          </div>
          <div className="text-2xl font-bold text-slate-900 leading-none">{newHires30d}</div>
          <div className="text-[11px] text-slate-500 mt-1.5">yeni eklenen</div>
        </div>

        <div className={`rounded-2xl border p-4 shadow-sm ${outstandingEquipTotal > 0 ? 'border-amber-100 bg-gradient-to-br from-amber-50 to-white' : 'border-slate-100 bg-gradient-to-br from-slate-50 to-white'}`}>
          <div className="flex items-center gap-2 mb-2">
            <div className={`p-1.5 rounded-md ${outstandingEquipTotal > 0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-200 text-slate-600'}`}><Package className="w-4 h-4" /></div>
            <div className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">{t("cm.pages_StaffManagement.a\xE7\u0131k_zimmet")}</div>
          </div>
          <div className="text-2xl font-bold text-slate-900 leading-none">{outstandingEquipTotal}</div>
          <div className="text-[11px] text-slate-500 mt-1.5">iade alınmamış</div>
        </div>

        <div className={`rounded-2xl border p-4 shadow-sm ${expiringTrainTotal > 0 ? 'border-rose-100 bg-gradient-to-br from-rose-50 to-white' : 'border-slate-100 bg-gradient-to-br from-slate-50 to-white'}`}>
          <div className="flex items-center gap-2 mb-2">
            <div className={`p-1.5 rounded-md ${expiringTrainTotal > 0 ? 'bg-rose-100 text-rose-700' : 'bg-slate-200 text-slate-600'}`}><GraduationCap className="w-4 h-4" /></div>
            <div className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">{t("cm.pages_StaffManagement.s\xFCresi_dolan_e\u011Fitim")}</div>
          </div>
          <div className="text-2xl font-bold text-slate-900 leading-none">{expiringTrainTotal}</div>
          <div className="text-[11px] text-slate-500 mt-1.5">önümüzdeki 60 gün</div>
        </div>
      </div>

      {/* v2 Foundation: source tabs (Personel / Sistem Kullanıcıları). */}
      <div className="flex gap-4 mb-4 border-b border-slate-200 px-2">
        {[{
        value: 'hr',
        label: 'Personel',
        testId: 'tab-source-hr'
      }, {
        value: 'users',
        label: 'Sistem Kullanıcıları',
        testId: 'tab-source-users'
      }].map(tab => <button key={tab.value} type="button" data-testid={tab.testId} onClick={() => setSourceTab(tab.value)} className={`pb-3 px-1 text-sm font-bold border-b-2 -mb-px transition-colors ${sourceTab === tab.value ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
            {tab.label}
          </button>)}
      </div>

      <Card className="border-0 shadow-sm rounded-2xl bg-white overflow-hidden ring-1 ring-slate-200">
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between bg-slate-50/30 pb-4">
          <CardTitle>
            {sourceTab === 'users' ? 'Sistem Kullanıcıları' : 'Personel Listesi'}
          </CardTitle>
          <div className="flex flex-col md:flex-row gap-2 w-full md:w-auto">
            <div className="relative w-full md:w-72">
              <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-slate-400" />
              <Input placeholder={t("cm.pages_StaffManagement.i_sim_e_posta_departman_ara")} value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
            </div>
            <Button variant="outline" size="sm" onClick={() => setFilterOpen(v => !v)} data-testid="btn-toggle-filters">
              <Filter className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffManagement.filtreler")}{activeFilterCount > 0 && <span className="ml-1.5 inline-flex items-center justify-center text-xs bg-slate-900 text-white rounded-full w-5 h-5">
                  {activeFilterCount}
                </span>}
            </Button>
          </div>
        </CardHeader>

        {filterOpen && <div className="px-6 pb-3 border-b border-slate-100">
            <div className="grid gap-3 md:grid-cols-5">
              <div>
                <Label className="text-xs">{t("cm.pages_StaffManagement.departman")}</Label>
                <select value={filterDept} onChange={e => setFilterDept(e.target.value)} className="w-full rounded-md border border-input px-3 py-2 text-sm" data-testid="filter-department">
                  <option value="">{t("cm.pages_StaffManagement.t\xFCm\xFC")}</option>
                  {departments.map(d => <option key={d.id} value={d.code || d.name}>{deptLabel(d.code || d.name)}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">{t("cm.pages_StaffManagement.pozisyon")}</Label>
                <Input list="filter-positions" value={filterPosition} onChange={e => setFilterPosition(e.target.value)} placeholder={t("cm.pages_StaffManagement.t\xFCm\xFC")} data-testid="filter-position" />
                <datalist id="filter-positions">
                  {positions.map(p => <option key={p.id} value={p.title} />)}
                </datalist>
              </div>
              <div>
                <Label className="text-xs">{t("cm.pages_StaffManagement.\xE7al\u0131\u015Fma_\u015Fekli")}</Label>
                <select value={filterEmpType} onChange={e => setFilterEmpType(e.target.value)} className="w-full rounded-md border border-input px-3 py-2 text-sm" data-testid="filter-employment-type">
                  <option value="">{t("cm.pages_StaffManagement.t\xFCm\xFC")}</option>
                  {EMPLOYMENT_TYPE_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">{t("cm.pages_StaffManagement.i_\u015Fe_giri\u015F_ba\u015Flang\u0131\xE7")}</Label>
                <Input type="date" value={filterHireFrom} onChange={e => setFilterHireFrom(e.target.value)} />
              </div>
              <div>
                <Label className="text-xs">{t("cm.pages_StaffManagement.i_\u015Fe_giri\u015F_biti\u015F")}</Label>
                <div className="flex gap-1">
                  <Input type="date" value={filterHireTo} onChange={e => setFilterHireTo(e.target.value)} />
                  {activeFilterCount > 0 && <Button variant="outline" size="sm" onClick={resetFilters} title={t("cm.pages_StaffManagement.filtreleri_temizle")}>
                      <X className="w-4 h-4" />
                    </Button>}
                </div>
              </div>
            </div>
          </div>}

        <CardContent className="p-0">
          <div className="overflow-x-auto" ref={tableContainerRef}>
            {/* Sticky header — CSS grid mirrors SmStaffRow column template */}
            <div
              role="row"
              className="grid text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200 bg-slate-50"
              style={{ gridTemplateColumns: SM_GRID, minWidth: SM_MIN_W }}
            >
              <div className="py-3 px-3">{t("cm.pages_StaffManagement.ad_soyad")}</div>
              <div className="py-3 px-1">{t("cm.pages_StaffManagement.departman")}</div>
              <div className="py-3 px-1">{t("cm.pages_StaffManagement.pozisyon")}</div>
              <div className="py-3 px-1">{t("cm.pages_StaffManagement.i_leti\u015Fim")}</div>
              <div className="py-3 px-1">{t("cm.pages_StaffManagement.i_\u015Fe_giri\u015F")}</div>
              <div className="py-3 px-1">{t("cm.pages_StaffManagement.tip")}</div>
              <div className="py-3 px-1">{t("cm.pages_StaffManagement.uyumluluk")}</div>
              <div className="py-3 px-1">{t("cm.pages_StaffManagement.kaynak")}</div>
              <div className="py-3 px-2 text-right">{t("cm.pages_StaffManagement.i_\u015Flem")}</div>
            </div>
            {filtered.length === 0 ? (
              <div className="py-16 text-center" style={{ minWidth: SM_MIN_W }}>
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-slate-100 text-slate-400 mb-4">
                  <Users className="w-6 h-6" />
                </div>
                <h3 className="text-sm font-semibold text-slate-900 mb-1">{staff.length === 0 ? 'Henüz personel eklenmemiş' : 'Arama sonucu bulunamadı'}</h3>
                <p className="text-xs text-slate-500 mb-6">{staff.length === 0 ? 'Personel yönetimini kullanmaya başlamak için ilk personeli ekleyin.' : 'Farklı arama kriterleri deneyin.'}</p>
                {staff.length === 0 && <Button onClick={openCreate} data-testid="btn-add-staff" className="rounded-lg shadow-sm bg-slate-900 text-white hover:bg-slate-800">
                    <UserPlus className="w-4 h-4 mr-1.5" />{t("cm.pages_StaffManagement.i_lk_personeli_ekle")}</Button>}
              </div>
            ) : (
              <FixedSizeList
                height={Math.min(filtered.length * SM_ROW_H, 520)}
                itemCount={filtered.length}
                itemSize={SM_ROW_H}
                itemData={staffRowData}
                width={Math.max(tableWidth, SM_MIN_W)}
                style={{ overflowX: 'hidden' }}
                aria-label="Personel listesi"
              >
                {SmStaffRow}
              </FixedSizeList>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Add/Edit Staff Dialog */}
      <Dialog open={staffDialog.open} onOpenChange={o => !o && setStaffDialog({
      ...staffDialog,
      open: false
    })}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {staffDialog.mode === 'create' ? 'Yeni Personel Ekle' : staffDialog.derived ? 'İletişim Bilgilerini Düzenle' : 'Personeli Düzenle'}
            </DialogTitle>
          </DialogHeader>
          {staffDialog.mode === 'edit' && staffDialog.derived && <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">{t("cm.pages_StaffManagement.bu_personel_kullan\u0131c\u0131_kayd\u0131nda")}<b>{t("cm.pages_StaffManagement.isim_e_posta_telefon")}</b>{t("cm.pages_StaffManagement.buradan_g\xFCncellenebilir_rol_de")}<b>{t("cm.pages_StaffManagement.kullan\u0131c\u0131_y\xF6netimi")}</b>{t("cm.pages_StaffManagement._ni_kullan\u0131n")}</div>}
          <form onSubmit={submitStaff} className="grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <Label className="text-xs">{t("cm.pages_StaffManagement.ad_soyad")}</Label>
              <Input required value={staffDialog.form.name} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                name: e.target.value
              }
            })} />
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.e_posta")}</Label>
              <Input type="email" value={staffDialog.form.email} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                email: e.target.value
              }
            })} />
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.telefon")}</Label>
              <Input value={staffDialog.form.phone} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                phone: e.target.value
              }
            })} />
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.departman")}</Label>
              <select value={staffDialog.form.department} disabled={staffDialog.mode === 'edit' && staffDialog.derived} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                department: e.target.value
              }
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm disabled:opacity-60 disabled:cursor-not-allowed">
                <option value="">{t("cm.pages_StaffManagement._se\xE7in")}</option>
                {departments.map(d => <option key={d.id} value={d.code || d.name}>{d.name}</option>)}
                {departments.length === 0 && <>
                    <option value="front_desk">{deptLabel('front_desk')}</option>
                    <option value="housekeeping">{deptLabel('housekeeping')}</option>
                    <option value="finance">{deptLabel('finance')}</option>
                    <option value="management">{deptLabel('management')}</option>
                    <option value="sales">{deptLabel('sales')}</option>
                  </>}
              </select>
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.pozisyon")}</Label>
              <Input list="positions-list" value={staffDialog.form.position} disabled={staffDialog.mode === 'edit' && staffDialog.derived} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                position: e.target.value
              }
            })} />
              <datalist id="positions-list">
                {positions.map(p => <option key={p.id} value={p.title} />)}
              </datalist>
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.i_\u015Fe_giri\u015F")}</Label>
              <Input type="date" value={staffDialog.form.hire_date} disabled={staffDialog.mode === 'edit' && staffDialog.derived} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                hire_date: e.target.value
              }
            })} />
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.\xE7al\u0131\u015Fma_\u015Fekli")}</Label>
              <select value={staffDialog.form.employment_type} disabled={staffDialog.mode === 'edit' && staffDialog.derived} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                employment_type: e.target.value
              }
            })} className="w-full rounded-md border border-input px-3 py-2 text-sm disabled:opacity-60 disabled:cursor-not-allowed">
                <option value="full_time">{t("cm.pages_StaffManagement.tam_zamanl\u0131")}</option>
                <option value="part_time">{t("cm.pages_StaffManagement.yar\u0131_zamanl\u0131")}</option>
                <option value="seasonal">{t("cm.pages_StaffManagement.sezonluk")}</option>
                <option value="contract">{t("cm.pages_StaffManagement.s\xF6zle\u015Fmeli")}</option>
                <option value="intern">{t("cm.pages_StaffManagement.stajyer")}</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.saatlik_\xFCcret_try_br\xFCt")}</Label>
              <Input type="number" step="0.01" min="0" value={staffDialog.form.hourly_rate} placeholder={t("cm.pages_StaffManagement.bo\u015F_b\u0131rak\u0131rsan\u0131z_140_asgari")} disabled={staffDialog.mode === 'edit' && staffDialog.derived} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                hourly_rate: e.target.value
              }
            })} />
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.ayl\u0131k_standart_saat")}</Label>
              <Input type="number" step="1" min="0" value={staffDialog.form.monthly_hours} placeholder={t("cm.pages_StaffManagement.varsay\u0131lan_195")} disabled={staffDialog.mode === 'edit' && staffDialog.derived} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                monthly_hours: e.target.value
              }
            })} />
            </div>
            <div>
              <Label className="text-xs">{t("cm.pages_StaffManagement.y\u0131ll\u0131k_i_zin_hakk\u0131_g\xFCn")}</Label>
              <Input type="number" min="0" max="365" value={staffDialog.form.annual_leave_entitlement} disabled={staffDialog.mode === 'edit' && staffDialog.derived} onChange={e => setStaffDialog({
              ...staffDialog,
              form: {
                ...staffDialog.form,
                annual_leave_entitlement: e.target.value
              }
            })} />
            </div>
            <DialogFooter className="md:col-span-2">
              <Button type="button" variant="outline" onClick={() => setStaffDialog({
              ...staffDialog,
              open: false
            })}>{t("cm.pages_StaffManagement.vazge\xE7")}</Button>
              <Button type="submit" disabled={savingStaff} data-testid="btn-save-staff">
                {savingStaff ? 'Kaydediliyor...' : staffDialog.mode === 'create' ? 'Ekle' : 'Güncelle'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Departments / Positions Settings */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{t("cm.pages_StaffManagement.departman_pozisyon_y\xF6netimi")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <CardTitle className="flex items-center gap-2 text-base"><Building2 className="w-4 h-4" />{t("cm.pages_StaffManagement.departmanlar")}</CardTitle>
                <Button type="button" variant="outline" size="sm" onClick={syncDepartmentsFromStaff} disabled={syncingDepts} data-testid="btn-sync-depts-from-staff" title={t("cm.pages_StaffManagement.personel_verisindeki_eksik_dep")}>
                  <RotateCw className={`w-3.5 h-3.5 mr-1 ${syncingDepts ? 'animate-spin' : ''}`} />{t("cm.pages_StaffManagement.personelden_senkronize_et")}</Button>
              </CardHeader>
              <CardContent>
                <form onSubmit={addDepartment} className="grid gap-2 mb-3">
                  <Input placeholder={t("cm.pages_StaffManagement.ad_\xF6r_resepsiyon")} value={newDept.name} onChange={e => setNewDept({
                  ...newDept,
                  name: e.target.value
                })} />
                  <Input placeholder={t("cm.pages_StaffManagement.kod_opsiyonel_\xF6r_front_desk")} value={newDept.code} onChange={e => setNewDept({
                  ...newDept,
                  code: e.target.value
                })} />
                  <Button type="submit" size="sm">
                    <Plus className="w-3.5 h-3.5 mr-1" />{t("cm.pages_StaffManagement.ekle")}</Button>
                </form>
                <div className="space-y-1">
                  {departments.map(d => <div key={d.id} className="flex items-center justify-between rounded border border-slate-100 px-2 py-1.5 text-sm">
                      <div>
                        <div className="font-medium">{d.name}</div>
                        <div className="text-xs text-slate-400">{d.code}</div>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => removeDepartment(d.id, d.name)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>)}
                  {departments.length === 0 && <p className="text-xs text-slate-500 text-center py-3">{t("cm.pages_StaffManagement.hen\xFCz_departman_yok")}</p>}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Briefcase className="w-4 h-4" />{t("cm.pages_StaffManagement.pozisyonlar")}</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={addPosition} className="grid gap-2 mb-3">
                  <Input placeholder={t("cm.pages_StaffManagement.ba\u015Fl\u0131k_\xF6r_resepsiyonist")} value={newPos.title} onChange={e => setNewPos({
                  ...newPos,
                  title: e.target.value
                })} />
                  <select value={newPos.department} onChange={e => setNewPos({
                  ...newPos,
                  department: e.target.value
                })} className="w-full rounded-md border border-input px-3 py-2 text-sm">
                    <option value="">{t("cm.pages_StaffManagement.departman_opsiyonel")}</option>
                    {departments.map(d => <option key={d.id} value={d.code || d.name}>{d.name}</option>)}
                  </select>
                  <Input type="number" step="0.01" min="0" placeholder={t("cm.pages_StaffManagement.varsay\u0131lan_saatlik_opsiyonel")} value={newPos.default_hourly_rate} onChange={e => setNewPos({
                  ...newPos,
                  default_hourly_rate: e.target.value
                })} />
                  <Button type="submit" size="sm">
                    <Plus className="w-3.5 h-3.5 mr-1" />{t("cm.pages_StaffManagement.ekle")}</Button>
                </form>
                <div className="space-y-1">
                  {positions.map(p => <div key={p.id} className="flex items-center justify-between rounded border border-slate-100 px-2 py-1.5 text-sm">
                      <div>
                        <div className="font-medium">{p.title}</div>
                        <div className="text-xs text-slate-400">
                          {p.department || '—'}{p.default_hourly_rate ? ` • ${p.default_hourly_rate} TRY/sa` : ''}
                        </div>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => removePosition(p.id, p.title)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>)}
                  {positions.length === 0 && <p className="text-xs text-slate-500 text-center py-3">{t("cm.pages_StaffManagement.hen\xFCz_pozisyon_yok")}</p>}
                </div>
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>
    </div>;
};
export default StaffManagement;