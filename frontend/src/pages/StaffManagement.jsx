import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Users, UserPlus, RefreshCw, Search, Pencil, UserMinus,
  ExternalLink, Building2, Briefcase, Calendar, Clock, Plus, X,
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
import { confirmDialog, promptDialog } from '@/lib/dialogs';

const EMPTY_STAFF = {
  name: '', email: '', phone: '', department: '', position: '',
  hire_date: '', employment_type: 'full_time',
  hourly_rate: '', monthly_hours: '', annual_leave_entitlement: 14,
};

const StaffManagement = () => {
  const navigate = useNavigate();
  const [refreshing, setRefreshing] = useState(false);
  const [staff, setStaff] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [positions, setPositions] = useState([]);
  const [leaveCounts, setLeaveCounts] = useState({ pending: 0, approved: 0 });
  const [shifts, setShifts] = useState([]);
  const [search, setSearch] = useState('');

  const [staffDialog, setStaffDialog] = useState({ open: false, mode: 'create', form: EMPTY_STAFF, id: null });
  const [savingStaff, setSavingStaff] = useState(false);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newDept, setNewDept] = useState({ name: '', code: '', description: '' });
  const [newPos, setNewPos] = useState({ title: '', department: '', default_hourly_rate: '' });

  const loadAll = useCallback(async () => {
    setRefreshing(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const [stRes, dRes, pRes, lRes, shRes] = await Promise.all([
        axios.get('/hr/staff'),
        axios.get('/hr/departments').catch(() => ({ data: { items: [] } })),
        axios.get('/hr/positions').catch(() => ({ data: { items: [] } })),
        axios.get('/hr/leave-requests').catch(() => ({ data: { counts: {} } })),
        axios.get('/hr/shifts', { params: { start: today, end: today } }).catch(() => ({ data: { items: [] } })),
      ]);
      setStaff(stRes.data?.staff || []);
      setDepartments(dRes.data?.items || []);
      setPositions(pRes.data?.items || []);
      setLeaveCounts(lRes.data?.counts || {});
      setShifts(shRes.data?.items || []);
    } catch (e) {
      console.error(e);
      toast.error('Personel verileri yüklenemedi');
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return staff;
    return staff.filter((s) =>
      (s.name || '').toLowerCase().includes(q)
      || (s.email || '').toLowerCase().includes(q)
      || (s.department || '').toLowerCase().includes(q)
      || (s.position || '').toLowerCase().includes(q)
    );
  }, [staff, search]);

  const newHires30d = useMemo(() => {
    const cutoff = Date.now() - 30 * 24 * 3600 * 1000;
    return staff.filter((s) => {
      const hd = s.hire_date || s.created_at;
      if (!hd) return false;
      return new Date(hd).getTime() >= cutoff;
    }).length;
  }, [staff]);

  const openCreate = () => setStaffDialog({ open: true, mode: 'create', form: EMPTY_STAFF, id: null, derived: false });
  const openEdit = (s) => {
    setStaffDialog({
      open: true, mode: 'edit', id: s.id,
      derived: s.derived_from === 'users',
      form: {
        name: s.name || '', email: s.email || '', phone: s.phone || '',
        department: s.department || '', position: s.position || '',
        hire_date: s.hire_date || '', employment_type: s.employment_type || 'full_time',
        hourly_rate: s.hourly_rate ?? '', monthly_hours: s.monthly_hours ?? '',
        annual_leave_entitlement: s.annual_leave_entitlement ?? 14,
      },
    });
  };

  const submitStaff = async (e) => {
    e.preventDefault();
    const f = staffDialog.form;
    if (!f.name?.trim()) { toast.error('İsim zorunludur'); return; }
    let payload;
    if (staffDialog.mode === 'edit' && staffDialog.derived) {
      // Users-derived personel: sadece iletişim alanları gönder
      payload = {
        name: f.name,
        email: f.email || null,
        phone: f.phone || null,
      };
    } else {
      payload = {
        ...f,
        hourly_rate: f.hourly_rate === '' ? undefined : Number(f.hourly_rate),
        monthly_hours: f.monthly_hours === '' ? undefined : Number(f.monthly_hours),
        annual_leave_entitlement: Number(f.annual_leave_entitlement) || 14,
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
      setStaffDialog({ open: false, mode: 'create', form: EMPTY_STAFF, id: null, derived: false });
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally {
      setSavingStaff(false);
    }
  };

  const offboardStaff = async (s) => {
    // Personel ASLA silinmez. "Ayrılış" = pasifleştirme; bordro/devam/izin
    // kayıtları korunur, sadece aktif listeden çıkar. Yanlışlıkla tıklamayı
    // önlemek için ad-yazarak onay iste.
    const expected = (s.name || '').trim();
    const typed = await promptDialog({
      title: 'İşten Ayrılış Kaydı',
      message:
        `"${expected}" personeli için ayrılış işlemi yapılacak.\n\n`
        + 'Personel sistemden silinmez — bordro, devam ve izin geçmişi korunur, '
        + 'sadece aktif listeden çıkar.\n\n'
        + 'Onaylamak için personelin tam adını aşağıya yazın:',
      placeholder: expected,
      confirmText: 'Ayrılışı Onayla',
      cancelText: 'Vazgeç',
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
  };

  const addDepartment = async (e) => {
    e.preventDefault();
    if (!newDept.name.trim()) return;
    try {
      await axios.post('/hr/departments', newDept);
      toast.success('Departman eklendi');
      setNewDept({ name: '', code: '', description: '' });
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    }
  };

  const removeDepartment = async (id, name) => {
    if (!await confirmDialog({ message: `"${name}" departmanı silinsin mi?` })) return;
    try {
      await axios.delete(`/hr/departments/${id}`);
      toast.success('Silindi');
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  const addPosition = async (e) => {
    e.preventDefault();
    if (!newPos.title.trim()) return;
    try {
      await axios.post('/hr/positions', {
        ...newPos,
        default_hourly_rate: newPos.default_hourly_rate === '' ? undefined : Number(newPos.default_hourly_rate),
      });
      toast.success('Pozisyon eklendi');
      setNewPos({ title: '', department: '', default_hourly_rate: '' });
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Eklenemedi');
    }
  };

  const removePosition = async (id, title) => {
    if (!await confirmDialog({ message: `"${title}" pozisyonu silinsin mi?` })) return;
    try {
      await axios.delete(`/hr/positions/${id}`);
      toast.success('Silindi');
      loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  const headerActions = (
    <>
      <Button variant="outline" size="sm" onClick={() => navigate('/hr')}>
        <ExternalLink className="w-4 h-4 mr-1.5" />İK Paneli
      </Button>
      <Button variant="outline" size="sm" onClick={() => navigate('/hr/shifts')}>
        <Calendar className="w-4 h-4 mr-1.5" />Vardiya Planı
      </Button>
      <Button variant="outline" size="sm" onClick={() => setSettingsOpen(true)}>
        <Building2 className="w-4 h-4 mr-1.5" />Departman / Pozisyon
      </Button>
      <Button variant="outline" size="sm" onClick={loadAll} disabled={refreshing}>
        <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />Yenile
      </Button>
      <Button size="sm" onClick={openCreate} data-testid="btn-add-staff">
        <UserPlus className="w-4 h-4 mr-1.5" />Yeni Personel
      </Button>
    </>
  );

  return (
    <div className="p-2">
      <PageHeader
        icon={Users}
        title="Personel Yönetimi"
        subtitle="Çalışanlar, departmanlar, pozisyonlar — tek noktadan yönet"
        actions={headerActions}
      />

      <div className="grid gap-3 md:grid-cols-4 mb-4">
        <KpiCard intent="info" icon={Users} label="Aktif Personel" value={staff.length}
          sub={departments.length ? `${departments.length} departman` : 'departman tanımı yok'} />
        <KpiCard intent="success" icon={Clock} label="Bugünkü Vardiya" value={shifts.length}
          sub={shifts.length ? 'planlanmış' : 'Vardiya Planı\'ndan ekleyin'} />
        <KpiCard intent="warning" icon={Calendar} label="Bekleyen İzin" value={leaveCounts.pending || 0}
          sub="onay bekliyor" />
        <KpiCard intent="info" icon={UserPlus} label="Son 30g İşe Alım" value={newHires30d}
          sub="yeni eklenen" />
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <CardTitle>Personel Listesi</CardTitle>
          <div className="relative w-full md:w-72">
            <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-slate-400" />
            <Input
              placeholder="İsim, e-posta, departman ara..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b">
                  <th className="py-2">Ad Soyad</th>
                  <th>Departman</th>
                  <th>Pozisyon</th>
                  <th>İletişim</th>
                  <th>İşe Giriş</th>
                  <th>Tip</th>
                  <th>Kaynak</th>
                  <th className="text-right">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="py-2">
                      <button
                        type="button"
                        onClick={() => navigate(`/staff/${s.id}`)}
                        className="font-medium text-slate-900 hover:text-sky-700 hover:underline text-left"
                      >
                        {s.name}
                      </button>
                    </td>
                    <td className="capitalize text-slate-600">{s.department || '—'}</td>
                    <td className="capitalize text-slate-600">{s.position || '—'}</td>
                    <td className="text-slate-600">
                      <div className="text-xs">{s.email || '—'}</div>
                      {s.phone && <div className="text-xs text-slate-400">{s.phone}</div>}
                    </td>
                    <td className="text-slate-600 text-xs">{s.hire_date || '—'}</td>
                    <td className="text-slate-600 text-xs">{s.employment_type || '—'}</td>
                    <td>
                      {s.derived_from === 'users'
                        ? <StatusBadge intent="neutral">Kullanıcı</StatusBadge>
                        : <StatusBadge intent="info">HR</StatusBadge>}
                    </td>
                    <td className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => navigate(`/staff/${s.id}`)} title="Profil">
                          <ExternalLink className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => openEdit(s)}
                          title={s.derived_from === 'users'
                            ? 'İletişim bilgilerini düzenle (rol/departman için Kullanıcı Yönetimi)'
                            : 'Düzenle'}
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => offboardStaff(s)}
                          title="İşten Ayrılış (silmez, pasifleştirir)"
                          className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                        >
                          <UserMinus className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-10 text-center">
                      <div className="space-y-2">
                        <p className="text-slate-500">{staff.length === 0 ? 'Henüz personel yok' : 'Arama sonucu yok'}</p>
                        {staff.length === 0 && (
                          <Button size="sm" onClick={openCreate}>
                            <UserPlus className="w-4 h-4 mr-1.5" />İlk Personeli Ekle
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Add/Edit Staff Dialog */}
      <Dialog open={staffDialog.open} onOpenChange={(o) => !o && setStaffDialog({ ...staffDialog, open: false })}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {staffDialog.mode === 'create'
                ? 'Yeni Personel Ekle'
                : staffDialog.derived
                  ? 'İletişim Bilgilerini Düzenle'
                  : 'Personeli Düzenle'}
            </DialogTitle>
          </DialogHeader>
          {staffDialog.mode === 'edit' && staffDialog.derived && (
            <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
              Bu personel kullanıcı kaydından türetildi. Yalnızca <b>isim, e-posta, telefon</b> buradan
              güncellenebilir; rol, departman ve maaş gibi alanlar için <b>Kullanıcı Yönetimi</b>'ni kullanın.
            </div>
          )}
          <form onSubmit={submitStaff} className="grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <Label className="text-xs">Ad Soyad *</Label>
              <Input required value={staffDialog.form.name}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, name: e.target.value } })} />
            </div>
            <div>
              <Label className="text-xs">E-posta</Label>
              <Input type="email" value={staffDialog.form.email}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, email: e.target.value } })} />
            </div>
            <div>
              <Label className="text-xs">Telefon</Label>
              <Input value={staffDialog.form.phone}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, phone: e.target.value } })} />
            </div>
            <div>
              <Label className="text-xs">Departman</Label>
              <select
                value={staffDialog.form.department}
                disabled={staffDialog.mode === 'edit' && staffDialog.derived}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, department: e.target.value } })}
                className="w-full rounded-md border border-input px-3 py-2 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <option value="">— Seçin —</option>
                {departments.map((d) => <option key={d.id} value={d.code || d.name}>{d.name}</option>)}
                {departments.length === 0 && (
                  <>
                    <option value="front_desk">Front Desk</option>
                    <option value="housekeeping">Housekeeping</option>
                    <option value="finance">Finans</option>
                    <option value="management">Yönetim</option>
                    <option value="sales">Satış</option>
                  </>
                )}
              </select>
            </div>
            <div>
              <Label className="text-xs">Pozisyon</Label>
              <Input list="positions-list" value={staffDialog.form.position}
                disabled={staffDialog.mode === 'edit' && staffDialog.derived}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, position: e.target.value } })} />
              <datalist id="positions-list">
                {positions.map((p) => <option key={p.id} value={p.title} />)}
              </datalist>
            </div>
            <div>
              <Label className="text-xs">İşe Giriş</Label>
              <Input type="date" value={staffDialog.form.hire_date}
                disabled={staffDialog.mode === 'edit' && staffDialog.derived}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, hire_date: e.target.value } })} />
            </div>
            <div>
              <Label className="text-xs">Çalışma Şekli</Label>
              <select
                value={staffDialog.form.employment_type}
                disabled={staffDialog.mode === 'edit' && staffDialog.derived}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, employment_type: e.target.value } })}
                className="w-full rounded-md border border-input px-3 py-2 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <option value="full_time">Tam Zamanlı</option>
                <option value="part_time">Yarı Zamanlı</option>
                <option value="seasonal">Sezonluk</option>
                <option value="contract">Sözleşmeli</option>
                <option value="intern">Stajyer</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Saatlik Ücret (TRY, brüt)</Label>
              <Input type="number" step="0.01" min="0" value={staffDialog.form.hourly_rate}
                placeholder="boş bırakırsanız 140 (asgari)"
                disabled={staffDialog.mode === 'edit' && staffDialog.derived}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, hourly_rate: e.target.value } })} />
            </div>
            <div>
              <Label className="text-xs">Aylık Standart Saat</Label>
              <Input type="number" step="1" min="0" value={staffDialog.form.monthly_hours}
                placeholder="varsayılan 195"
                disabled={staffDialog.mode === 'edit' && staffDialog.derived}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, monthly_hours: e.target.value } })} />
            </div>
            <div>
              <Label className="text-xs">Yıllık İzin Hakkı (gün)</Label>
              <Input type="number" min="0" max="365" value={staffDialog.form.annual_leave_entitlement}
                disabled={staffDialog.mode === 'edit' && staffDialog.derived}
                onChange={(e) => setStaffDialog({ ...staffDialog, form: { ...staffDialog.form, annual_leave_entitlement: e.target.value } })} />
            </div>
            <DialogFooter className="md:col-span-2">
              <Button type="button" variant="outline" onClick={() => setStaffDialog({ ...staffDialog, open: false })}>
                Vazgeç
              </Button>
              <Button type="submit" disabled={savingStaff} data-testid="btn-save-staff">
                {savingStaff ? 'Kaydediliyor...' : (staffDialog.mode === 'create' ? 'Ekle' : 'Güncelle')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Departments / Positions Settings */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Departman & Pozisyon Yönetimi</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Building2 className="w-4 h-4" />Departmanlar</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={addDepartment} className="grid gap-2 mb-3">
                  <Input placeholder="Ad (ör: Resepsiyon)" value={newDept.name}
                    onChange={(e) => setNewDept({ ...newDept, name: e.target.value })} />
                  <Input placeholder="Kod (opsiyonel, ör: front_desk)" value={newDept.code}
                    onChange={(e) => setNewDept({ ...newDept, code: e.target.value })} />
                  <Button type="submit" size="sm">
                    <Plus className="w-3.5 h-3.5 mr-1" />Ekle
                  </Button>
                </form>
                <div className="space-y-1">
                  {departments.map((d) => (
                    <div key={d.id} className="flex items-center justify-between rounded border border-slate-100 px-2 py-1.5 text-sm">
                      <div>
                        <div className="font-medium">{d.name}</div>
                        <div className="text-xs text-slate-400">{d.code}</div>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => removeDepartment(d.id, d.name)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ))}
                  {departments.length === 0 && (
                    <p className="text-xs text-slate-500 text-center py-3">Henüz departman yok</p>
                  )}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Briefcase className="w-4 h-4" />Pozisyonlar</CardTitle></CardHeader>
              <CardContent>
                <form onSubmit={addPosition} className="grid gap-2 mb-3">
                  <Input placeholder="Başlık (ör: Resepsiyonist)" value={newPos.title}
                    onChange={(e) => setNewPos({ ...newPos, title: e.target.value })} />
                  <select
                    value={newPos.department}
                    onChange={(e) => setNewPos({ ...newPos, department: e.target.value })}
                    className="w-full rounded-md border border-input px-3 py-2 text-sm"
                  >
                    <option value="">Departman (opsiyonel)</option>
                    {departments.map((d) => <option key={d.id} value={d.code || d.name}>{d.name}</option>)}
                  </select>
                  <Input type="number" step="0.01" min="0" placeholder="Varsayılan saatlik (opsiyonel)"
                    value={newPos.default_hourly_rate}
                    onChange={(e) => setNewPos({ ...newPos, default_hourly_rate: e.target.value })} />
                  <Button type="submit" size="sm">
                    <Plus className="w-3.5 h-3.5 mr-1" />Ekle
                  </Button>
                </form>
                <div className="space-y-1">
                  {positions.map((p) => (
                    <div key={p.id} className="flex items-center justify-between rounded border border-slate-100 px-2 py-1.5 text-sm">
                      <div>
                        <div className="font-medium">{p.title}</div>
                        <div className="text-xs text-slate-400">
                          {p.department || '—'}{p.default_hourly_rate ? ` • ${p.default_hourly_rate} TRY/sa` : ''}
                        </div>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => removePosition(p.id, p.title)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ))}
                  {positions.length === 0 && (
                    <p className="text-xs text-slate-500 text-center py-3">Henüz pozisyon yok</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default StaffManagement;
