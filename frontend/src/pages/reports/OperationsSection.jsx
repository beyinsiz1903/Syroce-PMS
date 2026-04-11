import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Hotel, AlertTriangle, Calendar, CheckCircle2, Clock, Activity,
  Users, Wrench, DollarSign, CreditCard, Shield, Utensils, Building2
} from 'lucide-react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import {
  COLORS, formatCurrency, KPICard, SectionHeader, EmptyState, StatBox,
  ROOM_STATUS_LABELS
} from './ReportHelpers';

export const NoShowSection = ({ s, noShowGuests, cancelledGuests }) => (
  <div className="space-y-6" data-testid="section-noshow">
    <SectionHeader title="No-Show & İptaller" description="No-show ve iptal edilen rezervasyonlar" />
    <div className="grid grid-cols-2 gap-3">
      <KPICard title="No-Show" value={s.no_shows || 0} icon={AlertTriangle} color="red" />
      <KPICard title="İptal" value={s.cancellations || 0} icon={Calendar} color="amber" />
    </div>
    {noShowGuests.length > 0 && (
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm text-rose-700">No-Show Listesi ({noShowGuests.length})</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="border-b bg-rose-50"><th className="text-left py-2 px-3 text-xs font-semibold text-rose-700">Misafir</th><th className="text-left py-2 px-3 text-xs font-semibold text-rose-700">Oda</th><th className="text-left py-2 px-3 text-xs font-semibold text-rose-700">Giriş Tarihi</th><th className="text-right py-2 px-3 text-xs font-semibold text-rose-700">Tutar</th></tr></thead>
            <tbody>{noShowGuests.map((g, i) => (
              <tr key={i} className="border-b hover:bg-rose-50/30"><td className="py-2 px-3 font-medium">{g.guest_name || '-'}</td><td className="py-2 px-3">{g.room_number || '-'}</td><td className="py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
            ))}</tbody>
          </table></div>
        </CardContent>
      </Card>
    )}
    {cancelledGuests.length > 0 && (
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm text-amber-700">İptal Listesi ({cancelledGuests.length})</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="border-b bg-amber-50"><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Misafir</th><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Oda</th><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Tarih</th><th className="text-right py-2 px-3 text-xs font-semibold text-amber-700">Tutar</th></tr></thead>
            <tbody>{cancelledGuests.map((g, i) => (
              <tr key={i} className="border-b hover:bg-amber-50/30"><td className="py-2 px-3 font-medium">{g.guest_name || '-'}</td><td className="py-2 px-3">{g.room_number || '-'}</td><td className="py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
            ))}</tbody>
          </table></div>
        </CardContent>
      </Card>
    )}
    {noShowGuests.length === 0 && cancelledGuests.length === 0 && (
      <Card><CardContent className="py-12"><EmptyState icon={AlertTriangle} message="No-show veya iptal kaydı yok" submessage="Bu dönem için herhangi bir no-show veya iptal bulunmuyor" /></CardContent></Card>
    )}
  </div>
);

export const RoomStatusSection = ({ roomStatus, roomStatusData }) => (
  <div className="space-y-6" data-testid="section-room-status">
    <SectionHeader title="Oda Durumu" description="Canlı oda durumu özeti" actions={<Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">Canli</Badge>} />
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {Object.entries(roomStatus).map(([key, val]) => (
        <StatBox key={key} label={ROOM_STATUS_LABELS[key] || key} value={val} color={key === 'available' ? 'green' : key === 'occupied' ? 'blue' : key === 'dirty' ? 'amber' : key === 'maintenance' ? 'red' : 'gray'} />
      ))}
    </div>
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Durumu Dağılımı</CardTitle></CardHeader>
      <CardContent>
        {roomStatusData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart><Pie data={roomStatusData} cx="50%" cy="50%" innerRadius={60} outerRadius={110} dataKey="value" paddingAngle={3} label={({ name, value }) => name + ': ' + value}>
              {roomStatusData.map((e, i) => <Cell key={i} fill={e.color} />)}
            </Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart>
          </ResponsiveContainer>
        ) : <EmptyState icon={Hotel} message="Oda durumu verisi yok" />}
      </CardContent>
    </Card>
  </div>
);

