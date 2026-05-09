import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  ArrowLeft, RefreshCw, User, Mail, Phone, Building2, Briefcase,
  Calendar, Clock, DollarSign, Award, FileText, AlertCircle,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { formatCurrency } from '@/lib/currency';

const LEAVE_TYPE_LABEL = {
  annual: 'Yıllık', sick: 'Hastalık', maternity: 'Doğum',
  paternity: 'Babalık', unpaid: 'Ücretsiz', bereavement: 'Vefat',
  excused: 'Mazeret',
};
const STATUS_INTENT = {
  pending: 'warning', approved: 'success', rejected: 'danger',
  scheduled: 'info', completed: 'success', missed: 'danger',
};
const STATUS_LABEL = {
  pending: 'Beklemede', approved: 'Onaylandı', rejected: 'Reddedildi',
  scheduled: 'Planlı', completed: 'Tamamlandı', missed: 'Kaçırıldı',
};

const StaffProfile = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

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

  useEffect(() => { load(); }, [load]);

  const headerActions = (
    <>
      <Button variant="outline" size="sm" onClick={() => navigate('/staff-management')}>
        <ArrowLeft className="w-4 h-4 mr-1.5" />Personel Listesi
      </Button>
      <Button variant="outline" size="sm" onClick={load} disabled={loading}>
        <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />Yenile
      </Button>
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

      {/* Genel bilgi kartı */}
      <Card className="mb-4">
        <CardContent className="grid gap-3 md:grid-cols-4 py-4">
          <div className="flex items-center gap-2 text-sm text-slate-700">
            <Mail className="w-4 h-4 text-slate-400" /> {s.email || '—'}
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-700">
            <Phone className="w-4 h-4 text-slate-400" /> {s.phone || '—'}
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-700">
            <Building2 className="w-4 h-4 text-slate-400" /> {s.department || '—'}
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-700">
            <Briefcase className="w-4 h-4 text-slate-400" /> {s.employment_type || '—'}
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-700">
            <Calendar className="w-4 h-4 text-slate-400" /> İşe Giriş: {s.hire_date || '—'}
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-700">
            <DollarSign className="w-4 h-4 text-slate-400" />
            Saatlik: {s.hourly_rate ? `${s.hourly_rate} TRY` : 'tanımsız (140 TRY default)'}
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-700">
            <Clock className="w-4 h-4 text-slate-400" />
            Aylık Saat: {s.monthly_hours || '195 (default)'}
          </div>
          <div className="flex items-center gap-2 text-sm">
            {s.derived_from === 'users'
              ? <StatusBadge intent="neutral">Kullanıcıdan türetildi</StatusBadge>
              : <StatusBadge intent="info">HR-yönetimli</StatusBadge>}
          </div>
        </CardContent>
      </Card>

      {/* KPI özeti */}
      <div className="grid gap-3 md:grid-cols-4 mb-4">
        <KpiCard intent="info" icon={Clock} label="Son 30g Saat" value={att.total_hours_30d || 0}
          sub={`${att.days_present_30d || 0} gün`} />
        <KpiCard intent="warning" icon={Calendar} label="Bekleyen İzin" value={lv.pending || 0}
          sub={`Toplam ${lv.total || 0} talep`} />
        <KpiCard intent="success" icon={Award} label="Performans Ort." value={perf.avg_score || 0}
          sub={`${perf.total || 0} değerlendirme`} />
        <KpiCard intent="info" icon={FileText} label="Bordro Kayıtları" value={pay.count || 0}
          sub="son 12 ay" />
      </div>

      <Tabs defaultValue="attendance">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="attendance">Devam</TabsTrigger>
          <TabsTrigger value="leave">İzin</TabsTrigger>
          <TabsTrigger value="performance">Performans</TabsTrigger>
          <TabsTrigger value="payroll">Bordro</TabsTrigger>
          <TabsTrigger value="shifts">Vardiya</TabsTrigger>
        </TabsList>

        <TabsContent value="attendance" className="mt-4">
          <Card>
            <CardHeader><CardTitle>Son 30 Gün Devam Kayıtları</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-500 border-b">
                      <th className="py-2">Tarih</th><th>Giriş</th><th>Çıkış</th>
                      <th className="text-right">Saat</th>
                    </tr>
                  </thead>
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
              <KpiCard intent="neutral" label={`Hastalık (kalan/hak)`} value={`${bal.sick?.remaining ?? 0} / ${bal.sick?.entitlement ?? 5}`} />
            </div>
          )}
          <Card>
            <CardHeader><CardTitle>İzin Geçmişi</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-500 border-b">
                      <th className="py-2">Tür</th><th>Başl.</th><th>Bitiş</th>
                      <th className="text-right">Gün</th><th>Durum</th><th>Sebep</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(lv.items || []).map((l) => (
                      <tr key={l.id} className="border-t border-slate-100">
                        <td className="py-2">{LEAVE_TYPE_LABEL[l.leave_type] || l.leave_type}</td>
                        <td>{l.start_date}</td>
                        <td>{l.end_date}</td>
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
            <CardHeader><CardTitle>Performans Değerlendirmeleri</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-500 border-b">
                      <th className="py-2">Tarih</th><th>Dönem</th>
                      <th className="text-right">Puan</th><th>Güçlü</th><th>Gelişim</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(perf.items || []).map((p) => (
                      <tr key={p.id} className="border-t border-slate-100 align-top">
                        <td className="py-2">{(p.reviewed_at || '').slice(0, 10)}</td>
                        <td>{p.period || '—'}</td>
                        <td className="text-right font-semibold">{p.overall_score}</td>
                        <td className="text-slate-600 text-xs max-w-xs">{p.strengths || '—'}</td>
                        <td className="text-slate-600 text-xs max-w-xs">{p.improvement_areas || '—'}</td>
                      </tr>
                    ))}
                    {(perf.items || []).length === 0 && (
                      <tr><td colSpan={5} className="py-6 text-center text-slate-500">Değerlendirme yok</td></tr>
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
                  <thead>
                    <tr className="text-left text-slate-500 border-b">
                      <th className="py-2">Ay</th>
                      <th className="text-right">Saat</th><th className="text-right">Mesai</th>
                      <th className="text-right">Brüt</th><th className="text-right">Net</th>
                    </tr>
                  </thead>
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
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Yaklaşan Vardiyalar</span>
                <Button size="sm" variant="outline" onClick={() => navigate('/hr/shifts')}>
                  Vardiya Planlayıcı
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-500 border-b">
                      <th className="py-2">Tarih</th><th>Tip</th>
                      <th>Başl.</th><th>Bitiş</th><th>Not</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shifts.map((sh) => (
                      <tr key={sh.id} className="border-t border-slate-100">
                        <td className="py-2">{sh.shift_date}</td>
                        <td className="capitalize">{sh.shift_type}</td>
                        <td>{sh.start_time}</td>
                        <td>{sh.end_time}</td>
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
      </Tabs>
    </div>
  );
};

export default StaffProfile;