export const HousekeepingSection = ({ hk }) => (
  <div className="space-y-6" data-testid="section-housekeeping">
    <SectionHeader title="Housekeeping Raporu" description="Temizlik operasyonları ve verimlilik" />
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <KPICard title="Tamamlanan" value={hk.completed || 0} icon={CheckCircle2} color="green" />
      <KPICard title="Bekleyen" value={hk.pending || 0} icon={Clock} color="amber" />
      <KPICard title="Devam Eden" value={hk.in_progress || 0} icon={Activity} color="blue" />
      <KPICard title="Haftalık Toplam" value={hk.total_week || 0} icon={Activity} color="purple" />
    </div>
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">Housekeeping Performans Özeti</CardTitle></CardHeader>
      <CardContent>
        <div className="space-y-4">
          {['completed', 'pending', 'in_progress'].map(status => {
            const val = hk[status] || 0;
            const total = (hk.completed || 0) + (hk.pending || 0) + (hk.in_progress || 0);
            const pct = total > 0 ? (val / total * 100).toFixed(0) : 0;
            const colors = { completed: 'bg-emerald-500', pending: 'bg-amber-500', in_progress: 'bg-blue-500' };
            const labels = { completed: 'Tamamlanan', pending: 'Bekleyen', in_progress: 'Devam Eden' };
            return (
              <div key={status}>
                <div className="flex justify-between text-sm mb-1"><span className="text-gray-600">{labels[status]}</span><span className="font-medium">{val} ({pct}%)</span></div>
                <div className="w-full bg-gray-100 rounded-full h-2.5"><div className={`h-2.5 rounded-full ${colors[status]}`} style={{ width: pct + '%' }} /></div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  </div>
);

export const PaymentsSection = ({ payments, paymentData }) => (
  <div className="space-y-6" data-testid="section-payments">
    <SectionHeader title="Ödeme Raporu" description="Ödeme yöntemleri ve tutar dağılımı" />
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      <KPICard title="Toplam Ödenen" value={payments.total_paid} icon={CheckCircle2} color="green" />
      <KPICard title="Bekleyen Fatura" value={payments.total_pending} icon={Clock} color="amber" />
      <KPICard title="Ödeme Yöntemi" value={(Object.keys(payments.by_method || {}).length) + ' tur'} icon={CreditCard} color="blue" />
    </div>
    <div className="grid md:grid-cols-2 gap-4">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Ödeme Yöntemi Dagilimi</CardTitle></CardHeader>
        <CardContent>
          {paymentData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart><Pie data={paymentData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" paddingAngle={3} label={({ name, value }) => name + ': ' + formatCurrency(value)}>
                {paymentData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart>
            </ResponsiveContainer>
          ) : <EmptyState icon={CreditCard} message="Ödeme verisi yok" />}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Ödeme Detayları</CardTitle></CardHeader>
        <CardContent>
          {paymentData.length > 0 ? (
            <div className="space-y-3">{paymentData.map((p, i) => (
              <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                <div className="flex items-center gap-3">
                  <span className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                  <span className="font-medium text-sm">{p.name}</span>
                </div>
                <span className="font-bold text-sm">{formatCurrency(p.value)}</span>
              </div>
            ))}</div>
          ) : <p className="text-gray-400 text-center py-12">Veri yok</p>}
        </CardContent>
      </Card>
    </div>
  </div>
);

export const DepartmentsSection = ({ s, hk, maint, finance }) => (
  <div className="space-y-6" data-testid="section-departments">
    <SectionHeader title="Departman Özeti" description="Tüm departmanların günlük performans özeti" />
    <div className="grid md:grid-cols-2 gap-4">
      <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Users className="w-4 h-4 text-blue-500" />Ön Büro</CardTitle></CardHeader>
        <CardContent><div className="grid grid-cols-3 gap-3">
          <StatBox label="Giriş" value={s.arrivals || 0} color="blue" />
          <StatBox label="Çıkış" value={s.departures || 0} color="amber" />
          <StatBox label="Otelde" value={s.in_house || 0} color="green" />
        </div></CardContent>
      </Card>
      <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-500" />Housekeeping</CardTitle></CardHeader>
        <CardContent><div className="grid grid-cols-3 gap-3">
          <StatBox label="Tamam" value={hk.completed || 0} color="green" />
          <StatBox label="Bekleyen" value={hk.pending || 0} color="amber" />
          <StatBox label="Devam" value={hk.in_progress || 0} color="blue" />
        </div></CardContent>
      </Card>
      <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Wrench className="w-4 h-4 text-orange-500" />Teknik Servis</CardTitle></CardHeader>
        <CardContent><div className="grid grid-cols-2 gap-3">
          <StatBox label="Acik" value={maint.open || 0} color="amber" />
          <StatBox label="Tamamlanan" value={maint.completed_month || 0} color="green" />
        </div></CardContent>
      </Card>
      <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><DollarSign className="w-4 h-4 text-emerald-500" />Finans</CardTitle></CardHeader>
        <CardContent><div className="grid grid-cols-2 gap-3">
          <StatBox label="Bekleyen" value={finance.pending_invoices || 0} color="red" />
          <StatBox label="Odenen" value={finance.paid_invoices_month || 0} color="green" />
        </div></CardContent>
      </Card>
    </div>
  </div>
);

export const FnBSection = ({ s }) => (
  <div className="space-y-6" data-testid="section-fnb">
    <SectionHeader title="F&B Raporu" description="Yiyecek & İçecek gelir ve performans özeti" />
    <div className="grid grid-cols-2 gap-3">
      <KPICard title="Bugünkü F&B Geliri" value={s.fnb_revenue} icon={Utensils} color="amber" />
      <KPICard title="Toplam Gelir İçi Payı" value={s.today_revenue > 0 ? (((s.fnb_revenue || 0) / s.today_revenue * 100).toFixed(1) + '%') : '%0'} icon={Activity} color="purple" />
    </div>
    <Card className="bg-gradient-to-br from-amber-50 to-amber-100/30 border-amber-200">
      <CardContent className="p-6 text-center">
        <Utensils className="w-12 h-12 text-amber-500 mx-auto mb-3" />
        <h3 className="text-lg font-bold text-gray-900">F&B Geliri</h3>
        <p className="text-3xl font-bold text-amber-700 mt-2">{formatCurrency(s.fnb_revenue)}</p>
        <p className="text-sm text-gray-500 mt-2">Bugünkü toplam yiyecek & içecek geliri</p>
        <div className="mt-4 grid grid-cols-2 gap-3 max-w-xs mx-auto">
          <div className="p-3 bg-white/70 rounded-lg"><p className="text-xs text-gray-500">Oda Geliri</p><p className="font-bold text-gray-900">{formatCurrency(s.today_revenue)}</p></div>
          <div className="p-3 bg-white/70 rounded-lg"><p className="text-xs text-gray-500">F&B Payi</p><p className="font-bold text-amber-700">{s.today_revenue > 0 ? ((s.fnb_revenue || 0) / s.today_revenue * 100).toFixed(1) : '0'}%</p></div>
        </div>
      </CardContent>
    </Card>
  </div>
);
